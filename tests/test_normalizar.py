import unittest
from datetime import date
from decimal import Decimal

from ingesta import normalizar as n


class MontoTest(unittest.TestCase):
    def test_formatos(self):
        casos = {
            "1.795.500.00": Decimal("1795500.00"),  # formato roto del CSV 26.2
            "4.500.00": Decimal("4500.00"),
            "1.234,56": Decimal("1234.56"),
            "1,234.56": Decimal("1234.56"),
            "1.500": Decimal("1500"),
            "12.345.678": Decimal("12345678"),
            "1500.5": Decimal("1500.5"),
            "$ 2.400": Decimal("2400"),
            "0": Decimal("0"),
            "1500.": Decimal("1500"),
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(n.monto(entrada), esperado)

    def test_vacios(self):
        for entrada in ("", "  ", "-", None):
            self.assertIsNone(n.monto(entrada))

    def test_invalido(self):
        with self.assertRaises(ValueError):
            n.monto("a convenir")


class CamposTest(unittest.TestCase):
    def test_fecha(self):
        self.assertEqual(n.fecha("2026-02-15"), date(2026, 2, 15))
        self.assertEqual(n.fecha("2026-02-15 10:30:00"), date(2026, 2, 15))
        self.assertEqual(n.fecha("15/02/2026"), date(2026, 2, 15))
        self.assertIsNone(n.fecha(""))
        with self.assertRaises(ValueError):
            n.fecha("febrero")

    def test_booleano(self):
        self.assertTrue(n.booleano("SI"))
        self.assertTrue(n.booleano("Sí"))
        self.assertFalse(n.booleano("no"))
        self.assertIsNone(n.booleano(""))
        with self.assertRaises(ValueError):
            n.booleano("quizás")

    def test_validadores(self):
        self.assertEqual(
            n.validadores("DNI,Mi argentina,ANSES,AFIP"),
            [("dni_tramite", "DNI"), ("mi_argentina", "Mi argentina"), ("css_anses", "ANSES"),
             ("clave_fiscal", "AFIP")],
        )
        self.assertEqual(n.validadores("Firma remota"), [("otro", "Firma remota")])
        self.assertEqual(n.validadores("NIC-AFIP"), [("nic_no_residente", "NIC-AFIP"), ("clave_fiscal", "NIC-AFIP")])
        registro, _ = n.normalizar_fila({"ID_TRAMITE": "425", "VALIDADOR_IDENTIDAD": "NIC-AFIP"})
        self.assertEqual(registro["validadores"], ["NIC-AFIP"])
        self.assertEqual(n.validadores(""), [])

    def test_slugify(self):
        self.assertEqual(n.slugify("Credencial de Legítimo Usuario (CLU)"), "credencial-de-legitimo-usuario-clu")


class LeerCsvTest(unittest.TestCase):
    def test_encabezados_alternativos_punto_y_coma_y_cp1252(self):
        contenido = "Id Trámite;Nombre trámite;Órgano rector\n10;Inscripción;AFIP\n\n".encode("cp1252")
        columnas, filas = n.leer_csv(contenido)
        self.assertEqual(columnas, ["ID_TRAMITE", "NOMBRE_TRAMITE", "ORGANO_RECTOR"])
        self.assertEqual(filas, [{"ID_TRAMITE": "10", "NOMBRE_TRAMITE": "Inscripción", "ORGANO_RECTOR": "AFIP"}])

    def test_utf16_con_tabulaciones(self):
        contenido = "ID_TRAMITE\tNOMBRE_TRAMITE\r\n6174\tInscripción\r\n".encode("utf-16")
        columnas, filas = n.leer_csv(contenido)
        self.assertEqual(columnas, ["ID_TRAMITE", "NOMBRE_TRAMITE"])
        self.assertEqual(filas, [{"ID_TRAMITE": "6174", "NOMBRE_TRAMITE": "Inscripción"}])

    def test_bom_y_comillas(self):
        contenido = '﻿ID_TRAMITE,VALIDADOR_IDENTIDAD\n7,"DNI,AFIP"\n'.encode("utf-8")
        _, filas = n.leer_csv(contenido)
        self.assertEqual(filas[0]["VALIDADOR_IDENTIDAD"], "DNI,AFIP")

    def test_normalizar_fila(self):
        registro, advertencias = n.normalizar_fila({
            "ID_TRAMITE": "9003", "NOMBRE_TRAMITE": "  Credencial  CLU ", "FECHA_PUBLICACION_PROD": "ayer",
            "MARCA_ARANCELADO": "SI", "PAGO_MINIMO": "1.795.500.00",
        })
        self.assertEqual(registro["nombre"], "Credencial CLU")
        self.assertIsNone(registro["fecha_publicacion"])
        self.assertEqual(registro["pago_minimo"], Decimal("1795500.00"))
        self.assertEqual(len(advertencias), 1)

    def test_fila_sin_id(self):
        registro, advertencias = n.normalizar_fila({"NOMBRE_TRAMITE": "x"})
        self.assertIsNone(registro)
        self.assertTrue(advertencias)


class HashTest(unittest.TestCase):
    def test_estable_ante_orden_y_formato_decimal(self):
        a = {"x": Decimal("4500"), "y": date(2026, 1, 1)}
        b = {"y": date(2026, 1, 1), "x": Decimal("4500.00")}
        self.assertEqual(n.hash_registro(a), n.hash_registro(b))


if __name__ == "__main__":
    unittest.main()
