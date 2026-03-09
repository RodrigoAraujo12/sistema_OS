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
            return _enriquecer_os(os)
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
