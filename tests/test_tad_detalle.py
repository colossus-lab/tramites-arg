"""Test de integración de la carga del detalle de TAD (fuente api_tad)."""

from argparse import Namespace

from ingesta import tad, tad_detalle, tad_requisitos
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
