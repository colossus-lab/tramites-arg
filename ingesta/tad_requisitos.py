"""Requisitos y costos extraídos de la descripción HTML de TAD (fuente api_tad).

    python -m ingesta.tad_requisitos             extrae y actualiza la base
    python -m ingesta.tad_requisitos --dry-run   extrae, muestra el resumen y deshace

Lee el HTML ya cargado por `ingesta.tad_detalle cargar`. Cada requisito y costo
queda asociado a la fuente api_tad de la que salió; una nueva corrida reemplaza
los requisitos de una fuente solo si cambiaron, y para los costos cierra la fila
vigente y abre otra (historial). Los costos del CSV de TAD no se tocan: estos
usan otro concepto.
"""

import argparse
import sys
from collections import Counter
from decimal import Decimal

import psycopg2
from psycopg2.extras import Json

from ingesta import extraer_html
from ingesta.tad import DATABASE_URL
from ingesta.tad_detalle import TIPO_FUENTE

CONCEPTO_COSTO = "arancel (descripción TAD)"


class Simulacion(Exception):
    """Corta la transacción en --dry-run para que se deshaga."""


def dos_decimales(v):
    return None if v is None else Decimal(v).quantize(Decimal("0.01"))


def sincronizar_requisitos(cur, fuente_id, tramite_id, requisitos):
    deseados = [(r.descripcion, r.tipo, r.seccion, r.obligatorio) for r in requisitos]
    cur.execute(
        "SELECT descripcion, tipo, seccion, obligatorio FROM requisito WHERE fuente_id = %s ORDER BY orden",
        (fuente_id,),
    )
    if cur.fetchall() == deseados:
        return False
    cur.execute("DELETE FROM requisito WHERE fuente_id = %s", (fuente_id,))
    for orden, (descripcion, tipo, seccion, obligatorio) in enumerate(deseados, 1):
        cur.execute(
            """INSERT INTO requisito (tramite_id, tipo, descripcion, orden, seccion, obligatorio, fuente_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (tramite_id, tipo, descripcion, orden, seccion, obligatorio, fuente_id),
        )
    return True


def sincronizar_costos(cur, fuente_id, tramite_id, costos, concepto=CONCEPTO_COSTO):
    deseados = {c.unidad: (c.gratuito, dos_decimales(c.monto_min), dos_decimales(c.monto_max), c.detalle)
                for c in costos}
    cur.execute(
        """SELECT id, unidad, gratuito, monto_min, monto_max, detalle FROM costo
           WHERE fuente_id = %s AND concepto = %s AND vigente_hasta IS NULL""",
        (fuente_id, concepto),
    )
    actuales = {fila[1]: (fila[0], tuple(fila[2:])) for fila in cur.fetchall()}
    cambio = False
    for unidad, (costo_id, valores) in actuales.items():
        if deseados.get(unidad) != valores:
            cur.execute("UPDATE costo SET vigente_hasta = current_date WHERE id = %s", (costo_id,))
            cambio = True
    for unidad, (gratuito, minimo, maximo, detalle) in deseados.items():
        if unidad in actuales and actuales[unidad][1] == deseados[unidad]:
            continue
        cur.execute(
            """INSERT INTO costo (tramite_id, concepto, gratuito, monto_min, monto_max, unidad, fuente_id, detalle)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (tramite_id, concepto, gratuito, minimo, maximo, unidad, fuente_id, detalle),
        )
        cambio = True
    return cambio


def aplicar(cur, resumen):
    cur.execute(
        """SELECT id, tramite_id, datos ->> 'descripcion_html' FROM fuente
           WHERE tipo = %s AND activo AND tramite_id IS NOT NULL ORDER BY id""",
        (TIPO_FUENTE,),
    )
    for fuente_id, tramite_id, html in cur.fetchall():
        requisitos = extraer_html.requisitos(html)
        costos = extraer_html.costos(html)
        resumen["fuentes"] += 1
        resumen["con_requisitos"] += bool(requisitos)
        resumen["requisitos"] += len(requisitos)
        resumen["con_costo"] += any(not c.gratuito for c in costos)
        resumen["gratuitos"] += any(c.gratuito for c in costos)
        resumen["requisitos_actualizados"] += sincronizar_requisitos(cur, fuente_id, tramite_id, requisitos)
        resumen["costos_actualizados"] += sincronizar_costos(cur, fuente_id, tramite_id, costos)


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="aplica todo y hace rollback")
    args = parser.parse_args(argv)

    resumen = Counter()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ingesta_corrida (fuente_tipo) VALUES ('extraccion_html_tad') RETURNING id")
            corrida_id = cur.fetchone()[0]
        estado, error = "ok", None
        try:
            with conn, conn.cursor() as cur:
                aplicar(cur, resumen)
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
                              cambios = %s, advertencias = %s, error = %s WHERE id = %s""",
                    (estado, resumen["fuentes"], resumen["requisitos_actualizados"] + resumen["costos_actualizados"],
                     Json(dict(resumen)), error, corrida_id),
                )
    finally:
        conn.close()

    print(f"\nCorrida {corrida_id}: {estado}")
    print(f"  descripciones: {resumen['fuentes']}")
    print(f"  con requisitos: {resumen['con_requisitos']} ({resumen['requisitos']} requisitos) | "
          f"actualizados: {resumen['requisitos_actualizados']}")
    print(f"  con costo: {resumen['con_costo']} | gratuitos según el texto: {resumen['gratuitos']} | "
          f"actualizados: {resumen['costos_actualizados']}")


if __name__ == "__main__":
    sys.exit(main())
