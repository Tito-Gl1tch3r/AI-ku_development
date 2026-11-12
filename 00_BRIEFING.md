# BRIEFING — reducir el tiempo de entrenamiento en Kaggle

> Este documento es el estado de la cuestión. Todo lo que aparece como **MEDIDO** salió
> de un fichero o de un experimento concreto (se indica cuál). Todo lo que aparece como
> **PAPEL** es aritmética o estimación, no medición.
>
> Regla de la casa: una cifra sin medición propia se marca **PREVISTO-PAPEL(P)**.
> No se admite prosa que sustituya números.

---

## 0. Resumen en una línea

El plan de entrenamiento completo son **1.974.760.183 tokens**. La última medición real
de velocidad es **47,7 tok/s**, lo que pone el entrenamiento en **~11.500 horas de reloj**
(~1,3 años continuos). El objetivo de este encargo es encontrar de dónde salen las horas
y qué cambios legítimos las reducen más por unidad de esfuerzo.

---

## 1. Volumen real de datos — MEDIDO

Fuente: `datos/manifiesto_ESPECIALISTAS_v8.json` (141 tandas, 836 ficheros, `offset=0` en
los 836).

| Concepto | Valor |
|---|---|
| Tandas | 141 |
| Tokens totales | 1.974.760.183 (1,975 B) |
| Media por tanda | 14,0 M |
| Tandas < 1 M | 26 (5,3 M en total) |
| Tanda mayor | `177/sub_2` = 198,0 M |
| Subconjunto Phi (`177/sub_0..2`) | 0,423 B = 21 % del volumen |

---

## 2. Velocidad — MEDIDO, y es el problema

Fuente: `medidas/piloto_OPT1.json` y `medidas/piloto_BASE.json`.

| Config | ms/step | tok/s | VRAM pico cuda:0 / cuda:1 |
|---|---|---|---|
| BASE | 11.531,7 | — | — |
| **OPT1** | **10.725,2** | **47,7** | 7.481 / 11.068 MiB |

Condiciones de la medición, leídas del código (`codigo/celda_SESION1_v141.py`, línea 979:
`tok_s = ids.numel()/ms`):

- **T = 512, batch = 1** (47,7 × 10,725 s = 511,6 tokens ⇒ no hay otra lectura posible).
- **Banco de expertos reducido a 8** (`V4X_PILOTO_EXPERTS=8`, `experts_full=128`).
- Modelo **partido en 2 GPU** (`modo: real_split_p3`; 14 capas con el experto 137 en `cuda:1`).

Las dos últimas líneas importan: **el 47,7 tok/s es optimista**, no pesimista. El banco
de 8 expertos ejecuta una fracción de la cómputo del modelo real, que tiene
`num_experts_per_tok = 177`.

### 2.1 Lo que esto implica

| Base | tok/s | Horas de reloj para 1,975 B |
|---|---|---|
| PAPEL anterior (40 % MFU, 2×T4) | 410 | 1.338 |
| **MEDIDO (OPT1, banco 8)** | **47,7** | **11.500** |

**Factor de desvío: 8,6×.** A 15 h de reloj por semana (30 GPU-h/semana con 2×T4), las
11.500 h son ~767 semanas.

### 2.2 La brecha contra la aritmética

Del `p0_microbench.json` (medido con GEMMs sintéticos): bf16 emulado da **7,46 ms/token**
como techo aritmético en esta máquina. El piloto está en **21,0 ms/token** (10.725 ms / 512).
Es decir, **2,8× por encima del techo aritmético incluso con el banco reducido a 8**.

Ahí está la pregunta central del encargo.

---

## 3. Presupuesto de memoria — calculado y verificado

| Pieza | GiB |
|---|---|
| Base congelada (fp16/bf16) | 11,44 |
| Slot entrenable Nemo (229,5 M, bf16) | 0,43 |
| Gradientes del slot | 0,43 |
| AdamW fp32 del slot | 2,56 |
| **Total Nemo** | **14,86** (cabe en 1×T4: 14,16 GiB útiles) |
| Phi (3.179,2 M) | **58,81** — no cabe en 2×T4 (28,32 GiB) |

Por eso Phi está propuesto para quedar fuera: su estado AdamW son 35,53 GiB.

---

## 4. Restricciones que NO se pueden tocar

Estas no son opiniones, son decretos de la casa. Una propuesta que las viole se descarta
sin evaluarla:

1. `assert FULL_SFT` — **LoRA vetado** (decreto 57).
2. Vetados: `V4X_LOAD_4BIT`, `V4X_NF4`, `V4X_QLORA`, cuantización de pesos, fp8 en
   entrenamiento, pesos entrenables en bf16.
3. Techo de hardware: **Kaggle, 1×T4 o 2×T4** (LTUS-0 = 14.500 MiB, LTUS-1 = 29.000 MiB).
   Cuota: **30 GPU-hora por semana**; con 2×T4 cada hora de reloj cuesta 2 GPU-h ⇒
   15 h de reloj/semana.
4. El techo de RAM es la **cuota de Kaggle**, no un servidor propio.
5. «Adaptativa» se refiere a la **CPU**, no a la VRAM.

---

## 5. Preguntas concretas del encargo

### P1 — ¿Dónde se van los 10,7 s del step?
Descomponer el step de 512 tokens con banco 8: cuánto es cómputo GEMM, cuánto atención,
cuánto *bubble* de sincronización por el split en 2 GPU, cuánto lanzamiento de kernels
(overhead de Python/CUDA), cuánto optimizador.

### P2 — ¿Cuánto cuesta el split en 2 GPU?
El modelo está partido por capas entre `cuda:0` y `cuda:1`. Cada frontera entre una capa
de una GPU y la siguiente de la otra es una copia PCIe por step. Cuantificar: número de
fronteras, bytes por frontera, tiempo por step. Comparar con el escenario de **una sola
GPU** para las tandas que caben en 14,86 GiB (que es la mayoría).

### P3 — T=512 frente a T=8192
El piloto midió a T=512. El plan real usa T=8192 (16× más tokens por step). Modelar cómo
escala el coste (GEMM lineal, atención cuadrática, overhead de kernel constante) y decir
a qué T conviene entrenar realmente.

### P4 — La sombra fp16
Existe un adaptador `acel_BF16_TURING.py` que ejecuta los pesos congelados en fp16 en
lugar de bf16 emulado. El `p0` mide **11,47×** de ventaja en GEMM
(fp16 21,8 TFLOPS vs bf16 1,9 TFLOPS). Pero 11,47× es el ratio del GEMM, **no** el
speedup del step: por ley de Amdahl, con el GEMM siendo el 50–90 % del step, el speedup
cae entre **2,2× y 3,7×**. Anclas del `p0`: `ratio_wgrad0 = 0,709` (wgrad = 29,1 % del
step); `moe_layer` 215,48 → 162,01 ms; `mamba` 134,96 → 91,14; `attn` 59,69 → 40,21.
**Pregunta:** cuantificar el speedup real de la sombra sobre el step completo, y qué se
puede hacer con el slot entrenable, que sigue atado a bf16 por decreto y se come la
ganancia cuando el slot es grande (37 % del modelo en Phi, ~4 % en Nemo).

### P5 — ¿Qué palanca da más horas por unidad de esfuerzo?
Comparar, con números y no con adjetivos: una GPU frente a dos, T, sombra fp16,
`torch.compile`, CUDA graphs, gradient checkpointing, trocear por capas, prefetch de
datos. Cada una con su speedup estimado, su coste de implementación y su efecto en VRAM.

### P6 — Techo al que se puede aspirar
Dado el techo aritmético de 7,46 ms/token en bf16 (y el de fp16, 0,65 ms/token), decir
cuál es el mejor caso realista con estas restricciones y cuántas semanas costaría el
entrenamiento completo en ese mejor caso.

---

## 6. Formato de entrega que se espera

1. Un **`VEREDICTO.md`** con las respuestas P1–P6. Cada cifra etiquetada como
   **MEDIDO** (con el fichero o el experimento del que sale) o **PAPEL** (aritmética).
2. Un **`plan.json`** legible por máquina: lista de configuraciones candidatas, cada una
   con `{nombre, knobs, tok_s_estimado, horas_totales, semanas, vram_gib, riesgo, viola_decreto}`.
3. Un **`presupuesto_step.csv`**: dónde se va el tiempo del step, en ms y en %.
4. Si en algún momento una cifra no se puede sostener con una medición ni con aritmética
   explícita, decirlo. No rellenar huecos.

---

## 7. Contenido del paquete

| Ruta | Qué es |
|---|---|
| `codigo/celda_KAGGLE_v3_entreno.py` | La celda de SFT actual. Punto de partida real. |
| `codigo/ltus0_autopista.py` | Motor de referencia (99 KB). |
| `codigo/celda_SESION1_v141.py` | La celda que **produjo** `piloto_OPT1.json`. Contiene el bucle del piloto. |
| `codigo/configuration_v4x.py`, `codigo/config.json` | Arquitectura: 177 expertos, `num_experts_per_tok=177`. |
| `codigo/modeling_v4x.py` | Implementación del modelo. |
| `codigo/acel_BF16_TURING.py` | Sombra fp16 sobre pesos congelados. |
| `codigo/celda_P0_microbench.py` | El banco que produjo `p0_microbench.json`. |
| `codigo/celda_P0_conv1d_ab.py` | A/B de conv1d. |
| `codigo/presupuesto_lossless.py` | Calculadora de memoria. |
| `codigo/verificar_ltus.py` | 14 comprobaciones del motor. |
| `medidas/p0_microbench.json` | **Medición**: GEMM fp16/bf16, H2D, wgrad, capas. |
| `medidas/piloto_OPT1.json` | **Medición clave**: 47,7 tok/s, ms/step, VRAM pico. |
| `medidas/piloto_BASE.json` | **Medición**: 11.531,7 ms/step. |
| `medidas/piloto_acumulado.json` | Acumulado BASE + config. |
| `medidas/sesion1_resultado.json` | Resultado de la sesión 1, con tiempos. |
| `medidas/sesion1_veredicto_esperado.json` | Qué se esperaba obtener. |
| `medidas/piloto_error_BASE.log` | Log de error del piloto BASE (12 KB). |
| `medidas/sonda_ram_kaggle.json` | Sonda de RAM — **ojo: este no es de Kaggle** (ver §8). |
| `datos/manifiesto_ESPECIALISTAS_v8.json` | Las 141 tandas con tokens reales. |
| `informes/` | Arquitectura del router, auditorías previas, actas, entrega CURA-26. |

---

## 8. Avisos sobre datos que parecen buenos y no lo son

- **`sonda_ram_kaggle.json` no es de Kaggle.** `MemTotal` = 1,936 GiB y `memlock` = 8 MiB
  corresponden a un contenedor pequeño, no a una T4 de Kaggle. La cuota de RAM de Kaggle
  sigue **sin medir**.
- **`piloto_OPT1.json` no mide el modelo real**, mide un banco de 8 expertos. Sirve como
  cota optimista.
- El `p0_microbench.json` trae `h2d.cuda1 = 1.146,92 GB/s`, que es imposible en PCIe 3.0
  x16 (techo ~15,75 GB/s): es una copia que no cruzó el bus. **Descartado a 8,5 GB/s.**
- `disco` falló en origen (`TypeError: 'memoryview'`).

---

## 9. Entorno

Arch + Hyprland en el puesto de trabajo, **sin PyTorch y sin GPU**. Todo el trabajo de
este paquete se ha hecho con aritmética, simulación numpy y lectores de ficheros.
Cualquier cifra de GPU que no salga de los JSON de `medidas/` es PAPEL.
