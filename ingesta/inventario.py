"""Carga del inventario curado de la Etapa 1 (db/semillas/inventario_etapa1.json).

    python -m ingesta.inventario             carga o actualiza
    python -m ingesta.inventario --dry-run   muestra el resumen y deshace

Cada fila del JSON queda como fuente 'manual' (id_externo = "N-001"). Según su acción:
- nuevo: crea el trámite (o lo actualiza si la fila cambió) con canales,
  variantes, costos, requisitos, destinatarios y hechos vitales;
- enriquecer: completa un trámite TAD existente (categoría manual,
  destinatarios y lo que traiga la fila) sin duplicarlo;
- incluido_en: variante o canal de otra fila; solo enlaza la fuente;
- omitir: fila paraguas o cambio institucional; no carga nada.
Una fila sin cambios (mismo hash) no se toca.
"""

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from ingesta import normalizar as n
from ingesta.tad import DATABASE_URL, TIPO_FUENTE as FUENTE_CSV

TIPO_FUENTE = "manual"
ARCHIVO = Path(__file__).resolve().parent.parent / "db" / "semillas" / "inventario_etapa1.json"
ACCIONES = {"nuevo", "enriquecer", "incluido_en", "omitir"}


class Simulacion(Exception):
    """Corta la transacción en --dry-run para que se deshaga."""


class ErrorInventario(Exception):
    pass


def validar(filas):
    ids = [f["id"] for f in filas]
    repetidos = [i for i, k in Counter(ids).items() if k > 1]
    if repetidos:
        raise ErrorInventario(f"ids repetidos: {repetidos}")
    for f in filas:
        if f.get("accion") not in ACCIONES:
            raise ErrorInventario(f"{f['id']}: acción desconocida {f.get('accion')!r}")
        if f["accion"] == "incluido_en" and f.get("en") not in ids:
            raise ErrorInventario(f"{f['id']}: incluido_en apunta a {f.get('en')!r}, que no existe")
        for r in f.get("requisitos", []):
            if r.get("tipo") == "tramite_previo" and r.get("previo") not in ids:
                raise ErrorInventario(f"{f['id']}: requisito previo {r.get('previo')!r} no existe")


def monto(v):
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


class Cargador:
    def __init__(self, cur, corrida_id, resumen):
        self.cur = cur
        self.corrida_id = corrida_id
        self.resumen = resumen
        cur.execute("SELECT codigo, id FROM categoria")
        self.categorias = dict(cur.fetchall())
        cur.execute("SELECT codigo, id FROM hecho_vital")
        self.hechos = dict(cur.fetchall())
        cur.execute("SELECT codigo, id FROM plataforma")
        self.plataformas = dict(cur.fetchall())
        cur.execute("SELECT id_externo, id, tramite_id, hash_contenido FROM fuente WHERE tipo = %s", (TIPO_FUENTE,))
        self.previas = {fila[0]: fila[1:] for fila in cur.fetchall()}
        self.tramites = {}            # id de fila -> tramite_id
        self.requisitos_previos = []  # (fuente_id, tramite_id, orden, requisito) a resolver al final
        self.reemplazos = []          # (tramite_id, id de fila reemplazante)

    def uno(self, sql, params):
        self.cur.execute(sql, params)
        fila = self.cur.fetchone()
        return fila[0] if fila else None

    def organismo(self, sigla, id_fila):
        organismo_id = self.uno(
            "SELECT organismo_actual(organismo_id) FROM organismo_alias WHERE alias_normalizado = normalizar_texto(%s)",
            (sigla,),
        )
        if organismo_id is None:
            raise ErrorInventario(f"{id_fila}: organismo {sigla!r} sin alias en la base")
        return organismo_id

    def categoria(self, codigo, id_fila):
        if codigo not in self.categorias:
            raise ErrorInventario(f"{id_fila}: categoría {codigo!r} inexistente")
        return self.categorias[codigo]

    def fuente(self, fila, tramite_id, hash_nuevo):
        """Alta o actualización de la fuente manual. Devuelve (fuente_id, evento o None si no cambió)."""
        previa = self.previas.get(fila["id"])
        if previa and previa[1] == tramite_id and previa[2] == hash_nuevo:
            return previa[0], None
        if previa is None:
            fuente_id = self.uno(
                """INSERT INTO fuente (tramite_id, tipo, id_externo, url, datos, hash_contenido, fecha_cambio)
                   VALUES (%s, %s, %s, %s, %s, %s, now()) RETURNING id""",
                (tramite_id, TIPO_FUENTE, fila["id"], fila.get("url"), Json(fila), hash_nuevo),
            )
            evento = "alta"
        else:
            fuente_id, evento = previa[0], "cambio"
            self.cur.execute(
                """UPDATE fuente SET tramite_id = %s, url = %s, datos = %s, hash_contenido = %s,
                          fecha_captura = now(), fecha_cambio = now(), activo = true WHERE id = %s""",
                (tramite_id, fila.get("url"), Json(fila), hash_nuevo, fuente_id),
            )
        self.cur.execute(
            "INSERT INTO fuente_evento (corrida_id, fuente_id, evento, hash_anterior, hash_nuevo) VALUES (%s, %s, %s, %s, %s)",
            (self.corrida_id, fuente_id, evento, previa[2] if previa else None, hash_nuevo),
        )
        return fuente_id, evento

    def nuevo(self, fila, hash_nuevo):
        previa = self.previas.get(fila["id"])
        tramite_id = previa[1] if previa else None
        if previa and previa[2] == hash_nuevo and tramite_id:
            return tramite_id, previa[0], None
        valores = (fila["nombre"], fila["nombre"], fila.get("descripcion"), self.organismo(fila["organismo"], fila["id"]),
                   self.categoria(fila["categoria"], fila["id"]), fila.get("estado", "vigente"), fila.get("norma"))
        if tramite_id is None:
            tramite_id = self.uno(
                """INSERT INTO tramite (nombre_ciudadano, nombre_oficial, descripcion, organismo_id, categoria_id,
                                        categoria_origen, estado, norma_base, slug)
                   VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, %s) RETURNING id""",
                (*valores, f"{n.slugify(fila['nombre'])}-{fila['id'].lower()}"),
            )
        else:
            self.cur.execute(
                """UPDATE tramite SET nombre_ciudadano = %s, nombre_oficial = %s, descripcion = %s, organismo_id = %s,
                          categoria_id = %s, categoria_origen = 'manual', estado = %s, norma_base = %s,
                          reemplazado_por_id = NULL
                   WHERE id = %s""",
                (*valores, tramite_id),
            )
        fuente_id, evento = self.fuente(fila, tramite_id, hash_nuevo)
        return tramite_id, fuente_id, evento

    def enriquecer(self, fila, hash_nuevo):
        tramite_id = self.uno(
            "SELECT tramite_id FROM fuente WHERE tipo = %s AND id_externo = %s", (FUENTE_CSV, str(fila["id_tad"]))
        )
        if tramite_id is None:
            raise ErrorInventario(f"{fila['id']}: el trámite TAD {fila['id_tad']} no está en la base")
        fuente_id, evento = self.fuente(fila, tramite_id, hash_nuevo)
        if evento:
            self.cur.execute(
                "UPDATE tramite SET categoria_id = %s, categoria_origen = 'manual' WHERE id = %s",
                (self.categoria(fila["categoria"], fila["id"]), tramite_id),
            )
        return tramite_id, fuente_id, evento

    def hijos(self, fila, tramite_id, fuente_id):
        """Reconstruye lo que cuelga de la fuente: canales, variantes, costos, requisitos, destinatarios."""
        cur = self.cur
        for tipo in fila.get("destinatarios", []):
            cur.execute("INSERT INTO tramite_destinatario VALUES (%s, %s) ON CONFLICT DO NOTHING", (tramite_id, tipo))
        for codigo in fila.get("hechos_vitales", []):
            cur.execute("INSERT INTO tramite_hecho_vital VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (tramite_id, self.hechos[codigo]))

        cur.execute("DELETE FROM canal WHERE fuente_id = %s", (fuente_id,))
        for canal in fila.get("canales", []):
            if canal.get("plataforma") and canal["plataforma"] not in self.plataformas:
                raise ErrorInventario(f"{fila['id']}: plataforma {canal['plataforma']!r} inexistente")
            canal_id = self.uno(
                """INSERT INTO canal (tramite_id, modalidad, plataforma_id, url_inicio, requiere_turno, detalle, fuente_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (tramite_id, canal["modalidad"], self.plataformas.get(canal.get("plataforma")),
                 canal.get("url", fila.get("url")), canal.get("requiere_turno"), canal.get("detalle"), fuente_id),
            )
            for a in canal.get("autenticacion", []):
                a = a if isinstance(a, dict) else {"metodo": a}
                cur.execute(
                    "INSERT INTO canal_autenticacion (canal_id, metodo, nivel_minimo) VALUES (%s, %s, %s)",
                    (canal_id, a["metodo"], a.get("nivel_minimo")),
                )

        variantes = {}
        for nombre in fila.get("variantes", []):
            variantes[nombre] = self.uno(
                """INSERT INTO tramite_variante (tramite_id, nombre) VALUES (%s, %s)
                   ON CONFLICT (tramite_id, nombre) DO UPDATE SET nombre = EXCLUDED.nombre RETURNING id""",
                (tramite_id, nombre),
            )
        self.costos(fila, tramite_id, fuente_id, variantes)

        cur.execute("DELETE FROM requisito WHERE fuente_id = %s", (fuente_id,))
        for orden, r in enumerate(fila.get("requisitos", []), 1):
            if r.get("tipo") == "tramite_previo":
                self.requisitos_previos.append((fuente_id, tramite_id, orden, r))
                continue
            cur.execute(
                """INSERT INTO requisito (tramite_id, tipo, descripcion, orden, obligatorio, fuente_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (tramite_id, r.get("tipo", "documento"), r["texto"], orden, r.get("obligatorio", True), fuente_id),
            )

    def costos(self, fila, tramite_id, fuente_id, variantes):
        deseados = {}
        for c in fila.get("costos", []):
            if c.get("variante") and c["variante"] not in variantes:
                raise ErrorInventario(f"{fila['id']}: costo con variante desconocida {c['variante']!r}")
            gratuito = c.get("gratuito", False)
            minimo = monto(c.get("monto_min", c.get("monto")))
            maximo = monto(c.get("monto_max", c.get("monto")))
            clave = (c.get("concepto", "arancel"), c.get("unidad", "ARS"), variantes.get(c.get("variante")))
            deseados[clave] = ((gratuito, minimo, maximo, c.get("norma"), c.get("detalle")), c.get("vigente_desde"))
        self.cur.execute(
            """SELECT id, concepto, unidad, variante_id, gratuito, monto_min, monto_max, norma, detalle FROM costo
               WHERE fuente_id = %s AND vigente_hasta IS NULL""",
            (fuente_id,),
        )
        actuales = {(f[1], f[2], f[3]): (f[0], tuple(f[4:])) for f in self.cur.fetchall()}
        for clave, (costo_id, valores) in actuales.items():
            if clave not in deseados or deseados[clave][0] != valores:
                self.cur.execute("UPDATE costo SET vigente_hasta = current_date WHERE id = %s", (costo_id,))
        for (concepto, unidad, variante_id), (valores, desde) in deseados.items():
            if (concepto, unidad, variante_id) in actuales and actuales[(concepto, unidad, variante_id)][1] == valores:
                continue
            gratuito, minimo, maximo, norma, detalle = valores
            self.cur.execute(
                """INSERT INTO costo (tramite_id, variante_id, concepto, gratuito, monto_min, monto_max, unidad, norma,
                                      vigente_desde, fuente_id, detalle)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::date, current_date), %s, %s)""",
                (tramite_id, variante_id, concepto, gratuito, minimo, maximo, unidad, norma, desde, fuente_id, detalle),
            )

    def cargar(self, filas):
        for fila in filas:
            accion = fila["accion"]
            if accion == "omitir":
                self.resumen["omitidas"] += 1
                continue
            if accion == "incluido_en":
                continue
            hash_nuevo = n.hash_registro(fila)
            if accion == "nuevo":
                tramite_id, fuente_id, evento = self.nuevo(fila, hash_nuevo)
            else:
                tramite_id, fuente_id, evento = self.enriquecer(fila, hash_nuevo)
            self.tramites[fila["id"]] = tramite_id
            if fila.get("reemplazado_por"):
                self.reemplazos.append((tramite_id, fila["reemplazado_por"]))
            if evento is None:
                self.resumen["sin_cambios"] += 1
                continue
            self.hijos(fila, tramite_id, fuente_id)
            self.resumen[f"{accion}_{evento}"] += 1

        for fila in filas:
            if fila["accion"] == "incluido_en":
                _, evento = self.fuente(fila, self.tramites[fila["en"]], n.hash_registro(fila))
                self.resumen["incluidas"] += 1

        for fuente_id, tramite_id, orden, r in self.requisitos_previos:
            self.cur.execute(
                """INSERT INTO requisito (tramite_id, tipo, descripcion, orden, obligatorio, tramite_previo_id, fuente_id)
                   VALUES (%s, 'tramite_previo', %s, %s, %s, %s, %s)""",
                (tramite_id, r["texto"], orden, r.get("obligatorio", True), self.tramites[r["previo"]], fuente_id),
            )
        for tramite_id, reemplazo in self.reemplazos:
            self.cur.execute("UPDATE tramite SET reemplazado_por_id = %s WHERE id = %s",
                             (self.tramites[reemplazo], tramite_id))

        ids = {f["id"] for f in filas}
        huerfanas = sorted(set(self.previas) - ids)
        if huerfanas:
            self.resumen["huerfanas"] = len(huerfanas)
            print(f"  fuentes manuales que ya no están en el inventario (no se tocan): {huerfanas}")


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archivo", type=Path, default=ARCHIVO)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="aplica todo y hace rollback")
    args = parser.parse_args(argv)

    filas = json.loads(args.archivo.read_text(encoding="utf-8"))["tramites"]
    validar(filas)
    resumen = Counter()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ingesta_corrida (fuente_tipo, archivos) VALUES ('inventario', %s) RETURNING id",
                        (Json([{"origen": str(args.archivo), "filas": len(filas)}]),))
            corrida_id = cur.fetchone()[0]
        estado, error = "ok", None
        try:
            with conn, conn.cursor() as cur:
                Cargador(cur, corrida_id, resumen).cargar(filas)
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
                              altas = %s, cambios = %s, sin_cambios = %s, advertencias = %s, error = %s WHERE id = %s""",
                    (estado, len(filas), resumen["nuevo_alta"], resumen["nuevo_cambio"] + resumen["enriquecer_cambio"],
                     resumen["sin_cambios"], Json(dict(resumen)), error, corrida_id),
                )
    finally:
        conn.close()

    print(f"\nCorrida {corrida_id}: {estado} ({len(filas)} filas)")
    print(f"  trámites nuevos: {resumen['nuevo_alta']} | actualizados: {resumen['nuevo_cambio']}")
    print(f"  TAD enriquecidos: {resumen['enriquecer_alta'] + resumen['enriquecer_cambio']}")
    print(f"  incluidas en otra fila: {resumen['incluidas']} | omitidas: {resumen['omitidas']} | "
          f"sin cambios: {resumen['sin_cambios']}")


if __name__ == "__main__":
    sys.exit(main())
