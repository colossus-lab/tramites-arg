import unittest

from ingesta.clasificar import clasificar, naturaleza


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
        self.assertEqual(clasificar("Autorización de impresión", "IGN", "MECON", []), (None, None))

    def test_etiqueta_vuce_no_clasifica(self):
        self.assertEqual(clasificar("Certificaciones - Consultas legales", "JGM", "JGM",
                                    ["Ventanilla Única de Comercio Exterior - VUCE"]), (None, None))


    def test_energia_y_ciencia(self):
        self.assertEqual(clasificar("Registro de Comercializadores", "ENREGE", "MECON", []), ("energia", "organismo"))
        self.assertEqual(clasificar("Permiso de exploración de hidrocarburos", "MECON", "MECON", []),
                         ("energia", "palabra_clave"))
        self.assertEqual(clasificar("Recurso - Carrera del investigador", "CONICET", "JGM", []),
                         ("ciencia_tecnologia", "organismo"))
        self.assertEqual(clasificar("Inscripción de usuarios ante el ROECyT", "JGM", "JGM", []),
                         ("ciencia_tecnologia", "palabra_clave"))
        self.assertEqual(clasificar("Informe anual de Universidades Privadas", "MCH", "MCH", [])[0], "educacion")

    def test_categorias_de_las_fichas(self):
        self.assertEqual(clasificar("PLN - Pedido de Informes Parlamentarios", "JGM", "JGM", [])[0], "gestion_publica")
        self.assertEqual(clasificar("Firma Digital Cese Autoridad de Registro AC-ONTI", "JGM", "JGM", [])[0],
                         "gestion_publica")
        self.assertEqual(clasificar("Solicitar Firma Digital Remota sin Token", "JGM", "JGM", [])[0], "transversal")
        self.assertEqual(clasificar("DNI exprés", "JGM", "JGM", [])[0], "identidad")
        self.assertEqual(clasificar("Renovación del fondo de garantía de una agencia de viajes", "JGM", "JGM", [])[0],
                         "turismo_deporte")
        # Náutica deportiva sigue en transporte; asignaciones de ANSES van a programas sociales.
        self.assertEqual(clasificar("Renovar el certificado náutico deportivo", "PNA", "MSN", [])[0], "transporte")
        self.assertEqual(clasificar("Tramitar la Ayuda Escolar Anual", "ANSES", "MCH", []),
                         ("programas_sociales", "palabra_clave"))
        self.assertEqual(clasificar("Tramitar Informe N° 2 - Inhibiciones", "RPI", "MJ", []), ("propiedad", "organismo"))


class NaturalezaTest(unittest.TestCase):
    def test_consultas_no_son_tramites(self):
        for nombre in ("Consultar el padrón electoral", "Consultar el calendario de pagos de ANSES",
                       "Consulta de infracciones de tránsito", "Validá los documentos electrónicos firmados digitalmente",
                       "Simulá tu crédito COMEX"):
            self.assertEqual(naturaleza(nombre), "consulta", nombre)

    def test_consultas_formales_y_solicitudes_si(self):
        for nombre in ("Consulta de clasificación de Productos", "Consultas Técnicas de Reglamentos Técnicos",
                       "Consulta Pública Sobre Comunicaciones M2M", "Consultar por conflicto de intereses en la función pública",
                       "Solicitar certificado de antecedentes penales", "Verificación de importación"):
            self.assertEqual(naturaleza(nombre), "tramite", nombre)

if __name__ == "__main__":
    unittest.main()
