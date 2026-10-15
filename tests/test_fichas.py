"""Parser y carga de fichas de argentina.gob.ar con fichas sintéticas."""

import unittest
from argparse import Namespace
from decimal import Decimal

from ingesta import fichas, tad
from tests.base_db import FIXTURES, BaseDB


def leer(nombre):
    return (FIXTURES / "fichas" / f"{nombre}.html").read_text(encoding="utf-8")


class ParserTest(unittest.TestCase):
    def test_secciones_migas_y_tad(self):
        d = fichas.parsear(leer("apostilla-fixture"))
        self.assertEqual(d["nombre"], "Apostillar documentos (fixture)")
        self.assertEqual(d["migas"], ["Ministerio de Relaciones Exteriores"])
        self.assertEqual(d["ids_tad"], [9001])
        self.assertEqual(d["actualizado"], "2026-05-04")
        requisitos, costos = fichas.requisitos_y_costos(d)
        self.assertEqual([r.descripcion for r in requisitos], ["Documento público original.", "Clave fiscal nivel 2."])
        self.assertEqual((costos[0].gratuito, costos[0].monto_min), (False, Decimal("4500")))

    def test_canales_y_gratuito(self):
        d = fichas.parsear(leer("registro-de-musicos-fixture"))
        self.assertEqual(d["inicio"], ["https://inamu.musica.ar/registro"])  # sin redes sociales
        self.assertEqual([(c["modalidad"], c.get("requiere_turno")) for c in fichas.canales(d)],
                         [("online", None), ("presencial", True)])
        self.assertTrue(fichas.requisitos_y_costos(d)[1][0].gratuito)
        self.assertEqual(d["dirigido"], "Músicos y músicas profesionales.")

    def test_canales_desde_el_texto(self):
        def modos(como):
            datos = {"inicio": [], "secciones": {"como": f"<p>{como}</p>"}}
            return [(c["modalidad"], c.get("plataforma"), c.get("detalle")) for c in fichas.canales(datos)]

        self.assertEqual(modos("Ingresá a TAD, trámite “Reforma de estructura”, con clave fiscal."),
                         [("online", "tad", None)])
        self.assertEqual(modos("Envianos un correo electrónico con el asunto “Asistencia”."),
                         [("online", None, "por correo electrónico")])
        # Un mail solo para consultas no es el canal del trámite.
        self.assertEqual(modos("Presentá la documentación en la Mesa de Entradas. Por consultas: correo electrónico x"),
                         [("presencial", None, None)])
        self.assertEqual(modos("Completá el formulario en la plataforma Agenciar."), [("online", None, None)])


class CargaTest(BaseDB):
    def test_vincula_por_tad_y_crea_organismo_y_tramite(self):
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v1", resumen), self.url, resumen=resumen)
        args = Namespace(database_url=self.url, carpeta=FIXTURES / "fichas", dry_run=False)
        fichas.cargar(args)

        # La ficha con link a TAD 9001 se suma al trámite existente, no crea otro.
        tad_9001 = self.uno("SELECT tramite_id FROM v_tramite_tad WHERE id_tad = 9001")[0]
        self.assertEqual(self.uno("SELECT tramite_id FROM fuente WHERE id_externo = 'apostilla-fixture'")[0], tad_9001)
        self.assertEqual(self.uno("SELECT monto_min FROM costo WHERE tramite_id = %s AND concepto = %s",
                                  tad_9001, fichas.CONCEPTO_COSTO)[0], 4500)
        # La otra crea el trámite en INAMU (organismo del seed, encontrado por la sigla de la miga),
        # con canal presencial con turno.
        nuevo = self.uno("""SELECT t.id, o.nombre_oficial, o.sigla, o.revisar FROM tramite t
                            JOIN organismo o ON o.id = t.organismo_id WHERE t.slug = 'registro-de-musicos-fixture-ficha'""")
        self.assertEqual(nuevo[1:], ("Instituto Nacional de la Música", "INAMU", False))
        self.assertEqual(self.uno("SELECT requiere_turno FROM canal WHERE tramite_id = %s AND modalidad = 'presencial'",
                                  nuevo[0])[0], True)

        # Segunda corrida: nada cambia.
        fichas.cargar(args)
        self.assertEqual(self.uno("SELECT sin_cambios, altas FROM ingesta_corrida ORDER BY id DESC LIMIT 1"), (2, 0))
        self.assertEqual(self.uno("SELECT count(*) FROM tramite WHERE slug LIKE '%-ficha'")[0], 1)
