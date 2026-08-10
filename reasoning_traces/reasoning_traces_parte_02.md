    linea_vacia
    json_invalido
    codificacion_invalida
    campo_ausente
    tipo_incorrecto
    conversacion_vacia
    mensaje_vacio
    contenido_vacio
    rol_invalido
    sin_user
    sin_assistant
    duplicado_exacto
    duplicado_aproximado

Report JSON keys (Spanish):
json

{
  "resumen": {
    "fichero": "...",
    "total_ejemplos": 15,
    "ejemplos_validos": 2,
    "ejemplos_invalidos": 13,
    "lineas_vacias": 1,
    "duplicados_exactos": 1,
    "duplicados_aproximados": 1,
    "errores_por_categoria": {"json_invalido": 1, ...},
    "distribucion_roles": {"user": 11, "assistant": 9, "system": 1},
    "total_mensajes": 21,
    "conversaciones_con_user": 10,
    "conversaciones_con_assistant": 9,
    "longitud_mensajes": {"n": 19, "min": 0, "max": 26, "media": 8.42, "mediana": 5},
    "longitud_conversaciones": {"n": 12, "min": 0, "max": 53, "media": 13.33, "mediana": 12}
  },
  "incidencias": [ {"linea": 3, "categoria": "json_invalido", "detalle": "...", "id_ejemplo": null, "es_duplicado_de": null} ],
  "generado": "2026-08-10T...",
  "version": "1.0.0"
}

Media rounding: round(media, 2). Mediana: float. n int.

Determinism: errors sorted by line then category. Categories counter sorted alphabetically in JSON (json.dumps with sort_keys or sorted dict). I'll produce sorted lists.

Now — details of valid vs invalid counting with duplicates: L5 and L14 get incidencias duplicado_exacto/duplicado_aproximado and are counted invalid. In "errores_por_categoria" duplicates are categories too (so counts include them). Fine and documented.

One more decision: ejemplos_validos counts lines with zero incidencias. Empty lines are NOT "ejemplos" (they're not JSON examples) → total_ejemplos = non-empty lines; lineas_vacias reported separately, not counted in total_ejemplos nor in validos/invalidos. Document clearly. Hmm — but "invalid examples" should maybe include empty lines? The spec: "número total de ejemplos, ejemplos válidos, ejemplos inválidos, duplicados, errores por categoría..." I'll keep empty lines separate (they're not examples) — and note it. Alternatively count them in total. I think separate is cleaner; README explains.

Also codificación inválida line: also not an example → same treatment? A line with undecodable bytes can't be parsed; I'll count it as lineas_no_procesables? Hmm. Simpler: treat as incidencia with category codificacion_invalida attached to that line, and count it in ejemplos_invalidos? It's not an example... I'll treat undecodable lines like empty lines: recorded in incidencias (category codificacion_invalida, line number), NOT counted in total_ejemplos. Document. For the test fixture I won't include such line in the main fixture (keeps numbers clean) but test it separately in a unit test.

Now about "requiere Python 3.10+": dataclasses, | unions in type hints (3.10 OK), argparse, statistics.median. Fine. I'll use from __future__ import annotations for safety anyway.

Let me think about implementation of near-duplicate signatures and the "es_duplicado_de" mapping: keep dict signature → first line number. For each parsed dict line: sig = normalizar(obj). If sig in seen_sigs: if raw_stripped line in seen_raw → duplicado_exacto (es_duplicado_de = first line with same raw) else duplicado_aproximado (es_duplicado_de = first line with same sig). Then add.

Also: exact-duplicate detection should probably be on the raw stripped line (fast) AND JSON-equivalent (json.dumps equal)? Two different raw lines could parse to identical JSON (e.g., different key order or extra whitespace) — that's "practically duplicate" really. Decision: exact = identical raw stripped text; near = normalized-signature equal (covers JSON-equivalent with different key order too). Document. Good.

Fixture note: L5 is byte-identical raw to L1 → exact. L14 differs → near. ✓.

Now the CLI output file: --output informe.json default None → if not provided, don't write JSON file (only terminal summary). Spec says "Permitir especificar un archivo de salida" → optional flag. OK.

--required-fields: default "id,conversation". Types: id→str, conversation→list; others→str. Document.

Exit codes: 0 success; 1 error (file not found, IO, bad args); 2 with --fail-on-issues and issues found.

Edge: file with only "\n" → no examples; total 0; valid 0; report still generated. Empty file → same.

Now write code. Let me draft carefully.

dataset_auditor/__init__.py:
python

"""dataset_auditor — análisis de calidad de datasets JSONL conversacionales."""
from .analisis import analizar_fichero, Incidencia, Duplicado, Informe
__version__ = "1.0.0"
__all__ = [...]

Hmm, module names: analisis.py (core), informe.py (report rendering) — or single core. Let me structure:

    analisis.py: data classes (Incidencia, Duplicado, Estadisticas, Resumen) + analizar_fichero(...) returning Informe.
    informe.py: resumen_a_dict(informe), a_json(informe, fichero, version), mostrar_terminal(informe).
    cli.py: argparse wiring.
    __main__.py.

That's 5 files + tests + fixture + README.

Now code:
python

# analisis.py
from __future__ import annotations
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
ROLES_VALIDOS: frozenset[str] = frozenset({"user", "assistant"})
CATEGORIAS: tuple[str, ...] = (
    "linea_vacia", "codificacion_invalida", "json_invalido", "campo_ausente",
    "tipo_incorrecto", "conversacion_vacia", "mensaje_vacio", "contenido_vacio",
    "rol_invalido", "sin_user", "sin_assistant", "duplicado_exacto",
    "duplicado_aproximado",
)
TIPO_ESPECIAL = {"conversation": list}  # tipos esperados para campos especiales
@dataclass
class Incidencia:
    linea: int
    categoria: str
    detalle: str = ""
    id_ejemplo: Optional[str] = None
    es_duplicado_de: Optional[int] = None
    def a_dict(self) -> dict[str, Any]:
        return {"linea": self.linea, "categoria": self.categoria,
                "detalle": self.detalle, "id_ejemplo": self.id_ejemplo,
                "es_duplicado_de": self.es_duplicado_de}
@dataclass
class Estadisticas:
    n: int = 0
    minimo: float = 0.0
    maximo: float = 0.0
    media: float = 0.0
    mediana: float = 0.0
    def a_dict(self) -> dict[str, Any]:
        return {"n": self.n, "minimo": round(self.minimo, 2),
                "maximo": round(self.maximo, 2), "media": round(self.media, 2),
                "mediana": round(self.mediana, 2)}
@dataclass
class Informe:
    fichero: str
    total_ejemplos: int = 0
    ejemplos_validos: int = 0
    ejemplos_invalidos: int = 0
    lineas_vacias: int = 0
    duplicados_exactos: int = 0
    duplicados_aproximados: int = 0
    errores_por_categoria: dict[str, int] = field(default_factory=dict)
    distribucion_roles: dict[str, int] = field(default_factory=dict)
    total_mensajes: int = 0
    conversaciones_con_user: int = 0
    conversaciones_con_assistant: int = 0
    longitud_mensajes: Estadisticas = field(default_factory=Estadisticas)
    longitud_conversaciones: Estadisticas = field(default_factory=Estadisticas)
    incidencias: list[Incidencia] = field(default_factory=list)

Normalization:
python

def _normalizar_str(s: str) -> str:
    return " ".join(s.split()).casefold()
def _firma_normalizada(obj: Any) -> tuple:
    if isinstance(obj, dict):
        return ("d", tuple((k, _firma_normalizada(v)) for k, v in sorted(obj.items())))
    if isinstance(obj, (list, tuple)):
        return ("l", tuple(_firma_normalizada(v) for v in obj))
    if isinstance(obj, str):
        return ("s", _normalizar_str(obj))
    if isinstance(obj, bool):
        return ("b", obj)
    if obj is None:
        return ("n",)
    if isinstance(obj, (int, float)):
        return ("num", repr(obj))
    return ("x", repr(obj))

Main analyzer:
python

def analizar_fichero(ruta: str | os.PathLike[str],
                     campos_requeridos: Iterable[str] = ("id", "conversation"),
                     max_incidencias: int = 1000) -> Informe:
    ruta_p = Path(ruta)
    campos = tuple(campos_requeridos)
    informe = Informe(fichero=str(ruta_p))
    cat = informe.errores_por_categoria
    for c_ in CATEGORIAS:
        cat[c_] = 0
    vistos_raw: dict[str, int] = {}      # línea → primera aparición
    vistos_firma: dict[tuple, int] = {}
    longitudes_mensaje: list[float] = []
    longitudes_conv: list[float] = []
    roles: Counter = Counter()
    conv_user = conv_assistant = 0
    total = validos = 0
    incidencias: list[Incidencia] = []
    def registrar(inc: Incidencia) -> None:
        cat[inc.categoria] += 1
        if len(incidencias) < max_incidencias:
            incidencias.append(inc)
    with open(ruta_p, "rb") as fh:
        for numero, linea_bytes in enumerate(fh, start=1):
            try:
                linea = linea_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                informe.lineas_vacias? no — registrar(Incidencia(numero, "codificacion_invalida", str(exc)))
                continue
            linea = linea.strip("\r\n")
            if linea.strip() == "":
                informe.lineas_vacias += 1
                registrar(Incidencia(numero, "linea_vacia", "línea vacía o solo espacios"))
                continue
            total += 1
            # duplicados raw
            if linea in vistos_raw:
                origen = vistos_raw[linea]
                informe.duplicados_exactos += 1
                registrar(Incidencia(numero, "duplicado_exacto", f"idéntica a la línea {origen}", es_duplicado_de=origen))
                continue?  # hmm: if we continue, we don't validate the line further.

Decision: for an exact duplicate, do we still run full validation on it? It's identical to the original, so its validation status equals the original's. Simplest: flag duplicate, and skip further validation (it adds no new info). But careful: what if the original itself is invalid? The duplicate line still gets counted as an example (total+=1) with incidencia duplicado_exacto → invalid. OK, continue after registering duplicate. But wait — then ejemplos_validos counts only non-duplicate valid lines; fine.

Hmm, but what about near-dup: we still validate the line fully (it may have other issues) AND flag near-dup. OK.
python

            try:
                obj = json.loads(linea)
            except json.JSONDecodeError as exc:
                registrar(Incidencia(numero, "json_invalido", f"{exc.msg} en posición {exc.pos}"))
                continue
            if not isinstance(obj, dict):
                registrar(Incidencia(numero, "tipo_incorrecto", f"la raíz debe ser un objeto (dict), se encontró {type(obj).__name__}"))
                continue
            id_ej = obj.get("id") if "id" in campos else None
            # campos requeridos
            for campo in campos:
                if campo not in obj:
                    registrar(Incidencia(numero, "campo_ausente", f"falta el campo «{campo}»", id_ejemplo=_str_id(id_ej)))
                else:
                    esperado = TIPO_ESPECIAL.get(campo, str)
                    if not isinstance(obj[campo], esperado):
                        registrar(Incidencia(numero, "tipo_incorrecto", f"el campo «{campo}» debe ser {esperado.__name__}, se encontró {type(obj[campo]).__name__}", id_ejemplo=_str_id(id_ej)))
            # conversación
            conv = obj.get("conversation")
            if isinstance(conv, list):
                if not conv:
                    registrar(Incidencia(numero, "conversacion_vacia", "la conversación no tiene mensajes", id_ejemplo=_str_id(id_ej)))
                else:
                    tiene_user = tiene_assistant = False
                    for i, msg in enumerate(conv):
                        base = f"conversation[{i}]"
                        if not isinstance(msg, dict):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"el mensaje {base} debe ser un objeto, se encontró {type(msg).__name__}", ...))
                            continue
                        if not msg:
                            registrar(Incidencia(numero, "mensaje_vacio", f"el mensaje {base} está vacío", ...))
                            continue
                        rol = msg.get("role")
                        if rol is None:
                            registrar(Incidencia(numero, "campo_ausente", f"falta «role» en {base}", ...))
                        elif not isinstance(rol, str):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"«role» en {base} debe ser str...", ...))
                        elif rol not in ROLES_VALIDOS:
                            registrar(Incidencia(numero, "rol_invalido", f"rol «{rol}» en {base} (válidos: user, assistant)", ...))
                        else:
                            roles[rol] += 1
                            if rol == "user": tiene_user = True
                            else: tiene_assistant = True
                        contenido = msg.get("content")
                        if contenido is None:
                            registrar(Incidencia(numero, "campo_ausente", f"falta «content» en {base}", ...))
                        elif not isinstance(contenido, str):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"«content» en {base} debe ser str...", ...))
                        else:
                            longitudes_mensaje.append(float(len(contenido)))
                            if contenido.strip() == "":
                                registrar(Incidencia(numero, "contenido_vacio", f"«content» en {base} está vacío (o solo espacios)", ...))
                    if tiene_user: conv_user += 1
                    if tiene_assistant: conv_assistant += 1
                    if not tiene_user:
                        registrar(Incidencia(numero, "sin_user", "la conversación no tiene ningún turno de usuario", ...))
                    if not tiene_assistant:
                        registrar(Incidencia(numero, "sin_assistant", "la conversación no tiene ningún turno de asistente", ...))
                    longitudes_conv.append(float(sum(len(m["content"]) for m in conv if isinstance(m, dict) and isinstance(m.get("content"), str))))
            elif "conversation" in obj:
                # tipo ya registrado por el chequeo de campos
                pass
            # firma para casi-duplicados
            firma = _firma_normalizada(obj)
            if firma in vistos_firma:
                origen = vistos_firma[firma]
                if linea not in vistos_raw:  # no es duplicado exacto ya registrado
                    informe.duplicados_aproximados += 1
                    registrar(Incidencia(numero, "duplicado_aproximado", f"prácticamente idéntica a la línea {origen}", id_ejemplo=..., es_duplicado_de=origen))
            else:
                vistos_firma[firma] = numero
            if linea not in vistos_raw:
                vistos_raw[linea] = numero
            # estado
            ...

Wait ordering problem: for exact dup we continue before adding to vistos_raw — the first occurrence already recorded. Fine. But note: I add to vistos_raw only after processing (non-dup) lines; for the exact-dup branch I continue before updating — correct since dup already exists.

But there's a subtle bug: for near-dup lines I must add them to vistos_raw too (so a later exact copy of a near-dup line is flagged exact). Yes — the if linea not in vistos_raw: vistos_raw[linea] = numero runs for non-exact-dup lines. Good.

Validity: after processing each line (non-empty, parsed, dict), determine es_valido = not any(inc.linea == numero for inc in incidencias)? Inefficient. Better: track per-line issue count. I'll use a small counter: issues_esta_linea incremented in registrar? registrar is global... Simplest: registrar returns bool added? Or track a dict linea→count. Let me restructure: incidencias_linea: dict[int, int]; registrar increments it. Then after processing line: if incidencias_linea.get(numero, 0) == 0 → validos += 1. Cleaner: registrar(inc) does cat[cat]+=1, incidencias.append if cap, and incidencias_linea[inc.linea] += 1. Then at end: validos = total - invalidos where invalidos = number of lines with ≥1 incidencia... but incidencias list is capped! incidencias_linea dict is not capped → good, keep it uncapped (int per line). invalidos = sum(1 for v in incidencias_linea.values() if v>0). But careful: lines with only "linea_vacia"/"codificacion" incidencias are NOT examples — excluded from total; but incidencias_linea would count them. So compute invalidos only over lines that are examples... I need to track which line numbers are examples. Simpler: track invalidas: set[int] of example line numbers with issues. registrar: if the incidencia belongs to an example line (linea in ejemplos_lineas?) hmm.

Cleanest: handle per-line explicitly. Let me restructure the loop to compute es_valida explicitly:

For each example line (parsed OK): collect local issues count via a helper that both registers and returns count? I'll do: problemas = 0 and a local def reg(inc): nonlocal problemas; registrar(inc); problemas += 1. But registrar is global-level; local closure per line works if defined inside loop. Slight overhead fine.

But the exact-dup branch: continue before computing es_valida — the duplicate line is invalid (it has a duplicado_exacto incidencia) → invalidos counted via incidencias_linea? Let me just maintain:

    total incremented for every non-empty line.
    invalidas: set[int] — add numero when any incidencia registered for that line.
    validos = total - len(invalidas) (since invalidas ⊆ example lines... but empty/codificacion lines also register incidencias and are not in total!). Fix: only register-line into invalidas if the line was counted as example. Order: empty lines and decode errors happen before total += 1, so at that point the line isn't an example. For those, just don't add to invalidas. So:

python

def reg(inc, ejemplo=False):   # ejemplo=True si la línea cuenta como ejemplo
    cat[inc.categoria] += 1
    if len(incidencias) < max_incidencias:
        incidencias.append(inc)
    if ejemplo:
        invalidas.add(inc.linea)

Empty line: reg(inc, ejemplo=False). JSON invalid: reg(..., ejemplo=True) (it IS an example — a broken one). Root not dict: ejemplo=True. Etc. Exact dup: reg(..., ejemplo=True). At end: validos = total - len(invalidas).

And per-line incidencias aren't needed beyond the set. Good — deterministic and simple.

Wait, one more: the near-dup line gets reg(duplicado_aproximado, ejemplo=True) → invalid. ✓.

es_valida per line not needed beyond set.

Also duplicates counters: informe.duplicados_exactos += 1 for each dup line. And cat counts include those categories. ✓ matches my manual table (duplicado_exacto:1, duplicado_aproximado:1).

Hmm, now recheck L8: {"id": 123, "conversation": []}:

    campos: id present, type wrong → tipo_incorrecto (1). conversation present, type list OK.
    conv: list, empty → conversacion_vacia (1). No sin_user/sin_assistant (conv empty → skip; my code: if not conv: registrar(conversacion_vacia) and the else branch handles user/assistant — so skip ✓).
    firma registered. L8 issues: 2. ✓ matches plan.

L9: system role → rol_invalido (1). tiene_user=False? roles counted only for valid roles → system not counted; tiene_user stays False, tiene_assistant False → also sin_user + sin_assistant! Uh oh — my manual plan said L9 → 1 issue (rol_invalido), but with the logic "tiene_user = any valid role" L9 would also get sin_user and sin_assistant. Which is right? The conversation has a system message and a user message; the user message has role "user" (valid) — wait L9 = [system, user]. The user message has valid role → tiene_user = True. Only system is invalid → rol_invalido. sin_assistant? No assistant → sin_assistant = True → flagged. Hmm! L9: roles = system + user → 1 rol_invalido + 1 sin_assistant. My manual table said L9 → 1 error. Now it's 2. Need to recompute: L9 incidencias: rol_invalido (msg0), sin_assistant (no assistant at all) → 2.

Hmm, is sin_assistant for L9 desirable? The conversation genuinely lacks an assistant turn → yes, flag it. So my manual table was wrong — the test expectations must be updated to match correct behavior: L9 has 2 incidencias. This is exactly the kind of discrepancy the user wants me to catch and reason about. Total issues recount:

    L3: json_invalido → 1
    L5: duplicado_exacto → 1
    L6: campo_ausente(id) → 1
    L7: campo_ausente(conversation) → 1
    L8: tipo_incorrecto(id), conversacion_vacia → 2
    L9: rol_invalido, sin_assistant → 2
    L10: sin_user → 1
    L11: sin_assistant → 1
    L12: campo_ausente(conversation[0].content) → 1 [message missing content → campo_ausente per my design]
    L13: contenido_vacio ×2 → 2
    L14: duplicado_aproximado → 1
    L15: tipo_incorrecto(raíz) → 1
    L16: tipo_incorrecto(conversation[1].content) → 1

Sum = 1+1+1+1+2+2+1+1+1+2+1+1+1 = 16 incidencias. invalidos = 13 lines (L3, L5..L16) — all still invalid. validos=2. Categories:

    json_invalido: 1
    duplicado_exacto: 1
    campo_ausente: L6(id), L7(conversation), L12(conversation[0].content) = 3
    tipo_incorrecto: L8(id), L15(raíz), L16(content) = 3
    conversacion_vacia: 1
    rol_invalido: 1
    sin_assistant: L9, L11 = 2
    sin_user: 1
    contenido_vacio: 2
    duplicado_aproximado: 1 Total = 1+1+3+3+1+1+2+1+2+1 = 16 ✓

Role distribution recount: L9 roles valid counted: user (from msg1) → users: L1(1),L2(2),L5(1),L6(1),L9(1),L11(1),L12(1),L13(1),L14(1),L16(1) = 11 users; assistants: L1,L2,L5,L6,L10,L12,L13,L14,L16 = 9; system: 1 (counted in distribucion? I count only valid roles in distribucion_roles... but then "system" won't appear in distribution even though it exists. Distribution of roles should reflect reality: include invalid roles in the distribution too? I think including all str roles (even invalid) in distribucion_roles is more informative. Decision: count every message with a str role into distribucion_roles (including system), AND flag rol_invalido for non-valid ones. Then distribution: user 11, assistant 9, system 1 = 21. total_mensajes = 21.

Hmm wait — but earlier I said total messages = 21 (all parseable). With L9's 2 messages: system+user → yes 21 total. But careful: only messages with str role counted. L12 msg0 has no role → not counted in distribution. L16 both have roles. So distribution = user 11, assistant 9, system 1 → 21 ✓ matches total.

Length stats: str contents: L9 now includes "Instrucciones"(13) and "Hola"(4) — already counted before ✓. Same 19 str contents, sum 160, min 0, max 26, mean 160/19 = 8.421... → 8.42, median 5.0.

Conversation lengths: same 12 convs → sum 160, min 0, max 53, mean 13.33, median 12.0. ✓ (L9 conv length = 13+4=17 — already included in my earlier computation ✓).

conversaciones_con_user: L1,L2,L5,L6,L9,L11,L12,L13,L14,L16 = 10 ✓. con_assistant: L1,L2,L5,L6,L10,L12,L13,L14,L16 = 9 ✓.

Good — the corrected table (with L9 → 2 incidencias, and content-missing → campo_ausente) is what I'll encode in tests. And I'll explicitly mention in the final summary that during design I caught the L9 double-count (sin_assistant + rol_invalido) and the "content missing → campo_ausente" classification decision.

Now — during actual test runs I might discover more real discrepancies (that's the exercise). E.g., media rounding, median type, roles counting of messages with missing content but valid role (L12 msg0: role=user, no content → counts as user ✓ counted).

L12 msg0: role present valid → user counted; content missing → campo_ausente. ✓.

Another subtlety — L13 msg0 content "" → contenido_vacio and length 0 counted. msg1 " " → strip empty → contenido_vacio, length 3 counted (len of raw content). OK — length stats include whitespace-only strings (they are strings). Fine, documented.

Now let me also double check the CLI exit behavior and the summary formatting. And --required-fields parse: split on commas, strip.

Alright — also add a validar function that returns the Informe for API use; tests use analizar_fichero directly.

Now README reproducibility: commands:

cd "prueba de agente arena.ai"
python -m dataset_auditor tests/data/muestra_defectuosa.jsonl --output informe.json
python -m unittest discover -s tests -v

Also a "uso como librería" snippet.

requirements.txt: I'll NOT create it; README states "Sin dependencias externas: solo biblioteca estándar. Por eso no se incluye requirements.txt."

Hmm — actually, should I include an empty requirements.txt to be explicit? The user said "Añadir requirements.txt únicamente si realmente es necesario." → Not necessary → omit. README explains. ✓.

Now write the actual files. Also I need to double-check python3 --version in sandbox — likely 3.10+. Will check.

One more thing about isolation: I should also verify that the main repo remains untouched by capturing its status before/after. Before: git -C /home/user/DATASETS-DE-PRONOMBRES-DE-AI-KU status --short shows ?? SCPD/ ?? tools/ (untracked from earlier restore). After my work: same. I'll show that.

Also — "configuraciones globales" — I won't touch git config, pip config, etc. No pip installs at all (stdlib only).

Now, the directory name: "prueba de agente arena.ai" — with spaces and a dot. Shell quoting: use quotes everywhere. write_file path: /home/user/prueba de agente arena.ai/dataset_auditor/__init__.py — absolute with spaces should be OK for the tool (it takes a string path).

Let me now also design terminal summary output:

============================================================
 dataset_auditor — informe de calidad
============================================================
 Fichero: tests/data/muestra_defectuosa.jsonl
------------------------------------------------------------
 Total de ejemplos ............ 15
 Ejemplos válidos ............. 2
 Ejemplos inválidos ........... 13
 Líneas vacías ................ 1
 Duplicados exactos ........... 1
 Duplicados aproximados ....... 1
------------------------------------------------------------
 Errores por categoría:
   campo_ausente .............. 3
   contenido_vacio ............ 2
   conversacion_vacia ......... 1
   duplicado_aproximado ....... 1
   duplicado_exacto ........... 1
   json_invalido .............. 1
   rol_invalido ............... 1
   sin_assistant .............. 2
   sin_user ................... 1
   tipo_incorrecto ............ 3
------------------------------------------------------------
 Distribución de roles ........ user=11 assistant=9 system=1
 Total de mensajes ............ 21
 Conversaciones con user ...... 10
 Conversaciones con assistant . 9
------------------------------------------------------------
 Longitud de mensajes (caracteres):
   n=19  min=0  max=26  media=8.42  mediana=5
 Longitud de conversaciones:
   n=12  min=0  max=53  media=13.33  mediana=12
------------------------------------------------------------
 Primeras incidencias (mostrando 16 de 16):
   [línea 3] json_invalido: Expecting ',' delimiter en posición 78
   [línea 5] duplicado_exacto: idéntica a la línea 1
   ...
 Informe JSON guardado en: informe.json

The exact json error message from json.loads: "Expecting ',' delimiter" and pos — fine, tests shouldn't depend on exact message (only category and line).

Now, tests to write (unittest):
python

import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
RUTA_FIXTURE = Path(__file__).parent / "data" / "muestra_defectuosa.jsonl"
RAIZ = Path(__file__).parent.parent
def escribir(tmp: str, lineas: list[str]) -> str: ...
class TestAuditor(unittest.TestCase):
    def test_fixture_completo(self): ... assert all the numbers
    def test_json_invalido(self)
    def test_lineas_vacias(self)
    def test_campos_ausentes(self)
    def test_tipos_incorrectos(self)
    def test_duplicados(self)
    def test_mensaje_vacio(self)
    def test_rol_invalido(self)
    def test_sin_user_y_sin_assistant(self)
    def test_contenido_vacio(self)
    def test_conversacion_vacia(self)
    def test_archivo_vacio(self)
    def test_archivo_inexistente(self) → FileNotFoundError
    def test_codificacion_invalida(self)
    def test_unicode_contenido(self)
    def test_norm_espacios_no_duplica(self) — two lines differing only in content (not just whitespace) → no near dup
    def test_casi_duplicado_ignora_id(self) — same conv different id → near dup
    def test_cli(self) — subprocess, --output, exit 0, JSON valid, numbers match
    def test_cli_fail_on_issues(self) — exit 2
    def test_cli_archivo_inexistente(self) — exit 1

The fixture numbers as a dict of expectations to assert.

Now — one subtlety about subprocess tests: cwd must be RAIZ so python -m dataset_auditor resolves. Use sys.executable.

Let me now think about whether python -m dataset_auditor from RAIZ works: RAIZ contains dataset_auditor/ package dir → yes.

Now — potential pitfalls I should verify during implementation (and honestly report):

    json.loads on line with trailing content? fine.
    CRLF handling: strip("\r\n") on each line — decode bytes then strip. I'll do linea = linea_bytes.decode("utf-8").rstrip("\r\n").
    Whitespace-only line: strip() == "" → linea_vacia. ✓
    json.loads accepts trailing whitespace; a line of "null" → root not dict → tipo_incorrecto. ✓
    Median with statistics.median on floats — returns float.
    Rounding: round(8.421..., 2) = 8.42; round(13.333...,2)=13.33; mean 160/19 = 8.421052... → 8.42 ✓; 160/12=13.333→13.33 ✓.
    Deterministic JSON: use sort_keys? I'll build dicts in fixed order and dump with ensure_ascii=False, indent=2.
    Very long lines: fine.
    Huge files: streaming, only incidencias capped; but vistos_raw/vistos_firma store all signatures in memory — acceptable, document as limitation (for 250k lines it's fine).

Also — one design question: should lineas_vacias also be in errores_por_categoria? I register incidencia linea_vacia → yes it's in cat counts. But informe.lineas_vacias is also tracked. Both. Fine.

And should ejemplos_invalidos include duplicate lines? Yes (they're in invalidas set). README documents.

Edge: file not found → raise FileNotFoundError from analizar_fichero; CLI catches and prints error, exit 1.

Argparse details:
python
