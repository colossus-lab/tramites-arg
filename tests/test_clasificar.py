import unittest

from ingesta.clasificar import clasificar


class ClasificarTest(unittest.TestCase):
    def test_prioridades(self):
        # El nombre de comercio exterior gana sobre el organismo.
        self.assertEqual(clasificar("Autorización de Importación de Alimentos", "SENASA", "MECON", []),
                         ("comercio_exterior", "comercio_exterior"))
        self.assertEqual(clasificar("Inscripción RENSPA", "SENASA", "MECON", []), ("agro", "organismo"))
        self.assertEqual(clasificar("Solicitud de Personería Gremial", "MCH", "MCH", []), ("trabajo", "palabra_clave"))
        self.assertEqual(clasificar("Trámite X", "JGM", "JGM", ["Derecho de autor"]),
                         ("propiedad_intelectual", "etiqueta"))

    def test_proveedores_del_estado_no_son_organizaciones(self):
        self.assertEqual(clasificar("SIPRO Inscripción Proveedor – Cooperativas, Mutuales", "JGM", "JGM", [])[0],
                         "empresas")

    def test_ministerio_solo_para_el_ministerio_mismo(self):
        self.assertEqual(clasificar("Autorización para microfilmar", "MSAL", "MSAL", []), ("salud", "ministerio"))
        self.assertEqual(clasificar("Mesa de entradas virtual", "CNEA", "MECON", []), (None, None))

    def test_etiqueta_vuce_no_clasifica(self):
        self.assertEqual(clasificar("Registro de poseedores de PCB", "JGM", "JGM",
                                    ["Ventanilla Única de Comercio Exterior - VUCE"]), (None, None))


if __name__ == "__main__":
    unittest.main()
