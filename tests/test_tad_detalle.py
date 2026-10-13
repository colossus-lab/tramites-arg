"""Test de integración de la carga del detalle de TAD (fuente api_tad)."""

from argparse import Namespace

from ingesta import clasificar, inventario, tad, tad_detalle, tad_requisitos, variantes
from tests.base_db import FIXTURES, BaseDB


class TadDetalleTest(BaseDB):
    def cargar(self, **kwargs):
        args = Namespace(database_url=self.url, carpeta=FIXTURES / "tad_detalle", dry_run=False, **kwargs)
        tad_detalle.cargar(args)

    def ingesta_csv(self, version):
        resumen = tad.Resumen()
        return tad.ejecutar(tad.leer_directorio(FIXTURES / version, resumen), self.url, resumen=resumen)

    def organismo(self, id_tad):
        return self.uno(
            """SELECT o.sigla, o.nombre_oficial, p.nombre_oficial, t.descripcion
               FROM v_tramite_tad v JOIN tramite t ON t.id = v.tramite_id
               JOIN organismo o ON o.id = t.organismo_id LEFT JOIN organismo p ON p.id = o.padre_id
               WHERE v.id_tad = %s""",
            id_tad,
        )

    def ultima_corrida(self):
        return self.uno(
            "SELECT estado, altas, cambios, sin_cambios FROM ingesta_corrida WHERE fuente_tipo = 'api_tad' "
            "ORDER BY id DESC LIMIT 1")

    def test_carga_y_organismos(self):
        self.ingesta_csv("tad_v1")

        tad_detalle.cargar(Namespace(database_url=self.url, carpeta=FIXTURES / "tad_detalle", dry_run=True))
        self.assertEqual(self.ultima_corrida()[0], "simulacion")
        self.assertEqual(self.uno("SELECT count(*) FROM fuente WHERE tipo = 'api_tad'")[0], 0)

        self.cargar()
        self.assertEqual(self.ultima_corrida(), ("ok", 4, 0, 0))  # 9006 no figura en el CSV
        # Regla 2, organismo nuevo colgado del ministerio del CSV.
        self.assertEqual(self.organismo(9001), ("CANC", "Coordinación de Legalizaciones",
                                                "Ministerio de Relaciones Exteriores", "Apostillar documentos públicos."))
        # Sin nombre para MEC: queda en el ministerio del CSV (AFIP -> ARCA).
        self.assertEqual(self.organismo(9002)[0], "ARCA")
        # Regla 1: RENAR por alias, aunque la etiqueta diga ANMAC.
        self.assertEqual(self.organismo(9003)[0], "RENAR")
        # Regla 2 reusando el organismo que ya existía con ese nombre.
        self.assertEqual(self.organismo(9004)[1], "Ente Nacional de Comunicaciones")
        self.assertEqual(self.uno("SELECT organismo_id FROM organismo_alias WHERE alias_original = 'ENACOM'")[0],
                         self.uno("SELECT id FROM organismo WHERE nombre_oficial = 'Ente Nacional de Comunicaciones'")[0])
        self.assertIsNone(self.uno("SELECT 1 FROM organismo WHERE sigla = 'IGJ'"))

        # Recarga: idempotente.
        self.cargar()
        self.assertEqual(self.ultima_corrida(), ("ok", 0, 0, 4))

        # Una descripción editada a mano no se pisa.
        self.conn.cursor().execute(
            "UPDATE tramite SET descripcion = 'Editada' WHERE id = (SELECT tramite_id FROM v_tramite_tad WHERE id_tad = 9003)")
        self.cargar()
        self.assertEqual(self.organismo(9003)[3], "Editada")

        # Un cambio en el CSV no devuelve el trámite al ministerio de ORGANO_RECTOR.
        _, _, r = self.ingesta_csv("tad_v2")
        self.assertEqual(r.cambios, 2)
        self.assertEqual(self.organismo(9001)[0], "CANC")
        # Y una baja en el CSV sigue dando de baja el trámite aunque tenga fuente api_tad.
        self.assertEqual(self.uno("SELECT estado FROM v_tramite_tad WHERE id_tad = 9002")[0], "baja")


class TadRequisitosTest(BaseDB):
    def test_extraccion(self):
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v1", resumen), self.url, resumen=resumen)
        tad_detalle.cargar(Namespace(database_url=self.url, carpeta=FIXTURES / "tad_detalle", dry_run=False))

        tad_requisitos.main(["--database-url", self.url])
        filas = self.todos(
            """SELECT r.descripcion, r.seccion FROM requisito r JOIN fuente f ON f.id = r.fuente_id
               WHERE f.id_externo = '9004' ORDER BY r.orden""")
        self.assertEqual(filas, [("Estatuto social.", "Requisitos"), ("Constancia de CUIT.", "Requisitos")])
        costos = self.todos(
            """SELECT c.concepto, c.gratuito, c.monto_min FROM costo c
               JOIN tramite t ON t.id = c.tramite_id JOIN fuente f ON f.tramite_id = t.id AND f.tipo = 'csv_tad'
               WHERE f.id_externo = '9004' AND c.vigente_hasta IS NULL ORDER BY c.concepto""")
        # El costo del CSV (no arancelado) y el del texto conviven con conceptos distintos.
        self.assertEqual([(c, g) for c, g, _ in costos], [("arancel (descripción TAD)", False), ("arancel TAD", True)])
        self.assertEqual(costos[0][2], 45000)

        # Segunda corrida: nada cambia.
        tad_requisitos.main(["--database-url", self.url])
        self.assertEqual(self.uno("SELECT cambios FROM ingesta_corrida ORDER BY id DESC LIMIT 1")[0], 0)
        self.assertEqual(self.uno("SELECT count(*) FROM costo WHERE concepto = 'arancel (descripción TAD)'")[0], 1)


class InventarioTest(BaseDB):
    def test_carga_idempotente(self):
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v1", resumen), self.url, resumen=resumen)
        args = ["--archivo", str(FIXTURES / "inventario_mini.json"), "--database-url", self.url]
        inventario.main(args)

        nuevo = self.uno("SELECT id, organismo_id, categoria_origen FROM tramite WHERE slug LIKE '%-n-001'")
        self.assertEqual(nuevo[2], "manual")
        self.assertEqual(self.uno("SELECT sigla FROM organismo WHERE id = %s", nuevo[1])[0], "RENAR")
        self.assertEqual(self.todos(
            """SELECT v.nombre, c.monto_min FROM costo c JOIN tramite_variante v ON v.id = c.variante_id
               WHERE c.tramite_id = %s ORDER BY c.monto_min""", nuevo[0]),
            [("Común", 100), ("Exprés", 200)])
        # El requisito previo apunta al trámite TAD enriquecido.
        previo = self.uno("SELECT tramite_previo_id FROM requisito WHERE tramite_id = %s AND tipo = 'tramite_previo'", nuevo[0])[0]
        self.assertEqual(previo, self.uno("SELECT tramite_id FROM v_tramite_tad WHERE id_tad = 9001")[0])
        self.assertEqual(self.uno("SELECT c.codigo, t.categoria_origen FROM tramite t JOIN categoria c ON c.id = t.categoria_id "
                                  "WHERE t.id = %s", previo), ("viajes", "manual"))
        # La baja apunta a su reemplazo, y ANMAC resuelve a RENAR por sucesor.
        baja = self.uno("SELECT estado, reemplazado_por_id, organismo_id FROM tramite WHERE slug LIKE '%-b-001'")
        self.assertEqual(baja[:2], ("baja", nuevo[0]))
        self.assertEqual(baja[2], nuevo[1])
        self.assertEqual(self.uno("SELECT tramite_id FROM fuente WHERE tipo = 'manual' AND id_externo = 'N-002'")[0], nuevo[0])

        # Segunda corrida: nada cambia; la clasificación automática no pisa las categorías manuales.
        inventario.main(args)
        self.assertEqual(self.uno("SELECT sin_cambios, altas FROM ingesta_corrida ORDER BY id DESC LIMIT 1"), (3, 0))
        clasificar.main(["--database-url", self.url])
        self.assertEqual(self.uno("SELECT c.codigo FROM tramite t JOIN categoria c ON c.id = t.categoria_id WHERE t.id = %s",
                                  previo)[0], "viajes")
        self.assertEqual(self.uno("SELECT count(*) FROM costo WHERE tramite_id = %s", nuevo[0])[0], 2)


class VariantesTest(BaseDB):
    def test_agrupacion_idempotente_y_estable_ante_la_ingesta(self):
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v1", resumen), self.url, resumen=resumen)
        args = ["--archivo", str(FIXTURES / "agrupaciones_mini.json"), "--database-url", self.url]
        variantes.main(args)
        variantes.main(args)

        canonico = self.uno("SELECT tramite_id FROM v_tramite_tad WHERE id_tad = 9003")[0]
        self.assertEqual(self.uno("SELECT nombre_ciudadano FROM tramite WHERE id = %s", canonico)[0],
                         "Trámite agrupado (fixture)")
        self.assertEqual(self.uno("SELECT count(*) FROM tramite_variante WHERE tramite_id = %s", canonico)[0], 2)
        self.assertEqual(self.uno("SELECT t.estado, t.reemplazado_por_id FROM tramite t JOIN v_tramite_tad v "
                                  "ON v.tramite_id = t.id WHERE v.id_tad = 9004"), ("fusionado", canonico))
        self.assertEqual(sorted(t for (t,) in self.todos(
            "SELECT tipo FROM tramite_destinatario WHERE tramite_id = %s AND origen = 'manual'", canonico)),
            ["empresa", "pf_ciudadano"])

        # v2 cambia el nombre de 9004 en el CSV: sigue fusionado.
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v2", resumen), self.url, resumen=resumen)
        self.assertEqual(self.uno("SELECT estado FROM v_tramite_tad WHERE id_tad = 9004")[0], "fusionado")
