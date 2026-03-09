"""
Testes unitarios para o modulo db.py – repositorios SQLite.

Cobre: criacao de schema, CRUD de usuarios, gerencias e supervisoes,
consultas com JOINs, e migracao de colunas.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.db import Database, GerenciaRepository, SupervisaoRepository, UserRepository

# Path sentinela para in-memory, nunca sera usado de fato
_MEMORY = Path(":memory:")


class InMemoryDatabase(Database):
    """Database que usa SQLite in-memory para testes (evita locks no Windows)."""

    def __init__(self):
        super().__init__(_MEMORY)
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    def connect(self):
        return self._conn


class TestDatabase(unittest.TestCase):
    """Testes para a classe Database."""

    def setUp(self):
        self.db = InMemoryDatabase()

    def test_init_schema_creates_tables(self):
        self.db.init_schema()
        conn = self.db.connect()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        self.assertIn("users", table_names)
        self.assertIn("gerencias", table_names)
        self.assertIn("supervisoes", table_names)

    def test_init_schema_idempotent(self):
        self.db.init_schema()
        self.db.init_schema()  # Nao deve falhar

    def test_ensure_column_added(self):
        self.db.init_schema()
        conn = self.db.connect()
        cols = conn.execute("PRAGMA table_info(users)").fetchall()
        col_names = {c["name"] for c in cols}
        self.assertIn("gerencia_id", col_names)
        self.assertIn("supervisao_id", col_names)
        self.assertIn("must_change_password", col_names)


class TestUserRepository(unittest.TestCase):
    """Testes para UserRepository."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = UserRepository(self.db)

    def test_count_users_empty(self):
        self.assertEqual(self.repo.count_users(), 0)

    def test_create_and_get_user(self):
        uid = self.repo.create_user("joao", "hash", "salt", "fiscal", 1, 1, True, "12345")
        self.assertGreater(uid, 0)
        user = self.repo.get_user_by_id(uid)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "joao")
        self.assertEqual(user["role"], "fiscal")
        self.assertEqual(user["matricula"], "12345")

    def test_get_user_by_username(self):
        self.repo.create_user("maria", "hash", "salt", "supervisor", None, None, False, "54321")
        user = self.repo.get_user_by_username("maria")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "maria")

    def test_get_nonexistent_user(self):
        self.assertIsNone(self.repo.get_user_by_id(999))
        self.assertIsNone(self.repo.get_user_by_username("naoexiste"))

    def test_list_users(self):
        self.repo.create_user("a", "h", "s", "fiscal", None, None, False, "001")
        self.repo.create_user("b", "h", "s", "supervisor", None, None, False, "002")
        users = self.repo.list_users()
        self.assertEqual(len(users), 2)

    def test_update_password(self):
        uid = self.repo.create_user("x", "old_hash", "old_salt", "fiscal", None, None, False, "003")
        self.repo.update_password(uid, "new_hash", "new_salt")
        user = self.repo.get_user_by_id(uid)
        self.assertEqual(user["password_hash"], "new_hash")
        self.assertEqual(user["salt"], "new_salt")

    def test_set_must_change_password(self):
        uid = self.repo.create_user("y", "h", "s", "fiscal", None, None, False, "004")
        self.repo.set_must_change_password(uid, True)
        user = self.repo.get_user_by_id(uid)
        self.assertTrue(user["must_change_password"])

    def test_update_user(self):
        uid = self.repo.create_user("z", "h", "s", "fiscal", None, None, False, "005")
        self.repo.update_user(uid, "z_novo", "supervisor", 1, 1, "005_novo")
        user = self.repo.get_user_by_id(uid)
        self.assertEqual(user["username"], "z_novo")
        self.assertEqual(user["role"], "supervisor")
        self.assertEqual(user["matricula"], "005_novo")

    def test_duplicate_username_raises(self):
        self.repo.create_user("dup", "h", "s", "fiscal", None, None, False, "006")
        with self.assertRaises(Exception):
            self.repo.create_user("dup", "h", "s", "fiscal", None, None, False, "007")

    def test_delete_user(self):
        uid = self.repo.create_user("del_me", "h", "s", "fiscal", None, None, False, "DEL1")
        self.assertTrue(self.repo.delete_user(uid))
        self.assertIsNone(self.repo.get_user_by_id(uid))

    def test_delete_nonexistent_user(self):
        self.assertFalse(self.repo.delete_user(99999))

    def test_get_supervisor_matriculas_by_gerencia(self):
        # Cria gerencia primeiro no DB
        ger_repo = GerenciaRepository(self.db)
        gid = ger_repo.create_gerencia("Test Ger")
        self.repo.create_user("sup1", "h", "s", "supervisor", gid, None, False, "S01")
        self.repo.create_user("sup2", "h", "s", "supervisor", gid, None, False, "S02")
        self.repo.create_user("fiscal1", "h", "s", "fiscal", gid, None, False, "F01")

        matriculas = self.repo.get_supervisor_matriculas_by_gerencia(gid)
        self.assertEqual(set(matriculas), {"S01", "S02"})


class TestGerenciaRepository(unittest.TestCase):
    """Testes para GerenciaRepository."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = GerenciaRepository(self.db)

    def test_create_and_list(self):
        gid = self.repo.create_gerencia("Gerencia X")
        self.assertGreater(gid, 0)
        gerencias = self.repo.list_gerencias()
        self.assertEqual(len(gerencias), 1)
        self.assertEqual(gerencias[0]["name"], "Gerencia X")

    def test_get_gerencia(self):
        gid = self.repo.create_gerencia("Gerencia Y")
        g = self.repo.get_gerencia(gid)
        self.assertIsNotNone(g)
        self.assertEqual(g["name"], "Gerencia Y")

    def test_get_nonexistent(self):
        self.assertIsNone(self.repo.get_gerencia(999))

    def test_update_gerencia(self):
        gid = self.repo.create_gerencia("Antigo")
        self.repo.update_gerencia(gid, "Novo")
        g = self.repo.get_gerencia(gid)
        self.assertEqual(g["name"], "Novo")


class TestSupervisaoRepository(unittest.TestCase):
    """Testes para SupervisaoRepository."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.ger_repo = GerenciaRepository(self.db)
        self.repo = SupervisaoRepository(self.db)
        self.gid = self.ger_repo.create_gerencia("Ger Test")

    def test_create_and_list(self):
        sid = self.repo.create_supervisao("Sup A", self.gid)
        self.assertGreater(sid, 0)
        sups = self.repo.list_supervisoes()
        self.assertEqual(len(sups), 1)
        self.assertEqual(sups[0]["name"], "Sup A")
        self.assertEqual(sups[0]["gerencia_name"], "Ger Test")

    def test_list_by_gerencia(self):
        gid2 = self.ger_repo.create_gerencia("Ger 2")
        self.repo.create_supervisao("Sup 1", self.gid)
        self.repo.create_supervisao("Sup 2", gid2)
        sups = self.repo.list_supervisoes(gerencia_id=self.gid)
        self.assertEqual(len(sups), 1)
        self.assertEqual(sups[0]["name"], "Sup 1")

    def test_get_supervisao(self):
        sid = self.repo.create_supervisao("Sup B", self.gid)
        s = self.repo.get_supervisao(sid)
        self.assertIsNotNone(s)
        self.assertEqual(s["name"], "Sup B")
        self.assertEqual(s["gerencia_id"], self.gid)

    def test_update_supervisao(self):
        gid2 = self.ger_repo.create_gerencia("Ger 2")
        sid = self.repo.create_supervisao("Sup C", self.gid)
        self.repo.update_supervisao(sid, "Sup C Novo", gid2)
        s = self.repo.get_supervisao(sid)
        self.assertEqual(s["name"], "Sup C Novo")
        self.assertEqual(s["gerencia_id"], gid2)


if __name__ == "__main__":
    unittest.main()
