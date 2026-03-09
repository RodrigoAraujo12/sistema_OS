"""
db.py – Camada de acesso a dados (SQLite) do Sistema Sefaz.

Contem:
- Database: gerencia conexoes e inicializacao do schema
- UserRepository: CRUD de usuarios
- GerenciaRepository: CRUD de gerencias
- SupervisaoRepository: CRUD de supervisoes

O banco fica em backend/app.db. A estrutura e criada automaticamente
no primeiro uso via Database.init_schema().
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("sefaz.db")

DB_PATH = Path(__file__).parent / "app.db"


class Database:
    """Gerencia a conexao SQLite e a criacao/migracao do schema."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def connect(self) -> sqlite3.Connection:
        """Abre uma conexao com row_factory = sqlite3.Row (acesso por nome)."""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Cria as tabelas (se nao existirem) e adiciona colunas novas."""
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    matricula TEXT UNIQUE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gerencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS supervisoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gerencia_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    FOREIGN KEY (gerencia_id) REFERENCES gerencias (id)
                )
                """
            )
        # Colunas adicionadas apos a versao inicial (migracao simples)
        self._ensure_column("users", "gerencia_id", "INTEGER")
        self._ensure_column("users", "supervisao_id", "INTEGER")
        self._ensure_column("users", "must_change_password", "INTEGER DEFAULT 0")
        logger.info("Schema do banco inicializado com sucesso.")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """Adiciona uma coluna a tabela apenas se ainda nao existir (migracao segura)."""
        with self.connect() as conn:
            existing = conn.execute(f"PRAGMA table_info({table})").fetchall()
            columns = {row["name"] for row in existing}
            if column in columns:
                return
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.debug("Coluna '%s' adicionada a tabela '%s'.", column, table)


class UserRepository:
    """Repositorio de usuarios – CRUD completo com JOINs para gerencia/supervisao."""

    # Query base reutilizada por get_user_by_username e get_user_by_id
    _USER_SELECT = """
        SELECT u.id, u.username, u.password_hash, u.salt, u.role, u.matricula,
            u.gerencia_id, g.name AS gerencia_name,
            u.supervisao_id, s.name AS supervisao_name,
            u.must_change_password
        FROM users u
        LEFT JOIN gerencias g ON g.id = u.gerencia_id
        LEFT JOIN supervisoes s ON s.id = u.supervisao_id
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def count_users(self) -> int:
        """Retorna o total de usuarios cadastrados."""
        with self._db.connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS total FROM users").fetchone()
            return int(row["total"]) if row else 0

    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        role: str,
        gerencia_id: int | None,
        supervisao_id: int | None,
        must_change_password: bool,
        matricula: str | None = None,
    ) -> int:
        """Insere um novo usuario e retorna o id gerado."""
        with self._db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, salt, role, gerencia_id, supervisao_id, must_change_password, matricula
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    password_hash,
                    salt,
                    role,
                    gerencia_id,
                    supervisao_id,
                    int(must_change_password),
                    matricula,
                ),
            )
            return int(cur.lastrowid)

    def list_users(self, role: str | None = None) -> list[dict[str, Any]]:
        """Lista usuarios com JOINs para nomes de gerencia e supervisao."""
        query = """
            SELECT u.id, u.username, u.role, u.matricula,
                   u.gerencia_id, g.name AS gerencia_name,
                   u.supervisao_id, s.name AS supervisao_name
            FROM users u
            LEFT JOIN gerencias g ON g.id = u.gerencia_id
            LEFT JOIN supervisoes s ON s.id = u.supervisao_id
        """
        with self._db.connect() as conn:
            if role:
                rows = conn.execute(
                    query + " WHERE u.role = ? ORDER BY u.username",
                    (role,),
                ).fetchall()
            else:
                rows = conn.execute(query + " ORDER BY u.username").fetchall()
        return [dict(row) for row in rows]

    def _get_user_by(self, where_clause: str, params: tuple) -> dict[str, Any] | None:
        """Busca usuario com clausula WHERE customizada (helper interno)."""
        with self._db.connect() as conn:
            row = conn.execute(
                f"{self._USER_SELECT} WHERE {where_clause}",
                params,
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """Busca usuario pelo nome (inclui hash e salt para autenticacao)."""
        return self._get_user_by("u.username = ?", (username,))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Busca usuario pelo id (inclui hash e salt)."""
        return self._get_user_by("u.id = ?", (user_id,))

    def update_password(self, user_id: int, password_hash: str, salt: str) -> None:
        """Atualiza hash e salt da senha de um usuario."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (password_hash, salt, user_id),
            )

    def set_must_change_password(self, user_id: int, must_change: bool) -> None:
        """Ativa ou desativa a flag de troca obrigatoria de senha."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE users SET must_change_password = ? WHERE id = ?",
                (int(must_change), user_id),
            )

    def get_supervisor_matriculas_by_gerencia(self, gerencia_id: int) -> list[str]:
        """Retorna as matriculas de todos os supervisores de uma gerencia."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT matricula FROM users WHERE role = 'supervisor' AND gerencia_id = ?",
                (gerencia_id,),
            ).fetchall()
        return [row["matricula"] for row in rows if row["matricula"]]

    def get_fiscal_names_by_supervisao(self, supervisao_id: int) -> list[str]:
        """Retorna os usernames de todos os fiscais de uma supervisao."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT username FROM users WHERE role = 'fiscal' AND supervisao_id = ?",
                (supervisao_id,),
            ).fetchall()
        return [row["username"] for row in rows]

    def update_user(
        self,
        user_id: int,
        username: str,
        role: str,
        gerencia_id: int | None,
        supervisao_id: int | None,
        matricula: str | None = None,
    ) -> None:
        """Atualiza dados cadastrais do usuario (sem alterar senha)."""
        with self._db.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET username = ?, role = ?, gerencia_id = ?, supervisao_id = ?, matricula = ?
                WHERE id = ?
                """,
                (username, role, gerencia_id, supervisao_id, matricula, user_id),
            )

    def delete_user(self, user_id: int) -> bool:
        """Remove um usuario pelo id. Retorna True se removido, False se nao existia."""
        with self._db.connect() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0


class GerenciaRepository:
    """Repositorio de gerencias – unidades organizacionais de nivel superior."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_gerencia(self, name: str) -> int:
        """Cria uma gerencia e retorna o id."""
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO gerencias (name) VALUES (?)",
                (name,),
            )
            return int(cur.lastrowid)

    def list_gerencias(self) -> list[dict[str, Any]]:
        """Lista todas as gerencias ordenadas por nome."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id, name FROM gerencias ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_gerencia(self, gerencia_id: int) -> dict[str, Any] | None:
        """Busca uma gerencia pelo id."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id, name FROM gerencias WHERE id = ?",
                (gerencia_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_gerencia(self, gerencia_id: int, name: str) -> None:
        """Atualiza o nome de uma gerencia."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE gerencias SET name = ? WHERE id = ?",
                (name, gerencia_id),
            )


class SupervisaoRepository:
    """Repositorio de supervisoes – vinculadas a uma gerencia."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_supervisao(self, name: str, gerencia_id: int) -> int:
        """Cria uma supervisao vinculada a uma gerencia e retorna o id."""
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO supervisoes (name, gerencia_id) VALUES (?, ?)",
                (name, gerencia_id),
            )
            return int(cur.lastrowid)

    def list_supervisoes(self, gerencia_id: int | None = None) -> list[dict[str, Any]]:
        """Lista supervisoes (opcionalmente filtradas por gerencia) com nome da gerencia."""
        query = """
            SELECT s.id, s.name, s.gerencia_id, g.name AS gerencia_name
            FROM supervisoes s
            JOIN gerencias g ON g.id = s.gerencia_id
        """
        params: tuple = ()
        if gerencia_id is not None:
            query += " WHERE s.gerencia_id = ?"
            params = (gerencia_id,)
        query += " ORDER BY s.name"
        with self._db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_supervisao(self, supervisao_id: int) -> dict[str, Any] | None:
        """Busca uma supervisao pelo id (com JOIN para nome da gerencia)."""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT s.id, s.name, s.gerencia_id, g.name AS gerencia_name
                FROM supervisoes s
                JOIN gerencias g ON g.id = s.gerencia_id
                WHERE s.id = ?
                """,
                (supervisao_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_supervisao(self, supervisao_id: int, name: str, gerencia_id: int) -> None:
        """Atualiza nome e gerencia de uma supervisao."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE supervisoes SET name = ?, gerencia_id = ? WHERE id = ?",
                (name, gerencia_id, supervisao_id),
            )

