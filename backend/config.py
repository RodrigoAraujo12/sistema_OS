"""
config.py – Carrega variaveis de ambiente do arquivo .env.

Centraliza todas as configuracoes do projeto em um unico lugar para
facilitar ajustes entre ambientes (dev, homologacao, producao) sem
alterar o codigo-fonte.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Carrega o .env que fica na raiz do projeto (um nivel acima de /backend)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# ─── Configuracoes gerais ───────────────────────────────────────

APP_TITLE: str = os.getenv("APP_TITLE", "Sistema Sefaz")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
DEFAULT_PASSWORD: str = os.getenv("DEFAULT_PASSWORD", "temp1234")

# ─── CORS ───────────────────────────────────────────────────────

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
CORS_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ─── Logging ────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """
    Configura o logger raiz do projeto com formato padronizado.
    Retorna o logger principal 'sefaz' para uso nos modulos.
    """
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=LOG_LEVEL, format=log_format)
    logger = logging.getLogger("sefaz")
    logger.setLevel(LOG_LEVEL)
    return logger
