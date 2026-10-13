"""Detalle de cada trámite TAD desde la API pública del buscador (tad2-rest).

    python -m ingesta.tad_detalle descargar      baja el detalle de los trámites TAD activos
    python -m ingesta.tad_detalle descargar --refrescar
    python -m ingesta.tad_detalle cargar         vuelca lo descargado a la base
    python -m ingesta.tad_detalle cargar --dry-run

La descarga guarda un JSON por trámite en data/raw/tad_detalle/<id>.json y es
reanudable: saltea los que ya están, salvo con --refrescar.

La carga guarda cada detalle como fuente 'api_tad' del mismo trámite y le
asigna el organismo real a partir de la repartición GDE iniciadora
("DNDA#MJ" -> organismo MJ; "INAME#ANMAT" -> ANMAT), más específico que el
ministerio de ORGANO_RECTOR.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import Json

from ingesta import normalizar as n
from ingesta.tad import DATABASE_URL, USER_AGENT, TIPO_FUENTE as FUENTE_CSV

log = logging.getLogger("ingesta.tad_detalle")

API_URL = "https://tramitesadistancia.gob.ar/tad2-rest/tipoTramite/"
CARPETA = Path("data/raw/tad_detalle")
PAUSA = 0.5  # segundos entre pedidos
MAX_ERRORES_SEGUIDOS = 10
TIPO_FUENTE = "api_tad"
# Etiquetas que nombran a un organismo con su sigla: "Inspección General de Justicia - IGJ".
ETIQUETA_CON_SIGLA = re.compile(r"^(?P<nombre>.+?)\s+[-–]\s+(?P<sigla>[A-Z0-9]+)$")


class Simulacion(Exception):
    """Corta la transacción en --dry-run para que se deshaga."""


# Descarga ------------------------------------------------------------------

def pedir(sesion, ruta, intentos=3):
    for intento in range(1, intentos + 1):
        try:
            r = sesion.get(API_URL + ruta, timeout=30)
            r.raise_for_status()
            cuerpo = r.json()
            if cuerpo.get("error"):
                raise ValueError(f"la API respondió error: {cuerpo.get('mensaje')}")
            return cuerpo.get("respuesta")
        except (requests.RequestException, ValueError):
            if intento == intentos:
                raise
            time.sleep(5 * intento)


def ids_activos(database_url):
    with psycopg2.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT id_externo::integer FROM fuente WHERE tipo = %s AND activo ORDER BY 1", (FUENTE_CSV,))
        return [fila[0] for fila in cur.fetchall()]


def descargar(args):
    args.carpeta.mkdir(parents=True, exist_ok=True)
    ids = ids_activos(args.database_url)
    pendientes = [i for i in ids if args.refrescar or not (args.carpeta / f"{i}.json").exists()]
    log.info("%s trámites activos, %s por descargar", len(ids), len(pendientes))

    sesion = requests.Session()
    sesion.headers["User-Agent"] = USER_AGENT
    errores_seguidos = 0
    fallidos = []
    for i, id_tad in enumerate(pendientes, 1):
        try:
            tipo = pedir(sesion, str(id_tad))
            time.sleep(PAUSA)
            descripcion = pedir(sesion, f"descripcionTramite/{id_tad}")
            time.sleep(PAUSA)
        except (requests.RequestException, ValueError) as e:
            errores_seguidos += 1
            fallidos.append(id_tad)
            log.warning("ID %s: %s", id_tad, e)
            if errores_seguidos >= MAX_ERRORES_SEGUIDOS:
                raise SystemExit(f"{errores_seguidos} errores seguidos; se corta la descarga (reanudable)")
            continue
        errores_seguidos = 0
        registro = {
            "id": id_tad,
            "capturado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tipo_tramite": tipo,
            "descripcion_html": descripcion,
        }
        destino = args.carpeta / f"{id_tad}.json"
        temporal = destino.with_suffix(".tmp")
        temporal.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")
        temporal.replace(destino)
        if i % 100 == 0 or i == len(pendientes):
            log.info("%s/%s", i, len(pendientes))

    if fallidos:
        log.warning("%s fallidos (se reintentan en la próxima corrida): %s", len(fallidos), fallidos[:20])


# Carga ---------------------------------------------------------------------

def fecha_ms(v):
    return datetime.fromtimestamp(v / 1000, timezone.utc).date().isoformat() if v else None


def etiquetas(tipo):
    try:
        tags = json.loads(tipo.get("etiquetas") or "{}").get("tags", [])
    except (ValueError, AttributeError):
        return []
    return [t for t in (n.texto(tag) for tag in tags) if t]


def extraer(registro):
    """JSON descargado -> datos de la fuente api_tad (sin la fecha de captura, que no es contenido)."""
    tipo = registro["tipo_tramite"]
    reparticion = n.texto(tipo.get("reparticionIniciadoraEE")) or ""
    dependencia, _, organismo_gde = reparticion.rpartition("#")
    return n.a_json({
        "nombre": n.texto(tipo.get("nombre")),
        "descripcion_corta": n.texto(tipo.get("descripcionCorta")),
        "descripcion_html": registro.get("descripcion_html"),
        "reparticion_iniciadora": reparticion or None,
        "organismo_gde": organismo_gde or None,
        "dependencia_gde": dependencia or None,
        "etiquetas": etiquetas(tipo),
        "nivel_acceso_requerido": tipo.get("nivelAccesoRequerido"),
        "pago": tipo.get("pago"),
        "visible": tipo.get("visible"),
        "trata_ee": tipo.get("trataEE"),
        "id_tipo_tramite_sir": tipo.get("idTipoTramiteSir"),
        "fecha_alta": fecha_ms(tipo.get("fechaAlta")),
        "fecha_modificacion": fecha_ms(tipo.get("fechaModificacion")),
    })


def nombres_por_sigla(registros):
    """Sigla GDE -> nombre más frecuente en etiquetas del tipo "Nombre - SIGLA"."""
    nombres = defaultdict(Counter)
    for datos in registros.values():
        sigla = datos["organismo_gde"]
        for etiqueta in datos["etiquetas"]:
            m = ETIQUETA_CON_SIGLA.match(etiqueta)
            if sigla and m and m["sigla"] == sigla:
                nombres[sigla][m["nombre"]] += 1
    return {sigla: c.most_common(1)[0][0] for sigla, c in nombres.items()}


class ResolvedorOrganismos:
    """Sigla GDE (lo que sigue al '#' de la repartición) -> organismo.

    0. (En reparticion()) si la repartición completa "DNDA#MJ" tiene alias, gana.
    1. Si la sigla ya tiene alias, usa ese organismo (siguiendo sucesores).
    2. Si una etiqueta la nombra ("Nombre - SIGLA"), usa el organismo con ese
       nombre o lo crea, colgado del ministerio de ORGANO_RECTOR.
    3. Si no, devuelve None y el trámite queda en el ministerio de ORGANO_RECTOR.
       Son códigos de ministerios (MEC, MS) o de ministerios disueltos que GDE
       conserva (MPYT, MAD): el ministerio actual sale del CSV, no del código.
    """

    def __init__(self, cur, nacion_id, nombres, ministerios):
        self.cur = cur
        self.nacion_id = nacion_id
        self.nombres = nombres
        self.ministerios = ministerios  # sigla -> ministerio más frecuente según el CSV
        self.cache = {}
        self.nuevos = []
        self.sin_nombre = Counter()  # sigla -> trámites que quedaron en su ministerio

    def alias(self, texto):
        self.cur.execute(
            "SELECT organismo_actual(organismo_id) FROM organismo_alias WHERE alias_normalizado = normalizar_texto(%s)",
            (texto,),
        )
        fila = self.cur.fetchone()
        return fila[0] if fila else None

    def agregar_alias(self, texto, organismo_id, origen):
        self.cur.execute(
            """INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
               VALUES (normalizar_texto(%s), %s, %s, %s) ON CONFLICT (alias_normalizado) DO NOTHING""",
            (texto, texto, organismo_id, origen),
        )

    def reparticion(self, reparticion):
        """Alias de la repartición completa ("DNDA#MJ"): una dependencia mapeada a mano gana sobre la sigla."""
        if not reparticion or "#" not in reparticion:
            return None
        clave = ("reparticion", reparticion)
        if clave not in self.cache:
            self.cache[clave] = self.alias(reparticion)
        return self.cache[clave]

    def __call__(self, sigla):
        if sigla not in self.cache:
            self.cache[sigla] = self.resolver(sigla)
        if self.cache[sigla] is None:
            self.sin_nombre[sigla] += 1
        return self.cache[sigla]

    def resolver(self, sigla):
        organismo_id = self.alias(sigla)
        if organismo_id is not None:
            return organismo_id
        nombre = self.nombres.get(sigla)
        if nombre is None:
            return None
        organismo_id = self.alias(nombre)
        if organismo_id is None:
            self.cur.execute(
                """INSERT INTO organismo (jurisdiccion_id, nombre_oficial, sigla, padre_id)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (self.nacion_id, nombre, sigla, self.ministerios.get(sigla)),
            )
            organismo_id = self.cur.fetchone()[0]
            self.nuevos.append(f"{sigla}: {nombre}")
            self.agregar_alias(nombre, organismo_id, TIPO_FUENTE)
        self.agregar_alias(sigla, organismo_id, "gde")
        return organismo_id


def aplicar(cur, corrida_id, registros, resumen):
    cur.execute("SELECT id FROM jurisdiccion WHERE nivel = 'nacional'")
    nacion_id = cur.fetchone()[0]
    # Trámites TAD activos y el ministerio que les asigna ORGANO_RECTOR.
    cur.execute(
        """SELECT f.id_externo::integer, f.tramite_id, organismo_actual(a.organismo_id)
           FROM fuente f
           LEFT JOIN organismo_alias a ON a.alias_normalizado = normalizar_texto(f.datos ->> 'organo_rector')
           WHERE f.tipo = %s AND f.activo""",
        (FUENTE_CSV,),
    )
    activos = {fila[0]: fila[1:] for fila in cur.fetchall()}
    cur.execute("SELECT id_externo::integer, id, hash_contenido, datos FROM fuente WHERE tipo = %s", (TIPO_FUENTE,))
    previas = {fila[0]: fila[1:] for fila in cur.fetchall()}

    ministerios = defaultdict(Counter)
    for id_tad, datos in registros.items():
        if datos["organismo_gde"] and id_tad in activos:
            ministerios[datos["organismo_gde"]][activos[id_tad][1]] += 1
    resolver = ResolvedorOrganismos(
        cur, nacion_id, nombres_por_sigla(registros),
        {sigla: c.most_common(1)[0][0] for sigla, c in ministerios.items()},
    )

    for id_tad, datos in registros.items():
        if id_tad not in activos:
            resumen["fuera_del_csv"] += 1
            continue
        tramite_id, ministerio_id = activos[id_tad]
        hash_nuevo = n.hash_registro(datos)
        fuente_id, hash_anterior, anterior = previas.get(id_tad, (None, None, None))
        anterior = anterior or {}

        if fuente_id is None:
            cur.execute(
                """INSERT INTO fuente (tramite_id, tipo, id_externo, url, datos, hash_contenido, fecha_cambio)
                   VALUES (%s, %s, %s, %s, %s, %s, now()) RETURNING id""",
                (tramite_id, TIPO_FUENTE, str(id_tad), f"{API_URL}{id_tad}", Json(datos), hash_nuevo),
            )
            fuente_id, evento = cur.fetchone()[0], "alta"
        elif hash_anterior != hash_nuevo:
            cur.execute(
                """UPDATE fuente SET tramite_id = %s, datos = %s, hash_contenido = %s, fecha_captura = now(),
                          fecha_cambio = now(), activo = true WHERE id = %s""",
                (tramite_id, Json(datos), hash_nuevo, fuente_id),
            )
            evento = "cambio"
        else:
            cur.execute("UPDATE fuente SET fecha_captura = now() WHERE id = %s", (fuente_id,))
            evento = None

        if evento:
            diferencias = {k: [anterior.get(k), v] for k, v in datos.items() if anterior.get(k) != v}
            cur.execute(
                """INSERT INTO fuente_evento (corrida_id, fuente_id, evento, hash_anterior, hash_nuevo, diferencias)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (corrida_id, fuente_id, evento, hash_anterior, hash_nuevo,
                 Json(diferencias) if evento == "cambio" else None),
            )
            resumen[evento + "s"] += 1
        else:
            resumen["sin_cambios"] += 1

        # Se resuelve siempre (no solo ante cambios) para que un alias nuevo se aplique
        # en la próxima carga. La descripción se toma del detalle salvo edición manual.
        organismo_id = (resolver.reparticion(datos["reparticion_iniciadora"])
                        or (resolver(datos["organismo_gde"]) if datos["organismo_gde"] else None)
                        or ministerio_id)
        cur.execute(
            """UPDATE tramite
               SET organismo_id = %(organismo)s,
                   descripcion = CASE WHEN descripcion IS NULL OR descripcion = %(anterior)s
                                      THEN %(nueva)s ELSE descripcion END
               WHERE id = %(tramite)s
                 AND (organismo_id IS DISTINCT FROM %(organismo)s
                      OR ((descripcion IS NULL OR descripcion = %(anterior)s)
                          AND descripcion IS DISTINCT FROM %(nueva)s))""",
            {"organismo": organismo_id, "anterior": anterior.get("descripcion_corta"),
             "nueva": datos["descripcion_corta"], "tramite": tramite_id},
        )
        resumen["tramites_actualizados"] += cur.rowcount
    return resolver


def cargar(args):
    archivos = sorted(args.carpeta.glob("*.json"), key=lambda p: int(p.stem))
    registros = {int(p.stem): extraer(json.loads(p.read_text(encoding="utf-8"))) for p in archivos}
    log.info("%s detalles leídos de %s", len(registros), args.carpeta)

    resumen, nuevos, sin_nombre = Counter(), [], Counter()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingesta_corrida (fuente_tipo, archivos) VALUES (%s, %s) RETURNING id",
                (TIPO_FUENTE, Json([{"origen": str(args.carpeta), "archivos": len(archivos)}])),
            )
            corrida_id = cur.fetchone()[0]
        estado, error = "ok", None
        try:
            with conn, conn.cursor() as cur:
                resolver = aplicar(cur, corrida_id, registros, resumen)
                nuevos, sin_nombre = resolver.nuevos, resolver.sin_nombre
                if args.dry_run:
                    raise Simulacion
        except Simulacion:
            estado = "simulacion"
        except Exception as e:
            estado, error = "error", repr(e)
            raise
        finally:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """UPDATE ingesta_corrida SET finalizada_en = now(), estado = %s, filas_leidas = %s,
                              altas = %s, cambios = %s, sin_cambios = %s, advertencias = %s, error = %s
                       WHERE id = %s""",
                    (estado, len(registros), resumen["altas"], resumen["cambios"], resumen["sin_cambios"],
                     Json([f"organismo nuevo {o}" for o in nuevos]
                          + [f"sigla GDE sin nombre, queda en el ministerio del CSV: {s} ({k} trámites)"
                             for s, k in sin_nombre.most_common()]),
                     error, corrida_id),
                )
    finally:
        conn.close()

    print(f"\nCorrida {corrida_id}: {estado}")
    print(f"  detalles: {len(registros)} | altas {resumen['altas']} | cambios {resumen['cambios']} | "
          f"sin cambios {resumen['sin_cambios']} | fuera del CSV {resumen['fuera_del_csv']}")
    print(f"  trámites con organismo o descripción actualizados: {resumen['tramites_actualizados']}")
    print(f"  organismos nuevos: {len(nuevos)}")
    for o in nuevos:
        print(f"    - {o}")
    if sin_nombre:
        print("  siglas GDE sin nombre (quedan en el ministerio del CSV): "
              + ", ".join(f"{s} ({k})" for s, k in sin_nombre.most_common()))


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--carpeta", type=Path, default=CARPETA)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("descargar")
    p.add_argument("--refrescar", action="store_true", help="vuelve a bajar los que ya están")
    p.set_defaults(funcion=descargar)
    p = sub.add_parser("cargar")
    p.add_argument("--dry-run", action="store_true", help="aplica todo y hace rollback")
    p.set_defaults(funcion=cargar)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
