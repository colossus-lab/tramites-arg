import unittest
from decimal import Decimal

from ingesta.extraer_html import costos, requisitos


def textos(html):
    return [(r.descripcion, r.seccion, r.obligatorio) for r in requisitos(html)]


class RequisitosTest(unittest.TestCase):
    def test_titulo_y_listas_obligatoria_y_opcional(self):
        html = """
        <p><strong>Documentación obligatoria</strong></p>
        <ul><li>Estatuto social.</li><li>Constancia de CUIT.</li></ul>
        <p><strong>Documentación opcional</strong></p>
        <ul><li>Poder del representante.</li></ul>
        <p><strong>¿Cómo hago?</strong></p>
        <ul><li>Ingresá a TAD con tu clave fiscal.</li></ul>
        """
        self.assertEqual(textos(html), [
            ("Estatuto social.", "Documentación obligatoria", True),
            ("Constancia de CUIT.", "Documentación obligatoria", True),
            ("Poder del representante.", "Documentación opcional", False),
        ])

    def test_parrafos_sin_vinetas_y_notas(self):
        html = """
        <p>Te explicamos cómo tramitar el certificado.</p>
        <p><strong>Requisitos:</strong></p>
        <p>Ser mayor de 18 años de edad.</p>
        <p>Certificado médico de aptitud psicofísica.</p>
        <p>Para más información escribí a consultas@ejemplo.gob.ar</p>
        <p>El trámite es gratuito.</p>
        <p>Nota:</p>
        <p>Demora 20 días hábiles.</p>
        """
        r = requisitos(html)
        self.assertEqual([x.descripcion for x in r],
                         ["Ser mayor de 18 años de edad.", "Certificado médico de aptitud psicofísica."])
        self.assertEqual([x.tipo for x in r], ["condicion", "documento"])

    def test_sublista_bajo_item_y_pasos_de_plataforma(self):
        html = """
        <p>Para llevar adelante el trámite se deberá:</p>
        <ol>
          <li>Completar los Datos del Trámite.</li>
          <li>Subir la siguiente documentación obligatoria:
            <ul><li>Partitura.</li><li>Comprobante de pago de la tasa.</li></ul>
          </li>
        </ol>
        """
        r = requisitos(html)
        self.assertEqual([(x.descripcion, x.tipo) for x in r],
                         [("Partitura.", "documento"), ("Comprobante de pago de la tasa.", "pago_previo")])
        self.assertEqual(r[0].seccion, "Subir la siguiente documentación obligatoria")

    def test_vinetas_con_br_y_saltos_en_medio_de_la_oracion(self):
        html = """<p><b>Se debe adjuntar al trámite:</b></p>
        <p>• Nota de solicitud firmada por el
        titular.<br>• Copia de la habilitación <strong>municipal</strong> vigente.</p>"""
        self.assertEqual([x.descripcion for x in requisitos(html)],
                         ["Nota de solicitud firmada por el titular.", "Copia de la habilitación municipal vigente."])

    def test_frase_que_anuncia_documentos(self):
        html = """<p>Antes de iniciar, tené digitalizados los documentos detallados en la Resolución 1/2020.</p>
        <p>Estatuto de constitución de la sociedad.</p><p>Estados contables de los dos últimos ejercicios.</p>"""
        self.assertEqual(len(requisitos(html)), 2)

    def test_seccion_de_pasos_no_es_requisito(self):
        html = """<p>Para realizar el trámite deberá realizar los siguientes pasos:</p>
        <p>1. Confirme sus datos.</p><p>2. Adjunte la documentación.</p>"""
        self.assertEqual(requisitos(html), [])

    def test_html_vacio(self):
        self.assertEqual(requisitos(None), [])
        self.assertEqual(costos(""), [])


class CostosTest(unittest.TestCase):
    def test_arancel_en_oracion(self):
        [c] = costos("<p>El arancel es de $45.000 por cada profesional. El pago debe hacerse por VEP.</p>")
        self.assertEqual((c.gratuito, c.unidad, c.monto_min, c.monto_max), (False, "ARS", Decimal("45000"),
                                                                           Decimal("45000")))
        self.assertIn("por cada profesional", c.detalle)

    def test_seccion_de_costo_sin_palabra_clave(self):
        html = "<p><strong>¿Cuál es el costo del trámite?</strong></p><p>$ 1.500,50 habilitación; $ 3.000 renovación.</p>"
        [c] = costos(html)
        self.assertEqual((c.monto_min, c.monto_max), (Decimal("1500.50"), Decimal("3000")))

    def test_montos_que_no_son_costos(self):
        html = """<p>Se otorgan créditos de $1.000.000 con tasa bonificada.</p>
        <p>Tope máximo de ingreso del grupo familiar: $ 83.000.</p>
        <p>El monto máximo es de $11 millones para cooperativas.</p>"""
        self.assertEqual(costos(html), [])

    def test_gratuito_y_dolares(self):
        self.assertTrue(costos("<p>Este trámite es gratuito.</p>")[0].gratuito)
        [usd] = costos("<p>Tasa por buque con patente: U$S 100,00 por conexión.</p>")
        self.assertEqual((usd.unidad, usd.monto_min), ("USD", Decimal("100.00")))


if __name__ == "__main__":
    unittest.main()
