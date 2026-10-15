import unittest

from ingesta.destinatarios import destinatarios


class DestinatariosTest(unittest.TestCase):
    def test_persona_humana_y_juridica(self):
        self.assertEqual(destinatarios("Licencias TIC - Obtención de Licencia (Personas Humanas)", [], "telecomunicaciones"),
                         {"pf_ciudadano": "palabra_clave"})
        self.assertEqual(destinatarios("Licencias TIC - Obtención de Licencia (Personas Jurídicas)", [], "telecomunicaciones"),
                         {"empresa": "palabra_clave"})

    def test_organismo_publico_es_exclusivo(self):
        self.assertEqual(destinatarios("PLN - Pedido de Informes Parlamentarios", [], None),
                         {"organismo_publico": "palabra_clave"})
        self.assertEqual(destinatarios("Firma Digital Cese Autoridad de Registro AC-ONTI", ["AFIP"], None),
                         {"organismo_publico": "palabra_clave"})

    def test_falsos_positivos(self):
        self.assertNotIn("pf_extranjero_residente", destinatarios("Plan de erradicación de brucelosis bovina", [], "agro"))
        self.assertNotIn("pf_extranjero_residente", destinatarios("Habilitación de Residencia Asistida", [], None))
        self.assertNotIn("profesional", destinatarios("Registro Nacional de Buques - Inscripción Matrícula Nacional", [], None))

    def test_categoria_y_validador(self):
        self.assertEqual(destinatarios("Reclamo de Acceso a la Información Pública", ["NIC-AFIP"], "transversal"),
                         {"pf_ciudadano": "palabra_clave", "pf_no_residente": "validador"})
        self.assertEqual(destinatarios("Certificado X", [], "comercio_exterior"), {"empresa": "categoria"})
        self.assertEqual(destinatarios("Certificado X", [], "salud"), {})
        self.assertEqual(destinatarios("Resoluciones varias", [], "gestion_publica"), {"organismo_publico": "categoria"})

    def test_texto_dirigido_de_la_ficha(self):
        # El cargador concatena el nombre y el "¿A quién está dirigido?" de la ficha.
        self.assertEqual(destinatarios("Obtener duplicado A cualquier persona interesada, mayor de 15 años.", [], None),
                         {"pf_ciudadano": "palabra_clave"})
        self.assertEqual(destinatarios("Habilitación Todo establecimiento elaborador de alimentos", [], None),
                         {"empresa": "palabra_clave"})
        self.assertEqual(set(destinatarios("Registro Personas físicas o jurídicas.", [], None)), {"pf_ciudadano", "empresa"})
        self.assertNotIn("pf_ciudadano", destinatarios("Licencia (Personas Jurídicas)", [], None))


if __name__ == "__main__":
    unittest.main()
