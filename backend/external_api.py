"""
Servico de dados externos - Ordens de Servico.

Fonte de dados: API ATF via SOAP (doc da listagem). Quando ATF_BASE_URL
nao esta configurado, o sistema usa dados MOCK para desenvolvimento.
"""

from __future__ import annotations

import logging
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any
from xml.sax.saxutils import escape as _escape_xml

from .config import ATF_CACHE_TTL

logger = logging.getLogger("sefaz.external_api")

# ─── Constantes de negocio ──────────────────────────────────────

STATUSES_ATIVOS = ("aberta", "em_andamento")
DIAS_CRITICO_THRESHOLD = 15  # Reservado para uso futuro em alertas

# Pesos da formula de indice de saude (score 0-100 por gerencia)
PESO_TAXA_CONCLUSAO = 0.50 # (100 - taxa%) * 0.50 → ate -50 pts
PESO_SEM_CIENCIA = 0.50    # % sem ciencia * 0.50 → ate -50 pts


# ─── MOCK: Ordens de Servico ────────────────────────────────────
# Formato interno legado, usado por alertas e dashboard.

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


def filtrar_atf_por_matriculas(
    ordens: list[dict[str, Any]],
    matriculas_visiveis: set[str] | None,
) -> list[dict[str, Any]]:
    """
    Restringe OS no formato ATF as matriculas que o usuario pode enxergar.

    None = sem restricao (admin). Conjunto vazio = nao ve nada — esse e o
    resultado correto para quem nao tem matricula ou equipe, e nao "ve
    tudo": este filtro falha fechado de proposito.

    O formato ATF nao tem 'matricula_supervisor', que e do formato legado
    usado por alertas e dashboard. A unica ligacao entre a OS e as pessoas
    e a lista fiscais[].matricula, entao a hierarquia inteira e resolvida
    como um conjunto de matriculas montado no banco local (ver
    _matriculas_visiveis, em main.py).
    """
    if matriculas_visiveis is None:
        return ordens
    if not matriculas_visiveis:
        return []
    return [
        o for o in ordens
        if any(f.get("matricula") in matriculas_visiveis for f in o.get("fiscais", []))
    ]


def listar_ordens_servico(
    situacao_filter: str | None = None,
    tipo: str | None = None,
    user_role: str | None = None,
    user_matricula: str | None = None,
    user_name: str | None = None,
    supervisor_matriculas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Lista Ordens de Servico com filtros opcionais e filtragem hierarquica.

    Usado apenas por alertas e dashboard, que ainda consomem o formato
    interno legado. A consulta de OS do painel usa listar_ordens_atf().
    """
    results = list(_MOCK_ORDENS)
    if situacao_filter is not None:
        codigo = int(situacao_filter)
        results = [o for o in results if o.get("situacao", {}).get("codigo") == codigo]
    if tipo:
        results = [os for os in results if os["tipo"] == tipo]
    return _filtrar_por_hierarquia(results, user_role, user_matricula, user_name, supervisor_matriculas)


def gerar_alertas(
    user_role: str | None = None,
    user_matricula: str | None = None,
    user_name: str | None = None,
    supervisor_matriculas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Gera alertas baseados em regras de negocio sobre as OS visiveis ao usuario.

    Usa o formato interno legado (MOCK).
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
    Calcula metricas de uma lista de OS.

    Reutilizado por visao geral, gerencias, supervisoes e fiscais.
    """
    total = len(os_list)
    abertas = sum(1 for o in os_list if o["status"] == "aberta")
    andamento = sum(1 for o in os_list if o["status"] == "em_andamento")
    concluidas = sum(1 for o in os_list if o["status"] == "concluida")
    canceladas = sum(1 for o in os_list if o["status"] == "cancelada")
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
        "os_sem_ciencia": sem_ciencia,
        "taxa_conclusao": taxa_conclusao,
    }


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
            "os_sem_ciencia": metricas_gerais["os_sem_ciencia"],
            "taxa_conclusao": metricas_gerais["taxa_conclusao"],
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
        desempenho.append({
            "id": gid,
            "nome": nome,
            "total_os": metricas["total_os"],
            "abertas": metricas["abertas"],
            "em_andamento": metricas["em_andamento"],
            "concluidas": metricas["concluidas"],
            "canceladas": metricas["canceladas"],
            "os_sem_ciencia": metricas["os_sem_ciencia"],
            "taxa_conclusao": metricas["taxa_conclusao"],
        })
    desempenho.sort(key=lambda g: g["taxa_conclusao"])
    return desempenho


def _calcular_ranking_criticidade(
    desempenho_gerencias: list[dict[str, Any]],
    ger_os: dict[int, list[dict]],
) -> list[dict[str, Any]]:
    """
    Calcula o indice de saude (0-100) para cada gerencia.

    Formula:
      - Taxa de conclusao baixa: (100 - taxa%) * 0.50 → ate -50 pts
      - % de OS sem ciencia: pct_sem_ciencia * 0.50 → ate -50 pts
    """
    ranking = []
    for g in desempenho_gerencias:
        if g["total_os"] == 0:
            ranking.append({
                "id": g["id"], "nome": g["nome"],
                "indice_saude": 100, "nivel": "saudavel",
                "total_os": 0, "os_sem_ciencia": 0,
                "pct_sem_ciencia": 0, "taxa_conclusao": 0,
                "problemas": [],
            })
            continue

        total = g["total_os"]
        os_sem_ciencia_ger = g["os_sem_ciencia"]
        pct_sem_ciencia = (os_sem_ciencia_ger / total) * 100 if total else 0

        score = 100.0
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

        problemas = _detectar_problemas(g, os_sem_ciencia_ger, pct_sem_ciencia)

        ranking.append({
            "id": g["id"], "nome": g["nome"],
            "indice_saude": score, "nivel": nivel,
            "total_os": g["total_os"],
            "os_sem_ciencia": os_sem_ciencia_ger,
            "pct_sem_ciencia": round(pct_sem_ciencia, 1),
            "taxa_conclusao": g["taxa_conclusao"],
            "problemas": problemas,
        })

    ranking.sort(key=lambda r: r["indice_saude"])
    return ranking


def _detectar_problemas(
    g: dict[str, Any],
    os_sem_ciencia_ger: int,
    pct_sem_ciencia: float,
) -> list[str]:
    """Monta lista de problemas detectados para uma gerencia (ranking)."""
    problemas: list[str] = []
    if pct_sem_ciencia > 10:
        problemas.append(f'{os_sem_ciencia_ger} OS sem ciencia ({round(pct_sem_ciencia)}%)')
    elif os_sem_ciencia_ger > 0:
        problemas.append(f'{os_sem_ciencia_ger} OS sem ciencia')
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
            "os_sem_ciencia": metricas["os_sem_ciencia"],
            "taxa_conclusao": metricas["taxa_conclusao"],
        })
    desempenho.sort(key=lambda s: s["taxa_conclusao"])
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
        carga.append({
            "nome": fiscal_name,
            "supervisao_id": fiscal_name_to_sup.get(fiscal_name),
            "os_ativas": len(os_list),
        })
    carga.sort(key=lambda f: f["os_ativas"], reverse=True)
    return carga


# ─── ATF API Integration ─────────────────────────────────────────
#
# Quando ATF_BASE_URL estiver configurado no .env, o sistema faz
# requisicoes HTTPS ao servico do ATF e parseia o XML retornado.
# Quando NAO estiver configurado, usa dados MOCK para desenvolvimento.
#
# Para ativar: adicione ATF_BASE_URL=https://<host-do-atf> no .env

_MODELOS_ATF: dict[str, str] = {
    "1": "NORMAL",
    "2": "SIMPLIFICADA",
    "7": "ESPECIAL",
    "8": "ESPECÍFICA",
}

# Tabela de status de OS (doc da listagem). O servico devolve o codigo em
# statusOS, entao ela serve como fallback: completar a descricao a partir
# do codigo, ou recuperar o codigo a partir do nome (noStatusOS) caso o
# campo numerico venha vazio.
_STATUS_ATF: dict[int, str] = {
    0: "AGUARDANDO AUTORIZAÇÃO",
    1: "AUTORIZADA",
    2: "CANCELADA",
    3: "SUBSTITUÍDA",
    4: "ENCERRADA",
    5: "BLOQUEADA",
    6: "EM ANÁLISE PARA ENCERRAMENTO",
    7: "EXECUÇÃO SUSPENSA",
}
_STATUS_ATF_POR_NOME: dict[str, int] = {v: k for k, v in _STATUS_ATF.items()}

# Tabela de motivos de abertura ATIVOS (doc da listagem, cdMotivoAbertOS).
# Motivos marcados como (INATIVO) na documentacao foram omitidos.
_MOTIVOS_ABERTURA_ATF: dict[str, str] = {
    "163": "ALTERACAO CADASTRAL",
    "164": "ANALISE DE CREDITO",
    "165": "ATENDIMENTO DEMANDA EXTERNA",
    "166": "ATENDIMENTO DEMANDA SER-PB",
    "167": "BENEFÍCIO FISCAL",
    "168": "DENÚNCIA FISCAL",
    "169": "DOCS ELETRÔNICOS X EFD / GIM",
    "170": "DOCS ELETRÔNICOS OU PGDAS D",
    "171": "ECF - CESSAÇÃO",
    "172": "ECF - OUTROS",
    "173": "ENTRADAS X SAÍDAS",
    "174": "INADIMPLÊNCIA",
    "176": "INSCRIÇÃO ESTADUAL",
    "177": "LEVANTAMENTO DA CONTA MERCADORIAS",
    "178": "LEVANTAMENTO DE ESTOQUE",
    "179": "MONITORAMENTO",
    "180": "OUTRAS INCONSISTÊNCIAS EFD / GIM",
    "181": "OUTRAS INCONSISTÊNCIAS PGDASD",
    "182": "OUTROS",
    "183": "PROGRAMAÇÃO FISCAL",
    "184": "PEDIDO DE RESSARCIMENTO",
    "185": "REVISÃO / CANCELAMENTO DE DAR / FATURA",
    "186": "REVISÃO / COMPLEMENTO / NOVO FEITO",
    "187": "SUBSTITUIÇÃO TRIBUTÁRIA",
    "188": "VALOR ADICIONADO - IPM",
    "189": "VENDAS X CARTAO DE CREDITO",
    "191": "INATIVAÇÃO CADASTRAL",
    "192": "MONITORAMENTO SIMPLES NACIONAL",
    "193": "MALHA DECADÊNCIA 2017 - 2018",
    "194": "ACOMPANHAMENTO PERMANENTE",
    "195": "MALHA FISCAL",
    "196": "BD MALHA - MALHA FISCAL",
    "197": "MONITORAMENTO SCANC",
    "198": "PEDIDO DE RESTITUIÇÃO",
    "200": "ATEND SER GT/COTEPE",
    "202": "AUD ALTERACAO CADASTRAL",
    "203": "AUD COMP _ PROGRAMAÇÃO_ INDICADORES",
    "204": "AUD COMPLETA _ SOLICITAÇÃO",
    "205": "AUD COMPLETA _ SUBST TRIBUTÁRIA",
    "207": "ATEND EXT MINISTÉRIO PÚBLICO",
    "208": "ATEND EXT TRIB JUSTICA",
    "210": "ATEND EXT TRIBUNAL DE CONTAS",
    "211": "ATEND EXT. OUTROS",
    "212": "AI DILIGÊNCIA CRF",
    "213": "AI DILIGÊNCIA GEJUP",
    "214": "AI REVISÃO",
    "215": "AI NOVO FEITO",
    "216": "AI TERMO COMP. INFRACAO",
    "217": "REGIME ESPECIAL",
    "218": "AUDITORIA DE CONFORMIDADE",
    "219": "PEDIDO RESSARCIMENTO",
    "220": "PEDIDO RESTITUIÇÃO",
    "221": "LIBERAÇÃO SELO FISCAL",
    "223": "RETIFICAÇÃO ANEXO SCANC",
    "224": "RETIFICAÇÃO ANEXO SCANC",
    "225": "IMPORTACAO/EXPORTACAO",
    "226": "ZONA FRANCA MANAUS/AREAS LIVRE COMÉRCIO",
    "227": "MONIT SMTC",
    "228": "MONIT PMPF",
    "229": "MONIT MOINHOS/FARINHA DE TRIGO",
    "230": "MONIT OMISSO/INADIMPLÊNCIA",
    "231": "AUD INATIVAÇÃO CADASTRAL",
    "232": "CONTAGEM DE ESTOQUE",
    "233": "EC 87/2015 DIFAL NÃO CONTRIBUINTE",
    "234": "ATEND EXT DENÚNCIA FISCAL",
    "235": "ATEND EXT PGE",
    "236": "VALOR ADICIONADO IPM",
    "237": "ATENDIMENTO DEMANDA INTERNA DA SEFAZ PB",
    "238": "ATENDIMENTO DEMANDA EXTERNA (OUTROS ÓRGÃOS)",
    "239": "DIFAL NÃO CONTRIBUINTES",
    "241": "MONITORAMENTO SMPC",
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


# ─── Enriquecimento do MOCK ATF (demanda Pedro Henrique) ────────
# Campos adicionais da demanda do 1o endpoint: motivo de abertura,
# orgao executor, equipe fiscal, encerramento, eventos de
# acompanhamento (tipo Normal) e dados estendidos dos fiscais.
# Gerados deterministicamente sobre o mock existente.

# Motivos usados no mock – nomes reais da tabela de motivos ATIVOS
_MOTIVOS_ATF = [
    "DENÚNCIA FISCAL", "MONITORAMENTO", "MALHA FISCAL",
    "PROGRAMAÇÃO FISCAL", "AUDITORIA DE CONFORMIDADE",
]
_ORGAOS_EXECUTORES = [
    "GEFIS - 1ª GERÊNCIA REGIONAL", "GEFIS - 2ª GERÊNCIA REGIONAL",
    "GOF - NÚCLEO ICMS",
]
_EQUIPES_FISCAIS = ["EQUIPE A", "EQUIPE B", "EQUIPE C", "EQUIPE D"]


def _enriquecer_mock_atf() -> None:
    from datetime import timedelta

    for i, os_item in enumerate(_MOCK_ATF_ORDENS):
        abertura = datetime.strptime(os_item["data_abertura"], "%Y-%m-%d").date()
        inicio_fisc = abertura + timedelta(days=3)
        encerrada = os_item["situacao"]["codigo"] == 4
        encerramento = abertura + timedelta(days=20 + (i * 7) % 60) if encerrada else None
        qtd_eventos = 2 + i % 7

        os_item["motivo_abertura"] = _MOTIVOS_ATF[i % len(_MOTIVOS_ATF)]
        os_item["orgao_executor"] = _ORGAOS_EXECUTORES[i % len(_ORGAOS_EXECUTORES)]
        os_item["equipe_fiscal"] = _EQUIPES_FISCAIS[i % len(_EQUIPES_FISCAIS)]
        os_item["data_inicio_fiscalizacao"] = inicio_fisc.strftime("%Y-%m-%d")
        os_item["data_encerramento"] = encerramento.strftime("%Y-%m-%d") if encerramento else None
        os_item["qtd_eventos"] = qtd_eventos
        ultimo_evento = encerramento or (inicio_fisc + timedelta(days=qtd_eventos * 2))
        os_item["data_ultimo_evento"] = ultimo_evento.strftime("%Y-%m-%d")

        for f in os_item["fiscais"]:
            f["status"] = "ATIVO" if f.get("data_ciencia") else "DESIGNADO"
            f["data_designacao"] = os_item["data_abertura"]
            f["data_cancelamento"] = None


_enriquecer_mock_atf()


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
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    orgao_executor: str | None = None,
    data_encerramento_ini: str | None = None,
    data_encerramento_fim: str | None = None,
    pagina: int = 1,
    limite: int = 20,
    matriculas_visiveis: set[str] | None = None,
) -> dict[str, Any]:
    """Filtra o mock ATF e retorna paginacao + ordens."""
    resultados = filtrar_atf_por_matriculas(list(_MOCK_ATF_ORDENS), matriculas_visiveis)

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
    if motivo_abertura:
        # Aceita codigo (cdMotivoAbertOS, como na API real) ou texto livre
        nome_motivo = _MOTIVOS_ABERTURA_ATF.get(str(motivo_abertura))
        if nome_motivo:
            resultados = [
                o for o in resultados
                if o.get("motivo_abertura", "").upper() == nome_motivo.upper()
            ]
        else:
            term = motivo_abertura.lower()
            resultados = [o for o in resultados if term in o.get("motivo_abertura", "").lower()]
    if equipe_fiscal:
        term = equipe_fiscal.lower()
        resultados = [o for o in resultados if term in o.get("equipe_fiscal", "").lower()]
    if orgao_executor:
        term = orgao_executor.lower()
        resultados = [o for o in resultados if term in o.get("orgao_executor", "").lower()]
    if data_encerramento_ini:
        resultados = [
            o for o in resultados
            if o.get("data_encerramento") and o["data_encerramento"] >= data_encerramento_ini
        ]
    if data_encerramento_fim:
        resultados = [
            o for o in resultados
            if o.get("data_encerramento") and o["data_encerramento"] <= data_encerramento_fim
        ]

    total = len(resultados)
    total_paginas = max(1, (total + limite - 1) // limite)
    inicio = (pagina - 1) * limite
    pagina_data = [dict(o) for o in resultados[inicio: inicio + limite]]

    return {
        "paginacao": {
            "pagina_atual": pagina,
            "limite_por_pagina": limite,
            "total_paginas": total_paginas,
            "total_registros": total,
        },
        "ordens": pagina_data,
    }


# ─── Cliente SOAP do ATF (doc da listagem) ───────────────────────────
#
# Servico unico: listarOrdensServicoWebService()
#   POST {ATF_BASE_URL}/<caminho-do-servico>
# Os parametros de busca vao em CDATA dentro de <elementoEntrada>.
# O retorno traz TODOS os dados de cada OS (inclusive os campos
# calculados) e NAO e paginado — a paginacao e feita neste backend.

_ATF_WS_PATH = "/<caminho-do-servico>"


# ─── Cache das respostas do ATF ──────────────────────────────────
#
# O servico devolve a lista completa e nao pagina — a paginacao e feita
# aqui. Sem cache, virar de pagina ou clicar num cabecalho para ordenar
# refazia a consulta inteira, com timeout de 60s. O cache guarda a
# resposta crua por alguns segundos para que paginacao, ordenacao e o
# relatorio dos mesmos filtros reaproveitem uma unica ida ao ATF.


class _CacheATF:
    """
    Cache por tempo das listas devolvidas pelo ATF.

    A chave e o XML de parametros enviado ao servico: a representacao
    exata do que foi pedido, que nao tem como sair de sincronia com os
    filtros da funcao.

    O usuario NAO entra na chave. Isso e proposital e seguro porque o que
    se guarda e a resposta crua do ATF — a filtragem por hierarquia roda
    depois, por requisicao, em listar_ordens_atf. Guardar ja filtrado por
    usuario e que seria perigoso, porque uma chave montada errado passaria
    a servir dados de um usuario para outro.
    """

    def __init__(self, ttl_segundos: float, max_entradas: int = 32) -> None:
        self._ttl = ttl_segundos
        self._max = max_entradas
        self._dados: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = Lock()

    def get(self, chave: str) -> list[dict[str, Any]] | None:
        if self._ttl <= 0:
            return None
        agora = monotonic()
        with self._lock:
            item = self._dados.get(chave)
            if item is None:
                return None
            gravado_em, ordens = item
            if agora - gravado_em > self._ttl:
                del self._dados[chave]
                return None
            # Copia rasa na saida: quem chama preenche dias_execucao nas OS.
            # Sem a copia, duas requisicoes simultaneas mexeriam nos mesmos
            # dicionarios — e a segunda ainda os veria alterados pela primeira.
            return [dict(o) for o in ordens]

    def set(self, chave: str, ordens: list[dict[str, Any]]) -> None:
        if self._ttl <= 0:
            return
        agora = monotonic()
        with self._lock:
            for k in [k for k, (t, _) in self._dados.items() if agora - t > self._ttl]:
                del self._dados[k]
            if len(self._dados) >= self._max:
                del self._dados[min(self._dados, key=lambda k: self._dados[k][0])]
            self._dados[chave] = (agora, [dict(o) for o in ordens])

    def limpar(self) -> None:
        with self._lock:
            self._dados.clear()


_cache_atf = _CacheATF(ATF_CACHE_TTL)


def limpar_cache_atf() -> None:
    """Descarta o cache do ATF. Usado pelos testes e util para depuracao."""
    _cache_atf.limpar()


def _data_para_atf(data_iso: str) -> str:
    """Converte YYYY-MM-DD (formato interno) para dd/mm/aaaa (ATF)."""
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return data_iso


def _data_do_atf(valor: str | None) -> str:
    """Normaliza data vinda do ATF (dd/mm/aaaa ou ISO) para YYYY-MM-DD."""
    if not valor:
        return ""
    valor = valor.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return valor


def _int_ou_none(valor: str | None) -> int | None:
    try:
        return int(str(valor).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _float_ou_none(valor: str | None) -> float | None:
    try:
        return float(str(valor).strip().replace(",", "."))
    except (ValueError, TypeError, AttributeError):
        return None


def _montar_parametros_atf(
    numero_os: str | None = None,
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    situacao: int | str | None = None,
    matricula_fiscal: str | None = None,
    equipe_fiscal: str | None = None,
    orgao_executor: str | None = None,
    cnpj: str | None = None,
    ie: str | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_encerramento_ini: str | None = None,
    data_encerramento_fim: str | None = None,
) -> str:
    """Monta o XML <parametros> do elementoEntrada (nomes da doc da listagem)."""
    campos: list[str] = []

    def _add(tag: str, valor: Any) -> None:
        # O escape e obrigatorio: os valores vem da query string do usuario.
        # Sem ele da para (a) fechar a tag e injetar um filtro que o usuario
        # nao deveria controlar — "X</numeroOS><cdOrgaoExec>629</cdOrgaoExec>"
        # — e (b) fechar o CDATA do envelope com "]]>" e escrever direto no
        # corpo SOAP. Escapar o ">" resolve os dois: sem ">" literal nao se
        # forma a sequencia "]]>", e o ATF desfaz o escape ao reparsear o
        # conteudo do CDATA como XML.
        if valor not in (None, ""):
            campos.append(f"<{tag}>{_escape_xml(str(valor))}</{tag}>")

    _add("numeroOS", numero_os)
    _add("cdModeloOS", modelo)
    _add("cdMotivoAbertOS", motivo_abertura)
    _add("statusOS", situacao)
    _add("matriculaFiscal", matricula_fiscal)
    _add("cdEquipeFisc", equipe_fiscal)
    _add("cdOrgaoExec", orgao_executor)
    _add("cnpj", cnpj)
    _add("inscrEstadual", ie)
    # Regra da doc: campos de periodo devem ser informados conjuntamente
    if data_abertura_ini and data_abertura_fim:
        _add("dataAberturaOSIni", _data_para_atf(data_abertura_ini))
        _add("dataAberturaOSFin", _data_para_atf(data_abertura_fim))
    if data_encerramento_ini and data_encerramento_fim:
        _add("dataEncerraOSIni", _data_para_atf(data_encerramento_ini))
        _add("dataEncerraOSFin", _data_para_atf(data_encerramento_fim))

    # IMPORTANTE: o parser do ATF nao tolera quebras de linha dentro do
    # CDATA — os parametros devem ir em linha unica (verificado contra o
    # servico de desenvolvimento em 10/08/2026; com \n ele responde
    # "É necessário informar pelo menos um filtro").
    return "<parametros>" + "".join(campos) + "</parametros>"


def _montar_envelope_soap(parametros_xml: str) -> str:
    """Monta o envelope SOAP conforme o exemplo Postman da doc da listagem."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "    <soap:Body>\n"
        '        <ns:listarOrdemServicoRequest xmlns:ns="http://www.receita.pb.gov.br">\n'
        f"            <ns:elementoEntrada><![CDATA[{parametros_xml}]]></ns:elementoEntrada>\n"
        "        </ns:listarOrdemServicoRequest>\n"
        "    </soap:Body>\n"
        "</soap:Envelope>"
    )


def _parse_resposta_soap(xml_text: str) -> list[dict[str, Any]]:
    """
    Extrai e parseia o retorno do listarOrdensServicoWebService.

    Contrato (doc da listagem, revisao recebida em 13/08/2026):
        resultado (operacao, listaOrdemServico*)
        listaOrdemServico (ordemServico*)
        ordemServico (nrOrdemServico, dataAbertura, nrInscrEstadual,
            docContribuinte, nomeContribuinte, cdModeloOS, noModeloOS,
            cdMotivoAberturaOS, noMotivoAberturaOS, statusOS, noStatusOS,
            dataInicialFisc, dataEncerramentoFisc, cdOrgaoExec,
            sgOrgaoExec, noOrgaoExec, cdEquipeFisc, qtDiasExecucao,
            dataUltimoEventoOS, noProcedimento, mediaEventosModMot,
            mediaDiasExecModMot, fiscais+)
        fiscal (matricula, nome, dataDesignacao, dataCiencia,
            dataCancelamento, status)

    O servico tambem devolve noEquipeFisc, que a doc omite na lista de
    retorno mas vem preenchido na resposta real.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)

    # O XML de dados vem escapado dentro de <retorno> (no namespace do
    # ATF); o ElementTree ja desfaz o escape no .text. Fallback: inline.
    retorno_el = next(
        (el for el in root.iter() if el.tag.lower().endswith("retorno")), None,
    )
    if retorno_el is not None and (retorno_el.text or "").strip():
        dados_root = ET.fromstring(retorno_el.text.strip())
    else:
        dados_root = root

    # Erros de negocio vem em <dsMensagemErro> dentro do resultado
    erro = dados_root.findtext(".//dsMensagemErro")
    if erro and erro.strip():
        raise ValueError(f"ATF: {erro.strip()}")

    ordens: list[dict[str, Any]] = []
    for os_el in dados_root.findall(".//ordemServico"):
        fiscais = []
        for f_el in os_el.findall(".//fiscal"):
            fiscais.append({
                "matricula": (f_el.findtext("matricula", "") or "").strip(),
                "nome": (f_el.findtext("nome", "") or "").strip(),
                "data_designacao": _data_do_atf(f_el.findtext("dataDesignacao")) or None,
                "data_ciencia": _data_do_atf(f_el.findtext("dataCiencia")) or None,
                "data_cancelamento": _data_do_atf(f_el.findtext("dataCancelamento")) or None,
                "status": (f_el.findtext("status", "") or "").strip() or None,
            })

        # A situacao ja vem pronta do servico: statusOS (codigo) +
        # noStatusOS (descricao). Nao mapeamos mais pelo nome porque as
        # duas fontes divergem — a doc lista "EM ANALISE PARA ENCERRAMENTO"
        # e o servico responde "EM ANALISE DE ENCERRAMENTO", o que fazia o
        # mapa por nome cair no -1. O nome so entra como fallback quando o
        # codigo nao vier.
        cd_status = _int_ou_none(os_el.findtext("statusOS"))
        no_status = (os_el.findtext("noStatusOS", "") or "").strip()
        situacao = None
        if cd_status is not None or no_status:
            codigo = cd_status
            if codigo is None:
                codigo = _STATUS_ATF_POR_NOME.get(no_status.upper(), -1)
            situacao = {
                "codigo": codigo,
                "descricao": no_status or _STATUS_ATF.get(codigo, ""),
            }

        ordens.append({
            "numero_os": (os_el.findtext("nrOrdemServico", "") or "").strip(),
            "modelo": (os_el.findtext("noModeloOS", "") or "").strip(),
            "modelo_codigo": _int_ou_none(os_el.findtext("cdModeloOS")),
            "motivo_abertura": (os_el.findtext("noMotivoAberturaOS", "") or "").strip(),
            "motivo_abertura_codigo": _int_ou_none(os_el.findtext("cdMotivoAberturaOS")),
            "ie": (os_el.findtext("nrInscrEstadual", "") or "").strip(),
            "cnpj": (os_el.findtext("docContribuinte", "") or "").strip() or None,
            "razao_social": (os_el.findtext("nomeContribuinte", "") or "").strip(),
            "orgao_executor": (os_el.findtext("noOrgaoExec", "") or "").strip(),
            "orgao_executor_sigla": (os_el.findtext("sgOrgaoExec", "") or "").strip(),
            "orgao_executor_codigo": _int_ou_none(os_el.findtext("cdOrgaoExec")),
            "equipe_fiscal": (os_el.findtext("noEquipeFisc", "") or "").strip(),
            "equipe_fiscal_codigo": _int_ou_none(os_el.findtext("cdEquipeFisc")),
            "procedimento": (os_el.findtext("noProcedimento", "") or "").strip(),
            "situacao": situacao,
            "data_abertura": _data_do_atf(os_el.findtext("dataAbertura")),
            "data_inicio_fiscalizacao": _data_do_atf(os_el.findtext("dataInicialFisc")) or None,
            "data_encerramento": _data_do_atf(os_el.findtext("dataEncerramentoFisc")) or None,
            "data_ultimo_evento": _data_do_atf(os_el.findtext("dataUltimoEventoOS")) or None,
            "dias_execucao": _int_ou_none(os_el.findtext("qtDiasExecucao")),
            "qtd_media_eventos_modelo_motivo": _float_ou_none(os_el.findtext("mediaEventosModMot")),
            "tempo_medio_execucao_modelo_motivo": _float_ou_none(os_el.findtext("mediaDiasExecModMot")),
            "fiscais": fiscais,
        })

    return ordens


def _pos_filtrar_atf(
    ordens: list[dict[str, Any]],
    situacoes: list[int] | None = None,
    matriculas: list[str] | None = None,
    razao_social: str | None = None,
    data_ciencia_ini: str | None = None,
    data_ciencia_fim: str | None = None,
) -> list[dict[str, Any]]:
    """
    Aplica localmente filtros que o servico do ATF nao suporta:
    multiplas situacoes/matriculas, razao social e periodo de ciencia.
    """
    resultados = ordens

    if situacoes:
        codigos = set(situacoes)
        resultados = [
            o for o in resultados
            if o.get("situacao") and o["situacao"].get("codigo") in codigos
        ]
    if matriculas:
        mats = set(matriculas)
        resultados = [
            o for o in resultados
            if any(f.get("matricula") in mats for f in o.get("fiscais", []))
        ]
    if razao_social:
        term = razao_social.lower()
        resultados = [
            o for o in resultados if term in (o.get("razao_social") or "").lower()
        ]
    if data_ciencia_ini or data_ciencia_fim:
        def _ciencia_ok(os_item: dict) -> bool:
            datas = [
                f["data_ciencia"] for f in os_item.get("fiscais", [])
                if f.get("data_ciencia")
            ]
            if not datas:
                return False
            primeira = min(datas)
            if data_ciencia_ini and primeira < data_ciencia_ini:
                return False
            if data_ciencia_fim and primeira > data_ciencia_fim:
                return False
            return True
        resultados = [o for o in resultados if _ciencia_ok(o)]

    return resultados


# Campos que a listagem aceita ordenar, com o tipo de comparacao de cada
# um. A tabela tambem funciona como allowlist: campo fora dela e ignorado,
# entao querystring arbitraria nao ordena por dado interno.
_ORDENACAO_ATF: dict[str, str] = {
    "numero_os": "texto",
    "razao_social": "texto",
    "modelo": "texto",
    "motivo_abertura": "texto",
    "procedimento": "texto",
    "situacao": "situacao",
    "data_abertura": "data",
    "dias_execucao": "numero",
    "data_ultimo_evento": "data",
    "dias_sem_evento": "dias_sem_evento",
}


def _sem_acento(texto: str) -> str:
    """
    Remove acentos para a ordenacao alfabetica.
    Sem isso 'Ávila' cairia depois de 'Azevedo', porque o codepoint de
    'Á' e maior que o de qualquer letra sem acento.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )


def _ordenar_atf(
    ordens: list[dict[str, Any]],
    campo: str | None,
    descendente: bool,
    hoje: date,
) -> list[dict[str, Any]]:
    """
    Ordena a lista COMPLETA — precisa rodar antes de _paginar_atf.

    Ordenar so a pagina daria resultado enganoso: o usuario veria os 20
    registros do recorte em ordem, e nao os 20 primeiros do conjunto.

    Cada campo usa a comparacao do seu tipo: texto sem acento e sem caixa,
    data em ISO (cuja ordem lexicografica ja e cronologica) e numero.
    Registros sem valor vao para o fim nas DUAS direcoes — uma OS sem
    evento nao e nem a mais recente nem a mais antiga, e ausencia, e
    deixa-la no topo ao inverter a ordem so atrapalharia.
    """
    tipo = _ORDENACAO_ATF.get(campo or "")
    if tipo is None:
        return ordens

    def chave(o: dict[str, Any]) -> Any:
        if tipo == "situacao":
            return (o.get("situacao") or {}).get("codigo")
        if tipo == "dias_sem_evento":
            bruto = o.get("data_ultimo_evento")
            if not bruto:
                return None
            try:
                return (hoje - datetime.strptime(bruto, "%Y-%m-%d").date()).days
            except ValueError:
                return None
        valor = o.get(campo)
        if tipo == "texto":
            valor = (valor or "").strip()
            return _sem_acento(valor.casefold()) if valor else None
        return valor if valor not in ("", None) else None

    decorados = [(chave(o), o) for o in ordens]
    com_valor = [(k, o) for k, o in decorados if k is not None]
    sem_valor = [o for k, o in decorados if k is None]
    com_valor.sort(key=lambda par: par[0], reverse=descendente)
    return [o for _, o in com_valor] + sem_valor


def _paginar_atf(
    ordens: list[dict[str, Any]], pagina: int, limite: int,
) -> dict[str, Any]:
    """Pagina localmente a lista completa retornada pelo ATF."""
    total = len(ordens)
    total_paginas = max(1, (total + limite - 1) // limite)
    inicio = (pagina - 1) * limite
    return {
        "paginacao": {
            "pagina_atual": pagina,
            "limite_por_pagina": limite,
            "total_paginas": total_paginas,
            "total_registros": total,
        },
        "ordens": ordens[inicio: inicio + limite],
    }


def _chamar_atf_https(
    base_url: str,
    numero_os: str | None = None,
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    situacao: int | str | None = None,
    matricula_fiscal: str | None = None,
    equipe_fiscal: str | None = None,
    orgao_executor: str | None = None,
    cnpj: str | None = None,
    ie: str | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_encerramento_ini: str | None = None,
    data_encerramento_fim: str | None = None,
) -> list[dict[str, Any]]:
    """
    Chama o listarOrdensServicoWebService via SOAP (doc da listagem).

    POST https://.../<caminho-do-servico> com envelope SOAP e parametros
    em CDATA. Retorna a lista COMPLETA de OS (sem paginacao).
    """
    import requests

    base = base_url.rstrip("/")
    url = base if base.endswith("OrdemServico") else f"{base}{_ATF_WS_PATH}"

    parametros = _montar_parametros_atf(
        numero_os=numero_os, modelo=modelo, motivo_abertura=motivo_abertura,
        situacao=situacao, matricula_fiscal=matricula_fiscal,
        equipe_fiscal=equipe_fiscal, orgao_executor=orgao_executor,
        cnpj=cnpj, ie=ie,
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_encerramento_ini=data_encerramento_ini,
        data_encerramento_fim=data_encerramento_fim,
    )
    chave = f"{url}|{parametros}"
    em_cache = _cache_atf.get(chave)
    if em_cache is not None:
        logger.debug("Cache ATF: reaproveitando %d OS para %s", len(em_cache), parametros)
        return em_cache

    envelope = _montar_envelope_soap(parametros)

    try:
        resp = requests.post(
            url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=60,
        )
        resp.raise_for_status()
        ordens = _parse_resposta_soap(resp.text)
    except Exception:
        logger.exception("Erro ao chamar API ATF em %s", url)
        raise

    # So o sucesso vai para o cache: erro de negocio do ATF (ValueError) e
    # falha de rede sobem sem serem guardados, para nao repetir a mesma
    # resposta ruim durante todo o TTL.
    _cache_atf.set(chave, ordens)
    logger.debug("Cache ATF: %d OS guardadas para %s", len(ordens), parametros)
    return ordens


# ─── Campos calculados (demanda Pedro Henrique) ──────────────────


def _dias_execucao(os_item: dict[str, Any], hoje: date) -> int | None:
    """
    Numero de dias de execucao da OS.

    = data de encerramento - data de inicio da fiscalizacao;
    se a OS nao estiver encerrada, calcula pela data de hoje.
    """
    inicio_str = os_item.get("data_inicio_fiscalizacao") or os_item.get("data_abertura")
    if not inicio_str:
        return None
    try:
        inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date()
        fim_str = os_item.get("data_encerramento")
        fim = datetime.strptime(fim_str, "%Y-%m-%d").date() if fim_str else hoje
    except (ValueError, TypeError):
        return None
    return (fim - inicio).days


def _calcular_medias_modelo_motivo(
    universo: list[dict[str, Any]], hoje: date,
) -> dict[tuple[str, str], dict[str, float]]:
    """
    Medias por "Modelo / Motivo" (algoritmos 1 e 2 da demanda).

    Universo: OS abertas nos ultimos dois anos que estao encerradas.
    - Tempo medio de execucao = total de dias de execucao / total de OS
    - Qtd media de eventos = total de eventos tipo Normal / total de OS
    """
    corte = hoje.replace(year=hoje.year - 2).strftime("%Y-%m-%d")
    grupos: dict[tuple[str, str], dict[str, float]] = {}

    for o in universo:
        if not o.get("data_encerramento"):
            continue
        if (o.get("data_abertura") or "") < corte:
            continue
        dias = _dias_execucao(o, hoje)
        if dias is None:
            continue
        chave = (o.get("modelo") or "", o.get("motivo_abertura") or "")
        g = grupos.setdefault(chave, {"os": 0, "dias": 0, "eventos": 0})
        g["os"] += 1
        g["dias"] += dias
        g["eventos"] += o.get("qtd_eventos") or 0

    return {
        chave: {
            "tempo_medio_execucao": round(g["dias"] / g["os"], 1),
            "qtd_media_eventos": round(g["eventos"] / g["os"], 1),
        }
        for chave, g in grupos.items()
    }


def _anexar_campos_calculados(
    ordens: list[dict[str, Any]],
    medias: dict[tuple[str, str], dict[str, float]],
    hoje: date,
) -> None:
    """Anexa dias de execucao e medias por Modelo/Motivo a cada OS."""
    for o in ordens:
        o["dias_execucao"] = _dias_execucao(o, hoje)
        m = medias.get((o.get("modelo") or "", o.get("motivo_abertura") or ""))
        o["tempo_medio_execucao_modelo_motivo"] = m["tempo_medio_execucao"] if m else None
        o["qtd_media_eventos_modelo_motivo"] = m["qtd_media_eventos"] if m else None


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
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    orgao_executor: str | None = None,
    data_encerramento_ini: str | None = None,
    data_encerramento_fim: str | None = None,
    pagina: int = 1,
    limite: int = 20,
    ordenar_por: str | None = None,
    ordem: str = "asc",
    matriculas_visiveis: set[str] | None = None,
) -> dict[str, Any]:
    """
    Lista OS via API ATF.

    Se ATF_BASE_URL estiver configurado no .env, executa o fluxo real em
    duas etapas: servico 1 (numeros da pagina) + servico 2 (dados das OS).
    Caso contrario, usa dados MOCK para desenvolvimento/teste.
    Em ambos os casos anexa os campos calculados da demanda (dias de
    execucao e medias por Modelo/Motivo).

    ordenar_por aceita os campos de _ORDENACAO_ATF; a ordenacao roda sobre
    o conjunto inteiro, antes do recorte da pagina.

    matriculas_visiveis aplica a hierarquia do usuario (None = admin). Ela
    entra antes da ordenacao e da paginacao de proposito: filtrar depois
    deixaria total_registros e total_paginas contando OS que o usuario nao
    pode ver, e ainda entregaria paginas parcialmente vazias.
    """
    from .config import ATF_BASE_URL

    hoje = datetime.now(timezone.utc).date()

    if ATF_BASE_URL:
        logger.debug("Chamando API ATF: %s", ATF_BASE_URL)
        matriculas_lista = [m.strip() for m in (matriculas or "").split(",") if m.strip()]

        # O servico aceita um unico statusOS e uma unica matriculaFiscal;
        # selecoes multiplas sao aplicadas no pos-filtro local.
        ordens = _chamar_atf_https(
            ATF_BASE_URL,
            numero_os=numero_os,
            modelo=modelo,
            motivo_abertura=motivo_abertura,
            situacao=situacoes[0] if situacoes and len(situacoes) == 1 else None,
            matricula_fiscal=matriculas_lista[0] if len(matriculas_lista) == 1 else None,
            equipe_fiscal=equipe_fiscal,
            orgao_executor=orgao_executor,
            cnpj=cnpj, ie=ie,
            data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
            data_encerramento_ini=data_encerramento_ini,
            data_encerramento_fim=data_encerramento_fim,
        )
        ordens = _pos_filtrar_atf(
            ordens,
            situacoes=situacoes if situacoes and len(situacoes) > 1 else None,
            matriculas=matriculas_lista if len(matriculas_lista) > 1 else None,
            razao_social=razao_social,
            data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
        )
        ordens = filtrar_atf_por_matriculas(ordens, matriculas_visiveis)
        # dias_execucao vem calculado do ATF; completa localmente se faltar
        for o in ordens:
            if o.get("dias_execucao") is None:
                o["dias_execucao"] = _dias_execucao(o, hoje)
        ordens = _ordenar_atf(ordens, ordenar_por, ordem == "desc", hoje)
        return _paginar_atf(ordens, pagina, limite)

    logger.debug("ATF_BASE_URL nao configurado – usando dados MOCK ATF (%d registros)", len(_MOCK_ATF_ORDENS))
    resultado = _filtrar_mock_atf(
        numero_os=numero_os, modelo=modelo, ie=ie, cnpj=cnpj,
        razao_social=razao_social, matriculas=matriculas, situacoes=situacoes,
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
        motivo_abertura=motivo_abertura, equipe_fiscal=equipe_fiscal,
        orgao_executor=orgao_executor,
        data_encerramento_ini=data_encerramento_ini,
        data_encerramento_fim=data_encerramento_fim,
        pagina=pagina, limite=limite,
        matriculas_visiveis=matriculas_visiveis,
    )
    # Medias calculadas sobre TODO o universo mock (nao apenas a pagina)
    medias = _calcular_medias_modelo_motivo(_MOCK_ATF_ORDENS, hoje)
    _anexar_campos_calculados(resultado["ordens"], medias, hoje)
    return resultado


def _calcular_evolucao_mensal(todas_os: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calcula evolucao mensal de OS abertas por mes de abertura."""
    os_por_mes: dict[str, int] = defaultdict(int)
    for o in todas_os:
        if o.get("data_abertura"):
            try:
                mes = o["data_abertura"][:7]
                os_por_mes[mes] += 1
            except (ValueError, TypeError):
                pass

    meses_ordenados = sorted(os_por_mes.keys())
    return [{"mes": m, "abertas": os_por_mes[m]} for m in meses_ordenados]


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
    chaves_comparativo = (
        "total_os", "abertas", "em_andamento", "concluidas", "os_sem_ciencia",
    )
    for k in chaves_comparativo:
        val_atual = kpi_atual[k]
        val_ant = kpi_ant[k]
        delta = round(val_atual - val_ant, 1) if isinstance(val_atual, (int, float)) else 0
        comparativo[k] = {"atual": val_atual, "anterior": val_ant, "delta": delta}
    comparativo["_labels"] = {"mes_atual": mes_atual, "mes_anterior": mes_anterior}

    return comparativo
