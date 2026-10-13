"""Base temporal para tests de integración: la crea con los SQL de db/ y la borra al final.
Necesita un Postgres accesible en TEST_ADMIN_URL (por defecto, el de docker-compose.yml);
si no hay, los tests se saltean.
"""

import os
import unittest
import uuid
from pathlib import Path

import psycopg2

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://tramites:tramites@localhost:5433/postgres")
SQL_INICIAL = ("schema.sql", "seed.sql", "organismos_apn.sql")


class BaseDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            admin = psycopg2.connect(ADMIN_URL, connect_timeout=3)
        except psycopg2.OperationalError as e:
            raise unittest.SkipTest(f"sin Postgres en {ADMIN_URL}: {e}")
        admin.autocommit = True
        cls.nombre_db = f"tramites_test_{uuid.uuid4().hex[:8]}"
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {cls.nombre_db}")
        admin.close()
        cls.url = ADMIN_URL.rsplit("/", 1)[0] + "/" + cls.nombre_db
        cls.conn = psycopg2.connect(cls.url)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            for archivo in SQL_INICIAL:
                cur.execute((RAIZ / "db" / archivo).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        admin = psycopg2.connect(ADMIN_URL)
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE {cls.nombre_db} WITH (FORCE)")
        admin.close()

    def uno(self, sql, *params):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or None)
            return cur.fetchone()

    def todos(self, sql, *params):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or None)
            return cur.fetchall()
