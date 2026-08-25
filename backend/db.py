"""
db.py – Camada de acesso a dados (SQLite) do Sistema Sefaz.

Contem:
- Database: gerencia conexoes e inicializacao do schema
- UserRepository: CRUD de usuarios
- GerenciaRepository: CRUD de gerencias
- SupervisaoRepository: CRUD de supervisoes
- EquipeFiscalRepository: equipes fiscais do ATF e seus membros

O banco fica em backend/app.db. A estrutura e criada automaticamente
no primeiro uso via Database.init_schema().
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger("sefaz.db")

DB_PATH = Path(__file__).parent / "app.db"


class Database:
    """Gerencia a conexao SQLite e a criacao/migracao do schema."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """
        Conexao com row_factory = sqlite3.Row, commit/rollback e fechamento.

        O `with` do proprio sqlite3 faz commit no sucesso e rollback na
        excecao, mas NAO fecha a conexao. Usa-lo sozinho — como era feito
        aqui — deixava um handle aberto por chamada de metodo, esperando o
        coletor de lixo. Este wrapper mantem o mesmo commit/rollback e
        garante o close() no finally, sem mudar nenhum ponto de uso.
        """
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

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
            # Equipes fiscais do ATF (cdEquipeFisc) e sua composicao.
            # Diferente de gerencias/supervisoes, que sao cadastro local
            # editavel, estas duas sao um espelho do que a SEFAZ informa:
            # o importador as recria por completo a cada carga.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equipes_fiscais (
                    codigo INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equipe_membros (
                    codigo_equipe INTEGER NOT NULL,
                    matricula TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    PRIMARY KEY (codigo_equipe, matricula),
                    FOREIGN KEY (codigo_equipe) REFERENCES equipes_fiscais (codigo)
                )
                """
            )
            # Colunas adicionadas apos a versao inicial (migracao simples).
            # Na mesma conexao das tabelas: sao operacoes de startup, nao ha
            # motivo para abrir uma conexao por coluna.
            for coluna, definicao in (
                ("gerencia_id", "INTEGER"),
                ("supervisao_id", "INTEGER"),
                ("must_change_password", "INTEGER DEFAULT 0"),
                ("matricula", "TEXT"),
                ("equipe_codigo", "INTEGER"),
            ):
                self._ensure_column(conn, "users", coluna, definicao)
        logger.info("Schema do banco inicializado com sucesso.")

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, definition: str,
    ) -> None:
        """Adiciona uma coluna a tabela apenas se ainda nao existir (migracao segura)."""
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
            u.equipe_codigo, e.nome AS equipe_nome,
            u.must_change_password
        FROM users u
        LEFT JOIN gerencias g ON g.id = u.gerencia_id
        LEFT JOIN supervisoes s ON s.id = u.supervisao_id
        LEFT JOIN equipes_fiscais e ON e.codigo = u.equipe_codigo
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
        equipe_codigo: int | None = None,
    ) -> int:
        """Insere um novo usuario e retorna o id gerado."""
        with self._db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, salt, role, gerencia_id, supervisao_id,
                    must_change_password, matricula, equipe_codigo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    equipe_codigo,
                ),
            )
            return int(cur.lastrowid)

    def list_users(self, role: str | None = None) -> list[dict[str, Any]]:
        """Lista usuarios com JOINs para nomes de gerencia e supervisao."""
        query = """
            SELECT u.id, u.username, u.role, u.matricula,
                   u.gerencia_id, g.name AS gerencia_name,
                   u.supervisao_id, s.name AS supervisao_name,
                   u.equipe_codigo, e.nome AS equipe_nome
            FROM users u
            LEFT JOIN gerencias g ON g.id = u.gerencia_id
            LEFT JOIN supervisoes s ON s.id = u.supervisao_id
            LEFT JOIN equipes_fiscais e ON e.codigo = u.equipe_codigo
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

    def get_matriculas_cadastradas(self) -> set[str]:
        """
        Matriculas que ja tem usuario, para a importacao em lote saber o
        que pular. Um set porque a checagem e feita por linha da planilha.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT matricula FROM users WHERE matricula IS NOT NULL"
            ).fetchall()
        return {str(row["matricula"]) for row in rows}

    def delete_users_by_matricula(self, matriculas: set[str]) -> int:
        """
        Remove usuarios pelas matriculas. Retorna quantos sairam.

        Usado para tirar os usuarios de exemplo quando o banco passa a ter
        gente de verdade. Nunca alcanca o admin, que nao tem matricula.
        """
        if not matriculas:
            return 0
        marcadores = ",".join("?" * len(matriculas))
        with self._db.connect() as conn:
            cur = conn.execute(
                f"DELETE FROM users WHERE matricula IN ({marcadores}) AND role != 'admin'",
                tuple(matriculas),
            )
            return int(cur.rowcount)

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

    def get_matriculas_by_supervisao(self, supervisao_id: int) -> list[str]:
        """
        Matriculas de todos os usuarios lotados na supervisao.

        Sem filtro por cargo de proposito: e a base do que um supervisor
        enxerga, e um supervisor tambem pode estar designado em uma OS.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT matricula FROM users WHERE supervisao_id = ?",
                (supervisao_id,),
            ).fetchall()
        return [row["matricula"] for row in rows if row["matricula"]]

    def get_equipe_codigos_by_gerencia(self, gerencia_id: int) -> list[int]:
        """
        Codigos das equipes fiscais amarradas aos supervisores da gerencia.

        Existe para o gerente enxergar o mesmo que a soma dos seus
        supervisores: sem isso, um supervisor com equipe amarrada veria
        OS que o proprio gerente nao ve.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT equipe_codigo FROM users
                WHERE role = 'supervisor' AND gerencia_id = ?
                  AND equipe_codigo IS NOT NULL
                """,
                (gerencia_id,),
            ).fetchall()
        return [int(row["equipe_codigo"]) for row in rows]

    def get_matriculas_by_gerencia(self, gerencia_id: int) -> list[str]:
        """Matriculas de todos os usuarios lotados na gerencia (todos os cargos)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT matricula FROM users WHERE gerencia_id = ?",
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
        equipe_codigo: int | None = None,
    ) -> None:
        """Atualiza dados cadastrais do usuario (sem alterar senha)."""
        with self._db.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET username = ?, role = ?, gerencia_id = ?, supervisao_id = ?,
                    matricula = ?, equipe_codigo = ?
                WHERE id = ?
                """,
                (username, role, gerencia_id, supervisao_id, matricula, equipe_codigo, user_id),
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



class EquipeFiscalRepository:
    """
    Equipes fiscais do ATF (cdEquipeFisc) e sua composicao.

    Espelho de dado externo, nao cadastro local: a origem e a planilha
    que a SEFAZ envia, e `substituir_tudo` recarrega a tabela inteira a
    cada importacao. Nada aqui e editavel pela aplicacao — o que o admin
    edita e o vinculo `users.equipe_codigo`, que mora em UserRepository.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def substituir_tudo(
        self, equipes: list[tuple[int, str]], membros: list[tuple[int, str, str]],
    ) -> tuple[int, int]:
        """
        Recarrega equipes e membros numa transacao unica.

        Substituicao total, e nao merge, de proposito: quem sai de uma
        equipe some da planilha seguinte sem deixar rastro, e um merge
        manteria o vinculo antigo vivo — dando a um supervisor acesso a
        OS de quem nao e mais dele. Retorna (equipes, membros) gravados.

        Nao mexe em `users.equipe_codigo`: um codigo que aponte para uma
        equipe extinta e tratado na leitura, onde vira conjunto vazio.
        """
        with self._db.connect() as conn:
            conn.execute("DELETE FROM equipe_membros")
            conn.execute("DELETE FROM equipes_fiscais")
            conn.executemany(
                "INSERT INTO equipes_fiscais (codigo, nome) VALUES (?, ?)",
                equipes,
            )
            conn.executemany(
                """
                INSERT INTO equipe_membros (codigo_equipe, matricula, nome)
                VALUES (?, ?, ?)
                """,
                membros,
            )
        logger.info(
            "Equipes fiscais importadas: %d equipes, %d vinculos.",
            len(equipes), len(membros),
        )
        return len(equipes), len(membros)

    def list_equipes(self) -> list[dict[str, Any]]:
        """Lista as equipes com a contagem de membros, em ordem alfabetica."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.codigo, e.nome, COUNT(m.matricula) AS total_membros
                FROM equipes_fiscais e
                LEFT JOIN equipe_membros m ON m.codigo_equipe = e.codigo
                GROUP BY e.codigo, e.nome
                ORDER BY e.nome
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_matriculas_by_equipe(self, codigo_equipe: int) -> list[str]:
        """Matriculas dos membros de uma equipe. Vazio se a equipe nao existe."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT matricula FROM equipe_membros WHERE codigo_equipe = ?",
                (codigo_equipe,),
            ).fetchall()
        return [row["matricula"] for row in rows]

    def get_matriculas_by_equipes(self, codigos: list[int]) -> list[str]:
        """
        Matriculas de varias equipes de uma vez, sem repetir.

        Uma consulta so em vez de uma por equipe: o gerente pode ter
        muitos supervisores, e isso roda a cada listagem de OS.
        """
        if not codigos:
            return []
        marcadores = ",".join("?" * len(codigos))
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT matricula FROM equipe_membros
                WHERE codigo_equipe IN ({marcadores})
                """,
                tuple(codigos),
            ).fetchall()
        return [row["matricula"] for row in rows]

    def get_equipes_por_matricula(self) -> dict[str, list[dict[str, Any]]]:
        """
        Mapa matricula -> equipes a que ela pertence, com codigo e nome.

        E o inverso de get_membros, e responde a pergunta da tela de
        usuarios: "de que equipe essa pessoa e?". Nao confundir com
        `users.equipe_codigo`, que e a equipe que um supervisor CHEFIA.

        Traz tudo de uma vez em vez de uma consulta por usuario: a lista
        inteira sao poucas centenas de linhas, e a tela pede todas juntas.
        Quem esta em duas equipes aparece com as duas.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT m.matricula, e.codigo, e.nome
                FROM equipe_membros m
                JOIN equipes_fiscais e ON e.codigo = m.codigo_equipe
                ORDER BY e.nome
                """
            ).fetchall()
        mapa: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            mapa.setdefault(str(row["matricula"]), []).append(
                {"codigo": int(row["codigo"]), "nome": row["nome"]}
            )
        return mapa

    def get_membros(self, codigo_equipe: int) -> list[dict[str, Any]]:
        """Membros de uma equipe (matricula e nome), em ordem alfabetica."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT matricula, nome FROM equipe_membros
                WHERE codigo_equipe = ? ORDER BY nome
                """,
                (codigo_equipe,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_equipe(self, codigo_equipe: int) -> dict[str, Any] | None:
        """Busca uma equipe pelo codigo do ATF."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT codigo, nome FROM equipes_fiscais WHERE codigo = ?",
                (codigo_equipe,),
            ).fetchone()
        return dict(row) if row else None

    def count_equipes(self) -> int:
        """Total de equipes importadas. Zero significa 'nunca importado'."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS total FROM equipes_fiscais"
            ).fetchone()
            return int(row["total"]) if row else 0
