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
from datetime import datetime, timezone
from pathlib import Path

import requests

from ingesta.tad import DATABASE_URL, USER_AGENT

log = logging.getLogger("ingesta.fichas")

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
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
