
def construir_parser():
    p = argparse.ArgumentParser(prog="dataset_auditor", description="...")
    p.add_argument("archivo", help="ruta al archivo JSONL")
    p.add_argument("--output", "-o", help="ruta del informe JSON de salida")
    p.add_argument("--required-fields", default="id,conversation", help="...")
    p.add_argument("--max-detalle", type=int, default=1000, help="máximo de incidencias detalladas en el informe")
    p.add_argument("--fail-on-issues", action="store_true", help="salir con código 2 si hay incidencias")
    p.add_argument("--version", action="version", version=f"dataset_auditor {__version__}")
    return p
def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    campos = [c.strip() for c in args.required_fields.split(",") if c.strip()]
    if not campos: parser.error(...)? handle: print error, return 2? argparse error exits with 2 automatically if using parser.error — but that exits; ok acceptable: validate before, use parser.error.
    try:
        informe = analizar_fichero(args.archivo, campos_requeridos=campos, max_incidencias=args.max_detalle)
    except FileNotFoundError as e:
        print(f"error: no se encuentra el archivo: {e}", file=sys.stderr); return 1
    except OSError as e:
        print(f"error: {e}", file=sys.stderr); return 1
    mostrar_terminal(informe)
    if args.output:
        escribir_json(informe, args.output, version=__version__)
        print(f"Informe guardado en: {args.output}")
    if args.fail_on_issues and informe.ejemplos_invalidos > 0:
        return 2
    return 0

__main__.py:
python

import sys
from .cli import main
if __name__ == "__main__":
    sys.exit(main())

informe.py: funciones mostrar_terminal(informe), informe_a_dict(informe, version), escribir_json(informe, ruta, version).

For the JSON report, include "generado" timestamp? That breaks reproducibility of output bytes but fine; keep ISO timestamp. Tests shouldn't assert exact bytes, just fields.

Let me also include in resumen: "lineas_procesadas" (total lines incl. empty)? Maybe useful: lineas_totales = total_ejemplos + lineas_vacias + (undecodable lines count). I'll add lineas_no_utf8 count. Minor extra. Keep: total_ejemplos, lineas_vacias, lineas_no_utf8.

OK. Time to execute. Order of operations:

    bash: environment inspection (python version, ls /home/user, git status of main repo read-only, confirm location).
    bash: create tree dir, verify isolation (realpath).
    write files (init, analisis, informe, cli, main).
    write fixture.
    write tests.
    run tests → expect maybe failures; fix.
    run CLI on fixture; inspect; verify against table.
    final validation: rerun tests, run CLI with --fail-on-issues, check exit codes, confirm main repo untouched, verify README commands.
    Summary.

Also per user request: "El árbol debe quedar completamente separado del proyecto principal" — I'll also not create any git repo inside it (optional). Actually creating a local git repo inside the test tree could be considered "mecanismo equivalente" — but unnecessary; plain directory is cleaner and truly isolated. I'll mention that choice.

Also should I rm -rf anything? No — don't delete. The directory doesn't exist yet presumably. Check first: ls /home/user — only DATASETS-DE-PRONOMBRES-DE-AI-KU and dotfiles. Create fresh.

Let me write the code now, carefully.

Actually one more check on _firma_normalizada for near-dup: L1 vs L14:_

    L1 obj: {"id":"e1","conversation":[{"role":"user","content":"Hola, AI-ku."},{"role":"assistant","content":"Hola."}]}
    L14 obj: {"id":"e14","conversation":[{"role":"user","content":"Hola, AI-ku."},{"role":"assistant","content":"Hola."}]} Normalized: both → ("d", (("conversation", ("l", (("d",(("content",("s","hola, ai-ku.")),("role",("s","user")))), ("d",(("content",("s","hola.")),("role",("s","assistant")))))), ("id", ("s","e1"))) vs id "e14" — DIFFERENT because id is included in the signature! Near-dup must ignore id/metadata differences, or at least ignore id. Decision: signature computed on the CONVERSATION only (messages), not the whole object. For examples without "conversation" field... then no signature (can't near-dup). So: firma = firma_normalizada(conv) when conv is a list. Then L1 vs L14 → equal → near dup ✓. And L5 exact dup of L1 → raw equal → exact branch (continue) → never reaches signature check ✓. But careful: two DIFFERENT examples with identical conversation but different ids → near dup ✓ desired.

So signature = normalized conversation (list of messages). Messages normalized recursively (including content whitespace collapse + casefold). Good — and role differences produce different signatures.

What about "practically duplicate" broader (e.g., one word changed)? Out of scope — documented as limitation (deterministic whitespace/case normalization only). Good, honest scope.

Now the tests for near-dup ignoring id: fixture L14 covers it (id e14 vs e1).

Let me also double-check informe.ejemplos_invalidos with duplicates: L5 in invalidas (dup registered with ejemplo=True) ✓; L14 ✓.

One more: line 4 whitespace-only " " → decode ok, strip()=="" → linea_vacia. ✓

And file ends with newline → no extra empty line (split on \n via enumerate; last line "" if file ends with \n → enumerate includes final ""? for numero, b in enumerate(fh) — iterating a binary file yields lines including the final empty line after trailing newline! E.g., b"a\nb\n" → lines b"a\n", b"b\n" — no trailing empty. Actually file iteration splits on \n and the last line "b\n" is yielded; there's no empty line after. But b"a\nb" (no trailing newline) → b"a\n", b"b". And a file with content "\n" → one line "\n" → empty line ✓. Good, no phantom empty lines. But a file ending with "\n\n" → last line is "\n" → empty → flagged ✓ correct.

Now, open(ruta_p, "rb") — if file doesn't exist → FileNotFoundError propagates; CLI catches.

Alright, also think about --max-detalle semantics: incidencias list capped but invalidas set and cat counts uncapped. Document.

Time to also prepare expected test constants:
python

ESP_FIXTURE = {
    "total_ejemplos": 15,
    "ejemplos_validos": 2,
    "ejemplos_invalidos": 13,
    "lineas_vacias": 1,
    "duplicados_exactos": 1,
    "duplicados_aproximados": 1,
    "errores_por_categoria": {
        "campo_ausente": 3, "contenido_vacio": 2, "conversacion_vacia": 1,
        "duplicado_aproximado": 1, "duplicado_exacto": 1, "json_invalido": 1,
        "rol_invalido": 1, "sin_assistant": 2, "sin_user": 1,
        "tipo_incorrecto": 3,
    },
    "distribucion_roles": {"user": 11, "assistant": 9, "system": 1},
    "total_mensajes": 21,
    "conversaciones_con_user": 10,
    "conversaciones_con_assistant": 9,
    "longitud_mensajes": {"n": 19, "minimo": 0.0, "maximo": 26.0, "media": 8.42, "mediana": 5.0},
    "longitud_conversaciones": {"n": 12, "minimo": 0.0, "maximo": 53.0, "media": 13.33, "mediana": 12.0},
}

Wait — media 160/19 = 8.421052631578947 → round(...,2) = 8.42 ✓. 160/12 = 13.3333 → 13.33 ✓.

Category counts check: campo_ausente: L6(id) + L7(conversation) + L12(content[0]) = 3 ✓. tipo_incorrecto: L8(id) + L15(raíz) + L16(content) = 3 ✓. sin_assistant: L9 + L11 = 2 ✓. Sum: 3+2+1+1+1+1+1+2+1+3 = 16 ✓.

Also note: L12's msg0 ({"role":"user"}) — role present valid → counted user (11 includes it ✓), content missing → campo_ausente. ✓

Hmm — L9 msg0 {"role":"system","content":"Instrucciones"} → rol_invalido; content str → length counted (13) ✓ included in 19 count ✓.

Also potential question: does L9's system role count toward total_mensajes (21)? total_mensajes = all messages in parseable conversations? Or messages with str role? Decide: total_mensajes = messages with a valid str role (21). But L12 msg0 has role user (valid) → counted. So messages counted = those with str role in valid set? Then system excluded from total but included in distribution? Inconsistent. Better: total_mensajes = all messages examined (any dict message in a conversation), = 21? Let me count all dict messages: L1:2, L2:3, L5:2, L6:2, L8:0, L9:2, L10:1, L11:1, L12:2, L13:2, L14:2, L16:2 = 21. And distribucion_roles = str roles present: user 11 + assistant 9 + system 1 = 21. Both 21 — coincidentally equal here because every message has a str role except... L12 msg0 has role "user" ✓ str. So all 21 messages have str roles. Consistent: total_mensajes=21, distribution sums to 21 ✓. In general total_mensajes = number of dict messages; distribution = subset with str role. Fine; document.

Alright. Also the report: incidencias detail cap default 1000 — fixture has 16, all listed.

I also want informe_a_dict to include "errores_por_categoria" as sorted dict, "distribucion_roles" sorted, etc.

Now — the CLI test with subprocess: run [sys.executable, "-m", "dataset_auditor", str(RUTA_FIXTURE), "--output", str(tmp)] cwd=RAIZ. Assert returncode 0, output file exists, json.loads works, resumen.total_ejemplos==15. And --fail-on-issues → returncode 2. And missing file → returncode 1.

Now write everything. Let me also plan the narration around phases. Keep it professional, in Spanish (user writes Spanish). The final summary must cover the 8 requested points.

One more consideration: the user says "prueba de agente arena.ai" — the actual intended name likely "prueba de agente arena.ai". I'll create the directory with that literal name: prueba de agente arena.ai. I'll note the assumption.

Also should the tool's language be Spanish? The spec fields are Spanish; I'll make CLI messages and report keys Spanish. Code identifiers English. Good.

Let me start executing. First inspection commands.

Then creation: mkdir -p "/home/user/prueba de agente arena.ai/dataset_auditor" "/home/user/prueba de agente arena.ai/tests/data".

Then write files via write_file with absolute paths. If write_file fails on absolute path outside repo, fallback to bash heredocs. Let me try write_file first.

Files:

    dataset_auditor/__init__.py
    dataset_auditor/analisis.py
    dataset_auditor/informe.py
    dataset_auditor/cli.py
    dataset_auditor/__main__.py
    tests/__init__.py
    tests/data/muestra_defectuosa.jsonl (careful exact content!)
    tests/test_dataset_auditor.py
    README.md

Fixture content — write precisely (16 lines). Note L5 must be byte-identical to L1 (same JSON text). I'll craft:

L1: {"id": "e1", "conversation": [{"role": "user", "content": "Hola, AI-ku."}, {"role": "assistant", "content": "Hola."}]} L2: {"id": "e2", "conversation": [{"role": "user", "content": "¿Qué hora es?"}, {"role": "assistant", "content": "No tengo reloj, lo siento."}, {"role": "user", "content": "Vale, gracias."}]} L3: {"id": "e3", "conversation": [{"role": "user", "content": "hola"}] L4: (spaces only " ") L5: same as L1 L6: {"conversation": [{"role": "user", "content": "Sin id."}, {"role": "assistant", "content": "Vale."}]} L7: {"id": "e7"} L8: {"id": 123, "conversation": []} L9: {"id": "e9", "conversation": [{"role": "system", "content": "Instrucciones"}, {"role": "user", "content": "Hola"}]} L10: {"id": "e10", "conversation": [{"role": "assistant", "content": "Hola"}]} L11: {"id": "e11", "conversation": [{"role": "user", "content": "Hola"}]} L12: {"id": "e12", "conversation": [{"role": "user"}, {"role": "assistant", "content": "ok"}]} L13: {"id": "e13", "conversation": [{"role": "user", "content": ""}, {"role": "assistant", "content": " "}]} L14: {"id": "e14", "conversation": [{"role": "user", "content": "Hola, AI-ku."}, {"role": "assistant", "content": "Hola."}]} L15: ["esto", "no", "es", "un", "objeto"] L16: {"id": "e16", "conversation": [{"role": "user", "content": 42}, {"role": "assistant", "content": "No entiendo."}]}

Now tests will import from dataset_auditor.analisis import analizar_fichero. RAIZ insertion into sys.path: tests run via python -m unittest discover -s tests from RAIZ — cwd in sys.path? When using -m unittest, sys.path[0] is cwd → RAIZ on path → import dataset_auditor works. Also tests/init.py present. Good.

Let me write the code files now mentally complete:

analisis.py — as sketched. Let me finalize with type hints and docstrings.

Also decide: analizar_fichero(ruta, campos_requeridos=("id","conversation"), max_incidencias=1000). Return Informe.

Careful with one thing: in the loop, for exact duplicates we continue BEFORE adding to vistos_raw — but the line was already seen so vistos_raw already has it. ✓. But also note we skip signature/validation for exact dups — fine.

But subtle: what if the same raw line appears but the first occurrence was itself flagged json_invalido? Raw equality of an unparseable line — e.g., two identical broken lines: second flagged duplicado_exacto. OK acceptable.

Another subtle: id_ejemplo extraction: obj.get("id") if isinstance str else None. For report usefulness. Use _id_texto(obj) helper._

informe.py: functions mostrar_terminal(informe) and informe_a_dict(informe, version, fichero) and escribir_json.

Now cli.py main() as sketched; and the --required-fields empty handling: if empty after split → parser.error("--required-fields no puede estar vacío").

Edge: max_incidencias <= 0 → treat as unlimited? Keep: if <=0 → unlimited (None). Simple: if max_incidencias and len<... hmm; just allow negative → cap disabled. I'll implement: if max_incidencias <= 0 or len(incidencias) < max_incidencias.

Now, run tests; predict which might fail on first run. Honestly I might make small mistakes (e.g., forgetting informe.lineas_vacias increment, or double counting). The exercise wants me to find and fix them. I'll run and report honestly.

Also add a couple of "extra" checks the user didn't mention but a good auditor should: conversacion_vacia (done) and maybe "primer turno no es de usuario"? Not required; skip to avoid overreach — mention as future improvement. Also "mensajes fuera de orden (assistant→user)"? Mention as future.

README: include a real example output — I'll paste after running.

Also mention in README the counting rules: qué se considera válido/inválido, duplicados como inválidos, líneas vacías fuera de total, etc.

Let me now begin executing tool calls. I'll keep narration concise but visible, per "no minimices tus pasos".

Phase 0 commands:

    python3 --version
    ls -la /home/user
    git -C /home/user/DATASETS-DE-PRONOMBRES-DE-AI-KU status --short (read-only)
    realpath /home/user/DATASETS-DE-PRONOMBRES-DE-AI-KU /home/user

Then create dirs.

Then write files. Then run unit tests (expect possibly failing), fix, rerun. Then CLI demo. Then final checks + summary.

Let me also remember: DON'T commit anything to main repo, don't push, don't touch git. The session is closed anyway; remote ops fail. All local.

One more: after building, I'll also verify isolation by listing the main repo tree before/after (md5 of git status output?) — simple: git -C ... status --short again and diff manually.

Also the user said "No borrar archivos existentes" — I won't.

Also "No introducir dependencias innecesarias" — none.

OK, let me go. I'll now write out all the code in my head into the files.

Actually, let me reconsider one thing in analisis.py: the registrar closure and invalidas set. Also cat counter initialized with all categories = 0 — but then categories never used won't appear in "errores_por_categoria" JSON if I filter zeros. I'll keep zeros filtered in the report (cleaner) — or keep all with zeros? Keep only nonzero in the dict for cleanliness; README lists all categories. In tests, assert equality with the nonzero dict. My ESP_FIXTURE has nonzero only. But note "linea_vacia" and "codificacion_invalida" categories: linea_vacia=1 in fixture — include in errores_por_categoria? I said cat counts all incidencias including linea_vacia. Fixture has 1 empty line → linea_vacia: 1 in the counter. Hmm — but earlier my total sum was 16 WITHOUT linea_vacia. Let me decide: does linea_vacia go into errores_por_categoria? It's registered as incidencia → counted in cat. Then total incidencias = 17 (16 + 1 linea_vacia). My earlier table excluded it; recompute: errores_por_categoria includes linea_vacia: 1. invalidos unchanged (13) since empty lines aren't examples. ejemplos_validos=2, total=15.

Hmm, is that coherent? "errores por categoría" = all detected issues including empty lines. I think yes — it's an issue count. But then resumen also has lineas_vacias: 1 separately. OK. But then in tests, ESP_FIXTURE["errores_por_categoria"] includes "linea_vacia": 1. And total incidencias = 17. Fine — I'll adjust my mental table: categories: campo_ausente 3, contenido_vacio 2, conversacion_vacia 1, duplicado_aproximado 1, duplicado_exacto 1, json_invalido 1, linea_vacia 1, rol_invalido 1, sin_assistant 2, sin_user 1, tipo_incorrecto 3 → sum = 3+2+1+1+1+1+1+1+2+1+3 = 17 ✓.

Hmm wait — but should linea_vacia be in "errores"? It makes "errores por categoría" a superset including non-example issues. It's fine and clearly documented. Alternatively exclude linea_vacia from cat but keep counter separate. Cleaner conceptually: errores_por_categoria = issues on examples; lineas_vacias separate. Hmm. The spec: "errores por categoría" — empty lines are listed in spec's detection list as a problem category. I'll include them; simpler and consistent ("cualquier problema detectado"). Decide: include. Update tests accordingly.

Also codificacion_invalida would be in cat too if present (unit test only).

Alright — also mostrar_terminal prints incidencias up to cap with note "mostrando X de Y".

Let me now also draft exact terminal output text (for README) after real run.

Time to write. Also remember Python 3.10+: str | os.PathLike[str] in annotation with from __future__ import annotations is fine even on 3.9; but runtime isinstance with it not needed. Use PathLike[str] | str annotation only.

Let me write all files now.

For tests, I need to be careful with exact fixture numbers; I computed them by hand above. During the run, if a test fails, I'll investigate whether the code or my expectation is wrong — and fix accordingly, reporting honestly.

Let me write the bash inspection first (parallel-ish single call), then create dir, then write files (several write_file calls — they're independent, can batch in same block? They're independent of each other → yes, can call multiple write_file in one block. But each write_file is a separate tool call in the same block — allowed since independent. I'll batch 2-3 at a time to keep messages manageable.)

Let me draft final code text carefully now.

--- analisis.py ---
python

# -*- coding: utf-8 -*-
"""Núcleo de análisis de dataset_auditor.
Lee un fichero JSONL conversacional y detecta problemas de calidad:
JSON inválido, líneas vacías, campos ausentes, tipos incorrectos,
duplicados (exactos y aproximados), mensajes vacíos o sin contenido,
roles inválidos y conversaciones sin usuario o sin asistente.
"""
from __future__ import annotations
import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
ROLES_VALIDOS: frozenset[str] = frozenset({"user", "assistant"})
CATEGORIAS: tuple[str, ...] = (
    "linea_vacia",
    "codificacion_invalida",
    "json_invalido",
    "campo_ausente",
    "tipo_incorrecto",
    "conversacion_vacia",
    "mensaje_vacio",
    "contenido_vacio",
    "rol_invalido",
    "sin_user",
    "sin_assistant",
    "duplicado_exacto",
    "duplicado_aproximado",
)
# Tipos esperados de los campos con semántica especial; el resto se asume str.
TIPOS_ESPECIALES: dict[str, type] = {"conversation": list}
@dataclass
class Incidencia:
    """Un problema detectado en una línea concreta del fichero."""
    linea: int
    categoria: str
    detalle: str = ""
    id_ejemplo: Optional[str] = None
    es_duplicado_de: Optional[int] = None
    def a_dict(self) -> dict[str, Any]:
        return {
            "linea": self.linea,
            "categoria": self.categoria,
            "detalle": self.detalle,
            "id_ejemplo": self.id_ejemplo,
            "es_duplicado_de": self.es_duplicado_de,
        }
@dataclass
class Estadisticas:
    """Estadísticas básicas de una lista de longitudes."""
    n: int = 0
    minimo: float = 0.0
    maximo: float = 0.0
    media: float = 0.0
    mediana: float = 0.0
    @classmethod
    def desde_valores(cls, valores: list[float]) -> "Estadisticas":
        if not valores:
            return cls()
        return cls(
            n=len(valores),
            minimo=float(min(valores)),
            maximo=float(max(valores)),
            media=float(sum(valores) / len(valores)),
            mediana=float(statistics.median(valores)),
        )
    def a_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "minimo": round(self.minimo, 2),
            "maximo": round(self.maximo, 2),
            "media": round(self.media, 2),
            "mediana": round(self.mediana, 2),
        }
@dataclass
class Informe:
    """Resultado completo del análisis de un fichero JSONL."""
    fichero: str
    total_ejemplos: int = 0
    ejemplos_validos: int = 0
    ejemplos_invalidos: int = 0
    lineas_vacias: int = 0
    lineas_no_utf8: int = 0
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
    incidencias_omitidas: int = 0
def _id_texto(obj: Any) -> Optional[str]:
    """Devuelve el id del ejemplo si es una cadena, si no None."""
    if isinstance(obj, dict) and isinstance(obj.get("id"), str):
        return obj["id"]
    return None
def _firma_conversacion(conversacion: Any) -> Optional[tuple[Any, ...]]:
    """Firma normalizada de una conversación para detectar casi-duplicados.
    Normaliza cada mensaje: colapsa espacios y pasa a minúsculas el
    contenido, y ordena las claves del mensaje. Dos conversaciones con
    la misma firma se consideran prácticamente duplicadas aunque cambie
    el id del ejemplo o el espaciado.
    """
    def norm(valor: Any) -> Any:
        if isinstance(valor, dict):
            return ("d", tuple((k, norm(v)) for k, v in sorted(valor.items())))
        if isinstance(valor, list):
            return ("l", tuple(norm(v) for v in valor))
        if isinstance(valor, str):
            return ("s", " ".join(valor.split()).casefold())
        if valor is None:
            return ("n",)
        return ("v", repr(valor))
    if not isinstance(conversacion, list):
        return None
    return norm(conversacion)
def analizar_fichero(
    ruta: str | Path,
    campos_requeridos: Iterable[str] = ("id", "conversation"),
    max_incidencias: int = 1000,
) -> Informe:
    """Analiza un fichero JSONL y devuelve un Informe con todos los hallazgos."""
    campos = tuple(campos_requeridos)
    informe = Informe(fichero=str(Path(ruta)))
    contador: Counter[str] = Counter()
    lineas_originales: dict[str, int] = {}
    firmas_vistas: dict[tuple[Any, ...], int] = {}
    longitudes_mensaje: list[float] = []
    longitudes_conversacion: list[float] = []
    roles: Counter[str] = Counter()
    invalidos: set[int] = set()
    def registrar(inc: Incidencia, ejemplo: bool) -> None:
        contador[inc.categoria] += 1
        if max_incidencias > 0 and len(informe.incidencias) < max_incidencias:
            informe.incidencias.append(inc)
        else:
            informe.incidencias_omitidas += 1
        if ejemplo:
            invalidos.add(inc.linea)
    with open(informe.fichero, "rb") as fh:
        for numero, linea_bytes in enumerate(fh, start=1):
            try:
                linea = linea_bytes.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError as exc:
                informe.lineas_no_utf8 += 1
                registrar(Incidencia(numero, "codificacion_invalida", f"no es UTF-8 válido: {exc}"), ejemplo=False)
                continue
            if not linea.strip():
                informe.lineas_vacias += 1
                registrar(Incidencia(numero, "linea_vacia", "línea vacía o solo espacios"), ejemplo=False)
                continue
            informe.total_ejemplos += 1
            if linea in lineas_originales:
                origen = lineas_originales[linea]
                informe.duplicados_exactos += 1
                registrar(Incidencia(numero, "duplicado_exacto", f"es idéntica a la línea {origen}", es_duplicado_de=origen), ejemplo=True)
                continue
            try:
                objeto = json.loads(linea)
            except json.JSONDecodeError as exc:
                registrar(Incidencia(numero, "json_invalido", f"{exc.msg} (posición {exc.pos})"), ejemplo=True)
                continue
            if not isinstance(objeto, dict):
                registrar(Incidencia(numero, "tipo_incorrecto", f"la raíz debe ser un objeto, se encontró {type(objeto).__name__}"), ejemplo=True)
                continue
            id_ejemplo = _id_texto(objeto)
            for campo in campos:
                if campo not in objeto:
                    registrar(Incidencia(numero, "campo_ausente", f"falta el campo obligatorio «{campo}»", id_ejemplo=id_ejemplo), ejemplo=True)
                else:
                    esperado = TIPOS_ESPECIALES.get(campo, str)
                    if not isinstance(objeto[campo], esperado):
                        registrar(Incidencia(numero, "tipo_incorrecto", f"«{campo}» debe ser {esperado.__name__}, se encontró {type(objeto[campo]).__name__}", id_ejemplo=id_ejemplo), ejemplo=True)
            conversacion = objeto.get("conversation")
            if isinstance(conversacion, list):
                if not conversacion:
                    registrar(Incidencia(numero, "conversacion_vacia", "la conversación no contiene mensajes", id_ejemplo=id_ejemplo), ejemplo=True)
                else:
                    tiene_user = False
                    tiene_assistant = False
                    suma = 0.0
                    for i, mensaje in enumerate(conversacion):
                        ruta_msg = f"conversation[{i}]"
                        informe.total_mensajes += 1
                        if not isinstance(mensaje, dict):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"el mensaje {ruta_msg} debe ser un objeto, se encontró {type(mensaje).__name__}", id_ejemplo=id_ejemplo), ejemplo=True)
                            continue
                        if not mensaje:
                            registrar(Incidencia(numero, "mensaje_vacio", f"el mensaje {ruta_msg} está vacío", id_ejemplo=id_ejemplo), ejemplo=True)
                            continue
                        rol = mensaje.get("role")
                        if rol is None:
                            registrar(Incidencia(numero, "campo_ausente", f"falta «role» en {ruta_msg}", id_ejemplo=id_ejemplo), ejemplo=True)
                        elif not isinstance(rol, str):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"«role» en {ruta_msg} debe ser str, se encontró {type(rol).__name__}", id_ejemplo=id_ejemplo), ejemplo=True)
                        else:
                            roles[rol] += 1
                            if rol == "user":
                                tiene_user = True
                            elif rol == "assistant":
                                tiene_assistant = True
                            else:
                                registrar(Incidencia(numero, "rol_invalido", f"rol «{rol}» en {ruta_msg} (válidos: user, assistant)", id_ejemplo=id_ejemplo), ejemplo=True)
                        contenido = mensaje.get("content")
                        if contenido is None:
                            registrar(Incidencia(numero, "campo_ausente", f"falta «content» en {ruta_msg}", id_ejemplo=id_ejemplo), ejemplo=True)
                        elif not isinstance(contenido, str):
                            registrar(Incidencia(numero, "tipo_incorrecto", f"«content» en {ruta_msg} debe ser str, se encontró {type(contenido).__name__}", id_ejemplo=id_ejemplo), ejemplo=True)
                        else:
                            longitudes_mensaje.append(float(len(contenido)))
                            suma += float(len(contenido))
                            if not contenido.strip():
                                registrar(Incidencia(numero, "contenido_vacio", f"«content» en {ruta_msg} está vacío o solo tiene espacios", id_ejemplo=id_ejemplo), ejemplo=True)
                    if tiene_user:
                        informe.conversaciones_con_user += 1
                    if tiene_assistant:
                        informe.conversaciones_con_assistant += 1
                    if not tiene_user:
                        registrar(Incidencia(numero, "sin_user", "la conversación no tiene ningún turno de usuario", id_ejemplo=id_ejemplo), ejemplo=True)
                    if not tiene_assistant:
                        registrar(Incidencia(numero, "sin_assistant", "la conversación no tiene ningún turno de asistente", id_ejemplo=id_ejemplo), ejemplo=True)
                    longitudes_conversacion.append(suma)
            firma = _firma_conversacion(conversacion)
            if firma is not None and firma in firmas_vistas:
                origen = firmas_vistas[firma]
                informe.duplicados_aproximados += 1
                registrar(Incidencia(numero, "duplicado_aproximado", f"prácticamente idéntica a la línea {origen} (misma conversación normalizada)", id_ejemplo=id_ejemplo, es_duplicado_de=origen), ejemplo=True)
            elif firma is not None:
                firmas_vistas[firma] = numero
            lineas_originales[linea] = numero
    informe.ejemplos_invalidos = len(invalidos)
    informe.ejemplos_validos = informe.total_ejemplos - informe.ejemplos_invalidos
    informe.errores_por_categoria = dict(sorted(contador.items()))
    informe.distribucion_roles = dict(sorted(roles.items()))
    informe.longitud_mensajes = Estadisticas.desde_valores(longitudes_mensaje)
    informe.longitud_conversaciones = Estadisticas.desde_valores(longitudes_conversacion)
    return informe

Wait — there's a subtle problem with near-dup detection order: I check firma BEFORE adding lineas_originales[linea] — but after the JSON processing. For L14: firma matches L1's (L1 stored when processed). ✓. For exact dup L5, we continued earlier ✓.

BUT bug: near-dup check happens even if the line is otherwise invalid — fine.

Another subtle: for the near-dup, the duplicate line's own firma — if two near-dups of the same original (L14 and L14b), second near-dup points to first occurrence of firma (L1) ✓.

Also — total_mensajes += 1 counts even non-dict messages (e.g., a string message) — "mensajes examinados". OK.

Also conversaciones_con_user etc counted for convs regardless of other issues. ✓

lineas_originales[linea] = numero — do this only for non-dup lines at the end. But note json_invalido lines also get added (raw string) — fine.

Wait — one more ordering issue: I register duplicado_exacto with continue, so lineas_originales not updated (already there) ✓, firma not re-checked ✓.

Now informe.py:
python

# -*- coding: utf-8 -*-
"""Serialización y renderizado del informe."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .analisis import Informe
def informe_a_dict(informe: Informe, version: str) -> dict[str, Any]:
    return {
        "resumen": {
            "fichero": informe.fichero,
            "total_ejemplos": informe.total_ejemplos,
            "ejemplos_validos": informe.ejemplos_validos,
            "ejemplos_invalidos": informe.ejemplos_invalidos,
            "lineas_vacias": informe.lineas_vacias,
            "lineas_no_utf8": informe.lineas_no_utf8,
            "duplicados_exactos": informe.duplicados_exactos,
