"""Agrupa trámites TAD que son variantes de un mismo trámite (db/semillas/agrupaciones_tad.json).

    python -m ingesta.variantes             aplica las agrupaciones
    python -m ingesta.variantes --dry-run   muestra el resultado y deshace

El primer trámite de cada grupo es el canónico: toma el nombre del grupo y recibe una
tramite_variante por miembro (con tramite_origen_id apuntando al trámite TAD de origen,
que conserva su link, costos y requisitos). Los demás quedan con estado 'fusionado' y
reemplazado_por_id al canónico, así no cuentan como trámites distintos. Idempotente.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import psycopg2

from ingesta.tad import DATABASE_URL, TIPO_FUENTE as FUENTE_CSV

ARCHIVO = Path(__file__).resolve().parent.parent / "db" / "semillas" / "agrupaciones_tad.json"


def aplicar(cur, grupos, resumen):
    for grupo in grupos:
        ids = [v["id_tad"] for v in grupo["variantes"]]
        cur.execute(
            "SELECT id_externo::integer, tramite_id FROM fuente WHERE tipo = %s AND id_externo = ANY(%s)",
            (FUENTE_CSV, [str(i) for i in ids]),
        )
        tramites = dict(cur.fetchall())
        faltan = [i for i in ids if i not in tramites]
        if faltan:
            raise SystemExit(f"{grupo['nombre']}: trámites TAD {faltan} no están en la base")
        canonico = tramites[ids[0]]

        cur.execute("UPDATE tramite SET nombre_ciudadano = %s WHERE id = %s AND nombre_ciudadano IS DISTINCT FROM %s",
                    (grupo["nombre"], canonico, grupo["nombre"]))
        resumen["renombrados"] += cur.rowcount
        for v in grupo["variantes"]:
            origen = tramites[v["id_tad"]]
            cur.execute(
                """INSERT INTO tramite_variante (tramite_id, nombre, tramite_origen_id) VALUES (%s, %s, %s)
                   ON CONFLICT (tramite_id, nombre) DO UPDATE SET tramite_origen_id = EXCLUDED.tramite_origen_id
                   WHERE tramite_variante.tramite_origen_id IS DISTINCT FROM EXCLUDED.tramite_origen_id""",
                (canonico, v["nombre"], origen),
            )
            resumen["variantes"] += cur.rowcount
            if origen != canonico:
                cur.execute(
                    """UPDATE tramite SET estado = 'fusionado', reemplazado_por_id = %s
                       WHERE id = %s AND (estado <> 'fusionado' OR reemplazado_por_id IS DISTINCT FROM %s)""",
                    (canonico, origen, canonico),
                )
                resumen["fusionados"] += cur.rowcount
            if v.get("destinatario"):
                cur.execute("DELETE FROM tramite_destinatario WHERE tramite_id = %s AND origen = 'auto'", (canonico,))
                cur.execute(
                    """INSERT INTO tramite_destinatario (tramite_id, tipo, origen, regla) VALUES (%s, %s, 'manual', 'variantes')
                       ON CONFLICT (tramite_id, tipo) DO UPDATE SET origen = 'manual', regla = 'variantes'
                       WHERE tramite_destinatario.origen <> 'manual'""",
                    (canonico, v["destinatario"]),
                )
                resumen["destinatarios"] += cur.rowcount
        resumen["grupos"] += 1


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archivo", type=Path, default=ARCHIVO)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="aplica y hace rollback")
    args = parser.parse_args(argv)

    grupos = json.loads(args.archivo.read_text(encoding="utf-8"))["grupos"]
    resumen = Counter()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            aplicar(cur, grupos, resumen)
            if args.dry_run:
                conn.rollback()
    finally:
        conn.close()
    print(f"\n{'Simulación' if args.dry_run else 'Variantes'}: {resumen['grupos']} grupos | "
          f"renombrados {resumen['renombrados']} | variantes nuevas o cambiadas {resumen['variantes']} | "
          f"fusionados {resumen['fusionados']} | destinatarios {resumen['destinatarios']}")


if __name__ == "__main__":
    sys.exit(main())
