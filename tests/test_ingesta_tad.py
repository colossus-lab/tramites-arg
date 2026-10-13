"""Test de integración de la ingesta del CSV de TAD con los fixtures de tests/fixtures."""

from decimal import Decimal

from ingesta import tad
from tests.base_db import FIXTURES, BaseDB


def correr(url, version, **kwargs):
    resumen = tad.Resumen()
    archivos = tad.leer_directorio(FIXTURES / version, resumen)
    return tad.ejecutar(archivos, url, resumen=resumen, **kwargs)


class TramitesTadTest(BaseDB):
    def estado_tramite(self, id_tad):
        return self.uno("SELECT estado FROM v_tramite_tad WHERE id_tad = %s", id_tad)[0]

    def costos(self, id_tad):
        return self.todos(
            """SELECT c.gratuito, c.monto_min, c.vigente_hasta IS NULL FROM costo c
               JOIN fuente f ON f.id = c.fuente_id WHERE f.id_externo = %s ORDER BY c.id""",
            str(id_tad),
        )

    def canales(self, id_tad):
        return dict(self.todos(
            """SELECT p.codigo, c.activo FROM canal c JOIN plataforma p ON p.id = c.plataforma_id
               JOIN fuente f ON f.id = c.fuente_id WHERE f.id_externo = %s""",
            str(id_tad),
        ))

    def test_ciclo_completo(self):
        # Simulación: no deja nada escrito salvo la corrida.
        _, estado, resumen = correr(self.url, "tad_v1", dry_run=True)
        self.assertEqual((estado, resumen.altas), ("simulacion", 4))
        self.assertEqual(self.uno("SELECT count(*) FROM tramite")[0], 0)

        # v1: carga inicial.
        _, estado, r = correr(self.url, "tad_v1")
        self.assertEqual((estado, r.altas, r.cambios, r.bajas), ("ok", 4, 0, 0))
        self.assertEqual(r.max_fecha_publicacion.isoformat(), "2026-02-20")
        self.assertEqual(self.uno("SELECT organismo_sigla FROM v_tramite_tad WHERE id_tad = 9002")[0], "ARCA")
        self.assertEqual(self.uno("SELECT organismo_sigla FROM v_tramite_tad WHERE id_tad = 9003")[0], "RENAR")
        self.assertCountEqual(r.organismos_nuevos, ["Ministerio de Relaciones Exteriores",
                                                    "Ente Nacional de Comunicaciones"])
        self.assertEqual(self.uno("SELECT count(*) FROM v_organismo_a_revisar")[0], 2)
        self.assertEqual(self.costos(9003), [(False, Decimal("1795500.00"), True)])
        self.assertEqual(self.costos(9002), [(True, None, True)])
        self.assertEqual(self.canales(9001), {"tad": True, "mi_argentina": True})
        self.assertEqual(self.canales(9002), {"tad": True, "vuce": True})
        metodos = [m for (m,) in self.todos(
            """SELECT a.metodo FROM canal_autenticacion a JOIN canal c ON c.id = a.canal_id
               JOIN fuente f ON f.id = c.fuente_id WHERE f.id_externo = '9003' ORDER BY 1""")]
        self.assertEqual(metodos, ["clave_fiscal", "css_anses", "dni_tramite", "mi_argentina"])
        self.assertTrue(any("Firma remota" in a for a in r.advertencias))

        # v1 otra vez: idempotente.
        _, _, r = correr(self.url, "tad_v1")
        self.assertEqual((r.altas, r.cambios, r.bajas, r.sin_cambios), (0, 0, 0, 4))

        # v2: cambio de arancel, cambio de nombre, una baja, un alta; falta el CSV de Mi Argentina.
        _, _, r = correr(self.url, "tad_v2")
        self.assertEqual((r.altas, r.cambios, r.bajas, r.sin_cambios), (1, 2, 1, 1))
        self.assertEqual(self.costos(9001), [(False, Decimal("4500.00"), False), (False, Decimal("6000.00"), True)])
        self.assertEqual(self.estado_tramite(9002), "baja")
        self.assertEqual(self.canales(9002), {"tad": False, "vuce": False})
        # Sin el CSV de Mi Argentina, el canal se conserva.
        self.assertEqual(self.canales(9001), {"tad": True, "mi_argentina": True})
        self.assertEqual(
            self.uno("SELECT nombre_oficial FROM tramite t JOIN fuente f ON f.tramite_id = t.id "
                     "WHERE f.id_externo = '9004'")[0],
            "Licencia TIC para personas humanas (fixture)",
        )
        diferencias = self.uno(
            """SELECT e.diferencias FROM fuente_evento e JOIN fuente f ON f.id = e.fuente_id
               WHERE f.id_externo = '9001' AND e.evento = 'cambio'""")[0]
        self.assertEqual(set(diferencias), {"pago_minimo", "pago_maximo", "pago_promedio"})

        # v3: CSV truncado. No registra bajas masivas.
        _, _, r = correr(self.url, "tad_v3")
        self.assertEqual(r.bajas, 0)
        self.assertTrue(any("--forzar-bajas" in a for a in r.advertencias))
        self.assertEqual(self.estado_tramite(9003), "vigente")

        # v1 de nuevo: 9002 reaparece y 9005 se da de baja.
        _, _, r = correr(self.url, "tad_v1")
        self.assertEqual((r.reapariciones, r.bajas), (1, 1))
        self.assertEqual(self.estado_tramite(9002), "vigente")
        self.assertEqual(self.estado_tramite(9005), "baja")

        corridas = self.todos("SELECT estado FROM ingesta_corrida ORDER BY id")
        self.assertEqual([e for (e,) in corridas], ["simulacion", "ok", "ok", "ok", "ok", "ok"])


if __name__ == "__main__":
    unittest.main()
