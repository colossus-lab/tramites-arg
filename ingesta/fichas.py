"""Fichas de trámites de argentina.gob.ar (/servicio/<slug>).

    python -m ingesta.fichas descargar           lista las fichas del sitemap y baja las que faltan
    python -m ingesta.fichas descargar --refrescar
    python -m ingesta.fichas cargar [--dry-run]  parsea las fichas y las vuelca a la base

robots.txt de argentina.gob.ar permite /servicio/ (bloquea /tramitar, /servicios y /buscar)
y pide Crawl-delay: 10, así que hay una pausa de 10 s entre pedidos. La descarga guarda
el HTML crudo en data/raw/fichas/<slug>.html y es reanudable.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import requests
from bs4 import BeautifulSoup
from psycopg2.extras import Json

from ingesta import extraer_html
from ingesta import normalizar as n
from ingesta.tad import DATABASE_URL, USER_AGENT, TIPO_FUENTE as FUENTE_CSV
from ingesta.tad_requisitos import sincronizar_costos, sincronizar_requisitos

log = logging.getLogger("ingesta.fichas")

TIPO_FUENTE = "ficha_argentina_gob_ar"
CONCEPTO_COSTO = "arancel (ficha argentina.gob.ar)"
VINCULOS = Path(__file__).resolve().parent.parent / "db" / "semillas" / "fichas_vinculos.json"
CANDIDATOS = Path("data/fichas_candidatos.json")
SIMILITUD_AUTOMATICA = 0.75  # desde acá se vincula sin revisión
SIMILITUD_CANDIDATA = 0.45   # entre esta y la automática, va a revisión manual

SECCIONES = {
    "A QUIEN ESTA DIRIGIDO": "dirigido", "QUE NECESITO": "necesito", "COMO HAGO": "como",
    "CUAL ES EL COSTO": "costo", "CUANTO TIEMPO LLEVA": "tiempo", "VIGENCIA": "vigencia",
    "INFORMACION COMPLEMENTARIA": "complementaria",
}
ID_TAD = re.compile(r"(?:configuracionInicioTipoTramite/|detalle-tipo\?id=|idTipoTramite=)(\d+)")
REDES = ("facebook.com", "x.com", "twitter.com", "linkedin.com", "whatsapp.com", "t.me", "instagram.com",
         "youtube.com", "goo.gl")
PLATAFORMA_POR_HOST = [
    ("mi.argentina.gob.ar", "mi_argentina"), ("tramitesadistancia.gob.ar", "tad"), ("afip.gob.ar", "arca"),
    ("arca.gob.ar", "arca"), ("anses.gob.ar", "mi_anses"), ("migraciones.gob.ar", "radex"),
    ("dnrpa.gov.ar", "site_dnrpa"),
]
PRESENCIAL = re.compile(r"\bTURNO|PRESENCIAL|ACERCATE|DIRIGITE|PERSONALMENTE|EN LA OFICINA|EN LAS OFICINAS|SEDE")
# Migas que nombran un organismo (las demás son temas: "Minería", "Pequeña y Mediana Empresa").
MIGA_ORGANISMO = re.compile(
    r"^(MINISTERIO|SECRETARIA|SUBSECRETARIA|INSTITUTO|AGENCIA|DIRECCION|REGISTRO|ADMINISTRACION|COMISION|ENTE|"
    r"SERVICIO|SUPERINTENDENCIA|BIBLIOTECA|CONSEJO|OFICINA|TRIBUNAL|BANCO|AUTORIDAD|JEFATURA|PRESIDENCIA|"
    r"INSPECCION|CAJA|PREFECTURA|GENDARMERIA|POLICIA|ARMADA|EJERCITO|FUERZA AEREA|HOSPITAL|TEATRO|MUSEO|FONDO|"
    r"CORREO|ARCHIVO|DEFENSORIA|PROCURACION|SINDICATURA|CASA DE MONEDA|ORGANISMO)\b"
)

SITEMAP_URL = "https://www.argentina.gob.ar/sitemap.xml"
PREFIJO_FICHA = "https://www.argentina.gob.ar/servicio/"
CARPETA = Path("data/raw/fichas")
PAUSA = 10  # Crawl-delay de robots.txt
MAX_ERRORES_SEGUIDOS = 10


class Cliente:
    """Sesión HTTP que respeta la pausa entre pedidos y los 429 con Retry-After."""

    def __init__(self):
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = USER_AGENT
        self.ultimo = 0.0

    def get(self, url, intentos=3):
        for intento in range(1, intentos + 1):
            espera = PAUSA - (time.monotonic() - self.ultimo)
            if espera > 0:
                time.sleep(espera)
            self.ultimo = time.monotonic()
            try:
                r = self.sesion.get(url, timeout=60)
                if r.status_code == 429:
                    pausa = int(r.headers.get("Retry-After", "60") or 60)
                    log.warning("429 en %s; espero %s s", url, pausa)
                    time.sleep(pausa)
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.text
            except requests.RequestException:
                if intento == intentos:
                    raise
                time.sleep(15 * intento)
        raise requests.RequestException(f"sin respuesta útil de {url}")


def slug(url):
    return url[len(PREFIJO_FICHA):].strip("/").split("?")[0]


def urls_del_sitemap(cliente):
    indice = cliente.get(SITEMAP_URL)
    paginas = re.findall(r"<loc>([^<]+)</loc>", indice or "")
    urls = {}
    for pagina in paginas:
        contenido = cliente.get(pagina.replace("&amp;", "&")) or ""
        for loc, lastmod in re.findall(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", contenido):
            if loc.startswith(PREFIJO_FICHA) and slug(loc) and "/" not in slug(loc):
                urls[slug(loc)] = {"url": loc, "lastmod": lastmod or None}
        log.info("%s: %s fichas acumuladas", pagina, len(urls))
    return urls


def descargar(args):
    args.carpeta.mkdir(parents=True, exist_ok=True)
    cliente = Cliente()
    indice_path = args.carpeta / "_indice.json"
    if indice_path.exists() and not args.refrescar_indice:
        indice = json.loads(indice_path.read_text(encoding="utf-8"))
    else:
        indice = urls_del_sitemap(cliente)
        indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    pendientes = [s for s in sorted(indice) if args.refrescar or not (args.carpeta / f"{s}.html").exists()]
    horas = len(pendientes) * PAUSA / 3600
    log.info("%s fichas en el sitemap, %s por descargar (~%.1f h)", len(indice), len(pendientes), horas)

    errores_seguidos, faltantes = 0, []
    for i, s in enumerate(pendientes, 1):
        try:
            html = cliente.get(indice[s]["url"])
        except requests.RequestException as e:
            errores_seguidos += 1
            log.warning("%s: %s", s, e)
            if errores_seguidos >= MAX_ERRORES_SEGUIDOS:
                raise SystemExit(f"{errores_seguidos} errores seguidos; se corta la descarga (reanudable)")
            continue
        errores_seguidos = 0
        if html is None:
            faltantes.append(s)
            continue
        destino = args.carpeta / f"{s}.html"
        temporal = destino.with_suffix(".tmp")
        temporal.write_text(html, encoding="utf-8")
        temporal.replace(destino)
        if i % 50 == 0 or i == len(pendientes):
            log.info("%s/%s", i, len(pendientes))
    if faltantes:
        log.warning("%s fichas del sitemap devuelven 404: %s", len(faltantes), faltantes[:10])
    (args.carpeta / "_descarga.json").write_text(json.dumps(
        {"finalizada": datetime.now(timezone.utc).isoformat(timespec="seconds"), "404": faltantes},
        ensure_ascii=False), encoding="utf-8")


# Parseo --------------------------------------------------------------------

def parsear(html):
    """HTML de una ficha -> dict con nombre, migas, secciones (HTML), IDs de TAD y links de inicio."""
    sopa = BeautifulSoup(html, "html.parser")
    main = sopa.find("main") or sopa
    h1 = main.find("h1")
    nombre = n.texto(h1.get_text(" ")) if h1 else None

    migas_el = sopa.select_one("ol.breadcrumb") or sopa.find(class_="breadcrumb")
    migas = [n.texto(li.get_text(" ")) for li in migas_el.find_all("li")] if migas_el else []
    migas = [m for m in migas if m and m != "Inicio"]
    if migas and nombre and n.clave(migas[-1]) == n.clave(nombre):
        migas = migas[:-1]

    def meta(**attrs):
        m = sopa.find("meta", attrs=attrs)
        return n.texto(m.get("content")) if m else None

    secciones = {}
    for h2 in main.find_all("h2"):
        clave = SECCIONES.get(n.clave(h2.get_text(" ")))
        if not clave or clave in secciones:
            continue
        contenido = "".join(str(x) for x in h2.find_next_siblings())
        if contenido.strip():
            secciones[clave] = contenido

    inicio = []
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        host = urlparse(href).netloc.lower()
        if (href.startswith("http") and not any(r in host for r in REDES) and "argentina.gob.ar" != host.removeprefix("www.")
                and n.clave(a.get_text(" ")) in ("INICIAR TRAMITE", "CONSULTAR EN LINEA", "INGRESAR", "SOLICITAR TURNO")):
            if href not in inicio:
                inicio.append(href)

    actualizado = meta(property="og:updated_time")
    return {
        "nombre": nombre,
        "descripcion": meta(name="description"),
        "actualizado": actualizado[:10] if actualizado else None,
        "migas": migas,
        "ids_tad": sorted({int(i) for i in ID_TAD.findall(html)}),
        "inicio": inicio,
        "secciones": secciones,
        "dirigido": n.texto(BeautifulSoup(secciones.get("dirigido", ""), "html.parser").get_text(" ")),
    }


def canales(datos):
    """Canales que se deducen de la ficha (el canal TAD ya lo aporta la ingesta del CSV)."""
    resultado, plataformas = [], set()
    for url in datos["inicio"]:
        host = urlparse(url).netloc.lower()
        plataforma = next((p for h, p in PLATAFORMA_POR_HOST if h in host), None)
        if plataforma == "tad" or (plataforma and plataforma in plataformas):
            continue  # un canal por plataforma (el primer botón de inicio)
        plataformas.add(plataforma)
        resultado.append({"modalidad": "online", "plataforma": plataforma, "url": url})
    texto = n.clave(" ".join(BeautifulSoup(datos["secciones"].get(s, ""), "html.parser").get_text(" ")
                             for s in ("como", "necesito")))
    if PRESENCIAL.search(texto):
        resultado.append({"modalidad": "presencial", "requiere_turno": "TURNO" in texto})
    return resultado


def requisitos_y_costos(datos):
    necesito = datos["secciones"].get("necesito")
    requisitos = extraer_html.requisitos("<p><strong>Requisitos</strong></p>" + necesito) if necesito else []
    costo = datos["secciones"].get("costo")
    costos = extraer_html.costos("<p><strong>¿Cuál es el costo?</strong></p>" + costo) if costo else []
    return requisitos, costos


# Carga ---------------------------------------------------------------------

class Organismos:
    """Migas de navegación -> organismo. Crea el organismo más específico si no existe."""

    def __init__(self, cur):
        self.cur = cur
        cur.execute("SELECT id FROM jurisdiccion WHERE nivel = 'nacional'")
        self.nacion_id = cur.fetchone()[0]
        self.cache, self.nuevos = {}, []

    def alias(self, texto):
        candidatos = [texto]
        sigla = re.search(r"\(([A-Za-z0-9+]{2,12})\)\s*$", texto)
        if sigla:
            candidatos += [sigla.group(1), texto[: sigla.start()].strip()]
        for c in candidatos:
            self.cur.execute(
                "SELECT organismo_actual(organismo_id) FROM organismo_alias WHERE alias_normalizado = normalizar_texto(%s)",
                (c,),
            )
            fila = self.cur.fetchone()
            if fila:
                return fila[0]
        return None

    def no_informado(self):
        nombre = "Organismo no informado en argentina.gob.ar"
        organismo_id = self.alias(nombre)
        if organismo_id is None:
            self.cur.execute("INSERT INTO organismo (jurisdiccion_id, nombre_oficial, revisar) VALUES (%s, %s, true) "
                             "RETURNING id", (self.nacion_id, nombre))
            organismo_id = self.cur.fetchone()[0]
            self.cur.execute("INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen) "
                             "VALUES (normalizar_texto(%s), %s, %s, %s)", (nombre, nombre, organismo_id, TIPO_FUENTE))
        return organismo_id

    def __call__(self, migas):
        clave = tuple(migas)
        if clave in self.cache:
            return self.cache[clave]
        resueltos = [(m, self.alias(m)) for m in migas]
        especifica = next((i for i in range(len(migas) - 1, -1, -1) if MIGA_ORGANISMO.match(n.clave(migas[i]))), None)
        organismo_id = None
        if especifica is not None and resueltos[especifica][1]:
            organismo_id = resueltos[especifica][1]
        elif especifica is not None:
            padre = next((r for _, r in reversed(resueltos[:especifica]) if r), None)
            nombre = migas[especifica]
            sigla = re.search(r"\(([A-Za-z0-9+]{2,12})\)\s*$", nombre)
            self.cur.execute(
                """INSERT INTO organismo (jurisdiccion_id, nombre_oficial, sigla, padre_id, revisar)
                   VALUES (%s, %s, %s, %s, true) RETURNING id""",
                (self.nacion_id, nombre[: sigla.start()].strip() if sigla else nombre,
                 sigla.group(1) if sigla else None, padre),
            )
            organismo_id = self.cur.fetchone()[0]
            for texto in filter(None, [nombre, sigla.group(1) if sigla else None]):
                self.cur.execute(
                    """INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
                       VALUES (normalizar_texto(%s), %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (texto, texto, organismo_id, TIPO_FUENTE),
                )
            self.nuevos.append(" > ".join(migas[: especifica + 1]))
        else:
            organismo_id = next((r for _, r in reversed(resueltos) if r), None)
        self.cache[clave] = organismo_id
        return organismo_id


def cargar_vinculos():
    if not VINCULOS.exists():
        return {}
    return json.loads(VINCULOS.read_text(encoding="utf-8"))["vinculos"]


class Cargador:
    def __init__(self, cur, corrida_id, resumen):
        self.cur, self.corrida_id, self.resumen = cur, corrida_id, resumen
        self.organismos = Organismos(cur)
        self.vinculos = cargar_vinculos()
        self.candidatos = []
        cur.execute("SELECT codigo, id FROM plataforma")
        self.plataformas = dict(cur.fetchall())
        cur.execute("SELECT id, padre_id FROM organismo")
        self.padres = dict(cur.fetchall())
        cur.execute("SELECT id_externo, id, tramite_id, hash_contenido FROM fuente WHERE tipo = %s", (TIPO_FUENTE,))
        self.previas = {f[0]: f[1:] for f in cur.fetchall()}

    def raiz(self, organismo_id):
        if organismo_id and organismo_id not in self.padres:  # creado en esta corrida
            self.cur.execute("SELECT id, padre_id FROM organismo")
            self.padres = dict(self.cur.fetchall())
        vistos = set()
        while organismo_id and self.padres.get(organismo_id) and organismo_id not in vistos:
            vistos.add(organismo_id)
            organismo_id = self.padres[organismo_id]
        return organismo_id

    def tramite_por_tad(self, id_tad):
        self.cur.execute(
            """SELECT coalesce(t.reemplazado_por_id, t.id) FROM fuente f JOIN tramite t ON t.id = f.tramite_id
               WHERE f.tipo = %s AND f.id_externo = %s""",
            (FUENTE_CSV, str(id_tad)),
        )
        fila = self.cur.fetchone()
        return fila[0] if fila else None

    def tramite_por_clave(self, clave):
        """Clave de vínculo manual: un ID de TAD (número) o un id del inventario ("N-008")."""
        if isinstance(clave, int) or str(clave).isdigit():
            return self.tramite_por_tad(int(clave))
        self.cur.execute("SELECT tramite_id FROM fuente WHERE tipo = 'manual' AND id_externo = %s", (clave,))
        fila = self.cur.fetchone()
        return fila[0] if fila else None

    def similar(self, nombre, organismo_id):
        """Trámite más parecido dentro del mismo ministerio (raíz del organismo)."""
        raiz = self.raiz(organismo_id)
        mismos = [o for o in self.padres if self.raiz(o) == raiz] or [organismo_id]
        self.cur.execute(
            """SELECT t.id, t.nombre_ciudadano, similarity(t.nombre_ciudadano, %s) AS s
               FROM tramite t
               WHERE t.estado NOT IN ('fusionado') AND t.organismo_id = ANY(%s)
                 AND NOT EXISTS (SELECT 1 FROM fuente f WHERE f.tramite_id = t.id AND f.tipo = %s)
               ORDER BY s DESC LIMIT 1""",
            (nombre, mismos, TIPO_FUENTE),
        )
        return self.cur.fetchone()

    def vincular(self, slug_ficha, datos, organismo_id):
        """-> (tramite_id o None para crear uno nuevo, motivo)."""
        decision = self.vinculos.get(slug_ficha)
        if decision:
            if decision["accion"] == "nuevo":
                return None, "manual_nuevo"
            tramite_id = self.tramite_por_clave(decision["con"])
            if tramite_id is None:
                raise SystemExit(f"{slug_ficha}: el vínculo manual {decision['con']!r} no existe en la base")
            return tramite_id, "manual"
        for id_tad in datos["ids_tad"]:
            tramite_id = self.tramite_por_tad(id_tad)
            if tramite_id:
                return tramite_id, "id_tad"
        if organismo_id and datos["nombre"]:
            fila = self.similar(datos["nombre"], organismo_id)
            # Nombres muy cortos ("Autorización de importación") se parecen a cualquier cosa: van a revisión.
            especifico = min(len(n.clave(datos["nombre"]).split()), len(n.clave(fila[1]).split())) >= 4 if fila else False
            if fila and fila[2] >= SIMILITUD_AUTOMATICA and especifico:
                self.candidatos.append({"ficha": slug_ficha, "nombre": datos["nombre"], "candidato": fila[1],
                                        "similitud": round(fila[2], 2), "vinculado": True})
                return fila[0], "similitud"
            if fila and fila[2] >= SIMILITUD_CANDIDATA:
                self.candidatos.append({"ficha": slug_ficha, "nombre": datos["nombre"], "candidato": fila[1],
                                        "similitud": round(fila[2], 2)})
        return None, "nuevo"

    def cargar(self, slug_ficha, html, url):
        datos = parsear(html)
        if not datos["nombre"]:
            self.resumen["sin_nombre"] += 1
            return
        organismo_id = self.organismos(datos["migas"])
        datos = n.a_json(datos)
        hash_nuevo = n.hash_registro(datos)
        previa = self.previas.get(slug_ficha)
        if previa and previa[2] == hash_nuevo and previa[1]:
            self.resumen["sin_cambios"] += 1
            return

        tramite_id, motivo = self.vincular(slug_ficha, datos, organismo_id)
        if tramite_id is None and previa and previa[1] and motivo == "nuevo":
            tramite_id, motivo = previa[1], "previo"  # la ficha ya había creado su trámite
        if tramite_id is None:
            self.cur.execute(
                """INSERT INTO tramite (slug, nombre_ciudadano, nombre_oficial, descripcion, organismo_id,
                                        fecha_ultima_verificacion)
                   VALUES (%s, %s, %s, %s, %s, current_date) RETURNING id""",
                (f"{slug_ficha[:90]}-ficha", datos["nombre"], datos["nombre"], datos["descripcion"],
                 organismo_id or self.organismos.no_informado()),
            )
            tramite_id = self.cur.fetchone()[0]
        else:
            self.cur.execute("UPDATE tramite SET descripcion = %s WHERE id = %s AND descripcion IS NULL",
                             (datos["descripcion"], tramite_id))
        self.resumen[motivo] += 1

        if previa is None:
            self.cur.execute(
                """INSERT INTO fuente (tramite_id, tipo, id_externo, url, datos, hash_contenido, fecha_cambio)
                   VALUES (%s, %s, %s, %s, %s, %s, now()) RETURNING id""",
                (tramite_id, TIPO_FUENTE, slug_ficha, url, Json(datos), hash_nuevo),
            )
            fuente_id, evento = self.cur.fetchone()[0], "alta"
        else:
            fuente_id, evento = previa[0], "cambio"
            self.cur.execute(
                """UPDATE fuente SET tramite_id = %s, url = %s, datos = %s, hash_contenido = %s, activo = true,
                          fecha_captura = now(), fecha_cambio = now() WHERE id = %s""",
                (tramite_id, url, Json(datos), hash_nuevo, fuente_id),
            )
        self.cur.execute(
            "INSERT INTO fuente_evento (corrida_id, fuente_id, evento, hash_anterior, hash_nuevo) VALUES (%s, %s, %s, %s, %s)",
            (self.corrida_id, fuente_id, evento, previa[2] if previa else None, hash_nuevo),
        )
        self.resumen[evento] += 1

        self.cur.execute("DELETE FROM canal WHERE fuente_id = %s", (fuente_id,))
        for c in canales(datos):
            self.cur.execute(
                """INSERT INTO canal (tramite_id, modalidad, plataforma_id, url_inicio, requiere_turno, fuente_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (tramite_id, c["modalidad"], self.plataformas.get(c.get("plataforma")), c.get("url") or url,
                 c.get("requiere_turno"), fuente_id),
            )
        requisitos, costos = requisitos_y_costos(datos)
        sincronizar_requisitos(self.cur, fuente_id, tramite_id, requisitos)
        sincronizar_costos(self.cur, fuente_id, tramite_id, costos, CONCEPTO_COSTO)


class Simulacion(Exception):
    """Corta la transacción en --dry-run para que se deshaga."""


def cargar(args):
    indice = json.loads((args.carpeta / "_indice.json").read_text(encoding="utf-8"))
    archivos = sorted(args.carpeta.glob("*.html"))
    resumen = Counter()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ingesta_corrida (fuente_tipo) VALUES (%s) RETURNING id", (TIPO_FUENTE,))
            corrida_id = cur.fetchone()[0]
        estado, error, cargador = "ok", None, None
        try:
            with conn, conn.cursor() as cur:
                cargador = Cargador(cur, corrida_id, resumen)
                for archivo in archivos:
                    url = indice.get(archivo.stem, {}).get("url", PREFIJO_FICHA + archivo.stem)
                    cargador.cargar(archivo.stem, archivo.read_text(encoding="utf-8"), url)
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
                    """UPDATE ingesta_corrida SET finalizada_en = now(), estado = %s, filas_leidas = %s, altas = %s,
                              cambios = %s, sin_cambios = %s, advertencias = %s, error = %s WHERE id = %s""",
                    (estado, len(archivos), resumen["alta"], resumen["cambio"], resumen["sin_cambios"],
                     Json(dict(resumen)), error, corrida_id),
                )
    finally:
        conn.close()

    if cargador and cargador.candidatos:
        CANDIDATOS.parent.mkdir(parents=True, exist_ok=True)
        CANDIDATOS.write_text(json.dumps(sorted(cargador.candidatos, key=lambda c: -c["similitud"]),
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCorrida {corrida_id}: {estado} ({len(archivos)} fichas)")
    print(f"  altas {resumen['alta']} | cambios {resumen['cambio']} | sin cambios {resumen['sin_cambios']}")
    print(f"  vínculo con trámite existente: por ID de TAD {resumen['id_tad']}, por similitud {resumen['similitud']}, "
          f"manual {resumen['manual']} | trámites nuevos {resumen['nuevo'] + resumen['manual_nuevo']}")
    if cargador:
        print(f"  organismos nuevos (a revisar): {len(cargador.organismos.nuevos)}")
        if cargador.candidatos:
            print(f"  candidatos a revisar a mano: {len(cargador.candidatos)} (en {CANDIDATOS})")


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--carpeta", type=Path, default=CARPETA)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("descargar")
    p.add_argument("--refrescar", action="store_true", help="vuelve a bajar las fichas que ya están")
    p.add_argument("--refrescar-indice", action="store_true", help="vuelve a leer el sitemap")
    p.set_defaults(funcion=descargar)
    p = sub.add_parser("cargar")
    p.add_argument("--dry-run", action="store_true", help="aplica todo y hace rollback")
    p.set_defaults(funcion=cargar)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
