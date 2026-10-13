"""Exportación para la web: sanitización del HTML y que no salga ningún campo interno."""

import importlib.util
import json
import re
import unittest
from argparse import Namespace

from ingesta import tad, tad_detalle
from tests.base_db import FIXTURES, RAIZ, BaseDB

spec = importlib.util.spec_from_file_location("exportar_web", RAIZ / "scripts" / "exportar_web.py")
exportar_web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exportar_web)


class SanitizarTest(unittest.TestCase):
    def test_lista_blanca_y_links(self):
        html = ('<div style="x"><h2>Título</h2><script>alert(1)</script><p onclick="x">Hola <a href="/servicio/y">link</a>'
                ' <a href="javascript:alert(1)">malo</a></p><img src="x.png"><p> </p></div>')
        limpio = exportar_web.sanitizar(html)
        self.assertNotIn("script", limpio)
        self.assertNotIn("onclick", limpio)
        self.assertNotIn("style", limpio)
        self.assertNotIn("javascript", limpio)
        self.assertNotIn("<img", limpio)
        self.assertIn('<h3>Título</h3>', limpio)
        self.assertIn('href="https://www.argentina.gob.ar/servicio/y"', limpio)
        self.assertEqual(limpio.count("<p>"), 1)


class ExportarTest(BaseDB):
    def test_solo_campos_publicos(self):
        resumen = tad.Resumen()
        tad.ejecutar(tad.leer_directorio(FIXTURES / "tad_v1", resumen), self.url, resumen=resumen)
        tad_detalle.cargar(Namespace(database_url=self.url, carpeta=FIXTURES / "tad_detalle", dry_run=False))
        with self.conn.cursor() as cur:
            tramites, organismos, por_id, raiz = exportar_web.exportar(cur)
            agregados = exportar_web.agregar(tramites, organismos, por_id, raiz, cur)
        self.assertEqual(len(tramites), 4)
        texto = json.dumps(tramites, default=str)
        for prohibido in ('"hash', '"datos"', "tramite_id", "fuente_id", "corrida"):
            self.assertNotIn(prohibido, texto)
        # Ningún UUID interno (los ids públicos son slugs y números de TAD).
        self.assertIsNone(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", texto))
        for t in tramites:
            self.assertLessEqual(set(t), exportar_web.CAMPOS_TRAMITE)
        self.assertEqual(agregados["totales"]["tramites"], 4)
