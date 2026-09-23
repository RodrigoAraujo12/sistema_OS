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
        # Sem este PRAGMA o SQLite ignora as FOREIGN KEY declaradas no
        # schema: uma supervisao podia apontar para gerencia inexistente.
        # E por conexao, entao tem que ser aqui e nao no init_schema.
        conn.execute("PRAGMA foreign_keys = ON")
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
            # Quem chefia cada equipe so veio na planilha de 02/09/2026, e
            # marcado com fundo amarelo em vez de coluna propria (ver
            # importar_equipes). Aqui e coluna, nao tabela nova: chefiar e
            # atributo do vinculo que ja existia, e a planilha marca a
            # pessoa dentro do grupo, nunca fora dele.
            self._ensure_column(
                conn, "equipe_membros", "supervisor", "INTEGER NOT NULL DEFAULT 0"
            )
            # A gerencia dona de cada equipe, deduzida do nome da equipe
            # (ver backend/gerencias_atf.py). Guardamos o codigo do
            # ELEMENTO ORGANIZACIONAL do ATF, e nao `gerencias.id`: esta
            # tabela e espelho de dado externo, recriada a cada carga, e
            # o codigo do ATF sobrevive a uma gerencia local renomeada ou
            # ainda nao cadastrada.
            self._ensure_column(
                conn, "equipes_fiscais", "gerencia_codigo", "INTEGER"
            )
            # O mesmo codigo do lado do cadastro local, que e quem liga as
            # duas pontas. Fica nulo nas gerencias criadas a mao pelo
            # admin, que nao correspondem a elemento nenhum do ATF.
            self._ensure_column(conn, "gerencias", "codigo_atf", "INTEGER")
            # Sem o indice, importar duas vezes criaria a mesma gerencia
            # em duplicata — o upsert procura justamente por este campo.
            # Parcial porque NULL se repete a vontade: as locais.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_gerencias_codigo_atf "
                "ON gerencias (codigo_atf) WHERE codigo_atf IS NOT NULL"
            )
            # A tabela nova ja nasce com UNIQUE em matricula; em banco
            # migrado a coluna entrou por ALTER TABLE, que nao aceita
            # UNIQUE. Sem o indice, duas contas com a mesma matricula
            # passariam a enxergar as OS uma da outra. NULL nao conta:
            # o admin e os usuarios sem matricula continuam convivendo.
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_matricula "
                    "ON users (matricula)"
                )
            except sqlite3.IntegrityError:
                logger.warning(
                    "users.matricula tem valores repetidos; indice unico NAO criado. "
                    "Corrija os cadastros duplicados na tela de usuarios."
                )
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

    def get_user_by_matricula(self, matricula: str) -> dict[str, Any] | None:
        """Busca usuario pela matricula, a chave que vem da planilha da SEFAZ."""
        return self._get_user_by("u.matricula = ?", (str(matricula),))

    def amarrar_equipe_por_matricula(
        self, matricula: str, equipe_codigo: int | None, promover: bool = False,
    ) -> bool:
        """
        Amarra a equipe que a pessoa chefia ao usuario dela. True se mudou.

        `promover` sobe o papel de fiscal para supervisor, porque a chefia
        so tem efeito em `_matriculas_visiveis` para quem e supervisor:
        amarrar sem promover nao da acesso nenhum. Gerente e admin nunca
        sao rebaixados nem promovidos aqui — o papel deles vem do cadastro
        local, que manda mais do que a planilha.

        `equipe_codigo=None` promove sem tocar na coluna. E o caso de quem
        chefia duas equipes: a coluna guarda um codigo so, e a chefia dele
        ja vem inteira de `equipe_membros.supervisor`. Escrever None ali
        apagaria uma amarracao que o admin tenha feito a mao.
        """
        usuario = self.get_user_by_matricula(matricula)
        if usuario is None:
            return False
        papel = usuario["role"]
        novo_papel = "supervisor" if promover and papel == "fiscal" else papel
        muda_equipe = (
            equipe_codigo is not None and usuario.get("equipe_codigo") != equipe_codigo
        )
        if not muda_equipe and novo_papel == papel:
            return False
        with self._db.connect() as conn:
            if muda_equipe:
                conn.execute(
                    "UPDATE users SET equipe_codigo = ?, role = ? WHERE id = ?",
                    (equipe_codigo, novo_papel, usuario["id"]),
                )
            else:
                conn.execute(
                    "UPDATE users SET role = ? WHERE id = ?",
                    (novo_papel, usuario["id"]),
                )
        return True

    def lotar_gerencia_por_matricula(self, matricula: str, gerencia_id: int) -> bool:
        """
        Preenche a gerencia de quem esta sem lotacao. True se gravou.

        So escreve em cima de NULL, e o `WHERE` garante isso no proprio
        UPDATE: a lotacao que o admin fez na tela vale sobre a deduzida
        pela equipe — a mesma ordem que `_gerencia_por_matricula` usa no
        painel. Reexecutar nao mexe em quem ja esta lotado, entao rodar de
        novo depois de cada planilha e seguro.

        Nao toca em `supervisao_id`: a supervisao e recorte local, a
        gerencia do ATF nao tem nenhuma cadastrada, e inventar uma seria
        inventar hierarquia que ninguem confirmou.
        """
        with self._db.connect() as conn:
            cur = conn.execute(
                "UPDATE users SET gerencia_id = ? "
                "WHERE matricula = ? AND gerencia_id IS NULL",
                (gerencia_id, str(matricula)),
            )
            return cur.rowcount > 0

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
        Codigos das equipes que os supervisores da gerencia chefiam.

        Existe para o gerente enxergar o mesmo que a soma dos seus
        supervisores: sem isso, um supervisor com equipe amarrada veria
        OS que o proprio gerente nao ve.

        Soma as duas origens de chefia, na mesma ordem em que
        `_matriculas_visiveis` as consulta: a marca da planilha
        (`equipe_membros.supervisor`, que alcanca quem chefia mais de uma
        equipe) e a amarracao manual em `users.equipe_codigo`.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT equipe_codigo AS codigo FROM users
                WHERE role = 'supervisor' AND gerencia_id = ?
                  AND equipe_codigo IS NOT NULL
                UNION
                SELECT DISTINCT m.codigo_equipe AS codigo
                FROM equipe_membros m
                JOIN users u ON u.matricula = m.matricula
                WHERE m.supervisor = 1
                  AND u.role = 'supervisor' AND u.gerencia_id = ?
                """,
                (gerencia_id, gerencia_id),
            ).fetchall()
        return [int(row["codigo"]) for row in rows]

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

    def upsert_por_codigo_atf(self, codigo_atf: int, name: str) -> int:
        """
        Garante que a gerencia daquele elemento organizacional existe.

        Casa pelo `codigo_atf`, e nao pelo nome, porque o nome e editavel
        na tela de gerencias: se alguem renomear "GOFE-GEFTE" para "GOFE",
        uma nova importacao tem que reconhecer a mesma gerencia em vez de
        criar outra. Por isso tambem NAO sobrescreve o nome existente —
        renomear e direito do admin, e a importacao nao desfaz isso.

        Ao contrario de `equipes_fiscais`, aqui nao ha substituicao total:
        as gerencias locais criadas a mao tem usuarios lotados nelas
        (`users.gerencia_id`), e apagar levaria a lotacao junto.
        """
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM gerencias WHERE codigo_atf = ?", (codigo_atf,),
            ).fetchone()
            if row:
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO gerencias (name, codigo_atf) VALUES (?, ?)",
                (name, codigo_atf),
            )
            return int(cur.lastrowid)

    def list_gerencias(self) -> list[dict[str, Any]]:
        """Lista todas as gerencias ordenadas por nome."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, codigo_atf FROM gerencias ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_gerencia(self, gerencia_id: int) -> dict[str, Any] | None:
        """Busca uma gerencia pelo id."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id, name, codigo_atf FROM gerencias WHERE id = ?",
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
        self,
        equipes: list[tuple[int, str]],
        membros: list[tuple[int, str, str]],
        supervisores: set[tuple[int, str]] | None = None,
        gerencias: dict[int, int] | None = None,
    ) -> tuple[int, int]:
        """
        Recarrega equipes e membros numa transacao unica.

        Substituicao total, e nao merge, de proposito: quem sai de uma
        equipe some da planilha seguinte sem deixar rastro, e um merge
        manteria o vinculo antigo vivo — dando a um supervisor acesso a
        OS de quem nao e mais dele. Retorna (equipes, membros) gravados.

        `supervisores` e o conjunto de (codigo_equipe, matricula) que a
        planilha marca como chefia; quem nao estiver nele entra como
        membro comum. Omitir o argumento marca todo mundo como membro —
        e o certo para planilha antiga, que nao trazia a informacao.

        `gerencias` mapeia codigo_equipe -> codigo do elemento
        organizacional da gerencia dona dela, deduzido do nome da equipe
        (ver backend/gerencias_atf.py). Equipe fora do mapa fica com
        gerencia nula e some do corte por gerencia do painel.

        Nao mexe em `users.equipe_codigo`: um codigo que aponte para uma
        equipe extinta e tratado na leitura, onde vira conjunto vazio.
        """
        chefia = supervisores or set()
        por_equipe = gerencias or {}
        with self._db.connect() as conn:
            conn.execute("DELETE FROM equipe_membros")
            conn.execute("DELETE FROM equipes_fiscais")
            conn.executemany(
                "INSERT INTO equipes_fiscais (codigo, nome, gerencia_codigo) "
                "VALUES (?, ?, ?)",
                [(cod, nome, por_equipe.get(cod)) for cod, nome in equipes],
            )
            conn.executemany(
                """
                INSERT INTO equipe_membros
                    (codigo_equipe, matricula, nome, supervisor)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (cod, mat, nome, 1 if (cod, mat) in chefia else 0)
                    for cod, mat, nome in membros
                ],
            )
        logger.info(
            "Equipes fiscais importadas: %d equipes, %d vinculos, %d chefias, "
            "%d com gerencia.",
            len(equipes), len(membros), len(chefia), len(por_equipe),
        )
        return len(equipes), len(membros)

    def get_gerencias_atf_por_matricula(self) -> dict[str, list[int]]:
        """
        Mapa matricula -> codigos das gerencias (elementos organizacionais)
        das equipes de que ela participa, em ordem crescente.

        E a ponte que faltava entre a OS do ATF e a gerencia: a equipe vem
        do ATF e alcanca os 334 auditores, enquanto a lotacao local
        (`users.gerencia_id`) so existe para quem o admin cadastrou a mao.

        A lista quase sempre tem um item so. Ela e lista, e nao um valor,
        porque quem chama precisa saber a diferenca entre "a equipe diz
        qual e" e "as equipes discordam": o painel resolve o empate
        sozinho (ver `get_gerencia_atf_por_matricula`) e a lotacao em
        `users` prefere nao gravar nenhuma.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT m.matricula AS matricula,
                       e.gerencia_codigo AS gerencia
                FROM equipe_membros m
                JOIN equipes_fiscais e ON e.codigo = m.codigo_equipe
                WHERE e.gerencia_codigo IS NOT NULL
                ORDER BY m.matricula, e.gerencia_codigo
                """
            ).fetchall()
        mapa: dict[str, list[int]] = {}
        for row in rows:
            mapa.setdefault(str(row["matricula"]), []).append(int(row["gerencia"]))
        return mapa

    def get_gerencia_atf_por_matricula(self) -> dict[str, int]:
        """
        Mapa matricula -> codigo da gerencia, uma so por pessoa.

        Quem esta em duas equipes de gerencias diferentes aparece uma vez
        so, com a de MENOR codigo. E arbitrario, e de proposito: o corte
        do painel conta OS por gerencia, e deixar a mesma matricula em
        duas faria a soma passar do total sem que ninguem soubesse dizer
        por que. O caso e raro (a planilha tem 339 vinculos para 334
        pessoas) e quem precisa da visao completa tem o corte por equipe
        no filtro.

        O cadastro NAO usa este desempate: gravar `users.gerencia_id` e
        dizer onde a pessoa esta lotada, e um chute ali fica no banco.
        """
        return {
            matricula: codigos[0]
            for matricula, codigos in self.get_gerencias_atf_por_matricula().items()
        }

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

    def get_codigos_chefiados(self, matricula: str) -> list[int]:
        """
        Equipes que essa matricula CHEFIA, segundo a marca da planilha.

        Lista, e nao um codigo so, porque a planilha de 02/09/2026 marca
        duas pessoas como chefe de duas equipes cada. `users.equipe_codigo`
        nao daria conta: a coluna guarda um valor, e escolher um dos dois
        deixaria o supervisor cego para metade do que e dele.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT codigo_equipe FROM equipe_membros
                WHERE matricula = ? AND supervisor = 1
                ORDER BY codigo_equipe
                """,
                (str(matricula),),
            ).fetchall()
        return [int(row["codigo_equipe"]) for row in rows]

    def get_chefias_por_matricula(self) -> dict[str, list[dict[str, Any]]]:
        """
        Mapa matricula -> equipes que ela chefia, com codigo e nome.

        Versao em lote de `get_codigos_chefiados`, para a tela de usuarios
        pedir tudo de uma vez. Irmao de `get_equipes_por_matricula`, que
        responde a pergunta oposta: de que equipe a pessoa E MEMBRO.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT m.matricula, e.codigo, e.nome
                FROM equipe_membros m
                JOIN equipes_fiscais e ON e.codigo = m.codigo_equipe
                WHERE m.supervisor = 1
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
        """Membros de uma equipe, quem chefia primeiro, depois por nome."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT matricula, nome, supervisor FROM equipe_membros
                WHERE codigo_equipe = ? ORDER BY supervisor DESC, nome
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
