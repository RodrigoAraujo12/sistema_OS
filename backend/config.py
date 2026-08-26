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

# Senha do admin criado no primeiro boot. Sem valor no .env, o main gera
# uma aleatoria e registra no log — nunca ha credencial fixa no codigo.
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

# ─── Sessao e login ─────────────────────────────────────────────

# Validade do token de sessao. O padrao e uma jornada de trabalho: sem
# prazo, um token vazado valeria para sempre.
SESSION_TTL_MINUTES: int = int(os.getenv("SESSION_TTL_MINUTES", "480"))

# Limite de falhas de login antes do bloqueio temporario. O limite por
# usuario protege a conta; o por IP, mais folgado, existe para nao travar
# um predio inteiro que sai pelo mesmo IP.
LOGIN_MAX_FALHAS_USUARIO: int = int(os.getenv("LOGIN_MAX_FALHAS_USUARIO", "5"))
LOGIN_MAX_FALHAS_IP: int = int(os.getenv("LOGIN_MAX_FALHAS_IP", "20"))
LOGIN_BLOQUEIO_MINUTOS: int = int(os.getenv("LOGIN_BLOQUEIO_MINUTOS", "15"))

# ─── ATF API ────────────────────────────────────────────────────
# URL base do servico ATF. Quando vazia, o sistema usa dados MOCK.
# Exemplo: https://<host-do-atf>
ATF_BASE_URL: str = os.getenv("ATF_BASE_URL", "")

# URL do servico de DETALHE da OS (doc do detalhe). Vazia = usa a mesma do
# ATF_BASE_URL, que e o estado final desejado.
#
# Ela existe porque os dois servicos nem sempre estao publicados no
# mesmo ambiente: um deles pode responder so em homologacao enquanto o
# outro ja esta em producao. E ambientes distintos tem BANCOS
# DIFERENTES: a mesma OS volta com contribuinte, situacao e fiscais
# distintos em cada um. Enquanto
# estiverem separados, o detalhe serve para conferir a integracao, e nao
# para decidir acesso — ver _buscar_detalhe_os_atf, em main.py.
ATF_DETALHE_BASE_URL: str = os.getenv("ATF_DETALHE_BASE_URL", "")

# Caminho do endpoint SOAP, acrescentado a ATF_BASE_URL. Fica fora do
# repositorio (vem do .env) porque host + caminho juntos formam o
# endereco real do servico.
ATF_WS_PATH: str = os.getenv("ATF_WS_PATH", "")

# Verificacao do certificado TLS do servico externo. Ligada por padrao —
# desligar so em ambiente controlado e por tempo determinado.
#
# Existe para um caso especifico: servidor que apresenta certificado
# valido mas envia so o certificado folha, sem a CA intermediaria. O
# navegador disfarca, porque busca a intermediaria pela AIA do proprio
# certificado; o requests nao faz isso e derruba toda chamada com
# "unable to get local issuer certificate".
#
# Nessa situacao, a correcao certa e no servidor (instalar a cadeia
# completa); a segunda melhor e apontar verify= para um bundle que
# contenha a intermediaria. Desligar a verificacao, que e o que esta
# variavel faz, deixa a conexao exposta a interceptacao — e o trafego
# carrega dado fiscal e de contribuinte. Por isso o padrao aqui e
# "ligada" e qualquer desligamento vive apenas no .env, fora do
# repositorio, onde tambem se registra ate quando ele vale.
ATF_SSL_VERIFY: bool = os.getenv("ATF_SSL_VERIFY", "true").strip().lower() not in (
    "false", "0", "nao", "n", "no", "off",
)

# Por quantos segundos a resposta do ATF fica em cache. O servico devolve
# a lista inteira e nao pagina, entao sem cache cada troca de pagina ou de
# ordenacao refaz a consulta completa. 0 desliga o cache.
ATF_CACHE_TTL: float = float(os.getenv("ATF_CACHE_TTL", "60"))

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
    # Um estado inseguro nao pode ser silencioso: sem este aviso no boot,
    # ninguem lembra que a verificacao ficou desligada.
    if ATF_BASE_URL and not ATF_SSL_VERIFY:
        logger.warning(
            "ATF_SSL_VERIFY=false — certificado do ATF NAO sera verificado. "
            "Conexao sujeita a interceptacao; use apenas em ambiente controlado."
        )
    return logger
