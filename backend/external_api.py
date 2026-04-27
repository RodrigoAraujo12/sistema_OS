"""
Servico de dados externos - Ordens de Servico do Informix.

Este modulo consulta o banco Informix remoto para obter dados de OS.
Se o Informix nao estiver configurado, usa dados MOCK para desenvolvimento.

Configuracao do Informix via .env:
- INFORMIX_SERVER, INFORMIX_DATABASE, INFORMIX_HOST, etc.

Tabela: ordens_servico
Colunas: numero, tipo, ie, razao_social, matricula_supervisor, fiscais,
         status, prioridade, data_abertura, data_ciencia,
         data_ultima_movimentacao
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from .informix_db import get_informix_connection

logger = logging.getLogger("sefaz.external_api")

# ─── Constantes de negocio ──────────────────────────────────────

DIAS_CRITICO_THRESHOLD = 15  # OS parada > N dias e considerada critica
STATUSES_ATIVOS = ("aberta", "em_andamento")

# Pesos da formula de indice de saude (score 0-100 por gerencia)
PESO_CRITICAS = 0.40       # % de OS criticas → ate -40 pts
PESO_DIAS_PARADO = 0.5     # Cada dia medio parado → -0.5 pt
PESO_TAXA_CONCLUSAO = 0.20 # (100 - taxa%) * 0.20 → ate -20 pts
PESO_SEM_CIENCIA = 0.20    # % sem ciencia → ate -20 pts


# ─── MOCK: Ordens de Servico ────────────────────────────────────
# Agora vem da API externa (Informix). O sistema so consulta.

_MOCK_ORDENS: list[dict[str, Any]] = [
    {
        "numero": "OS-2026-001",
        "tipo": "Normal",
        "ie": "12.345.678-9",
        "razao_social": "Distribuidora ABC Ltda",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "em_andamento",
        "prioridade": "alta",
        "data_abertura": "2026-01-10",
        "data_ciencia": "2026-01-12",
        "data_ultima_movimentacao": "2026-01-25",
    },
    {
        "numero": "OS-2026-002",
        "tipo": "Especifico",
        "ie": "98.765.432-1",
        "razao_social": "Industria Delta S/A",
        "matricula_supervisor": "23457",
        "fiscais": ["Ana Ribeiro"],
        "status": "aberta",
        "prioridade": "urgente",
        "data_abertura": "2026-02-01",
        "data_ciencia": "2026-02-03",
        "data_ultima_movimentacao": "2026-02-03",
    },
    {
        "numero": "OS-2026-003",
        "tipo": "Simplificado",
        "ie": "55.667.778-3",
        "razao_social": "Transportes Rapido Ltda",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "em_andamento",
        "prioridade": "normal",
        "data_abertura": "2026-01-05",
        "data_ciencia": "2026-01-08",
        "data_ultima_movimentacao": "2026-01-20",
    },
    {
        "numero": "OS-2026-004",
        "tipo": "Normal",
        "ie": "33.445.556-4",
        "razao_social": "Supermercado Central Ltda",
        "matricula_supervisor": "23457",
        "fiscais": ["Ana Ribeiro"],
        "status": "aberta",
        "prioridade": "alta",
        "data_abertura": "2026-02-05",
        "data_ciencia": None,
        "data_ultima_movimentacao": "2026-02-05",
    },
    {
        "numero": "OS-2026-005",
        "tipo": "Simplificado",
        "ie": "77.889.900-5",
        "razao_social": "Farmacia Popular Ltda",
        "matricula_supervisor": "23457",
        "fiscais": ["Ana Ribeiro"],
        "status": "concluida",
        "prioridade": "normal",
        "data_abertura": "2025-12-15",
        "data_ciencia": "2025-12-18",
        "data_ultima_movimentacao": "2026-01-30",
    },
    {
        "numero": "OS-2026-006",
        "tipo": "Especifico",
        "ie": "12.345.678-9",
        "razao_social": "Distribuidora ABC Ltda",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "aberta",
        "prioridade": "alta",
        "data_abertura": "2026-02-07",
        "data_ciencia": "2026-02-09",
        "data_ultima_movimentacao": "2026-02-09",
    },
    {
        "numero": "OS-2026-007",
        "tipo": "Normal",
        "ie": "98.765.432-1",
        "razao_social": "Industria Delta S/A",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "em_andamento",
        "prioridade": "normal",
        "data_abertura": "2026-01-15",
        "data_ciencia": "2026-01-18",
        "data_ultima_movimentacao": "2026-02-01",
    },
    {
        "numero": "OS-2026-008",
        "tipo": "Simplificado",
        "ie": "33.445.556-4",
        "razao_social": "Supermercado Central Ltda",
        "matricula_supervisor": "23457",
        "fiscais": ["Ana Ribeiro"],
        "status": "aberta",
        "prioridade": "baixa",
        "data_abertura": "2025-12-01",
        "data_ciencia": "2025-12-05",
        "data_ultima_movimentacao": "2025-12-10",
    },
    {
        "numero": "OS-2026-009",
        "tipo": "Especifico",
        "ie": "55.667.778-3",
        "razao_social": "Transportes Rapido Ltda",
        "matricula_supervisor": "23457",
        "fiscais": ["Ana Ribeiro"],
        "status": "aberta",
        "prioridade": "urgente",
        "data_abertura": "2026-02-08",
        "data_ciencia": None,
        "data_ultima_movimentacao": "2026-02-08",
    },
    {
        "numero": "OS-2026-010",
        "tipo": "Normal",
        "ie": "77.889.900-5",
        "razao_social": "Farmacia Popular Ltda",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "cancelada",
        "prioridade": "alta",
        "data_abertura": "2026-01-20",
        "data_ciencia": "2026-01-22",
        "data_ultima_movimentacao": "2026-02-05",
    },
]

# ─── MOCK: Movimentacoes e detalhes por OS ──────────────────────

_MOCK_DETALHES: dict[str, dict[str, Any]] = {
    "OS-2026-001": {
        "objeto": "Verificacao de notas fiscais de entrada e saida do periodo 2025.",
        "valor_estimado": 125000.00,
        "endereco": "Rua das Flores, 123 - Centro, Joao Pessoa/PB",
        "cnpj": "12.345.678/0001-90",
        "telefone": "(83) 3222-1234",
        "observacoes": "Contribuinte cooperativo. Documentacao parcialmente entregue.",
        "movimentacoes": [
            {"data": "2026-01-10", "tipo": "Abertura", "descricao": "OS aberta pelo supervisor Patricia Oliveira.", "responsavel": "Patricia Oliveira"},
            {"data": "2026-01-12", "tipo": "Ciencia", "descricao": "Fiscal Carlos Mendes tomou ciencia da OS.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-15", "tipo": "Diligencia", "descricao": "Visita ao estabelecimento para coleta de documentos.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-20", "tipo": "Analise", "descricao": "Analise dos livros fiscais e notas do periodo.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-25", "tipo": "Notificacao", "descricao": "Contribuinte notificado para apresentar documentos complementares.", "responsavel": "Carlos Mendes"},
        ],
    },
    "OS-2026-002": {
        "objeto": "Fiscalizacao especifica de ICMS-ST sobre produtos importados.",
        "valor_estimado": 340000.00,
        "endereco": "Av. Epitacio Pessoa, 4500 - Manaira, Joao Pessoa/PB",
        "cnpj": "98.765.432/0001-10",
        "telefone": "(83) 3245-6789",
        "observacoes": "Denuncia anonima de subfaturamento em importacoes.",
        "movimentacoes": [
            {"data": "2026-02-01", "tipo": "Abertura", "descricao": "OS aberta com prioridade urgente por denuncia.", "responsavel": "Joao Silva"},
            {"data": "2026-02-03", "tipo": "Ciencia", "descricao": "Fiscal Ana Ribeiro tomou ciencia.", "responsavel": "Ana Ribeiro"},
        ],
    },
    "OS-2026-003": {
        "objeto": "Auditoria simplificada de transporte interestadual.",
        "valor_estimado": 45000.00,
        "endereco": "Rod. BR-230, Km 22 - Distrito Industrial, Campina Grande/PB",
        "cnpj": "55.667.778/0001-30",
        "telefone": "(83) 3333-7890",
        "observacoes": "Empresa com historico de irregularidades em CT-e.",
        "movimentacoes": [
            {"data": "2026-01-05", "tipo": "Abertura", "descricao": "OS simplificada aberta para verificacao de CT-e.", "responsavel": "Patricia Oliveira"},
            {"data": "2026-01-08", "tipo": "Ciencia", "descricao": "Fiscal Carlos Mendes tomou ciencia.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-12", "tipo": "Diligencia", "descricao": "Verificacao no posto fiscal da BR-230.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-20", "tipo": "Relatorio", "descricao": "Relatorio parcial com divergencias encontradas em 3 CT-e.", "responsavel": "Carlos Mendes"},
        ],
    },
    "OS-2026-004": {
        "objeto": "Verificacao de GIA e EFD do exercicio 2025.",
        "valor_estimado": 88000.00,
        "endereco": "Rua Nego, 456 - Tambau, Joao Pessoa/PB",
        "cnpj": "33.445.556/0001-40",
        "telefone": "(83) 3214-5678",
        "observacoes": "Aguardando ciencia do fiscal designado.",
        "movimentacoes": [
            {"data": "2026-02-05", "tipo": "Abertura", "descricao": "OS aberta para verificacao de obrigacoes acessorias.", "responsavel": "Joao Silva"},
        ],
    },
    "OS-2026-005": {
        "objeto": "Verificacao simplificada de creditos de ICMS.",
        "valor_estimado": 23000.00,
        "endereco": "Av. Dom Pedro II, 789 - Centro, Joao Pessoa/PB",
        "cnpj": "77.889.900/0001-50",
        "telefone": "(83) 3221-0987",
        "observacoes": "Fiscalizacao concluida sem irregularidades relevantes.",
        "movimentacoes": [
            {"data": "2025-12-15", "tipo": "Abertura", "descricao": "OS simplificada aberta.", "responsavel": "Joao Silva"},
            {"data": "2025-12-18", "tipo": "Ciencia", "descricao": "Fiscal Ana Ribeiro tomou ciencia.", "responsavel": "Ana Ribeiro"},
            {"data": "2025-12-22", "tipo": "Diligencia", "descricao": "Coleta de documentacao no estabelecimento.", "responsavel": "Ana Ribeiro"},
            {"data": "2026-01-10", "tipo": "Analise", "descricao": "Analise dos creditos declarados versus comprovados.", "responsavel": "Ana Ribeiro"},
            {"data": "2026-01-25", "tipo": "Relatorio", "descricao": "Relatorio final elaborado - sem divergencias significativas.", "responsavel": "Ana Ribeiro"},
            {"data": "2026-01-30", "tipo": "Conclusao", "descricao": "OS concluida e arquivada.", "responsavel": "Joao Silva"},
        ],
    },
    "OS-2026-006": {
        "objeto": "Fiscalizacao especifica de operacoes com beneficio fiscal.",
        "valor_estimado": 210000.00,
        "endereco": "Rua das Flores, 123 - Centro, Joao Pessoa/PB",
        "cnpj": "12.345.678/0001-90",
        "telefone": "(83) 3222-1234",
        "observacoes": "Mesma empresa da OS-2026-001. Foco em incentivos fiscais.",
        "movimentacoes": [
            {"data": "2026-02-07", "tipo": "Abertura", "descricao": "OS especifica aberta para verificacao de beneficios de ICMS.", "responsavel": "Patricia Oliveira"},
            {"data": "2026-02-09", "tipo": "Ciencia", "descricao": "Fiscal Carlos Mendes tomou ciencia.", "responsavel": "Carlos Mendes"},
        ],
    },
    "OS-2026-007": {
        "objeto": "Auditoria de estoque e inventario fiscal.",
        "valor_estimado": 175000.00,
        "endereco": "Av. Epitacio Pessoa, 4500 - Manaira, Joao Pessoa/PB",
        "cnpj": "98.765.432/0001-10",
        "telefone": "(83) 3245-6789",
        "observacoes": "Divergencia detectada entre estoque fisico e escritural.",
        "movimentacoes": [
            {"data": "2026-01-15", "tipo": "Abertura", "descricao": "OS aberta para auditoria de estoque.", "responsavel": "Patricia Oliveira"},
            {"data": "2026-01-18", "tipo": "Ciencia", "descricao": "Fiscal Carlos Mendes tomou ciencia.", "responsavel": "Carlos Mendes"},
            {"data": "2026-01-22", "tipo": "Diligencia", "descricao": "Contagem fisica de estoque no deposito.", "responsavel": "Carlos Mendes"},
            {"data": "2026-02-01", "tipo": "Analise", "descricao": "Comparacao entre inventario fisico e Bloco H do SPED.", "responsavel": "Carlos Mendes"},
        ],
    },
    "OS-2026-008": {
        "objeto": "Revisao simplificada de escrituracao fiscal digital.",
        "valor_estimado": 15000.00,
        "endereco": "Rua Nego, 456 - Tambau, Joao Pessoa/PB",
        "cnpj": "33.445.556/0001-40",
        "telefone": "(83) 3214-5678",
        "observacoes": "OS de prioridade baixa. Verificacao de rotina.",
        "movimentacoes": [
            {"data": "2025-12-01", "tipo": "Abertura", "descricao": "OS simplificada aberta para revisao de EFD.", "responsavel": "Joao Silva"},
            {"data": "2025-12-05", "tipo": "Ciencia", "descricao": "Fiscal Ana Ribeiro tomou ciencia.", "responsavel": "Ana Ribeiro"},
            {"data": "2025-12-10", "tipo": "Analise", "descricao": "Inicio da analise de EFD - periodo 01-06/2025.", "responsavel": "Ana Ribeiro"},
        ],
    },
    "OS-2026-009": {
        "objeto": "Fiscalizacao especifica de operacoes interestaduais com DIFAL.",
        "valor_estimado": 290000.00,
        "endereco": "Rod. BR-230, Km 22 - Distrito Industrial, Campina Grande/PB",
        "cnpj": "55.667.778/0001-30",
        "telefone": "(83) 3333-7890",
        "observacoes": "Urgente: indicio de sonegacao de DIFAL em compras interestaduais.",
        "movimentacoes": [
            {"data": "2026-02-08", "tipo": "Abertura", "descricao": "OS urgente aberta por indicio de sonegacao.", "responsavel": "Joao Silva"},
        ],
    },
    "OS-2026-010": {
        "objeto": "Verificacao de creditos extemporaneos de ICMS.",
        "valor_estimado": 67000.00,
        "endereco": "Av. Dom Pedro II, 789 - Centro, Joao Pessoa/PB",
        "cnpj": "77.889.900/0001-50",
        "telefone": "(83) 3221-0987",
        "observacoes": "OS cancelada a pedido da supervisao apos revisao dos indicios.",
        "movimentacoes": [
            {"data": "2026-01-20", "tipo": "Abertura", "descricao": "OS aberta para verificacao de creditos extemporaneos.", "responsavel": "Patricia Oliveira"},
            {"data": "2026-01-22", "tipo": "Ciencia", "descricao": "Fiscal Carlos Mendes tomou ciencia.", "responsavel": "Carlos Mendes"},
            {"data": "2026-02-05", "tipo": "Cancelamento", "descricao": "OS cancelada - indicios insuficientes apos reavaliacao.", "responsavel": "Patricia Oliveira"},
        ],
    },
}


def _calcular_dias_parado(data_ultima_mov: str | None) -> int:
    """Calcula quantos dias a OS esta parada desde a ultima movimentacao."""
    if not data_ultima_mov:
        return 0
    try:
        dt = datetime.strptime(data_ultima_mov, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, delta.days)
    except (ValueError, TypeError):
        return 0


def _enriquecer_os(os_dict: dict[str, Any]) -> dict[str, Any]:
    """Adiciona campo calculado dias_parado."""
    return {
        **os_dict,
        "dias_parado": _calcular_dias_parado(os_dict.get("data_ultima_movimentacao")),
    }


# ─── Constantes e helpers Informix ───────────────────────────────

_OS_COLUMNS = """
    numero, tipo, ie, razao_social, matricula_supervisor,
    fiscais, status, prioridade, data_abertura,
    data_ciencia, data_ultima_movimentacao
"""

_DATE_FIELDS = ("data_abertura", "data_ciencia", "data_ultima_movimentacao")


def _normalizar_row(row: dict[str, Any]) -> dict[str, Any]:
    """Converte campos crus do Informix (fiscais e datas) para o formato da API."""
    normalized = dict(row)
    if isinstance(normalized.get("fiscais"), str):
        normalized["fiscais"] = [f.strip() for f in normalized["fiscais"].split(",")]
    for field in _DATE_FIELDS:
        if field in normalized and normalized[field] and isinstance(normalized[field], (date, datetime)):
            normalized[field] = normalized[field].strftime("%Y-%m-%d")
    return normalized


def _listar_ordens_informix(
    status_filter: str | None = None,
    tipo: str | None = None,
) -> list[dict[str, Any]] | None:
    """Consulta todas as OS no Informix com filtros opcionais."""
    conn = get_informix_connection()
    if not conn.is_configured():
        return None

    query = f"SELECT {_OS_COLUMNS} FROM ordens_servico WHERE 1=1"
    params: list[str] = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)

    try:
        rows = conn.execute_query(query, tuple(params))
        return [_enriquecer_os(_normalizar_row(row)) for row in rows]
    except Exception:
        logger.exception("Erro ao consultar Informix")
        return None


def _filtrar_por_hierarquia(
    ordens: list[dict[str, Any]],
    user_role: str | None = None,
    user_matricula: str | None = None,
    user_name: str | None = None,
    supervisor_matriculas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Filtra OS de acordo com a hierarquia do usuario.

    - admin: ve tudo
    - fiscal: ve OS onde seu nome aparece em 'fiscais'
    - supervisor: ve OS onde 'matricula_supervisor' bate com sua matricula
    - gerente: ve OS de todos os supervisores da sua gerencia
    """
    if not user_role or user_role == "admin":
        return ordens

    if user_role == "fiscal":
        return [
            os for os in ordens
            if user_name and user_name in os.get("fiscais", [])
        ]

    if user_role == "supervisor":
        return [
            os for os in ordens
            if os.get("matricula_supervisor") == user_matricula
        ]

    if user_role == "gerente":
        if not supervisor_matriculas:
            return []
        matriculas_set = set(supervisor_matriculas)
        return [
            os for os in ordens
            if os.get("matricula_supervisor") in matriculas_set
        ]

    return ordens


def listar_ordens_servico(
    status_filter: str | None = None,
    tipo: str | None = None,
    user_role: str | None = None,
    user_matricula: str | None = None,
    user_name: str | None = None,
    supervisor_matriculas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Lista Ordens de Servico com filtros opcionais e filtragem hierarquica.

    Tenta consultar banco Informix primeiro.
    Se nao configurado ou falhar, usa dados MOCK.
    Apos obter os dados, aplica filtro de hierarquia conforme o papel do usuario.
    """
    result = _listar_ordens_informix(status_filter, tipo)
    if result is not None:
        logger.debug("Dados carregados do Informix: %d OS", len(result))
        return _filtrar_por_hierarquia(result, user_role, user_matricula, user_name, supervisor_matriculas)

    logger.debug("Usando dados MOCK (Informix nao configurado)")
    results = list(_MOCK_ORDENS)
    if status_filter:
        results = [os for os in results if os["status"] == status_filter]
    if tipo:
        results = [os for os in results if os["tipo"] == tipo]
    enriched = [_enriquecer_os(os) for os in results]
    return _filtrar_por_hierarquia(enriched, user_role, user_matricula, user_name, supervisor_matriculas)


def _consultar_os_informix(numero: str) -> dict[str, Any] | None:
    """Consulta OS especifica no Informix por numero."""
    conn = get_informix_connection()
    if not conn.is_configured():
        return None

    query = f"SELECT {_OS_COLUMNS} FROM ordens_servico WHERE numero = ?"

    try:
        rows = conn.execute_query(query, (numero,))
        if not rows:
            return None
        return _enriquecer_os(_normalizar_row(rows[0]))
    except Exception:
        logger.exception("Erro ao consultar OS %s no Informix", numero)
        return None


def consultar_os_por_numero(numero: str) -> dict[str, Any] | None:
    """
    Busca OS por numero.
    
    Tenta consultar banco Informix primeiro.
    Se nao configurado ou falhar, usa dados MOCK.
    """
    result = _consultar_os_informix(numero)
    if result is not None:
        logger.debug("OS %s carregada do Informix", numero)
        return result

    logger.debug("Buscando OS %s nos dados MOCK", numero)
    for os in _MOCK_ORDENS:
        if os["numero"] == numero:
            enriched = _enriquecer_os(os)
            detalhes = _MOCK_DETALHES.get(numero, {})
            enriched["objeto"] = detalhes.get("objeto", "")
            enriched["valor_estimado"] = detalhes.get("valor_estimado", 0)
            enriched["endereco"] = detalhes.get("endereco", "")
            enriched["cnpj"] = detalhes.get("cnpj", "")
            enriched["telefone"] = detalhes.get("telefone", "")
            enriched["observacoes"] = detalhes.get("observacoes", "")
            enriched["movimentacoes"] = detalhes.get("movimentacoes", [])
            return enriched
    return None


def gerar_alertas(
    user_role: str | None = None,
    user_matricula: str | None = None,
    user_name: str | None = None,
    supervisor_matriculas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Gera alertas baseados em regras de negocio sobre as OS visiveis ao usuario.

    Usa dados do Informix se disponivel, senao usa MOCK.
    Respeita a filtragem hierarquica.
    """
    # Buscar OS filtradas pela hierarquia do usuario
    todas_os = listar_ordens_servico(
        user_role=user_role,
        user_matricula=user_matricula,
        user_name=user_name,
        supervisor_matriculas=supervisor_matriculas,
    )
    
    now = datetime.now(timezone.utc)
    alertas: list[dict[str, Any]] = []

    # Passo unico: classifica alertas em uma iteracao sobre todas as OS
    for os_item in todas_os:
        is_ativa = os_item["status"] in STATUSES_ATIVOS
        dias = os_item.get("dias_parado", 0)

        # Alerta 1: OS urgentes ativas
        if is_ativa and os_item["prioridade"] == "urgente":
            alertas.append({
                "tipo": "os_urgente",
                "severidade": "alta",
                "titulo": f"OS urgente - {os_item['razao_social']}",
                "descricao": (
                    f"A OS {os_item['numero']} (IE: {os_item['ie']}) esta com prioridade URGENTE "
                    f"e status '{os_item['status']}'."
                ),
                "referencia": os_item["numero"],
                "data": now.isoformat(),
            })

        # Alerta 2: OS paradas ha mais de N dias
        if is_ativa and dias > DIAS_CRITICO_THRESHOLD:
            alertas.append({
                "tipo": "os_parada",
                "severidade": "alta",
                "titulo": f"OS parada ha {dias} dias - {os_item['razao_social']}",
                "descricao": (
                    f"A OS {os_item['numero']} (IE: {os_item['ie']}) nao possui movimentacao "
                    f"ha {dias} dias. Ultima movimentacao: {os_item.get('data_ultima_movimentacao', '-')}."
                ),
                "referencia": os_item["numero"],
                "data": now.isoformat(),
            })

        # Alerta 3: OS abertas sem ciencia
        if os_item["status"] == "aberta" and not os_item.get("data_ciencia"):
            alertas.append({
                "tipo": "os_sem_ciencia",
                "severidade": "media",
                "titulo": f"OS sem ciencia - {os_item['razao_social']}",
                "descricao": (
                    f"A OS {os_item['numero']} (IE: {os_item['ie']}) foi aberta em {os_item['data_abertura']} "
                    f"e ainda nao possui data de ciencia."
                ),
                "referencia": os_item["numero"],
                "data": now.isoformat(),
            })

    # Ordenar por severidade (alta primeiro)
    ordem_severidade = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    alertas.sort(key=lambda a: ordem_severidade.get(a["severidade"], 9))

    return alertas


# ─── Dashboard – helpers reutilizaveis ───────────────────────────


def _calcular_metricas_os(os_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calcula metricas padrão de uma lista de OS.

    Reutilizado por visao geral, gerencias, supervisoes e fiscais
    para evitar duplicacao de logica de contagem.
    """
    total = len(os_list)
    abertas = sum(1 for o in os_list if o["status"] == "aberta")
    andamento = sum(1 for o in os_list if o["status"] == "em_andamento")
    concluidas = sum(1 for o in os_list if o["status"] == "concluida")
    canceladas = sum(1 for o in os_list if o["status"] == "cancelada")
    ativas = [o for o in os_list if o["status"] in STATUSES_ATIVOS]
    dias_parado_medio = (
        round(sum(o.get("dias_parado", 0) for o in ativas) / len(ativas), 1)
        if ativas else 0
    )
    criticas = sum(1 for o in ativas if o.get("dias_parado", 0) > DIAS_CRITICO_THRESHOLD)
    sem_ciencia = sum(
        1 for o in os_list
        if o["status"] == "aberta" and not o.get("data_ciencia")
    )
    taxa_conclusao = round((concluidas / total * 100), 1) if total > 0 else 0

    return {
        "total_os": total,
        "abertas": abertas,
        "em_andamento": andamento,
        "concluidas": concluidas,
        "canceladas": canceladas,
        "dias_parado_medio": dias_parado_medio,
        "os_criticas": criticas,
        "os_sem_ciencia": sem_ciencia,
        "taxa_conclusao": taxa_conclusao,
    }


def _calcular_tempo_medio_conclusao(os_list: list[dict[str, Any]]) -> float:
    """Calcula o tempo medio (em dias) entre abertura e conclusao das OS concluidas."""
    tempos: list[int] = []
    for o in os_list:
        if o["status"] == "concluida" and o.get("data_abertura") and o.get("data_ultima_movimentacao"):
            try:
                dt_abertura = datetime.strptime(o["data_abertura"], "%Y-%m-%d")
                dt_conclusao = datetime.strptime(o["data_ultima_movimentacao"], "%Y-%m-%d")
                dias = (dt_conclusao - dt_abertura).days
                if dias >= 0:
                    tempos.append(dias)
            except (ValueError, TypeError):
                pass
    return round(sum(tempos) / len(tempos), 1) if tempos else 0


# ─── Dashboard (consolidacao de metricas para admin) ─────────────


def gerar_dashboard(
    todas_os: list[dict[str, Any]],
    gerencias: list[dict[str, Any]],
    supervisoes: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Gera dados consolidados do dashboard administrativo.

    Calcula metricas de desempenho por gerencia, supervisao e fiscal,
    alem de indicadores gerais para o panorama da fiscalizacao.
    """
    now = datetime.now(timezone.utc)

    # ── Mapas auxiliares ──────────────────────────────────────
    sup_matricula_to_supervisao: dict[str, int] = {}
    sup_to_gerencia: dict[int, int] = {}
    gerencia_names: dict[int, str] = {g["id"]: g["name"] for g in gerencias}
    supervisao_names: dict[int, str] = {}

    for s in supervisoes:
        sup_to_gerencia[s["id"]] = s["gerencia_id"]
        supervisao_names[s["id"]] = s["name"]

    for u in users:
        if u.get("role") == "supervisor" and u.get("matricula") and u.get("supervisao_id"):
            sup_matricula_to_supervisao[u["matricula"]] = u["supervisao_id"]

    # ── Visao geral (usando helper centralizado) ──────────────
    metricas_gerais = _calcular_metricas_os(todas_os)
    tempo_medio_conclusao = _calcular_tempo_medio_conclusao(todas_os)
    total_fiscais = sum(1 for u in users if u.get("role") == "fiscal")
    total_supervisores = sum(1 for u in users if u.get("role") == "supervisor")

    # ── Agrupar OS por gerencia e supervisao ──────────────────
    ger_os: dict[int, list[dict]] = defaultdict(list)
    sup_os: dict[int, list[dict]] = defaultdict(list)
    for o in todas_os:
        mat_sup = o.get("matricula_supervisor", "")
        sup_id = sup_matricula_to_supervisao.get(mat_sup)
        if sup_id:
            sup_os[sup_id].append(o)
            ger_id = sup_to_gerencia.get(sup_id)
            if ger_id:
                ger_os[ger_id].append(o)

    # ── Desempenho por gerencia ───────────────────────────────
    desempenho_gerencias = _calcular_desempenho_gerencias(
        gerencia_names, ger_os,
    )

    # ── Ranking de criticidade (indice de saude) ──────────────
    ranking_criticidade = _calcular_ranking_criticidade(
        desempenho_gerencias, ger_os,
    )

    # ── Desempenho por supervisao ─────────────────────────────
    desempenho_supervisoes = _calcular_desempenho_supervisoes(
        supervisao_names, sup_os, sup_to_gerencia, gerencia_names,
    )

    # ── Carga por fiscal ──────────────────────────────────────
    carga_fiscais = _calcular_carga_fiscais(todas_os, users)

    # ── Distribuicao por status (grafico pizza) ───────────────
    distribuicao_status = {
        "aberta": metricas_gerais["abertas"],
        "em_andamento": metricas_gerais["em_andamento"],
        "concluida": metricas_gerais["concluidas"],
        "cancelada": metricas_gerais["canceladas"],
    }

    # ── Evolucao mensal ───────────────────────────────────────
    evolucao_mensal = _calcular_evolucao_mensal(todas_os)

    # ── Comparativo mensal (mes atual vs mes anterior) ────────
    comparativo_mensal = _calcular_comparativo_mensal(todas_os, now)

    return {
        "visao_geral": {
            "total_os": metricas_gerais["total_os"],
            "os_abertas": metricas_gerais["abertas"],
            "os_em_andamento": metricas_gerais["em_andamento"],
            "os_concluidas": metricas_gerais["concluidas"],
            "os_canceladas": metricas_gerais["canceladas"],
            "dias_parado_medio": metricas_gerais["dias_parado_medio"],
            "os_criticas": metricas_gerais["os_criticas"],
            "os_sem_ciencia": metricas_gerais["os_sem_ciencia"],
            "tempo_medio_conclusao": tempo_medio_conclusao,
            "total_fiscais": total_fiscais,
            "total_supervisores": total_supervisores,
        },
        "comparativo_mensal": comparativo_mensal,
        "distribuicao_status": distribuicao_status,
        "evolucao_mensal": evolucao_mensal,
        "desempenho_gerencias": desempenho_gerencias,
        "ranking_criticidade": ranking_criticidade,
        "desempenho_supervisoes": desempenho_supervisoes,
        "carga_fiscais": carga_fiscais,
    }


def _calcular_desempenho_gerencias(
    gerencia_names: dict[int, str],
    ger_os: dict[int, list[dict]],
) -> list[dict[str, Any]]:
    """Calcula metricas de desempenho por gerencia."""
    desempenho = []
    for gid, nome in gerencia_names.items():
        os_list = ger_os.get(gid, [])
        metricas = _calcular_metricas_os(os_list)
        tempo_med = _calcular_tempo_medio_conclusao(os_list)
        desempenho.append({
            "id": gid,
            "nome": nome,
            "total_os": metricas["total_os"],
            "abertas": metricas["abertas"],
            "em_andamento": metricas["em_andamento"],
            "concluidas": metricas["concluidas"],
            "canceladas": metricas["canceladas"],
            "dias_parado_medio": metricas["dias_parado_medio"],
            "os_criticas": metricas["os_criticas"],
            "taxa_conclusao": metricas["taxa_conclusao"],
            "tempo_medio_conclusao": tempo_med,
        })
    desempenho.sort(key=lambda g: g["dias_parado_medio"], reverse=True)
    return desempenho


def _calcular_ranking_criticidade(
    desempenho_gerencias: list[dict[str, Any]],
    ger_os: dict[int, list[dict]],
) -> list[dict[str, Any]]:
    """
    Calcula o indice de saude (0-100) para cada gerencia.

    Formula proporcional (escala com volume alto de OS):
      - % de OS criticas (>15 dias): ate -40 pts
      - Dias parado medio: -0.5 pt/dia
      - Taxa de conclusao baixa: ate -20 pts
      - % de OS sem ciencia: ate -20 pts
    """
    ranking = []
    for g in desempenho_gerencias:
        if g["total_os"] == 0:
            ranking.append({
                "id": g["id"], "nome": g["nome"],
                "indice_saude": 100, "nivel": "saudavel",
                "total_os": 0, "os_criticas": 0, "pct_criticas": 0,
                "os_sem_ciencia": 0, "pct_sem_ciencia": 0,
                "dias_parado_medio": 0, "taxa_conclusao": 0,
                "tempo_medio_conclusao": 0, "problemas": [],
            })
            continue

        # OS sem ciencia nesta gerencia
        os_sem_ciencia_ger = sum(
            1 for o in ger_os.get(g["id"], [])
            if o["status"] == "aberta" and not o.get("data_ciencia")
        )

        total = g["total_os"]
        pct_criticas = (g["os_criticas"] / total) * 100 if total else 0
        pct_sem_ciencia = (os_sem_ciencia_ger / total) * 100 if total else 0

        score = 100.0
        score -= pct_criticas * PESO_CRITICAS
        score -= g["dias_parado_medio"] * PESO_DIAS_PARADO
        score -= (100 - g["taxa_conclusao"]) * PESO_TAXA_CONCLUSAO
        score -= pct_sem_ciencia * PESO_SEM_CIENCIA
        score = max(0, min(100, round(score, 1)))

        if score >= 75:
            nivel = "saudavel"
        elif score >= 50:
            nivel = "atencao"
        elif score >= 25:
            nivel = "critico"
        else:
            nivel = "emergencia"

        problemas = _detectar_problemas(g, pct_criticas, os_sem_ciencia_ger, pct_sem_ciencia)

        ranking.append({
            "id": g["id"], "nome": g["nome"],
            "indice_saude": score, "nivel": nivel,
            "total_os": g["total_os"], "os_criticas": g["os_criticas"],
            "pct_criticas": round(pct_criticas, 1),
            "os_sem_ciencia": os_sem_ciencia_ger,
            "pct_sem_ciencia": round(pct_sem_ciencia, 1),
            "dias_parado_medio": g["dias_parado_medio"],
            "taxa_conclusao": g["taxa_conclusao"],
            "tempo_medio_conclusao": g["tempo_medio_conclusao"],
            "problemas": problemas,
        })

    ranking.sort(key=lambda r: r["indice_saude"])
    return ranking


def _detectar_problemas(
    g: dict[str, Any],
    pct_criticas: float,
    os_sem_ciencia_ger: int,
    pct_sem_ciencia: float,
) -> list[str]:
    """Monta lista de problemas detectados para uma gerencia (ranking)."""
    problemas: list[str] = []
    if pct_criticas > 20:
        problemas.append(f'{g["os_criticas"]} OS parada(s) >{DIAS_CRITICO_THRESHOLD} dias ({round(pct_criticas)}%)')
    elif g["os_criticas"] > 0:
        problemas.append(f'{g["os_criticas"]} OS parada(s) >{DIAS_CRITICO_THRESHOLD} dias')
    if pct_sem_ciencia > 10:
        problemas.append(f'{os_sem_ciencia_ger} OS sem ciencia ({round(pct_sem_ciencia)}%)')
    elif os_sem_ciencia_ger > 0:
        problemas.append(f'{os_sem_ciencia_ger} OS sem ciencia')
    if g["dias_parado_medio"] > 10:
        problemas.append(f'Media {g["dias_parado_medio"]} dias parado')
    if g["taxa_conclusao"] < 30:
        problemas.append(f'Taxa de conclusao {g["taxa_conclusao"]}%')
    return problemas


def _calcular_desempenho_supervisoes(
    supervisao_names: dict[int, str],
    sup_os: dict[int, list[dict]],
    sup_to_gerencia: dict[int, int],
    gerencia_names: dict[int, str],
) -> list[dict[str, Any]]:
    """Calcula metricas de desempenho por supervisao."""
    desempenho = []
    for sid, nome in supervisao_names.items():
        os_list = sup_os.get(sid, [])
        metricas = _calcular_metricas_os(os_list)
        ger_id = sup_to_gerencia.get(sid)
        ger_nome = gerencia_names.get(ger_id, "-") if ger_id else "-"
        desempenho.append({
            "id": sid, "nome": nome,
            "gerencia_id": ger_id, "gerencia_nome": ger_nome,
            "total_os": metricas["total_os"],
            "abertas": metricas["abertas"],
            "em_andamento": metricas["em_andamento"],
            "concluidas": metricas["concluidas"],
            "dias_parado_medio": metricas["dias_parado_medio"],
            "os_criticas": metricas["os_criticas"],
            "taxa_conclusao": metricas["taxa_conclusao"],
        })
    desempenho.sort(key=lambda s: s["dias_parado_medio"], reverse=True)
    return desempenho


def _calcular_carga_fiscais(
    todas_os: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Calcula carga de trabalho por fiscal (apenas OS ativas)."""
    fiscal_name_to_sup: dict[str, int | None] = {
        u["username"]: u.get("supervisao_id")
        for u in users if u.get("role") == "fiscal"
    }

    fiscal_os: dict[str, list[dict]] = defaultdict(list)
    for o in todas_os:
        if o["status"] in STATUSES_ATIVOS:
            for fiscal in o.get("fiscais", []):
                fiscal_os[fiscal].append(o)

    carga = []
    for fiscal_name, os_list in fiscal_os.items():
        total = len(os_list)
        dias_med = round(sum(o.get("dias_parado", 0) for o in os_list) / total, 1) if total else 0
        paradas = sum(1 for o in os_list if o.get("dias_parado", 0) > DIAS_CRITICO_THRESHOLD)
        carga.append({
            "nome": fiscal_name,
            "supervisao_id": fiscal_name_to_sup.get(fiscal_name),
            "os_ativas": total,
            "dias_parado_medio": dias_med,
            "os_criticas": paradas,
        })
    carga.sort(key=lambda f: f["os_ativas"], reverse=True)
    return carga


# ─── ATF API Integration ─────────────────────────────────────────
#
# Quando ATF_BASE_URL estiver configurado no .env, o sistema faz
# requisicoes HTTPS ao servico do ATF e parseia o XML retornado.
# Quando NAO estiver configurado, usa dados MOCK para desenvolvimento.
#
# Para ativar: adicione ATF_BASE_URL=https://atf.sefaz.pb.gov.br no .env

_MODELOS_ATF: dict[str, str] = {
    "1": "NORMAL",
    "2": "SIMPLIFICADA",
    "7": "ESPECIAL",
    "8": "ESPECÍFICA",
}

_MOCK_ATF_ORDENS: list[dict[str, Any]] = [
    {
        "numero_os": "OS-2026-001", "modelo": "NORMAL",
        "ie": "12.345.678-9", "cnpj": "12.345.678/0001-90",
        "razao_social": "Distribuidora ABC Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-01-12"},
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2026-01-14"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-01-10",
    },
    {
        "numero_os": "OS-2026-002", "modelo": "SIMPLIFICADA",
        "ie": "98.765.432-1", "cnpj": "98.765.432/0001-10",
        "razao_social": "Industria Delta S/A",
        "fiscais": [
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2026-02-03"},
        ],
        "situacao": {"codigo": 5, "descricao": "BLOQUEADA"},
        "data_abertura": "2026-02-01",
    },
    {
        "numero_os": "OS-2026-003", "modelo": "ESPECIAL",
        "ie": "55.667.778-3", "cnpj": "55.667.778/0001-30",
        "razao_social": "Transportes Rapido Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-01-08"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-01-05",
    },
    {
        "numero_os": "OS-2026-004", "modelo": "NORMAL",
        "ie": "33.445.556-4", "cnpj": "33.445.556/0001-40",
        "razao_social": "Supermercado Central Ltda",
        "fiscais": [
            {"matricula": "34570", "nome": "Jose Almeida", "data_ciencia": None},
        ],
        "situacao": {"codigo": 0, "descricao": "AGUARDANDO AUTORIZAÇÃO"},
        "data_abertura": "2026-02-05",
    },
    {
        "numero_os": "OS-2026-005", "modelo": "SIMPLIFICADA",
        "ie": "77.889.900-5", "cnpj": "77.889.900/0001-50",
        "razao_social": "Farmacia Popular Ltda",
        "fiscais": [
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2025-12-18"},
            {"matricula": "34571", "nome": "Fernanda Costa", "data_ciencia": "2025-12-20"},
        ],
        "situacao": {"codigo": 4, "descricao": "ENCERRADA"},
        "data_abertura": "2025-12-15",
    },
    {
        "numero_os": "OS-2026-006", "modelo": "ESPECÍFICA",
        "ie": "12.345.678-9", "cnpj": "12.345.678/0001-90",
        "razao_social": "Distribuidora ABC Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-02-09"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-02-07",
    },
    {
        "numero_os": "OS-2026-007", "modelo": "NORMAL",
        "ie": "98.765.432-1", "cnpj": "98.765.432/0001-10",
        "razao_social": "Industria Delta S/A",
        "fiscais": [
            {"matricula": "34569", "nome": "Pedro Nascimento", "data_ciencia": "2026-01-18"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-01-15",
    },
    {
        "numero_os": "OS-2026-008", "modelo": "SIMPLIFICADA",
        "ie": "33.445.556-4", "cnpj": "33.445.556/0001-40",
        "razao_social": "Supermercado Central Ltda",
        "fiscais": [
            {"matricula": "34570", "nome": "Jose Almeida", "data_ciencia": "2025-12-05"},
        ],
        "situacao": {"codigo": 0, "descricao": "AGUARDANDO AUTORIZAÇÃO"},
        "data_abertura": "2025-12-01",
    },
    {
        "numero_os": "OS-2026-009", "modelo": "ESPECIAL",
        "ie": "55.667.778-3", "cnpj": "55.667.778/0001-30",
        "razao_social": "Transportes Rapido Ltda",
        "fiscais": [
            {"matricula": "34571", "nome": "Fernanda Costa", "data_ciencia": None},
        ],
        "situacao": {"codigo": 5, "descricao": "BLOQUEADA"},
        "data_abertura": "2026-02-08",
    },
    {
        "numero_os": "OS-2026-010", "modelo": "NORMAL",
        "ie": "77.889.900-5", "cnpj": "77.889.900/0001-50",
        "razao_social": "Farmacia Popular Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-01-22"},
        ],
        "situacao": {"codigo": 2, "descricao": "CANCELADA"},
        "data_abertura": "2026-01-20",
    },
    {
        "numero_os": "OS-2026-011", "modelo": "SIMPLIFICADA",
        "ie": "12.345.678-9", "cnpj": "12.345.678/0001-90",
        "razao_social": "Distribuidora ABC Ltda",
        "fiscais": [
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2026-03-03"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-03-01",
    },
    {
        "numero_os": "OS-2026-012", "modelo": "ESPECIAL",
        "ie": "98.765.432-1", "cnpj": "98.765.432/0001-10",
        "razao_social": "Industria Delta S/A",
        "fiscais": [
            {"matricula": "34569", "nome": "Pedro Nascimento", "data_ciencia": "2026-03-07"},
        ],
        "situacao": {"codigo": 6, "descricao": "EM ANÁLISE PARA ENCERRAMENTO"},
        "data_abertura": "2026-03-05",
    },
    {
        "numero_os": "OS-2026-013", "modelo": "NORMAL",
        "ie": "55.667.778-3", "cnpj": "55.667.778/0001-30",
        "razao_social": "Transportes Rapido Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-03-12"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-03-10",
    },
    {
        "numero_os": "OS-2026-014", "modelo": "ESPECÍFICA",
        "ie": "33.445.556-4", "cnpj": "33.445.556/0001-40",
        "razao_social": "Supermercado Central Ltda",
        "fiscais": [
            {"matricula": "34570", "nome": "Jose Almeida", "data_ciencia": "2026-03-15"},
        ],
        "situacao": {"codigo": 7, "descricao": "EXECUÇÃO SUSPENSA"},
        "data_abertura": "2026-03-12",
    },
    {
        "numero_os": "OS-2026-015", "modelo": "NORMAL",
        "ie": "77.889.900-5", "cnpj": "77.889.900/0001-50",
        "razao_social": "Farmacia Popular Ltda",
        "fiscais": [
            {"matricula": "34571", "nome": "Fernanda Costa", "data_ciencia": "2025-11-25"},
        ],
        "situacao": {"codigo": 3, "descricao": "SUBSTITUÍDA"},
        "data_abertura": "2025-11-20",
    },
    {
        "numero_os": "OS-2026-016", "modelo": "SIMPLIFICADA",
        "ie": "12.345.678-9", "cnpj": "12.345.678/0001-90",
        "razao_social": "Distribuidora ABC Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2025-11-18"},
        ],
        "situacao": {"codigo": 4, "descricao": "ENCERRADA"},
        "data_abertura": "2025-11-15",
    },
    {
        "numero_os": "OS-2026-017", "modelo": "NORMAL",
        "ie": "98.765.432-1", "cnpj": "98.765.432/0001-10",
        "razao_social": "Industria Delta S/A",
        "fiscais": [
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2026-03-22"},
            {"matricula": "34569", "nome": "Pedro Nascimento", "data_ciencia": "2026-03-23"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-03-20",
    },
    {
        "numero_os": "OS-2026-018", "modelo": "ESPECIAL",
        "ie": "55.667.778-3", "cnpj": "55.667.778/0001-30",
        "razao_social": "Transportes Rapido Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": None},
        ],
        "situacao": {"codigo": 0, "descricao": "AGUARDANDO AUTORIZAÇÃO"},
        "data_abertura": "2026-04-01",
    },
    {
        "numero_os": "OS-2026-019", "modelo": "NORMAL",
        "ie": "33.445.556-4", "cnpj": "33.445.556/0001-40",
        "razao_social": "Supermercado Central Ltda",
        "fiscais": [
            {"matricula": "34570", "nome": "Jose Almeida", "data_ciencia": "2026-03-27"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-03-25",
    },
    {
        "numero_os": "OS-2026-020", "modelo": "ESPECÍFICA",
        "ie": "77.889.900-5", "cnpj": "77.889.900/0001-50",
        "razao_social": "Farmacia Popular Ltda",
        "fiscais": [
            {"matricula": "34571", "nome": "Fernanda Costa", "data_ciencia": "2026-02-17"},
        ],
        "situacao": {"codigo": 2, "descricao": "CANCELADA"},
        "data_abertura": "2026-02-14",
    },
    {
        "numero_os": "OS-2026-021", "modelo": "SIMPLIFICADA",
        "ie": "12.345.678-9", "cnpj": "12.345.678/0001-90",
        "razao_social": "Distribuidora ABC Ltda",
        "fiscais": [
            {"matricula": "34567", "nome": "Carlos Mendes", "data_ciencia": "2026-02-23"},
        ],
        "situacao": {"codigo": 5, "descricao": "BLOQUEADA"},
        "data_abertura": "2026-02-20",
    },
    {
        "numero_os": "OS-2026-022", "modelo": "NORMAL",
        "ie": "98.765.432-1", "cnpj": "98.765.432/0001-10",
        "razao_social": "Industria Delta S/A",
        "fiscais": [
            {"matricula": "34568", "nome": "Ana Ribeiro", "data_ciencia": "2026-03-30"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-03-28",
    },
    {
        "numero_os": "OS-2026-023", "modelo": "ESPECIAL",
        "ie": "55.667.778-3", "cnpj": "55.667.778/0001-30",
        "razao_social": "Transportes Rapido Ltda",
        "fiscais": [
            {"matricula": "34569", "nome": "Pedro Nascimento", "data_ciencia": "2025-10-15"},
        ],
        "situacao": {"codigo": 4, "descricao": "ENCERRADA"},
        "data_abertura": "2025-10-10",
    },
    {
        "numero_os": "OS-2026-024", "modelo": "SIMPLIFICADA",
        "ie": "33.445.556-4", "cnpj": "33.445.556/0001-40",
        "razao_social": "Supermercado Central Ltda",
        "fiscais": [
            {"matricula": "34570", "nome": "Jose Almeida", "data_ciencia": "2026-04-07"},
        ],
        "situacao": {"codigo": 1, "descricao": "AUTORIZADA"},
        "data_abertura": "2026-04-05",
    },
    {
        "numero_os": "OS-2026-025", "modelo": "NORMAL",
        "ie": "77.889.900-5", "cnpj": "77.889.900/0001-50",
        "razao_social": "Farmacia Popular Ltda",
        "fiscais": [
            {"matricula": "34571", "nome": "Fernanda Costa", "data_ciencia": "2026-04-13"},
        ],
        "situacao": {"codigo": 6, "descricao": "EM ANÁLISE PARA ENCERRAMENTO"},
        "data_abertura": "2026-04-10",
    },
]


def _filtrar_mock_atf(
    numero_os: str | None = None,
    modelo: str | None = None,
    ie: str | None = None,
    cnpj: str | None = None,
    razao_social: str | None = None,
    matriculas: str | None = None,
    situacoes: list[int] | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_ciencia_ini: str | None = None,
    data_ciencia_fim: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    """Filtra o mock ATF e retorna paginacao + ordens."""
    resultados = list(_MOCK_ATF_ORDENS)

    if numero_os:
        resultados = [o for o in resultados if o["numero_os"] == numero_os]
    if modelo:
        nome_modelo = _MODELOS_ATF.get(str(modelo))
        resultados = [o for o in resultados if o["modelo"] == nome_modelo] if nome_modelo else []
    if ie:
        resultados = [o for o in resultados if o["ie"] == ie]
    if cnpj:
        resultados = [o for o in resultados if o.get("cnpj") == cnpj]
    if razao_social:
        term = razao_social.lower()
        resultados = [o for o in resultados if term in o["razao_social"].lower()]
    if matriculas:
        mats = {m.strip() for m in matriculas.split(",") if m.strip()}
        resultados = [o for o in resultados if any(f["matricula"] in mats for f in o["fiscais"])]
    if situacoes:
        situacoes_set = set(situacoes)
        resultados = [o for o in resultados if o["situacao"]["codigo"] in situacoes_set]
    if data_abertura_ini:
        resultados = [o for o in resultados if o["data_abertura"] >= data_abertura_ini]
    if data_abertura_fim:
        resultados = [o for o in resultados if o["data_abertura"] <= data_abertura_fim]
    if data_ciencia_ini or data_ciencia_fim:
        def _ciencia_in_range(os_item: dict) -> bool:
            dates = [f["data_ciencia"] for f in os_item["fiscais"] if f.get("data_ciencia")]
            if not dates:
                return False
            earliest = min(dates)
            if data_ciencia_ini and earliest < data_ciencia_ini:
                return False
            if data_ciencia_fim and earliest > data_ciencia_fim:
                return False
            return True
        resultados = [o for o in resultados if _ciencia_in_range(o)]

    total = len(resultados)
    total_paginas = max(1, (total + limite - 1) // limite)
    inicio = (pagina - 1) * limite
    pagina_data = resultados[inicio: inicio + limite]

    return {
        "paginacao": {
            "pagina_atual": pagina,
            "limite_por_pagina": limite,
            "total_paginas": total_paginas,
            "total_registros": total,
        },
        "ordens": pagina_data,
    }


def _parse_xml_atf(xml_text: str) -> dict[str, Any]:
    """Parseia o XML retornado pelo ATF para o formato interno da API."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)

    pag_el = root.find("paginacao")
    paginacao = {
        "pagina_atual": int(pag_el.findtext("pagina_atual", "1") or 1),
        "limite_por_pagina": int(pag_el.findtext("limite_por_pagina", "20") or 20),
        "total_paginas": int(pag_el.findtext("total_paginas", "1") or 1),
        "total_registros": int(pag_el.findtext("total_registros", "0") or 0),
    }

    ordens = []
    for ordem_el in root.findall("ordens/ordem"):
        fiscais = []
        for f_el in ordem_el.findall("fiscais/fiscal"):
            fiscais.append({
                "matricula": f_el.findtext("matricula", ""),
                "nome": f_el.findtext("nome", ""),
                "data_ciencia": f_el.findtext("data_ciencia"),
            })

        sit_el = ordem_el.find("situacao")
        situacao = {
            "codigo": int(sit_el.findtext("codigo", "0") or 0),
            "descricao": sit_el.findtext("descricao", ""),
        } if sit_el is not None else {"codigo": 0, "descricao": "AGUARDANDO AUTORIZAÇÃO"}

        ordens.append({
            "numero_os": ordem_el.findtext("numero_os", ""),
            "modelo": ordem_el.findtext("modelo", ""),
            "ie": ordem_el.findtext("ie", ""),
            "cnpj": ordem_el.findtext("cnpj"),
            "razao_social": ordem_el.findtext("razao_social", ""),
            "fiscais": fiscais,
            "situacao": situacao,
            "data_abertura": ordem_el.findtext("data_abertura", ""),
        })

    return {"paginacao": paginacao, "ordens": ordens}


def _chamar_atf_https(
    base_url: str,
    numero_os: str | None = None,
    modelo: str | None = None,
    ie: str | None = None,
    cnpj: str | None = None,
    razao_social: str | None = None,
    matriculas: str | None = None,
    situacoes: list[int] | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_ciencia_ini: str | None = None,
    data_ciencia_fim: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    """Chama o endpoint HTTPS do ATF e retorna os dados parseados do XML."""
    import requests

    params: list[tuple[str, Any]] = [("pagina", pagina), ("limite", limite)]
    if numero_os:
        params.append(("numero_os", numero_os))
    if modelo:
        params.append(("modelo", modelo))
    if ie:
        params.append(("ie", ie))
    if cnpj:
        params.append(("cnpj", cnpj))
    if razao_social:
        params.append(("razao_social", razao_social))
    if matriculas:
        params.append(("matriculas", matriculas))
    if situacoes:
        for s in situacoes:
            params.append(("situacao", s))
    if data_abertura_ini:
        params.append(("data_abertura_ini", data_abertura_ini))
    if data_abertura_fim:
        params.append(("data_abertura_fim", data_abertura_fim))
    if data_ciencia_ini:
        params.append(("data_ciencia_ini", data_ciencia_ini))
    if data_ciencia_fim:
        params.append(("data_ciencia_fim", data_ciencia_fim))

    try:
        resp = requests.get(f"{base_url}/ordens", params=params, timeout=30)
        resp.raise_for_status()
        return _parse_xml_atf(resp.text)
    except Exception:
        logger.exception("Erro ao chamar API ATF em %s", base_url)
        raise


def listar_ordens_atf(
    numero_os: str | None = None,
    modelo: str | None = None,
    ie: str | None = None,
    cnpj: str | None = None,
    razao_social: str | None = None,
    matriculas: str | None = None,
    situacoes: list[int] | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_ciencia_ini: str | None = None,
    data_ciencia_fim: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    """
    Lista OS via API ATF.

    Se ATF_BASE_URL estiver configurado no .env, chama o servico real via HTTPS.
    Caso contrario, usa dados MOCK para desenvolvimento/teste.
    """
    from .config import ATF_BASE_URL

    if ATF_BASE_URL:
        logger.debug("Chamando API ATF: %s", ATF_BASE_URL)
        return _chamar_atf_https(
            ATF_BASE_URL,
            numero_os=numero_os, modelo=modelo, ie=ie, cnpj=cnpj,
            razao_social=razao_social, matriculas=matriculas, situacoes=situacoes,
            data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
            data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
            pagina=pagina, limite=limite,
        )

    logger.debug("ATF_BASE_URL nao configurado – usando dados MOCK ATF (%d registros)", len(_MOCK_ATF_ORDENS))
    return _filtrar_mock_atf(
        numero_os=numero_os, modelo=modelo, ie=ie, cnpj=cnpj,
        razao_social=razao_social, matriculas=matriculas, situacoes=situacoes,
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
        pagina=pagina, limite=limite,
    )


def _calcular_evolucao_mensal(todas_os: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calcula evolucao mensal de OS abertas e concluidas (para grafico linha/barra)."""
    os_por_mes: dict[str, dict[str, int]] = defaultdict(lambda: {"abertas": 0, "concluidas": 0})
    for o in todas_os:
        if o.get("data_abertura"):
            try:
                mes = o["data_abertura"][:7]
                os_por_mes[mes]["abertas"] += 1
            except (ValueError, TypeError):
                pass
        if o["status"] == "concluida" and o.get("data_ultima_movimentacao"):
            try:
                mes = o["data_ultima_movimentacao"][:7]
                os_por_mes[mes]["concluidas"] += 1
            except (ValueError, TypeError):
                pass

    meses_ordenados = sorted(os_por_mes.keys())
    return [
        {"mes": m, "abertas": os_por_mes[m]["abertas"], "concluidas": os_por_mes[m]["concluidas"]}
        for m in meses_ordenados
    ]


def _calcular_comparativo_mensal(
    todas_os: list[dict[str, Any]], now: datetime,
) -> dict[str, Any]:
    """
    Compara KPIs do mes mais recente com o mes anterior.

    Usa os dois meses mais recentes com dados (fallback para calendario atual).
    """
    meses_com_dados = sorted(set(
        (o.get("data_abertura") or "")[:7]
        for o in todas_os
        if (o.get("data_abertura") or "")[:7] > ""
    ))

    if len(meses_com_dados) >= 2:
        mes_atual = meses_com_dados[-1]
        mes_anterior = meses_com_dados[-2]
    elif len(meses_com_dados) == 1:
        mes_atual = meses_com_dados[0]
        mes_anterior = ""
    else:
        mes_atual = now.strftime("%Y-%m")
        primeiro_dia = now.replace(day=1)
        if primeiro_dia.month == 1:
            mes_ant_dt = primeiro_dia.replace(year=primeiro_dia.year - 1, month=12)
        else:
            mes_ant_dt = primeiro_dia.replace(month=primeiro_dia.month - 1)
        mes_anterior = mes_ant_dt.strftime("%Y-%m")

    os_atual = [o for o in todas_os if (o.get("data_abertura") or "")[:7] == mes_atual]
    os_ant = [o for o in todas_os if (o.get("data_abertura") or "")[:7] == mes_anterior]

    kpi_atual = _calcular_metricas_os(os_atual)
    kpi_ant = _calcular_metricas_os(os_ant)

    comparativo: dict[str, Any] = {}
    # Selecionar apenas KPIs relevantes para o comparativo
    chaves_comparativo = (
        "total_os", "abertas", "em_andamento", "concluidas",
        "os_criticas", "os_sem_ciencia", "dias_parado_medio",
    )
    for k in chaves_comparativo:
        val_atual = kpi_atual[k]
        val_ant = kpi_ant[k]
        delta = round(val_atual - val_ant, 1) if isinstance(val_atual, (int, float)) else 0
        comparativo[k] = {"atual": val_atual, "anterior": val_ant, "delta": delta}
    comparativo["_labels"] = {"mes_atual": mes_atual, "mes_anterior": mes_anterior}

    return comparativo
