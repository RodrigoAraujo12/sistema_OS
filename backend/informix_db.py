"""
Modulo de conexao com banco Informix remoto.

Este modulo gerencia a conexao ODBC com o servidor Informix
onde estao armazenadas as Ordens de Servico (OS) da SEFAZ.

Configuracao via variaveis de ambiente (.env):
- INFORMIX_SERVER: nome/IP do servidor
- INFORMIX_DATABASE: nome do banco de dados
- INFORMIX_HOST: host do servidor
- INFORMIX_PORT: porta (padrao 9088)
- INFORMIX_USER: usuario
- INFORMIX_PASSWORD: senha
- INFORMIX_PROTOCOL: onsoctcp (padrao)

Requisitos:
- pyodbc instalado (pip install pyodbc)
- IBM Informix Client SDK ou ODBC Driver instalado no sistema
"""

from __future__ import annotations

import logging
import os
from typing import Any

# pyodbc sera usado para conexao ODBC com Informix
# Nota: .env ja e carregado em config.py (nao duplicar load_dotenv aqui)
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False


logger = logging.getLogger("sefaz.informix")


class InformixConnection:
    """
    Gerenciador de conexao com banco Informix.
    
    Uso:
        conn = InformixConnection()
        if conn.is_configured():
            rows = conn.execute_query("SELECT * FROM ordens_servico")
    """
    
    CONNECT_TIMEOUT = 10  # segundos para timeout de conexao ODBC

    def __init__(self) -> None:
        """Inicializa a configuracao a partir das variaveis de ambiente."""
        self.server = os.getenv("INFORMIX_SERVER", "")
        self.database = os.getenv("INFORMIX_DATABASE", "")
        self.host = os.getenv("INFORMIX_HOST", "")
        self.port = os.getenv("INFORMIX_PORT", "9088")
        self.user = os.getenv("INFORMIX_USER", "")
        self.password = os.getenv("INFORMIX_PASSWORD", "")
        self.protocol = os.getenv("INFORMIX_PROTOCOL", "onsoctcp")
        self._connection = None

        # Configura variaveis de ambiente necessarias para o CSDK
        informixdir = os.getenv("INFORMIXDIR", "")
        sqlhosts = os.getenv("INFORMIXSQLHOSTS", "")
        if informixdir:
            os.environ["INFORMIXDIR"] = informixdir
        if sqlhosts:
            os.environ["INFORMIXSQLHOSTS"] = sqlhosts
        if self.server:
            os.environ["INFORMIXSERVER"] = self.server
    
    def is_configured(self) -> bool:
        """Verifica se as configuracoes minimas estao presentes."""
        required = [self.server, self.database, self.host, self.user, self.password]
        return all(required) and PYODBC_AVAILABLE
    
    def get_connection_string(self) -> str:
        """Monta a connection string ODBC para Informix."""
        # Detecta automaticamente o nome do driver instalado
        driver_name = "IBM INFORMIX ODBC DRIVER"
        if PYODBC_AVAILABLE:
            for d in pyodbc.drivers():
                if "INFORMIX" in d.upper():
                    driver_name = d
                    break
        return (
            f"DRIVER={{{driver_name}}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"HOST={self.host};"
            f"SERVICE={self.port};"
            f"UID={self.user};"
            f"PWD={self.password};"
            f"PROTOCOL={self.protocol};"
        )
    
    def connect(self) -> pyodbc.Connection | None:
        """
        Estabelece conexao com o banco Informix.
        
        Returns:
            Objeto de conexao pyodbc ou None se falhar.
        """
        if not PYODBC_AVAILABLE:
            logger.error("pyodbc nao esta instalado. Execute: pip install pyodbc")
            return None
        
        if not self.is_configured():
            logger.warning(
                "Configuracoes do Informix incompletas. "
                "Verifique as variaveis de ambiente INFORMIX_* no arquivo .env"
            )
            return None
        
        try:
            conn_string = self.get_connection_string()
            self._connection = pyodbc.connect(conn_string, timeout=self.CONNECT_TIMEOUT)
            logger.info("Conexao com Informix estabelecida com sucesso")
            return self._connection
        except pyodbc.Error as e:
            logger.error("Erro ao conectar no Informix: %s", e)
            return None
    
    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """
        Executa uma query SELECT e retorna os resultados como lista de dicts.
        
        Args:
            query: SQL query a ser executada
            params: Tupla com parametros da query (para evitar SQL injection)
        
        Returns:
            Lista de dicionarios com os resultados (cada dict = uma linha)
        
        Se a conexao estiver perdida, tenta reconectar uma vez antes de falhar.
        """
        if not self._connection:
            self._connection = self.connect()
        
        if not self._connection:
            logger.error("Nao foi possivel estabelecer conexao com Informix")
            return []
        
        for attempt in range(2):
            try:
                cursor = self._connection.cursor()
                cursor.execute(query, params)
                
                # Obter nomes das colunas
                columns = [column[0].lower() for column in cursor.description]
                
                # Converter cada linha em dicionario
                results = []
                for row in cursor.fetchall():
                    row_dict = dict(zip(columns, row))
                    results.append(row_dict)
                
                cursor.close()
                logger.debug("Query executada com sucesso: %d linhas retornadas", len(results))
                return results
            
            except pyodbc.Error as e:
                if attempt == 0:
                    logger.warning("Conexao perdida, tentando reconectar: %s", e)
                    self._connection = None
                    self._connection = self.connect()
                    if not self._connection:
                        logger.error("Reconexao falhou")
                        return []
                else:
                    logger.error("Erro ao executar query no Informix: %s", e)
                    return []
        
        return []
    
    def close(self) -> None:
        """Fecha a conexao com o banco."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Conexao com Informix fechada")
            except Exception as e:
                logger.warning("Erro ao fechar conexao: %s", e)
            finally:
                self._connection = None
    
    def __enter__(self):
        """Context manager: conecta ao entrar."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: desconecta ao sair."""
        self.close()


# Instancia global (singleton) para reutilizar conexao
_informix_conn = InformixConnection()


def get_informix_connection() -> InformixConnection:
    """
    Retorna a instancia global de conexao Informix.
    
    Uso:
        conn = get_informix_connection()
        if conn.is_configured():
            data = conn.execute_query("SELECT * FROM tabela WHERE id = ?", (123,))
    """
    return _informix_conn
