"""
AI-ku Thinker-Max V4X — Arquitectura V4X

Extiende Nemotron-H (Mamba + MoE híbrido) con expertos externos
de Qwen3-Coder y Phi-4.

Estructura por capa MoE:
  - 128 expertos base Nemotron (up_proj + down_proj, relu2)
  - 1 shared expert Nemotron (up_proj + down_proj)
  - 48 expertos Qwen colapsados (gate_proj + up_proj + down_proj, silu)
  - 1 experto Phi colapsado (gate_proj + up_proj + down_proj, silu)
  - Router original Nemotron (128 expertos base)
  - Router V4X (178 expertos = 128 base + 48 Qwen + 1 Phi + 1 shared)

El forward:
  1. Nemotron procesa normalmente (Mamba/Attention + MoE base)
  2. En capas MoE, el router V4X decide si activar expertos externos
  3. La salida de los expertos externos se suma a la del MoE base
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import PreTrainedModel, PretrainedConfig
from typing import Optional, Tuple
import math


class V4XConfig(PretrainedConfig):
    model_type = "V4X"

    def __init__(
        self,
        hidden_size=2688,
        num_hidden_layers=52,
        num_base_experts=128,
        num_shared_experts=1,
        num_qwen_experts=48,
        num_phi_experts=1,
        num_experts_per_tok=6,
        base_intermediate_size=1856,
        shared_intermediate_size=3712,
        vocab_size=131072,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_base_experts = num_base_experts
        self.num_shared_experts = num_shared_experts
        self.num_qwen_experts = num_qwen_experts
        self.num_phi_experts = num_phi_experts
        self.num_experts_per_tok = num_experts_per_tok
        self.base_intermediate_size = base_intermediate_size
        self.shared_intermediate_size = shared_intermediate_size
        self.vocab_size = vocab_size
        self.total_new_experts = num_qwen_experts + num_phi_experts


# ═══════════════════════════════════════════════════════════════
# EXPERTOS
# ═══════════════════════════════════════════════════════════════

class NemotronExpert(nn.Module):
    """Experto base de Nemotron: up_proj + down_proj con relu2."""
    def __init__(self, hidden_size, intermediate_size):
        super().__init__()
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def forward(self, x):
        return self.down_proj(F.relu(self.up_proj(x)) ** 2)


class NewExpert(nn.Module):
    """Experto externo (Qwen/Phi colapsado): gate + up + down con silu."""
    def __init__(self, hidden_size, intermediate_size):
        super().__init__()
        self.gate_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def forward(self, x):
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


# ═══════════════════════════════════════════════════════════════
# ROUTER V4X
# ═══════════════════════════════════════════════════════════════

class V4XRouter(nn.Module):
    """
    Router unificado para todos los expertos.

    Fase 1: Top-K basado en logits puros (agnóstico).
    Fase 2: El SFT entrena el router para que aprenda qué experto usar.
    Fase 3: Bias inicial por especialización (opcional).
    """
    def __init__(self, hidden_size, num_total_experts, top_k,
                 num_base_experts=128, e_score_correction=True):
        super().__init__()
        self.top_k = top_k
        self.num_total_experts = num_total_experts
        self.num_base_experts = num_base_experts

        # Pesos del router (entrenable)
        self.weight = nn.Linear(hidden_size, num_total_experts, bias=False)

        # Bias de corrección (como el e_score_correction_bias de Nemotron)
        if e_score_correction:
            self.e_score_correction_bias = nn.Parameter(
                torch.zeros(num_total_experts))
        else:
            self.e_score_correction_bias = None

    def forward(self, hidden_states):
        """
        Args:
            hidden_states: (batch * seq_len, hidden_size)
        Returns:
            weights: (batch * seq_len, top_k) - pesos normalizados
            indices: (batch * seq_len, top_k) - índices de expertos
        """
        logits = self.weight(hidden_states)  # (tokens, num_experts)

        # Aplicar corrección de bias si existe
        if self.e_score_correction_bias is not None:
            logits = logits + self.e_score_correction_bias

        # Top-K selección
        weights, indices = torch.topk(logits, self.top_k, dim=-1)
        weights = F.softmax(weights, dim=-1, dtype=torch.float32).to(hidden_states.dtype)

        return weights, indices


# ═══════════════════════════════════════════════════════════════
# BLOQUE MOE V4X
# ═══════════════════════════════════════════════════════════════

class V4XMoEBlock(nn.Module):
    """
    Bloque MoE que combina expertos base de Nemotron + externos.

    Expertos 0-127: Nemotron base (up+down, relu2)
    Experto 128: Shared expert Nemotron (siempre activo)
    Expertos 129-176: Qwen colapsados (gate+up+down, silu)
    Experto 177: Phi colapsado (gate+up+down, silu)
    """
    def __init__(self, config: V4XConfig, layer_idx: int):
        super().__init__()
        self.config = config
        self.layer_idx = layer_idx
        self.hidden_size = config.hidden_size

        # Expertos base Nemotron (0-127)
        self.experts = nn.ModuleList([
            NemotronExpert(config.hidden_size, config.base_intermediate_size)
            for _ in range(config.num_base_experts)
        ])

        # Shared expert Nemotron (siempre activo)
        self.shared_experts = NemotronExpert(
            config.hidden_size, config.shared_intermediate_size)

        # Expertos nuevos: Qwen (48) + Phi (1)
        self.new_experts = nn.ModuleList([
            NewExpert(config.hidden_size, config.base_intermediate_size)
            for _ in range(config.total_new_experts)
        ])

        # Router V4X unificado
        total_routed = config.num_base_experts + config.total_new_experts
        self.v4x_router = V4XRouter(
            config.hidden_size,
            total_routed,
            config.num_experts_per_tok,
            config.num_base_experts
        )

        # Gate original de Nemotron (se mantiene para compatibilidad)
        self.gate = None  # Se carga desde los pesos

    def forward(self, hidden_states):
        """
        Args:
            hidden_states: (batch, seq_len, hidden_size)
        Returns:
            output: (batch, seq_len, hidden_size)
        """
        batch_size, seq_len, hidden_dim = hidden_states.shape
        hidden_flat = hidden_states.view(-1, hidden_dim)
        num_tokens = hidden_flat.shape[0]

        # 1. Shared expert (siempre activo)
        shared_output = self.shared_experts(hidden_flat)

        # 2. Router V4X: seleccionar top-K expertos
        weights, indices = self.v4x_router(hidden_flat)
        # weights: (num_tokens, top_k)
        # indices: (num_tokens, top_k)

        # 3. Ejecutar expertos seleccionados
        routed_output = torch.zeros_like(hidden_flat)

        # Expertos base Nemotron (0 a num_base-1)
        for expert_idx in range(self.config.num_base_experts):
            # Máscara: qué tokens activan este experto
            mask = (indices == expert_idx).any(dim=-1)  # (num_tokens,)
            if not mask.any():
                continue

            token_indices = mask.nonzero(as_tuple=True)[0]
            expert_input = hidden_flat[token_indices]
            expert_output = self.experts[expert_idx](expert_input)

            # Peso ponderado de este experto
            expert_weight = torch.where(
                indices[token_indices] == expert_idx,
                weights[token_indices],
                torch.zeros_like(weights[token_indices])
            ).sum(dim=-1, keepdim=True)

            routed_output[token_indices] += expert_output * expert_weight

        # Expertos nuevos (num_base a num_base + total_new - 1)
        for i, new_expert in enumerate(self.new_experts):
            global_idx = self.config.num_base_experts + i
            mask = (indices == global_idx).any(dim=-1)
            if not mask.any():
                continue

            token_indices = mask.nonzero(as_tuple=True)[0]
            expert_input = hidden_flat[token_indices]
            expert_output = new_expert(expert_input)

            expert_weight = torch.where(
                indices[token_indices] == global_idx,
                weights[token_indices],
                torch.zeros_like(weights[token_indices])
            ).sum(dim=-1, keepdim=True)

            routed_output[token_indices] += expert_output * expert_weight

        # 4. Combinar: shared + routed
        output = shared_output + routed_output
        return output.view(batch_size, seq_len, hidden_dim)


# ═══════════════════════════════════════════════════════════════
# MODELO COMPLETO
# ═══════════════════════════════════════════════════════════════

class V4XForCausalLM(PreTrainedModel):
    """
    AI-ku Thinker-Max V4X.

    El modelo base es Nemotron-H (cargado desde los pesos backbone.*).
    Los expertos nuevos se cargan desde backbone.layers.X.mixer.new_experts.*.

    Para inferencia real, usar llama.cpp con el GGUF convertido.
    Este forward es para entrenamiento del router con transformers/PEFT.
    """
    config_class = V4XConfig
    _no_split_modules = ["V4XMoEBlock"]

    def __init__(self, config: V4XConfig):
        super().__init__(config)
        self.config = config

    @classmethod
    def get_expert_metadata(cls):
        """Metadatos de expertos para logging/debugging. NO afectan al routing."""
        return {
            "0-127": {"origin": "nemotron", "type": "general", "activation": "relu2"},
            "128": {"origin": "nemotron", "type": "shared", "activation": "relu2"},
            "129-176": {"origin": "qwen3-coder", "type": "code", "activation": "silu"},
            "177": {"origin": "phi-4", "type": "reasoning", "activation": "silu"},
        }

    @classmethod
    def get_trainable_params_for_router_sft(cls, model):
        """
        Devuelve solo los parámetros del router para Fase 1/2 del SFT.
        Congela todo lo demás (expertos, atención, embeddings).

        Uso:
            params = V4XForCausalLM.get_trainable_params_for_router_sft(model)
            optimizer = torch.optim.AdamW(params, lr=1e-4)
        """
        trainable = []
        frozen = 0
        for name, param in model.named_parameters():
            if "v4x_router" in name or "e_score_correction" in name:
                param.requires_grad = True
                trainable.append(param)
            else:
                param.requires_grad = False
                frozen += 1
        print(f"V4X Router SFT: {len(trainable)} params entrenables, {frozen} congelados")
        return trainable

    @classmethod
    def init_router_with_semantic_bias(cls, model, tokenizer=None,
                                       code_keywords=None, reasoning_keywords=None):
        """
        Fase 3: Inicializa el router con bias semántico suave.

        Las filas del router para expertos Qwen se sesgan hacia tokens de código.
        Las filas del router para Phi se sesgan hacia tokens de razonamiento.

        Esto es SOLO inicialización. El entrenamiento ajustará los pesos.
        """
        if code_keywords is None:
            code_keywords = [
                "python", "function", "class", "import", "def", "return",
                "code", "script", "variable", "loop", "array", "debug",
                "error", "compile", "rust", "cpp", "javascript", "html",
                "css", "api", "json", "sql", "git", "docker", "linux",
            ]
        if reasoning_keywords is None:
            reasoning_keywords = [
                "prove", "therefore", "because", "logic", "theorem",
                "derive", "calculate", "equation", "math", "reason",
                "analyze", "conclude", "hypothesis", "proof", "solve",
                "integral", "derivative", "matrix", "probability",
            ]

        if tokenizer is None:
            print("⚠️ No tokenizer provided, skipping semantic bias init")
            return

        for name, module in model.named_modules():
            if isinstance(module, V4XRouter):
                with torch.no_grad():
                    weight = module.weight.weight  # (num_experts, hidden_size)

                    # No tocar expertos base (0-127), ya tienen buenos pesos
                    num_base = module.num_base_experts

                    # Obtener embeddings de keywords
                    embed_layer = None
                    for n, m in model.named_modules():
                        if "embed" in n.lower() and hasattr(m, "weight"):
                            embed_layer = m
                            break

                    if embed_layer is None:
                        print("⚠️ No embedding layer found, skipping bias")
                        return

                    embeddings = embed_layer.weight

                    # Qwen experts (129-176): bias hacia código
                    code_direction = torch.zeros(weight.shape[1], device=weight.device)
                    code_count = 0
                    for kw in code_keywords:
                        ids = tokenizer.encode(kw, add_special_tokens=False)
                        for tid in ids:
                            if tid < embeddings.shape[0]:
                                code_direction += embeddings[tid].float()
                                code_count += 1
                    if code_count > 0:
                        code_direction /= code_count
                        code_direction = F.normalize(code_direction, dim=0)
                        scale = weight[:num_base].norm(dim=1).mean().item() * 0.3
                        for i in range(48):  # Qwen experts
                            expert_idx = num_base + i
                            if expert_idx < weight.shape[0]:
                                weight[expert_idx] += (code_direction * scale).to(weight.dtype)

                    # Phi expert (177): bias hacia razonamiento
                    reason_direction = torch.zeros(weight.shape[1], device=weight.device)
                    reason_count = 0
                    for kw in reasoning_keywords:
                        ids = tokenizer.encode(kw, add_special_tokens=False)
                        for tid in ids:
                            if tid < embeddings.shape[0]:
                                reason_direction += embeddings[tid].float()
                                reason_count += 1
                    if reason_count > 0:
                        reason_direction /= reason_count
                        reason_direction = F.normalize(reason_direction, dim=0)
                        scale = weight[:num_base].norm(dim=1).mean().item() * 0.3
                        phi_idx = num_base + 48
                        if phi_idx < weight.shape[0]:
                            weight[phi_idx] += (reason_direction * scale).to(weight.dtype)

                print(f"✅ Router {name}: bias semántico aplicado (code={code_count} tokens, reasoning={reason_count} tokens)")
