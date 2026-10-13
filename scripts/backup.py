"""Backup de la base (pg_dump en formato custom) desde el contenedor de docker compose.

    python scripts/backup.py                 guarda backups/tramites-AAAAMMDD-HHMMSS.dump
    python scripts/backup.py --conservar 5   borra los más viejos y deja los últimos 5

Para restaurar sobre una base vacía:
    docker compose exec -T db pg_restore -U tramites -d tramites --clean --if-exists < backups/<archivo>.dump
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "backups"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conservar", type=int, default=10, help="cuántos backups conservar (default: 10)")
    args = parser.parse_args(argv)

    CARPETA.mkdir(exist_ok=True)
    destino = CARPETA / f"tramites-{datetime.now():%Y%m%d-%H%M%S}.dump"
    temporal = destino.with_suffix(".tmp")
    with temporal.open("wb") as salida:
        resultado = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "pg_dump", "-U", "tramites", "-d", "tramites", "-Fc"],
            cwd=RAIZ, stdout=salida, stderr=subprocess.PIPE,
        )
    if resultado.returncode != 0 or temporal.stat().st_size == 0:
        temporal.unlink(missing_ok=True)
        sys.exit(f"pg_dump falló: {resultado.stderr.decode(errors='replace').strip()}")
    temporal.replace(destino)
    print(f"Backup: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")

    viejos = sorted(CARPETA.glob("tramites-*.dump"))[:-args.conservar]
    for archivo in viejos:
        archivo.unlink()
    if viejos:
        print(f"Borrados {len(viejos)} backups viejos")


if __name__ == "__main__":
    main()
