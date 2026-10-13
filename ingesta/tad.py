"""Ingesta del catálogo de Trámites a Distancia (TAD) desde datos.gob.ar (dataset JGM 26).

    python -m ingesta.tad                    descarga los CSV y actualiza la base
    python -m ingesta.tad --desde-dir DIR    usa CSV ya descargados (mismos nombres de archivo)
    python -m ingesta.tad --dry-run          corre todo y deshace los cambios en la base

Cada ID_TRAMITE de TAD es una fila de `fuente` (tipo csv_tad) vinculada a un
`tramite`. Una corrida registra altas, cambios (por hash del registro
normalizado), bajas y reapariciones en `fuente_evento`.
"""

import argparse
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import Json

from ingesta import normalizar as n

log = logging.getLogger("ingesta.tad")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://tramites:tramites@localhost:5433/tramites")
CATALOGO_URL = "https://monitoreo.datos.gob.ar/catalog/jgm/data.json"
DESCARGA_URL = "https://infra.datos.gob.ar/catalog/jgm/dataset/26/distribution/{id}/download/{archivo}"
USER_AGENT = "TramitesArg-ingesta/0.1 (+https://github.com/colossus-lab/tramites-arg)"
TIPO_FUENTE = "csv_tad"
CONCEPTO_COSTO = "arancel TAD"
ORGANISMO_NO_INFORMADO = "Organismo no informado en TAD"
# Si el CSV trae menos de esta fracción de los trámites activos, no se registran
# bajas: es más probable un archivo truncado que una baja masiva.
UMBRAL_BAJAS = 0.8


@dataclass(frozen=True)
class Distribucion:
    id: str
    clave: str
    archivo: str
    obligatoria: bool = False


DISTRIBUCIONES = (
    Distribucion("26.1", "total", "lista-tramites-vigentes-total.csv", obligatoria=True),
    Distribucion("26.2", "arancelados", "lista-tramites-vigentes-arancelados.csv"),
    # Los nombres de archivo de 26.3 a 26.5 no están confirmados: primero se
    # resuelven por data.json y estos quedan como respaldo.
    Distribucion("26.3", "no_arancelados", "lista-tramites-vigentes-no-arancelados.csv"),
    Distribucion("26.4", "vuce", "lista-tramites-vigentes-vuce.csv"),
    Distribucion("26.5", "mi_argentina", "lista-tramites-vigentes-mi-argentina.csv"),
)

# Campos del registro que aporta cada distribución opcional. Si una no se pudo
# obtener, sus campos se arrastran de la corrida anterior para no inventar cambios.
CAMPOS_POR_DISTRIBUCION = {
    "arancelados": ("pago_minimo", "pago_maximo", "pago_promedio"),
    "vuce": ("en_vuce",),
    "mi_argentina": ("en_mi_argentina",),
}


@dataclass
class Archivo:
    distribucion: Distribucion
    contenido: bytes
    origen: str
    filas: int = 0

    def resumen(self):
        return {
            "distribucion": self.distribucion.id,
            "origen": self.origen,
            "sha256": hashlib.sha256(self.contenido).hexdigest(),
            "bytes": len(self.contenido),
            "filas": self.filas,
        }


@dataclass
class Resumen:
    filas_leidas: int = 0
    altas: int = 0
    cambios: int = 0
    bajas: int = 0
    reapariciones: int = 0
    sin_cambios: int = 0
    max_fecha_publicacion: object = None
    organismos_nuevos: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)

    def advertir(self, mensaje):
        log.warning(mensaje)
        self.advertencias.append(mensaje)


class Simulacion(Exception):
    """Corta la transacción en --dry-run para que se deshaga."""


# Obtención de archivos ------------------------------------------------------

def urls_desde_catalogo(sesion, resumen):
    try:
        r = sesion.get(CATALOGO_URL, timeout=30)
        r.raise_for_status()
        catalogo = r.json()
    except (requests.RequestException, ValueError) as e:
        resumen.advertir(f"No se pudo leer el catálogo {CATALOGO_URL} ({e}); se usan las URLs conocidas")
        return {}
    ids = {d.id for d in DISTRIBUCIONES}
    urls = {}
    for dataset in catalogo.get("dataset", []):
        for distribucion in dataset.get("distribution", []):
            if distribucion.get("identifier") in ids and distribucion.get("downloadURL"):
                urls[distribucion["identifier"]] = distribucion["downloadURL"]
    return urls


def bajar(sesion, url, intentos=3):
    for intento in range(1, intentos + 1):
        try:
            r = sesion.get(url, timeout=120)
            r.raise_for_status()
            if r.content.lstrip()[:1] == b"<":
                raise requests.RequestException("la respuesta es HTML, no CSV")
            return r.content
        except requests.HTTPError:
            raise
        except requests.RequestException:
            if intento == intentos:
                raise
            time.sleep(2 ** intento)


def descargar(destino, resumen):
    sesion = requests.Session()
    sesion.headers["User-Agent"] = USER_AGENT
    urls = urls_desde_catalogo(sesion, resumen)
    carpeta = destino / datetime.now().strftime("%Y%m%d-%H%M%S")
    archivos = {}
    for d in DISTRIBUCIONES:
        url = urls.get(d.id) or DESCARGA_URL.format(id=d.id, archivo=d.archivo)
        try:
            contenido = bajar(sesion, url)
        except requests.RequestException as e:
            if d.obligatoria:
                raise SystemExit(f"No se pudo descargar la distribución {d.id} ({url}): {e}")
            resumen.advertir(f"No se pudo descargar la distribución {d.id} ({url}): {e}")
            continue
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / d.archivo).write_bytes(contenido)
        archivos[d.clave] = Archivo(d, contenido, url)
        log.info("%s: %s bytes desde %s", d.id, len(contenido), url)
    log.info("CSV guardados en %s", carpeta)
    return archivos


def leer_directorio(carpeta, resumen):
    archivos = {}
    for d in DISTRIBUCIONES:
        ruta = carpeta / d.archivo
        if not ruta.exists():
            if d.obligatoria:
                raise SystemExit(f"Falta {ruta}")
            resumen.advertir(f"Falta {ruta}; se omite la distribución {d.id}")
            continue
        archivos[d.clave] = Archivo(d, ruta.read_bytes(), str(ruta))
    return archivos


# Combinación de distribuciones ---------------------------------------------

def combinar(archivos, resumen):
    """Une las cinco distribuciones en un registro por ID_TRAMITE."""
    registros = {}
    for d in DISTRIBUCIONES:
        archivo = archivos.get(d.clave)
        if archivo is None:
            continue
        columnas, filas = n.leer_csv(archivo.contenido)
        archivo.filas = len(filas)
        if "ID_TRAMITE" not in columnas or (d.obligatoria and "NOMBRE_TRAMITE" not in columnas):
            mensaje = f"{d.id}: faltan columnas obligatorias. Columnas encontradas: {columnas}"
            if d.obligatoria:
                raise SystemExit(mensaje)
            resumen.advertir(mensaje + "; se ignora el archivo")
            continue

        for fila in filas:
            registro, advertencias = n.normalizar_fila(fila)
            for a in advertencias:
                resumen.advertir(f"{d.id}: {a}")
            if registro is None:
                continue
            id_tramite = registro["id_tramite"]

            if d.clave == "total":
                if id_tramite in registros:
                    resumen.advertir(f"{d.id}: ID {id_tramite} duplicado; se conserva la primera fila")
                    continue
                registros[id_tramite] = {**registro, "en_vuce": None, "en_mi_argentina": None}
                continue

            base = registros.get(id_tramite)
            if base is None:
                resumen.advertir(f"{d.id}: el ID {id_tramite} no figura en 26.1; se agrega igual")
                base = registros[id_tramite] = {**registro, "en_vuce": None, "en_mi_argentina": None}
            for campo in ("nombre", "organo_rector", "fecha_publicacion", "link"):
                if base[campo] is None:
                    base[campo] = registro[campo]
            if not base["validadores"]:
                base["validadores"] = registro["validadores"]

            if d.clave == "arancelados":
                for campo in CAMPOS_POR_DISTRIBUCION["arancelados"]:
                    base[campo] = registro[campo]
                if base["arancelado"] is None:
                    base["arancelado"] = True
            elif d.clave == "no_arancelados":
                if base["arancelado"] is None:
                    base["arancelado"] = False
            elif d.clave == "vuce":
                base["en_vuce"] = True
            elif d.clave == "mi_argentina":
                base["en_mi_argentina"] = True

    for clave, campo in (("vuce", "en_vuce"), ("mi_argentina", "en_mi_argentina")):
        if clave in archivos:
            for registro in registros.values():
                if registro[campo] is None:
                    registro[campo] = False
    return registros


# Escritura en la base -------------------------------------------------------

def decimal_o_none(v):
    return None if v is None else Decimal(v)


class Contexto:
    def __init__(self, cur, corrida_id, resumen):
        self.cur = cur
        self.corrida_id = corrida_id
        self.resumen = resumen
        self._organismos = {}
        self._validadores_desconocidos = set()
        cur.execute("SELECT id FROM jurisdiccion WHERE nivel = 'nacional'")
        self.nacion_id = cur.fetchone()[0]
        cur.execute("SELECT codigo, id FROM plataforma WHERE jurisdiccion_id = %s", (self.nacion_id,))
        self.plataformas = dict(cur.fetchall())

    def organismo(self, nombre):
        """ORGANO_RECTOR -> id del organismo vigente. Si no hay alias, crea un organismo a revisar."""
        if not nombre or not n.clave(nombre):
            nombre = ORGANISMO_NO_INFORMADO
        if nombre in self._organismos:
            return self._organismos[nombre]
        self.cur.execute(
            "SELECT organismo_actual(organismo_id) FROM organismo_alias WHERE alias_normalizado = normalizar_texto(%s)",
            (nombre,),
        )
        fila = self.cur.fetchone()
        if fila:
            organismo_id = fila[0]
        else:
            self.cur.execute(
                "INSERT INTO organismo (jurisdiccion_id, nombre_oficial, revisar) VALUES (%s, %s, true) RETURNING id",
                (self.nacion_id, nombre),
            )
            organismo_id = self.cur.fetchone()[0]
            self.cur.execute(
                """INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
                   VALUES (normalizar_texto(%s), %s, %s, %s)""",
                (nombre, nombre, organismo_id, TIPO_FUENTE),
            )
            self.resumen.organismos_nuevos.append(nombre)
        self._organismos[nombre] = organismo_id
        return organismo_id

    def evento(self, fuente_id, evento, hash_anterior=None, hash_nuevo=None, diferencias=None):
        self.cur.execute(
            """INSERT INTO fuente_evento (corrida_id, fuente_id, evento, hash_anterior, hash_nuevo, diferencias)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (self.corrida_id, fuente_id, evento, hash_anterior, hash_nuevo,
             Json(diferencias) if diferencias else None),
        )

    def crear_tramite(self, id_tad, datos):
        nombre = datos["nombre"] or f"Trámite TAD {id_tad}"
        self.cur.execute(
            """INSERT INTO tramite (slug, nombre_ciudadano, nombre_oficial, organismo_id, fecha_ultima_verificacion)
               VALUES (%s, %s, %s, %s, current_date) RETURNING id""",
            (f"{n.slugify(nombre)}-tad-{id_tad}", nombre, datos["nombre"], self.organismo(datos["organo_rector"])),
        )
        return self.cur.fetchone()[0]

    def sincronizar(self, fuente_id, tramite_id, datos):
        self.sincronizar_canales(fuente_id, tramite_id, datos)
        self.sincronizar_costo(fuente_id, tramite_id, datos)

    def sincronizar_canales(self, fuente_id, tramite_id, datos):
        # None = la distribución que lo informa nunca se obtuvo: no se toca el canal.
        presencia = {"tad": True, "vuce": datos.get("en_vuce"), "mi_argentina": datos.get("en_mi_argentina")}
        for codigo, presente in presencia.items():
            if presente is None:
                continue
            plataforma_id = self.plataformas[codigo]
            if not presente:
                self.cur.execute(
                    "UPDATE canal SET activo = false WHERE fuente_id = %s AND plataforma_id = %s",
                    (fuente_id, plataforma_id),
                )
                continue
            self.cur.execute(
                """INSERT INTO canal (tramite_id, modalidad, plataforma_id, url_inicio, fuente_id)
                   VALUES (%s, 'online', %s, %s, %s)
                   ON CONFLICT (fuente_id, plataforma_id) WHERE fuente_id IS NOT NULL
                   DO UPDATE SET tramite_id = EXCLUDED.tramite_id, url_inicio = EXCLUDED.url_inicio, activo = true
                   RETURNING id""",
                (tramite_id, plataforma_id, datos["link"], fuente_id),
            )
            canal_id = self.cur.fetchone()[0]
            if codigo == "tad":
                self.sincronizar_autenticacion(canal_id, datos["validadores"])

    def sincronizar_autenticacion(self, canal_id, validadores):
        por_metodo = {}
        for original in validadores:
            for metodo in n.metodos(original):
                if metodo == "otro" and original not in self._validadores_desconocidos:
                    self._validadores_desconocidos.add(original)
                    self.resumen.advertir(f"Validador de identidad desconocido: {original!r} (se guarda como 'otro')")
                por_metodo.setdefault(metodo, []).append(original)
        self.cur.execute("DELETE FROM canal_autenticacion WHERE canal_id = %s", (canal_id,))
        for metodo, originales in por_metodo.items():
            self.cur.execute(
                "INSERT INTO canal_autenticacion (canal_id, metodo, detalle) VALUES (%s, %s, %s)",
                (canal_id, metodo, ", ".join(originales)),
            )

    def sincronizar_costo(self, fuente_id, tramite_id, datos):
        if datos.get("arancelado") is None:
            return
        if datos["arancelado"]:
            minimo, maximo, promedio = (decimal_o_none(datos.get(c)) for c in CAMPOS_POR_DISTRIBUCION["arancelados"])
            if minimo is not None and maximo is not None and minimo > maximo:
                self.resumen.advertir(
                    f"ID {datos['id_tramite']}: PAGO_MINIMO {minimo} > PAGO_MAXIMO {maximo}; se invierten"
                )
                minimo, maximo = maximo, minimo
            deseado = (False, minimo, maximo, promedio)
        else:
            deseado = (True, None, None, None)

        self.cur.execute(
            """SELECT id, gratuito, monto_min, monto_max, monto_promedio FROM costo
               WHERE fuente_id = %s AND concepto = %s AND vigente_hasta IS NULL""",
            (fuente_id, CONCEPTO_COSTO),
        )
        actual = self.cur.fetchone()
        if actual and tuple(actual[1:]) == deseado:
            return
        if actual:
            self.cur.execute("UPDATE costo SET vigente_hasta = current_date WHERE id = %s", (actual[0],))
        self.cur.execute(
            """INSERT INTO costo (tramite_id, concepto, gratuito, monto_min, monto_max, monto_promedio, fuente_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (tramite_id, CONCEPTO_COSTO, *deseado, fuente_id),
        )


@dataclass
class FuentePrevia:
    id: int
    tramite_id: object
    hash_contenido: str
    activo: bool
    datos: dict


def diferencias(antes, despues):
    claves = sorted(set(antes) | set(despues))
    return {k: [antes.get(k), despues.get(k)] for k in claves if antes.get(k) != despues.get(k)}


def aplicar(cur, corrida_id, registros, disponibles, forzar_bajas, resumen):
    ctx = Contexto(cur, corrida_id, resumen)
    cur.execute(
        "SELECT id_externo, id, tramite_id, hash_contenido, activo, datos FROM fuente WHERE tipo = %s",
        (TIPO_FUENTE,),
    )
    previas = {fila[0]: FuentePrevia(*fila[1:]) for fila in cur.fetchall()}
    sin_cambios = []

    for id_tad, registro in sorted(registros.items()):
        previa = previas.get(str(id_tad))
        datos = dict(registro)
        if previa:
            for clave, campos in CAMPOS_POR_DISTRIBUCION.items():
                if clave not in disponibles:
                    for campo in campos:
                        datos[campo] = previa.datos.get(campo)
        datos = n.a_json(datos)
        hash_nuevo = n.hash_registro(datos)

        if previa is None:
            tramite_id = ctx.crear_tramite(id_tad, datos)
            cur.execute(
                """INSERT INTO fuente (tramite_id, tipo, id_externo, url, datos, hash_contenido, fecha_cambio)
                   VALUES (%s, %s, %s, %s, %s, %s, now()) RETURNING id""",
                (tramite_id, TIPO_FUENTE, str(id_tad), datos["link"], Json(datos), hash_nuevo),
            )
            fuente_id = cur.fetchone()[0]
            ctx.evento(fuente_id, "alta", hash_nuevo=hash_nuevo)
            ctx.sincronizar(fuente_id, tramite_id, datos)
            resumen.altas += 1
            continue

        if previa.activo and previa.hash_contenido == hash_nuevo:
            sin_cambios.append(previa.id)
            continue

        evento = "cambio" if previa.activo else "reaparicion"
        tramite_id = previa.tramite_id or ctx.crear_tramite(id_tad, datos)
        cur.execute(
            """UPDATE fuente SET tramite_id = %s, url = %s, datos = %s, hash_contenido = %s, activo = true,
                      fecha_captura = now(),
                      fecha_cambio = CASE WHEN hash_contenido IS DISTINCT FROM %s THEN now() ELSE fecha_cambio END
               WHERE id = %s""",
            (tramite_id, datos["link"], Json(datos), hash_nuevo, hash_nuevo, previa.id),
        )
        # El CSV manda sobre nombre oficial y organismo sólo si el trámite no se
        # consolidó con otros trámites TAD; si se consolidó, el cambio queda en el
        # evento. El organismo del detalle (api_tad) es más específico que el
        # ministerio de ORGANO_RECTOR, así que si existe no se pisa.
        cur.execute(
            """UPDATE tramite t
               SET nombre_oficial = %s,
                   organismo_id = CASE WHEN EXISTS (SELECT 1 FROM fuente f WHERE f.tramite_id = t.id
                                                    AND f.tipo = 'api_tad' AND f.activo)
                                       THEN t.organismo_id ELSE %s END
               WHERE t.id = %s
                 AND NOT EXISTS (SELECT 1 FROM fuente f WHERE f.tramite_id = t.id AND f.id <> %s
                                 AND f.tipo = %s AND f.activo)""",
            (datos["nombre"], ctx.organismo(datos["organo_rector"]), tramite_id, previa.id, TIPO_FUENTE),
        )
        cur.execute(
            """UPDATE tramite SET fecha_ultima_verificacion = current_date,
                      estado = CASE WHEN estado = 'baja' THEN 'vigente' ELSE estado END
               WHERE id = %s""",
            (tramite_id,),
        )
        ctx.evento(previa.id, evento, previa.hash_contenido, hash_nuevo, diferencias(previa.datos or {}, datos))
        ctx.sincronizar(previa.id, tramite_id, datos)
        if evento == "cambio":
            resumen.cambios += 1
        else:
            resumen.reapariciones += 1

    if sin_cambios:
        cur.execute("UPDATE fuente SET fecha_captura = now() WHERE id = ANY(%s)", (sin_cambios,))
        cur.execute(
            """UPDATE tramite SET fecha_ultima_verificacion = current_date
               WHERE id IN (SELECT tramite_id FROM fuente WHERE id = ANY(%s))""",
            (sin_cambios,),
        )
    resumen.sin_cambios = len(sin_cambios)

    activas = [(id_externo, p) for id_externo, p in previas.items() if p.activo]
    no_vistas = [p for id_externo, p in activas if int(id_externo) not in registros]
    if not no_vistas:
        return
    if len(registros) < UMBRAL_BAJAS * len(activas) and not forzar_bajas:
        resumen.advertir(
            f"El CSV trae {len(registros)} trámites contra {len(activas)} activos en la base: "
            f"no se registran {len(no_vistas)} bajas. Si son reales, correr con --forzar-bajas."
        )
        return
    for previa in no_vistas:
        cur.execute("UPDATE fuente SET activo = false WHERE id = %s", (previa.id,))
        cur.execute("UPDATE canal SET activo = false WHERE fuente_id = %s", (previa.id,))
        cur.execute(
            """UPDATE tramite t SET estado = 'baja'
               WHERE t.id = %s AND t.estado = 'vigente'
                 AND NOT EXISTS (SELECT 1 FROM fuente f WHERE f.tramite_id = t.id AND f.id <> %s
                                 AND f.tipo = %s AND f.activo)""",
            (previa.tramite_id, previa.id, TIPO_FUENTE),
        )
        ctx.evento(previa.id, "baja", hash_anterior=previa.hash_contenido)
        resumen.bajas += 1


def cerrar_corrida(conn, corrida_id, estado, resumen, error=None):
    with conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE ingesta_corrida SET finalizada_en = now(), estado = %s, filas_leidas = %s, altas = %s,
                      cambios = %s, bajas = %s, reapariciones = %s, sin_cambios = %s,
                      max_fecha_publicacion = %s, advertencias = %s, error = %s
               WHERE id = %s""",
            (estado, resumen.filas_leidas, resumen.altas, resumen.cambios, resumen.bajas, resumen.reapariciones,
             resumen.sin_cambios, resumen.max_fecha_publicacion, Json(resumen.advertencias[:500]), error,
             corrida_id),
        )


def ejecutar(archivos, database_url=DATABASE_URL, dry_run=False, forzar_bajas=False, resumen=None):
    """Combina los archivos y los aplica a la base. Devuelve (id de corrida, estado, resumen)."""
    resumen = resumen or Resumen()
    registros = combinar(archivos, resumen)
    resumen.filas_leidas = len(registros)
    fechas = [r["fecha_publicacion"] for r in registros.values() if r["fecha_publicacion"]]
    resumen.max_fecha_publicacion = max(fechas, default=None)

    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingesta_corrida (fuente_tipo, archivos) VALUES (%s, %s) RETURNING id",
                (TIPO_FUENTE, Json([a.resumen() for a in archivos.values()])),
            )
            corrida_id = cur.fetchone()[0]
        try:
            with conn, conn.cursor() as cur:
                aplicar(cur, corrida_id, registros, set(archivos), forzar_bajas, resumen)
                if dry_run:
                    raise Simulacion
            estado = "ok"
        except Simulacion:
            estado = "simulacion"
        except Exception as e:
            cerrar_corrida(conn, corrida_id, "error", resumen, error=repr(e))
            raise
        cerrar_corrida(conn, corrida_id, estado, resumen)
    finally:
        conn.close()
    return corrida_id, estado, resumen


def imprimir(corrida_id, estado, resumen):
    print(f"\nCorrida {corrida_id}: {estado}")
    print(f"  trámites leídos: {resumen.filas_leidas}  (máx. FECHA_PUBLICACION_PROD: {resumen.max_fecha_publicacion})")
    print(f"  altas {resumen.altas} | cambios {resumen.cambios} | bajas {resumen.bajas} | "
          f"reapariciones {resumen.reapariciones} | sin cambios {resumen.sin_cambios}")
    if resumen.organismos_nuevos:
        print(f"  organismos nuevos a revisar: {len(resumen.organismos_nuevos)} (ver v_organismo_a_revisar)")
    if resumen.advertencias:
        print(f"  advertencias: {len(resumen.advertencias)}")
        for a in resumen.advertencias[:10]:
            print(f"    - {a}")
        if len(resumen.advertencias) > 10:
            print(f"    ... (todas en ingesta_corrida.advertencias)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde-dir", type=Path, help="carpeta con los CSV ya descargados")
    parser.add_argument("--guardar-en", type=Path, default=Path("data/raw/tad"),
                        help="dónde guardar los CSV descargados (default: data/raw/tad)")
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="aplica todo y hace rollback")
    parser.add_argument("--forzar-bajas", action="store_true",
                        help=f"registra bajas aunque el CSV traiga menos del {UMBRAL_BAJAS * 100:.0f}%% de los activos")
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    resumen = Resumen()
    if args.desde_dir:
        archivos = leer_directorio(args.desde_dir, resumen)
    else:
        archivos = descargar(args.guardar_en, resumen)
    corrida_id, estado, resumen = ejecutar(archivos, args.database_url, args.dry_run, args.forzar_bajas, resumen)
    imprimir(corrida_id, estado, resumen)


if __name__ == "__main__":
    sys.exit(main())
