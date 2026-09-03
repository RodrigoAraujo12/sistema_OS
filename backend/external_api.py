"""
Servico de dados externos - Ordens de Servico.

Fonte de dados: API ATF via SOAP. Dois servicos, no mesmo endpoint:
listarOrdensServicoWebService (doc da listagem), que alimenta o grid, e
detalharOrdemServicoWebService (doc do detalhe), chamado ao abrir uma OS
— uma por vez — e que traz o cadastro completo. Quando ATF_BASE_URL
nao esta configurado, o sistema usa dados MOCK para desenvolvimento.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any
from xml.sax.saxutils import escape as _escape_xml

from . import config
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



# ─── MOCK do detalhe da OS (doc do detalhe) ────────────────────────
# O servico de detalhe traz blocos que a listagem nao tem (endereco do
# contribuinte, eventos, prorrogacoes, notificacoes, processos). Sem
# ATF_BASE_URL eles sao gerados aqui, deterministicamente a partir da
# OS do mock, para o modal de detalhes continuar navegavel em
# desenvolvimento.

_MUNICIPIOS_MOCK = [
    ("JOAO PESSOA", "2507507", "58010-000"),
    ("CAMPINA GRANDE", "2504009", "58400-000"),
    ("PATOS", "2510808", "58700-000"),
    ("SOUSA", "2516300", "58800-000"),
    ("BAYEUX", "2501807", "58305-000"),
]
_LOGRADOUROS_MOCK = [
    ("AV", "EPITACIO PESSOA"), ("R", "DAS TRINCHEIRAS"),
    ("AV", "GETULIO VARGAS"), ("R", "JOAO SUASSUNA"),
]
_BAIRROS_MOCK = ["CENTRO", "TAMBAU", "MANAIRA", "CATOLE", "JAGUARIBE"]
_EVENTOS_MOCK = [
    ("1", "INICIO DE FISCALIZACAO", "ANALISE PRELIMINAR"),
    ("2", "SOLICITACAO DE DOCUMENTOS", "INTIMACAO DE DOCUMENTOS"),
    ("3", "ANALISE DE ESCRITURACAO", "CONFERENCIA EFD X GIM"),
    ("4", "LEVANTAMENTO FISCAL", "LEVANTAMENTO DA CONTA MERCADORIAS"),
    ("5", "ENCERRAMENTO", "RELATORIO CONCLUSIVO"),
]


def _detalhe_mock_atf(numero_os: str) -> dict[str, Any] | None:
    """Monta o detalhe completo de uma OS do MOCK. None se nao existir."""
    from datetime import timedelta

    indice = next(
        (i for i, o in enumerate(_MOCK_ATF_ORDENS) if o["numero_os"] == numero_os), None,
    )
    if indice is None:
        return None

    os_item = _MOCK_ATF_ORDENS[indice]
    abertura = datetime.strptime(os_item["data_abertura"], "%Y-%m-%d").date()
    inicio_fisc = datetime.strptime(os_item["data_inicio_fiscalizacao"], "%Y-%m-%d").date()
    prazo_final = inicio_fisc + timedelta(days=60)
    encerrada = os_item["situacao"]["codigo"] == 4

    municipio, cd_ibge, cep = _MUNICIPIOS_MOCK[indice % len(_MUNICIPIOS_MOCK)]
    sg_logradouro, logradouro = _LOGRADOUROS_MOCK[indice % len(_LOGRADOUROS_MOCK)]

    qtd_eventos = os_item.get("qtd_eventos") or 0
    eventos = []
    for n in range(qtd_eventos):
        tipo_cd, tipo_ds, procedimento = _EVENTOS_MOCK[n % len(_EVENTOS_MOCK)]
        inicio_evento = inicio_fisc + timedelta(days=n * 2)
        eventos.append({
            "tipo_codigo": tipo_cd,
            "tipo": tipo_ds,
            "data_inicial": inicio_evento.strftime("%Y-%m-%d"),
            "data_final": (inicio_evento + timedelta(days=1)).strftime("%Y-%m-%d"),
            "referencia_inicial": abertura.strftime("%m/%Y"),
            "referencia_final": inicio_evento.strftime("%m/%Y"),
            "procedimento": procedimento,
            "valor_levantado": round(1500.0 * (n + 1) + indice * 137.5, 2) if n % 2 else None,
            "observacao": f"Evento {n + 1} de acompanhamento da OS {numero_os}.",
            "arquivo": None,
        })

    prorrogacoes = []
    if indice % 3 == 0:
        prorrogacoes.append({
            "dias": 30,
            "prazo_atual": (prazo_final + timedelta(days=30)).strftime("%Y-%m-%d"),
            "prazo_anterior": prazo_final.strftime("%Y-%m-%d"),
            "situacao_prazo": "HOMOLOGADA",
            "justificativa": "Volume de documentos acima do previsto.",
            "usuario": os_item["fiscais"][0]["nome"],
            "data_homologacao": (prazo_final - timedelta(days=5)).strftime("%Y-%m-%d"),
            "usuario_homologacao": "SUPERVISOR GEFIS",
            "status": "ATIVA",
        })

    return {
        "numero_os": os_item["numero_os"],
        "modelo": os_item["modelo"],
        "modelo_codigo": os_item.get("modelo_codigo"),
        "motivo_abertura": os_item.get("motivo_abertura", ""),
        "motivo_abertura_codigo": os_item.get("motivo_abertura_codigo"),
        "situacao": dict(os_item["situacao"]),
        "termo_os": f"TERMO-{indice + 1:04d}",
        "termo_os_descricao": "TERMO DE INICIO DE FISCALIZACAO",
        "tipo_funcionario": "AUDITOR FISCAL",
        "periodo_fiscalizar": {
            "inicio": (abertura - timedelta(days=365)).strftime("%m/%Y"),
            "fim": abertura.strftime("%m/%Y"),
        },
        "orgao_origem": "GEFIS - GERENCIA EXECUTIVA DE FISCALIZACAO",
        "orgao_origem_codigo": 600,
        "orgao_executor": os_item.get("orgao_executor", ""),
        "orgao_executor_sigla": f"GR{indice % 5 + 1}",
        "orgao_executor_codigo": 620 + indice % 5,
        "data_abertura": os_item["data_abertura"],
        "data_inicio_fiscalizacao": os_item["data_inicio_fiscalizacao"],
        "data_emissao": abertura.strftime("%Y-%m-%d"),
        "data_prazo_final": prazo_final.strftime("%Y-%m-%d"),
        "data_encerramento": os_item.get("data_encerramento"),
        "data_inicio_exercicio": f"{abertura.year}-01-01",
        "data_final_exercicio": f"{abertura.year}-12-31",
        "situacao_prazo": "ENCERRADA" if encerrada else "DENTRO DO PRAZO",
        "data_ultimo_evento": os_item.get("data_ultimo_evento"),
        "descricoes_complementares": [{
            "data_inclusao": abertura.strftime("%Y-%m-%d"),
            "usuario": "SISTEMA ATF",
            "descricao": (
                f"OS {numero_os} aberta por {os_item.get('motivo_abertura', '')} "
                f"para o contribuinte {os_item['razao_social']}."
            ),
            "descricao_formatada": None,
        }],
        "contribuinte": {
            "nome": os_item["razao_social"],
            "natureza": "PESSOA JURIDICA",
            "ie": os_item["ie"],
            "documento": os_item.get("cnpj") or "",
            "tipo_documento": "CNPJ",
            "endereco": {
                "logradouro": f"{sg_logradouro} {logradouro}",
                "numero": str(100 + indice * 7),
                "complemento": "SALA 201" if indice % 4 == 0 else None,
                "bairro": _BAIRROS_MOCK[indice % len(_BAIRROS_MOCK)],
                "municipio": municipio,
                "municipio_codigo": cd_ibge,
                "uf": "PB",
                "cep": cep,
                "latitude": None,
                "longitude": None,
                "nao_decodificado": None,
                "reparticao": os_item.get("orgao_executor", ""),
                "atualizado_em": abertura.strftime("%Y-%m-%d"),
            },
        },
        "periodo_nf": {
            "inicio": (abertura - timedelta(days=365)).strftime("%Y-%m-%d"),
            "fim": abertura.strftime("%Y-%m-%d"),
        },
        "periodo_efd": {
            "inicio": (abertura - timedelta(days=365)).strftime("%Y-%m-%d"),
            "fim": abertura.strftime("%Y-%m-%d"),
        },
        "autorizacao": {
            "data": (abertura + timedelta(days=1)).strftime("%Y-%m-%d"),
            "usuario": "SUPERVISOR GEFIS",
            "matricula": "23456",
        },
        "notificacoes": [{
            "codigo": f"{9000 + indice}",
            "nome": f"NOTIFICACAO {9000 + indice}/{abertura.year}",
        }] if indice % 2 == 0 else [],
        "notificacoes_scamf": [],
        "processos": [{
            "numero": f"{1230 + indice}.000.{abertura.year}-4",
            "tipo": "PROCESSO ADMINISTRATIVO TRIBUTARIO",
        }] if indice % 5 == 0 else [],
        "fiscais": [
            {
                "matricula": f["matricula"],
                "nome": f["nome"],
                "status": f.get("status"),
                "data_ciencia": f.get("data_ciencia"),
                "data_designacao": f.get("data_designacao"),
                "data_cancelamento": f.get("data_cancelamento"),
                "responsavel": "SIM" if i == 0 else "NAO",
            }
            for i, f in enumerate(os_item["fiscais"])
        ],
        "prorrogacoes": prorrogacoes,
        "eventos": eventos,
        "qtd_eventos": len(eventos),
        "justificativas": [{
            "tipo": "ATRASO NA ENTREGA DE DOCUMENTOS",
            "descricao": "Contribuinte solicitou prazo adicional para entrega da EFD.",
            "usuario": os_item["fiscais"][0]["nome"],
            "data_inclusao": (inicio_fisc + timedelta(days=10)).strftime("%Y-%m-%d"),
        }] if indice % 4 == 1 else [],
        "valor_total_recolhido": round(5230.75 + indice * 411.3, 2) if encerrada else None,
        "id_os_gerou_banco": None,
        "ie": os_item["ie"],
        "cnpj": os_item.get("cnpj"),
        "razao_social": os_item["razao_social"],
    }


# ─── Cliente SOAP do ATF (doc da listagem) ───────────────────────────
#
# Servico unico: listarOrdensServicoWebService()
#   POST {ATF_BASE_URL}/<caminho-do-servico>
# Os parametros de busca vao em CDATA dentro de <elementoEntrada>.
# O retorno traz TODOS os dados de cada OS (inclusive os campos
# calculados) e NAO e paginado — a paginacao e feita neste backend.

# Vem do .env (ATF_WS_PATH) — ver backend/config.py.
def _atf_ws_path() -> str:
    return config.ATF_WS_PATH


# Com a verificacao desligada, o urllib3 repete um InsecureRequestWarning
# a cada chamada e afoga o log. O aviso que importa e dado uma vez no
# boot, por setup_logging() — ver ATF_SSL_VERIFY em config.py.
if config.ATF_BASE_URL and not config.ATF_SSL_VERIFY:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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

# Cache do detalhe (doc do detalhe), separado porque a chave e outra: uma
# entrada por OS consultada, guardada como lista de um item so. Existe
# pelo mesmo motivo do de cima — reabrir a mesma OS logo em seguida (ou
# um duplo clique na linha) nao precisa de outra ida ao ATF. O usuario
# tambem nao entra na chave: o que se guarda e a resposta crua, e a
# hierarquia e aplicada depois, por requisicao, em main.py.
_cache_detalhe_atf = _CacheATF(ATF_CACHE_TTL)


def limpar_cache_atf() -> None:
    """
    Descarta os caches do ATF (listagem e detalhe).

    Usado pelos testes e util para depuracao.
    """
    _cache_atf.limpar()
    _cache_detalhe_atf.limpar()


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


# Numero inteiro agrupado em milhar, sem parte decimal: "12.345".
_NUMERO_COM_MILHAR = re.compile(r"^-?\d{1,3}(?:\.\d{3})+$")


def _float_ou_none(valor: str | None) -> float | None:
    """
    Le numero no formato pt-BR do ATF: "." separa milhar, "," decimal.

    Ate 26/08/2026 esta funcao fazia um replace(",", ".") seco, que
    transforma "1.234,56" em "1.234.56" — float() rejeita e o valor virava
    None. Como o front so exibe quando != None (ver valor_levantado em
    OrdensPanel), o efeito era perverso: valores ABAIXO de mil apareciam
    e os de mil para cima sumiam da tela, justamente os que importam.
    Passou despercebido porque o XML de teste usava "18450,75", sem o
    ponto de milhar que o servico realmente manda.
    """
    texto = str(valor).strip() if valor is not None else ""
    if "," in texto:
        # Havendo virgula decimal, todo "." no numero e separador de milhar.
        texto = texto.replace(".", "").replace(",", ".")
    elif _NUMERO_COM_MILHAR.match(texto):
        # Sem decimais, "12.345" e doze mil — nao 12 inteiros e 345 milesimos.
        texto = texto.replace(".", "")
    # Um "." solitario fora desses casos ("1.5") fica como esta: se algum
    # dia o servico mudar para o formato ingles, o valor ainda e lido certo.
    try:
        return float(texto)
    except (ValueError, TypeError):
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


# Casa um "&" que NAO inicia uma entidade valida (&amp; &#38; &#x26; ...).
_AMP_SOLTO = re.compile(r"&(?!(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);)")


def _escapar_amp_solto(xml_text: str) -> str:
    """
    Escapa "&" soltos no XML de dados devolvido pelo ATF.

    O servico escapa o payload uma unica vez dentro de <retorno>, entao um
    "&" que ja era literal no dado (razao social tipo "PROCTER & GAMBLE")
    volta cru depois do unescape e quebra o parser. Reescapa so esses,
    preservando entidades legitimas.
    """
    return _AMP_SOLTO.sub("&amp;", xml_text)


def _erro_soap(resposta: Any) -> str | None:
    """
    Extrai o <faultstring> de um SOAP Fault, se a resposta for um.

    O SOAP 1.1 devolve falha com HTTP 500, entao um raise_for_status()
    seco descarta justamente a mensagem que diz o que houve — foi assim
    que o nome errado da operacao na doc do detalhe custou uma investigacao
    ("Message part [...] was not recognized"). Devolve None quando a
    resposta nao e um Fault.
    """
    import xml.etree.ElementTree as ET

    try:
        raiz = ET.fromstring(resposta.text)
    except ET.ParseError:
        return None
    fault = next((el for el in raiz.iter() if el.tag.lower().endswith("fault")), None)
    if fault is None:
        return None
    texto = next(
        (el.text for el in fault.iter()
         if el.tag.lower().endswith("faultstring") and (el.text or "").strip()),
        None,
    )
    return (texto or "").strip() or "falha SOAP sem mensagem"


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
        dados_root = ET.fromstring(_escapar_amp_solto(retorno_el.text.strip()))
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
    url = base if base.endswith("OrdemServico") else f"{base}{_atf_ws_path()}"

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
            verify=config.ATF_SSL_VERIFY,
        )
        falha = _erro_soap(resp)
        if falha:
            raise ValueError(f"ATF: {falha}")
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


# ─── Detalhe da OS (doc do detalhe) ─────────────────────────────────
#
# Servico detalharOrdemServicoWebService(), no MESMO endpoint da
# listagem (POST {ATF_BASE_URL}/<caminho-do-servico>): muda so a operacao
# dentro do envelope. Recebe apenas o numero da OS e devolve o cadastro
# completo — contribuinte com endereco, eventos de acompanhamento,
# prorrogacoes, notificacoes, processos, justificativas e recolhimentos
# — que a listagem (doc da listagem) nao traz.


def _montar_envelope_detalhe_soap(numero_os: str) -> str:
    """
    Monta o envelope SOAP do servico de detalhe (doc do detalhe).

    Duas diferencas em relacao ao da listagem: a operacao e outra e o
    elemento raiz dos filtros e <parametro>, no singular (a listagem usa
    <parametros>).

    ATENCAO ao nome da operacao: ele MUDA conforme o ambiente do ATF.
    Este envelope usa "detalharOrdemServicoRequest", o nome da doc, que
    e o aceito pelo ambiente para onde ATF_BASE_URL aponta. Em outro
    ambiente o servico pode publicar a operacao com um infixo a mais e
    responder HTTP 500 com o SOAP Fault "Message part [...] was not
    recognized. (Does it exist in service WSDL?)". Antes de migrar de
    ambiente, conferir o ?wsdl — nomes em NOTAS-INTERNAS.md.

    O escape do numero e obrigatorio pela mesma razao da listagem: o
    valor vem da URL, e sem ele da para fechar o CDATA com "]]>" e
    escrever direto no corpo SOAP.
    """
    parametro = f"<parametro><numeroOS>{_escape_xml(numero_os)}</numeroOS></parametro>"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "    <soap:Body>\n"
        '        <ns:detalharOrdemServicoRequest xmlns:ns="http://www.receita.pb.gov.br">\n'
        f"            <ns:elementoEntrada><![CDATA[{parametro}]]></ns:elementoEntrada>\n"
        "        </ns:detalharOrdemServicoRequest>\n"
        "    </soap:Body>\n"
        "</soap:Envelope>"
    )


def _txt(el: Any, caminho: str) -> str:
    """Texto de um filho do elemento, sem espacos nas pontas ("" se ausente)."""
    if el is None:
        return ""
    return (el.findtext(caminho, "") or "").strip()


def _txt_ou_none(el: Any, caminho: str) -> str | None:
    """Como _txt, mas devolve None no lugar de "" — para campos opcionais."""
    return _txt(el, caminho) or None


def _parse_notificacoes(lista_el: Any) -> list[dict[str, str]]:
    """
    Le uma das duas listas de notificacao do detalhe.

    A doc do detalhe escreve as tags de forma inconsistente entre elas
    (<notificao> com <cdnotificacao> numa, <notificacaoSCAMF> com
    <cdnotificao> na outra), entao a leitura vai por prefixo do nome da
    tag: filho que comeca com "cd" e o codigo, filho que comeca com "no"
    e o nome. Assim qualquer das grafias e aceita.
    """
    if lista_el is None:
        return []

    notificacoes: list[dict[str, str]] = []
    for item_el in list(lista_el):
        codigo = nome = ""
        for filho in item_el:
            tag = filho.tag.lower()
            valor = (filho.text or "").strip()
            if tag.startswith("cd"):
                codigo = valor
            elif tag.startswith("no"):
                nome = valor
        if codigo or nome:
            notificacoes.append({"codigo": codigo, "nome": nome})
    return notificacoes


def _parse_detalhe_soap(xml_text: str) -> dict[str, Any] | None:
    """
    Extrai e parseia o retorno do detalharOrdemServicoWebService.

    Contrato: doc do detalhe (<resultado>, com <operacao> e <ordServ>).
    Devolve None quando a resposta nao traz <ordServ>, que e como o
    servico indica que a OS nao existe.

    As chaves do dicionario repetem de proposito as da listagem
    (numero_os, modelo, situacao, data_abertura, fiscais...) onde os dois
    servicos trazem o mesmo dado: assim o detalhe se sobrepoe a linha do
    grid campo a campo, sem tradutor no meio.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)

    # Mesmo empacotamento da listagem: o XML de dados vem escapado dentro
    # de <retorno>; o ElementTree desfaz o escape no .text.
    retorno_el = next(
        (el for el in root.iter() if el.tag.lower().endswith("retorno")), None,
    )
    if retorno_el is not None and (retorno_el.text or "").strip():
        dados_root = ET.fromstring(_escapar_amp_solto(retorno_el.text.strip()))
    else:
        dados_root = root

    erro = (dados_root.findtext(".//dsMensagemErro") or "").strip()
    if erro:
        # "Nenhum registro satisfaz a pesquisa" e como o ATF diz que a OS
        # nao existe. Numa busca por numero isso e 404, e nao erro de
        # negocio — os outros dsMensagemErro continuam subindo como erro.
        if "nenhum registro" in _sem_acento(erro).casefold():
            return None
        raise ValueError(f"ATF: {erro}")

    os_el = dados_root.find(".//ordServ")
    if os_el is None:
        return None

    outras_el = os_el.find("outrasInfo")
    org_el = os_el.find("elementoOrg")
    exec_el = os_el.find("elementoOrgExecutor")
    contrib_el = os_el.find("contribuinte")
    endereco_el = contrib_el.find("endereco") if contrib_el is not None else None
    autoriz_el = os_el.find("autorizacao")
    periodo_el = os_el.find("periodoAFiscalizar")
    cargas_el = os_el.find("periodoCargas")
    nf_el = cargas_el.find("periodoNF") if cargas_el is not None else None
    efd_el = cargas_el.find("periodoEFD") if cargas_el is not None else None

    # Situacao: tpSituacaoOS (codigo) + noSituacaoOS (descricao). Mesma
    # forma da listagem, para o badge do modal nao precisar de outro caso.
    cd_situacao = _int_ou_none(_txt(os_el, "tpSituacaoOS"))
    no_situacao = _txt(os_el, "noSituacaoOS")
    situacao = None
    if cd_situacao is not None or no_situacao:
        codigo = cd_situacao
        if codigo is None:
            codigo = _STATUS_ATF_POR_NOME.get(no_situacao.upper(), -1)
        situacao = {"codigo": codigo, "descricao": no_situacao or _STATUS_ATF.get(codigo, "")}

    fiscais = [
        {
            "matricula": _txt(f_el, "nrMatFiscal"),
            "nome": _txt(f_el, "noHumFiscal"),
            # stFiscalOS e o CODIGO do status ("0"); a listagem manda o
            # texto ("DESIGNADO") na chave "status". Guardar os dois com o
            # mesmo nome fazia o codigo apagar a descricao ao mesclar.
            "status_codigo": _txt_ou_none(f_el, "stFiscalOS"),
            "data_ciencia": _data_do_atf(_txt(f_el, "dtCiencia")) or None,
            "data_designacao": _data_do_atf(_txt(f_el, "dtDesigna")) or None,
            # A doc do detalhe nao devolve a data de cancelamento do fiscal,
            # que a listagem tem: fica None e o front recupera da linha.
            "data_cancelamento": None,
            "responsavel": _txt_ou_none(f_el, "responsavel"),
        }
        for f_el in os_el.findall(".//fiscal")
    ]

    eventos = [
        {
            "tipo_codigo": _txt_ou_none(e_el, "tpEventoAcompOS"),
            "tipo": _txt(e_el, "dsTpEventoAcompOS"),
            "data_inicial": _data_do_atf(_txt(e_el, "dtInicialEvento")) or None,
            "data_final": _data_do_atf(_txt(e_el, "dtFinalEvento")) or None,
            "referencia_inicial": _txt_ou_none(e_el, "dtReferInicial"),
            "referencia_final": _txt_ou_none(e_el, "dtReferFinal"),
            "procedimento": _txt(e_el, "noProcedimento"),
            "valor_levantado": _float_ou_none(_txt(e_el, "vlLevantado")),
            "observacao": _txt_ou_none(e_el, "dsObservacao"),
            "arquivo": _txt_ou_none(e_el, "arquivoEvento"),
        }
        for e_el in os_el.findall(".//eventos")
    ]

    prorrogacoes = [
        {
            "dias": _int_ou_none(_txt(p_el, "nrDiasProrrog")),
            "prazo_atual": _data_do_atf(_txt(p_el, "dtPrazoAtual")) or None,
            "prazo_anterior": _data_do_atf(_txt(p_el, "dtPrazoAnt")) or None,
            "situacao_prazo": _txt_ou_none(p_el, "idSituacaoPrazo"),
            "justificativa": _txt_ou_none(p_el, "dsJustifProrrogaOS"),
            "usuario": _txt_ou_none(p_el, "noUsrProrrog"),
            "data_homologacao": _data_do_atf(_txt(p_el, "dtHomologacao")) or None,
            "usuario_homologacao": _txt_ou_none(p_el, "noUsrHomolog"),
            "status": _txt_ou_none(p_el, "stProrrogOS"),
        }
        for p_el in os_el.findall(".//prorrogacao")
    ]

    justificativas = [
        {
            "tipo": _txt(j_el, "dsTipoJustifAtraso"),
            "descricao": _txt(j_el, "dsJustifAtrasoOS"),
            "usuario": _txt_ou_none(j_el, "noUsrRespJustif"),
            "data_inclusao": _data_do_atf(_txt(j_el, "dtInclusaoJustif")) or None,
        }
        for j_el in os_el.findall(".//justificativa")
    ]

    processos = [
        {
            "numero": _txt(pr_el, "nrprocesso"),
            "tipo": _txt_ou_none(pr_el, "tposprocesso"),
        }
        for pr_el in os_el.findall(".//processo")
    ]

    # recolhimentoOS e denuncia entraram na doc do detalhe em 21/08/2026;
    # antes so o total recolhido era descrito. Lidos a partir do contrato:
    # nenhuma das 40 OS varridas no ambiente atual trouxe esses blocos
    # preenchidos, entao a leitura ainda nao foi confrontada com dado real.
    recolhimentos = [
        {
            "chave": _txt_ou_none(rec_el, "chaveRecolhimentoOS"),
            "descricao": _txt(rec_el, "dsRecolhimentoOS"),
            "data_inclusao": _data_do_atf(_txt(rec_el, "dtInclusao")) or None,
            "nosso_numero": _txt_ou_none(rec_el, "nrNossoNumero"),
            "ref": _txt_ou_none(rec_el, "ref"),
            "referencia": _txt_ou_none(rec_el, "dpReferencia"),
            "valor_principal": _float_ou_none(_txt(rec_el, "vlPrincipal")),
            "receita_codigo": _txt_ou_none(rec_el, "cdReceitaSefin"),
            "receita_nome": _txt(rec_el, "noReceitaSefin"),
            "situacao_debito": _txt_ou_none(rec_el, "noSituacaoDebito"),
            "situacao_arr": _txt_ou_none(rec_el, "noSituacaoARR"),
        }
        for rec_el in os_el.findall(".//recolhimentoOS")
    ]

    denuncias = [
        {
            "data": _data_do_atf(_txt(den_el, "dtDenuncia")) or None,
            "descricao": _txt(den_el, "dsDenuncia"),
        }
        for den_el in os_el.findall(".//denuncia")
    ]

    descricoes = [
        {
            "data_inclusao": _data_do_atf(_txt(d_el, "dtInclusao")) or None,
            "usuario": _txt_ou_none(d_el, "noUsrCriador"),
            "descricao": _txt(d_el, "dsComplementarOS"),
            "descricao_formatada": _txt_ou_none(d_el, "dsTxtComplOSFormatado"),
        }
        for d_el in os_el.findall(".//descricaoComplementarOS")
    ]

    contribuinte = None
    if contrib_el is not None:
        contribuinte = {
            "nome": _txt(contrib_el, "noHumanoInst"),
            "natureza": _txt_ou_none(contrib_el, "tpNatureza"),
            "ie": _txt(contrib_el, "nrInscrEstadual"),
            "documento": _txt(contrib_el, "nrDocHumanoInst"),
            "tipo_documento": _txt_ou_none(contrib_el, "tpDocumento"),
            "endereco": None,
        }
        if endereco_el is not None:
            contribuinte["endereco"] = {
                "logradouro": " ".join(
                    p for p in (
                        _txt(endereco_el, "sgTpLogradouro"),
                        _txt(endereco_el, "noLogradouro"),
                    ) if p
                ),
                "numero": _txt_ou_none(endereco_el, "nrresidencia"),
                "complemento": _txt_ou_none(endereco_el, "dscomplemento"),
                "bairro": _txt(endereco_el, "noBairro"),
                "municipio": _txt(endereco_el, "noMunicipio"),
                "municipio_codigo": _txt_ou_none(endereco_el, "cdMunicipio"),
                # cdibge tambem nao esta na doc, mas e o codigo padrao do
                # municipio — o unico que serve fora do ATF.
                "municipio_ibge": _txt_ou_none(endereco_el, "cdibge"),
                "uf": _txt(endereco_el, "dsAbrevUf") or _txt(endereco_el, "noUf"),
                "cep": _txt_ou_none(endereco_el, "nrCep"),
                "latitude": _txt_ou_none(endereco_el, "nrLatitude"),
                "longitude": _txt_ou_none(endereco_el, "nrLongitude"),
                # Endereco que o cadastro nao conseguiu decodificar: quando
                # vem preenchido, e o unico texto util do bloco.
                "nao_decodificado": _txt_ou_none(endereco_el, "dsEndNaoDecodifica"),
                "reparticao": _txt(endereco_el, "elementoOrg/noElementoOrg") or None,
                "atualizado_em": _data_do_atf(_txt(endereco_el, "tsAtualizacao")) or None,
            }

    # O executor sai de <elementoOrgExecutor>; <elementoOrg> traz o orgao
    # de origem da OS e repete o executor em cdElementoOrgExec — que serve
    # de reserva quando o bloco do executor nao vem.
    orgao_executor_codigo = (
        _int_ou_none(_txt(exec_el, "cdElementoOrg"))
        if exec_el is not None else _int_ou_none(_txt(org_el, "cdElementoOrgExec"))
    )
    orgao_executor_nome = (
        _txt(exec_el, "noElementoOrg") if exec_el is not None
        else _txt(org_el, "noElementoOrgExec")
    )

    detalhe: dict[str, Any] = {
        "numero_os": _txt(os_el, "nrOrdemServico"),
        "modelo": _txt(os_el, "noModeloOrdServ"),
        "modelo_codigo": _int_ou_none(_txt(os_el, "cdModeloOS")),
        "motivo_abertura": _txt(os_el, "noMotivoAberturaOS"),
        "motivo_abertura_codigo": _int_ou_none(_txt(os_el, "cdMotivoAberturaOS")),
        "situacao": situacao,
        "termo_os": _txt_ou_none(os_el, "idTermoOS"),
        "termo_os_descricao": _txt_ou_none(os_el, "dsIdTermoOS"),
        "tipo_funcionario": _txt_ou_none(os_el, "tpFuncionario"),
        "periodo_fiscalizar": {
            "inicio": _txt(periodo_el, "dpRefInicial"),
            "fim": _txt(periodo_el, "dpRefFinal"),
        } if periodo_el is not None else None,
        # Tres campos que a resposta traz e a doc do detalhe nao lista:
        # equipeFiscalizacao/noEquipe, tpBdFiscal e dsTpBdFiscal. O nome
        # da equipe sai com a mesma chave da listagem (equipe_fiscal),
        # que e onde o painel ja o espera.
        "equipe_fiscal": _txt(os_el, "equipeFiscalizacao/noEquipe"),
        # A revisao da doc de 21/08/2026 passou a descrever este bloco,
        # mas so com <noEquipe>. O <cdEquipe> chegou a ser anunciado pelo
        # time do ATF e nao entrou nem na doc nem na resposta (conferido
        # em 17 OS): fica lido por antecipacao, sem custo, e ate la o
        # codigo da equipe continua vindo da listagem pela mesclagem.
        "equipe_fiscal_codigo": _int_ou_none(_txt(os_el, "equipeFiscalizacao/cdEquipe")),
        "bd_fiscal": _txt_ou_none(os_el, "dsTpBdFiscal"),
        "bd_fiscal_codigo": _txt_ou_none(os_el, "tpBdFiscal"),
        "orgao_origem": _txt(org_el, "noElementoOrg") or None,
        "orgao_origem_codigo": _int_ou_none(_txt(org_el, "cdElementoOrg")),
        "orgao_executor": orgao_executor_nome,
        "orgao_executor_sigla": _txt(exec_el, "sgElementoOrg"),
        "orgao_executor_codigo": orgao_executor_codigo,
        "data_abertura": _data_do_atf(_txt(outras_el, "dtAbertura")),
        "data_inicio_fiscalizacao": _data_do_atf(_txt(outras_el, "dtInicialFisc")) or None,
        "data_emissao": _data_do_atf(_txt(outras_el, "dtEmissao")) or None,
        "data_prazo_final": _data_do_atf(_txt(outras_el, "dtPrazoFinal")) or None,
        "data_encerramento": _data_do_atf(_txt(outras_el, "dtEncerramento")) or None,
        "data_inicio_exercicio": _data_do_atf(_txt(outras_el, "dtInicioExercicio")) or None,
        "data_final_exercicio": _data_do_atf(_txt(outras_el, "dtFinalExercicio")) or None,
        "situacao_prazo": _txt_ou_none(outras_el, "stPrazoOS"),
        "descricoes_complementares": descricoes,
        "contribuinte": contribuinte,
        "periodo_nf": {
            "inicio": _data_do_atf(_txt(nf_el, "dtemisinicnf")),
            "fim": _data_do_atf(_txt(nf_el, "dtemisfimnf")),
        } if nf_el is not None else None,
        "periodo_efd": {
            "inicio": _data_do_atf(_txt(efd_el, "dtrefiniefd")),
            "fim": _data_do_atf(_txt(efd_el, "dtreffimefd")),
        } if efd_el is not None else None,
        "autorizacao": {
            "data": _data_do_atf(_txt(autoriz_el, "dtAutorizacao")) or None,
            "usuario": _txt_ou_none(autoriz_el, "noUsrAtualSit"),
            "matricula": _txt_ou_none(autoriz_el, "nrMatricula"),
        } if autoriz_el is not None else None,
        "notificacoes": _parse_notificacoes(os_el.find("listaNotificacao")),
        "notificacoes_scamf": _parse_notificacoes(os_el.find("listaNotificacaoSCAMF")),
        "processos": processos,
        "fiscais": fiscais,
        "prorrogacoes": prorrogacoes,
        "eventos": eventos,
        "qtd_eventos": len(eventos),
        "justificativas": justificativas,
        "recolhimentos": recolhimentos,
        "denuncias": denuncias,
        "valor_total_recolhido": _float_ou_none(
            _txt(os_el, "listaRecolhimentosOS/vlTotalRecolheOS"),
        ),
        "id_os_gerou_banco": _txt_ou_none(os_el, "idOsGerouBanco"),
    }

    # Repete os dados do contribuinte na raiz porque sao os mesmos campos
    # que a listagem entrega soltos (ie, cnpj, razao_social) — assim o
    # detalhe se basta, sem depender da linha do grid para o cabecalho.
    if contribuinte:
        detalhe["ie"] = contribuinte["ie"]
        detalhe["cnpj"] = contribuinte["documento"] or None
        detalhe["razao_social"] = contribuinte["nome"]

    # dataUltimoEventoOS nao existe neste servico: o ultimo evento sai da
    # propria lista, que aqui vem completa.
    datas_evento = [d for d in (e["data_final"] or e["data_inicial"] for e in eventos) if d]
    if datas_evento:
        detalhe["data_ultimo_evento"] = max(datas_evento)

    return detalhe



def _sobrepor(base: dict[str, Any], novo: dict[str, Any]) -> dict[str, Any]:
    """Copia sobre `base` apenas os campos preenchidos de `novo`."""
    resultado = dict(base)
    for chave, valor in (novo or {}).items():
        if valor is None or valor == "" or (isinstance(valor, list) and not valor):
            continue
        resultado[chave] = valor
    return resultado


def mesclar_detalhe_os(linha: dict[str, Any], detalhe: dict[str, Any]) -> dict[str, Any]:
    """
    Junta a OS da listagem (doc da listagem) com o detalhe (doc do detalhe).

    Nenhum dos dois servicos e superconjunto do outro: a listagem tem os
    campos calculados (dias de execucao, medias por Modelo/Motivo), o
    procedimento e o codigo da equipe; o detalhe tem contribuinte com
    endereco, eventos, prorrogacoes e o resto. Por isso o detalhe se
    sobrepoe campo a campo, e o que vier vazio nao apaga o que a listagem
    ja trouxe.

    Esta e a regra canonica. O painel repete a mesma logica em
    OrdensPanel.jsx (sobrepor/mesclarDetalhe) porque la a linha ja esta
    em maos e refazer a consulta da listagem custaria 1,5s a cada clique
    — se mudar aqui, mude la tambem.
    """
    os_completa = _sobrepor(linha, detalhe)

    # Fiscais: o detalhe manda, mas a data de cancelamento e a descricao
    # do status so existem na listagem — casa por matricula para nao
    # perde-las.
    if detalhe.get("fiscais"):
        da_linha = {f.get("matricula"): f for f in linha.get("fiscais", [])}
        os_completa["fiscais"] = [
            _sobrepor(da_linha.get(f.get("matricula"), {}), f)
            for f in detalhe["fiscais"]
        ]
    return os_completa


def _chamar_detalhe_atf_https(base_url: str, numero_os: str) -> dict[str, Any] | None:
    """
    Chama o detalharOrdemServicoWebService via SOAP (doc do detalhe).

    POST https://.../<caminho-do-servico> com o numero da OS em CDATA.
    Devolve o detalhe da OS, ou None quando o ATF nao a encontra.
    """
    import requests

    base = base_url.rstrip("/")
    url = base if base.endswith("OrdemServico") else f"{base}{_atf_ws_path()}"

    chave = f"{url}|detalhe|{numero_os}"
    em_cache = _cache_detalhe_atf.get(chave)
    if em_cache is not None:
        logger.debug("Cache ATF: reaproveitando detalhe da OS %s", numero_os)
        return em_cache[0] if em_cache else None

    envelope = _montar_envelope_detalhe_soap(numero_os)

    try:
        resp = requests.post(
            url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=60,
            verify=config.ATF_SSL_VERIFY,
        )
        # O SOAP Fault chega com HTTP 500: le a mensagem antes de tratar
        # como erro de transporte, senao ela se perde.
        falha = _erro_soap(resp)
        if falha:
            raise ValueError(f"ATF: {falha}")
        resp.raise_for_status()
        detalhe = _parse_detalhe_soap(resp.text)
    except Exception:
        logger.exception("Erro ao detalhar OS %s na API ATF em %s", numero_os, url)
        raise

    # "OS nao encontrada" tambem vai para o cache (como lista vazia): e
    # uma resposta valida do servico, e nao adianta reperguntar em
    # seguida. Erro de negocio e falha de rede sobem sem ser guardados.
    _cache_detalhe_atf.set(chave, [detalhe] if detalhe else [])
    return detalhe


def url_base_detalhe_atf() -> str:
    """
    URL do servico de detalhe: a propria, se configurada; senao a da
    listagem. Vazia nos dois casos significa MOCK.
    """
    from .config import ATF_BASE_URL, ATF_DETALHE_BASE_URL

    return ATF_DETALHE_BASE_URL or ATF_BASE_URL


def detalhe_em_outro_ambiente() -> bool:
    """
    Diz se o detalhe esta apontando para um ambiente diferente do da
    listagem.

    Quando esta, os dados vem de outro banco: a mesma OS volta com
    contribuinte, situacao e fiscais diferentes. Quem chama precisa saber
    disso para nao decidir permissao pela resposta do detalhe (main.py).
    """
    from .config import ATF_BASE_URL, ATF_DETALHE_BASE_URL

    if not ATF_DETALHE_BASE_URL or not ATF_BASE_URL:
        return False
    return ATF_DETALHE_BASE_URL.rstrip("/") != ATF_BASE_URL.rstrip("/")


def detalhar_ordem_atf(numero_os: str) -> dict[str, Any] | None:
    """
    Detalhe completo de uma OS (doc do detalhe).

    Uma OS por chamada — e o unico filtro que o servico aceita. Vai ao
    servico real quando ha URL configurada (ATF_DETALHE_BASE_URL, ou a
    da listagem); sem nenhuma, monta o detalhe a partir do MOCK, para o
    painel continuar navegavel em desenvolvimento.

    Devolve None quando a OS nao existe.
    """
    base_url = url_base_detalhe_atf()

    if base_url:
        logger.debug("Detalhando OS %s em %s", numero_os, base_url)
        return _chamar_detalhe_atf_https(base_url, numero_os)

    logger.debug("Sem URL do ATF configurada – detalhe da OS %s vem do MOCK", numero_os)
    return _detalhe_mock_atf(numero_os)


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


# ─── Dashboard de OS (dados reais do ATF) ───────────────────────
#
# Separado de gerar_dashboard(), que roda sobre o formato interno legado
# (_MOCK_ORDENS) e mede status e ciencia. Aqui a fonte e a listagem do
# ATF e o que se mede sao os cortes pedidos pela area fiscal em
# 31/08/2026: quantidade de OS por gerencia, orgao executor, fiscal,
# motivo, tipo (modelo) e mes de abertura — cada um com o tempo medio de
# execucao.
#
# A contagem de EVENTOS, que a mesma demanda pede, NAO esta aqui. A
# listagem nao traz evento nenhum: so mediaEventosModMot, uma media ja
# pronta por modelo+motivo, e dataUltimoEventoOS. A lista de eventos so
# existe no detalhe, uma chamada por OS (~1s cada, e sao milhares de OS
# por ano), o que nao cabe num painel sob demanda. Fica para o servico
# que a SEFAZ vai expor.

# Limite usado quando o dashboard precisa do universo inteiro em vez de
# uma pagina. Nao custa chamada extra ao ATF: o servico nao pagina do
# lado dele — a listagem ja volta completa e quem recorta e _paginar_atf,
# aqui dentro.
_LIMITE_UNIVERSO = 1_000_000

# Rotulos dos grupos "vazios". Aparecem no eixo do grafico, entao dizem o
# que falta, e nao apenas que falta: quem le precisa saber se o buraco e
# do ATF (orgao/motivo/modelo em branco) ou do nosso cadastro (gerencia).
_SEM_ORGAO = "Sem orgao executor"
_SEM_GERENCIA = "Sem gerencia cadastrada"
_SEM_MOTIVO = "Sem motivo informado"
_SEM_MODELO = "Sem modelo informado"
_SEM_FISCAL = "Sem fiscal designado"
_SEM_ABERTURA = "Sem data de abertura"

# O grupo "vazio" e reconhecido pelo rotulo, e nao por id nulo: no ATF um
# orgao pode vir com nome e sem cdOrgaoExec, e ai o id e None num grupo
# que existe de verdade. Cada linha do corte carrega `vazio` para o front
# nao ter que repetir estes textos do lado dele.
_ROTULOS_VAZIOS = frozenset({
    _SEM_ORGAO, _SEM_GERENCIA, _SEM_MOTIVO, _SEM_MODELO, _SEM_FISCAL, _SEM_ABERTURA,
})


def _resumo_grupo(os_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Quantidade e tempo medio de execucao de um grupo de OS.

    O tempo medio sai SO das OS encerradas. Numa OS que ainda corre,
    dias_execucao conta ate hoje e cresce sozinho todo dia — misturar as
    duas daria uma media que se mexe sem nada ter acontecido. Por isso
    `encerradas` vai junto na linha: e o denominador da media, e sem ele
    ninguem sabe se "42 dias" saiu de 300 OS ou de 2.
    """
    encerradas = [o for o in os_list if o.get("data_encerramento")]
    dias = [
        o["dias_execucao"] for o in encerradas
        if o.get("dias_execucao") is not None
    ]
    return {
        "total": len(os_list),
        "encerradas": len(encerradas),
        "em_execucao": len(os_list) - len(encerradas),
        "tempo_medio": round(sum(dias) / len(dias), 1) if dias else None,
    }


def _agrupar_os(
    ordens: list[dict[str, Any]],
    chaves_de: Callable[[dict[str, Any]], list[tuple[Any, str]]],
) -> list[dict[str, Any]]:
    """
    Agrupa OS por uma dimensao e devolve as linhas do corte, da maior
    para a menor.

    `chaves_de` devolve uma LISTA de chaves (id, rotulo) porque uma OS
    pode cair em mais de um grupo: ela tem varios fiscais e, por tabela,
    pode alcancar mais de uma gerencia. Nos cortes de dimensao unica —
    tipo, motivo, orgao, mes — a lista sempre tem um item so.

    Onde a lista tem mais de um item a soma das linhas passa do total de
    OS, de proposito: a mesma OS conta para cada fiscal designado. Quem
    exibe o corte precisa dizer isso, senao o numero parece errado.
    """
    grupos: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for o in ordens:
        for chave in chaves_de(o):
            grupos[chave].append(o)

    linhas = [
        {
            "id": ident,
            "rotulo": rotulo,
            "vazio": rotulo in _ROTULOS_VAZIOS,
            **_resumo_grupo(os_list),
        }
        for (ident, rotulo), os_list in grupos.items()
    ]
    # Maior primeiro; empate desfeito pelo rotulo para a ordem nao mudar
    # entre duas chamadas com os mesmos dados.
    linhas.sort(key=lambda linha: (-linha["total"], linha["rotulo"]))
    return linhas


def _chave_orgao_executor(o: dict[str, Any]) -> list[tuple[Any, str]]:
    """
    Orgao executor da OS — o que a area fiscal chama de equipe executora.

    Rotula pela sigla (GR2, GOFE-GEFTE), que e como o orgao e conhecido;
    o nome extenso so entra se a sigla nao vier. Nao confundir com
    equipe_fiscal (noEquipeFisc), que e outra dimensao e vem em branco em
    metade das OS.
    """
    rotulo = (
        (o.get("orgao_executor_sigla") or "").strip()
        or (o.get("orgao_executor") or "").strip()
        or _SEM_ORGAO
    )
    return [(o.get("orgao_executor_codigo"), rotulo)]


def _chave_modelo(o: dict[str, Any]) -> list[tuple[Any, str]]:
    """Tipo da OS = modelo no ATF (NORMAL, SIMPLIFICADA, ESPECIAL...)."""
    return [(o.get("modelo_codigo"), (o.get("modelo") or "").strip() or _SEM_MODELO)]


def _chave_motivo(o: dict[str, Any]) -> list[tuple[Any, str]]:
    """Motivo de abertura da OS."""
    return [(
        o.get("motivo_abertura_codigo"),
        (o.get("motivo_abertura") or "").strip() or _SEM_MOTIVO,
    )]


def _chave_mes_abertura(o: dict[str, Any]) -> list[tuple[Any, str]]:
    """Mes de abertura, com id ordenavel (YYYY-MM) e rotulo em MM/AAAA."""
    mes = (o.get("data_abertura") or "")[:7]
    if len(mes) != 7:
        return [(None, _SEM_ABERTURA)]
    ano, numero = mes.split("-")
    return [(mes, f"{numero}/{ano}")]


def _chaves_fiscal(o: dict[str, Any]) -> list[tuple[Any, str]]:
    """
    Um grupo por fiscal designado na OS.

    Sem deduplicar por matricula, a mesma OS entraria duas vezes no grupo
    de um fiscal que aparece repetido na lista — o que acontece no ATF
    quando ele e designado, cancelado e designado de novo.
    """
    vistos: dict[Any, str] = {}
    for f in o.get("fiscais") or []:
        matricula = (f.get("matricula") or "").strip()
        nome = (f.get("nome") or "").strip()
        if not matricula and not nome:
            continue
        vistos.setdefault(matricula or nome, nome or matricula)
    if not vistos:
        return [(None, _SEM_FISCAL)]
    return list(vistos.items())


def _chaves_gerencia(
    o: dict[str, Any], gerencia_por_matricula: dict[str, dict[str, Any]],
) -> list[tuple[Any, str]]:
    """
    Gerencias alcancadas pela OS, pelas matriculas dos seus fiscais.

    A gerencia NAO existe no ATF: e cadastro nosso, e a unica ponte ate
    a OS sao as matriculas em fiscais[]. Uma OS com fiscais de gerencias
    diferentes conta em cada uma — e entra uma vez so por gerencia, mesmo
    com varios fiscais dela na mesma OS.
    """
    encontradas: dict[Any, str] = {}
    for f in o.get("fiscais") or []:
        matricula = (f.get("matricula") or "").strip()
        gerencia = gerencia_por_matricula.get(matricula) if matricula else None
        if gerencia:
            encontradas.setdefault(gerencia["id"], gerencia["nome"])
    if not encontradas:
        return [(None, _SEM_GERENCIA)]
    return list(encontradas.items())


def gerar_dashboard_os(
    ordens: list[dict[str, Any]],
    gerencia_por_matricula: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Consolida os cortes de quantidade de OS sobre a listagem do ATF.

    `ordens` e o universo JA filtrado pela hierarquia de quem pediu — a
    agregacao nao filtra nada por conta propria, para nao haver dois
    lugares decidindo quem ve o que.

    `gerencia_por_matricula` mapeia matricula -> {id, nome} da gerencia,
    montado no banco local (ver _gerencia_por_matricula, em main.py).
    Vazio ou None, o corte por gerencia sai inteiro em "sem gerencia
    cadastrada" — que e a leitura honesta enquanto ninguem amarrou os
    fiscais a uma lotacao.
    """
    mapa_gerencia = gerencia_por_matricula or {}

    geral = _resumo_grupo(ordens)

    matriculas: set[str] = set()
    for o in ordens:
        for f in o.get("fiscais") or []:
            if (f.get("matricula") or "").strip():
                matriculas.add(f["matricula"].strip())

    por_gerencia = _agrupar_os(ordens, lambda o: _chaves_gerencia(o, mapa_gerencia))
    por_orgao = _agrupar_os(ordens, _chave_orgao_executor)
    por_fiscal = _agrupar_os(ordens, _chaves_fiscal)
    por_motivo = _agrupar_os(ordens, _chave_motivo)
    por_tipo = _agrupar_os(ordens, _chave_modelo)

    # O unico corte que nao se ordena por quantidade: mes e uma serie, e
    # so faz sentido no tempo. O id (YYYY-MM) ja ordena como texto; as OS
    # sem data de abertura nao tem lugar na linha e vao para o fim.
    por_mes = sorted(
        _agrupar_os(ordens, _chave_mes_abertura),
        key=lambda linha: (linha["vazio"], linha["id"] or ""),
    )

    sem_gerencia = next(
        (linha["total"] for linha in por_gerencia if linha["vazio"]), 0,
    )
    sem_fiscal = next(
        (linha["total"] for linha in por_fiscal if linha["vazio"]), 0,
    )

    return {
        "visao_geral": {
            "total_os": geral["total"],
            "encerradas": geral["encerradas"],
            "em_execucao": geral["em_execucao"],
            "tempo_medio": geral["tempo_medio"],
            "total_fiscais": len(matriculas),
            "total_orgaos": len([l for l in por_orgao if not l["vazio"]]),
            "total_gerencias": len([l for l in por_gerencia if not l["vazio"]]),
            # Os dois buracos que mudam como o painel deve ser lido: OS
            # que nenhum corte por pessoa alcanca.
            "os_sem_gerencia": sem_gerencia,
            "os_sem_fiscal": sem_fiscal,
        },
        "por_gerencia": por_gerencia,
        "por_orgao_executor": por_orgao,
        "por_fiscal": por_fiscal,
        "por_motivo": por_motivo,
        "por_tipo": por_tipo,
        "por_mes": por_mes,
    }


def universo_ordens_atf(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    matriculas_visiveis: set[str] | None = None,
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    orgao_executor: str | None = None,
    equipe_fiscal: str | None = None,
) -> list[dict[str, Any]]:
    """
    Todas as OS do periodo que o usuario pode ver, sem paginar.

    O recorte de periodo vai pela data de ABERTURA e desce ate o proprio
    ATF (dataAberturaIni/Fim) em vez de ser um filtro local depois: e o
    unico jeito de a consulta do painel nao arrastar a base inteira.

    Os quatro filtros de dimensao descem junto, pelo mesmo motivo e com
    um ganho medido: a chamada custa ~5,3s FIXOS mais ~2ms por OS
    (producao, 02/09/2026 — uma OS por numero leva 5,1s; 17 OS levam
    5,3s; 5376 levam 15,6s). Filtrar no ATF corta so a parte variavel:
    restringir a um orgao executor tirou 41% das linhas e 23% do tempo.
    Ajuda, e nunca leva a zero — nenhum filtro derruba os 5,3s de piso.

    Filtrar por uma dimensao ACHATA o corte dela — filtrado o orgao, o
    grafico "por orgao executor" vira uma barra so. Isso e esperado: o
    painel passa a ser o daquele orgao, e os outros cortes (motivo, tipo,
    mes, fiscal) e que carregam a leitura.
    """
    resultado = listar_ordens_atf(
        data_abertura_ini=data_inicio,
        data_abertura_fim=data_fim,
        modelo=modelo,
        motivo_abertura=motivo_abertura,
        orgao_executor=orgao_executor,
        equipe_fiscal=equipe_fiscal,
        pagina=1,
        limite=_LIMITE_UNIVERSO,
        matriculas_visiveis=matriculas_visiveis,
    )
    return resultado.get("ordens", [])


# ─── Eventos de acompanhamento em lote (doc dos eventos) ────────
#
# Servico listarEventosOrdemServico, no MESMO endpoint da listagem e do
# detalhe (POST {ATF_BASE_URL}{ATF_WS_PATH}): muda so a operacao dentro
# do envelope. E o bloco 2 da demanda de 31/08/2026 — quantidade de
# EVENTOS —, que ate agora nao tinha como ser atendido: a listagem so
# traz mediaEventosModMot (uma media pronta por modelo+motivo) e a lista
# de eventos de verdade so existia no detalhe, uma chamada por OS.
#
# Medido contra desenvolvimento em 02/09/2026: 230 eventos de 188 OS em
# 0,9s numa janela de 15 dias, e 0,2s nas consultas seguintes. Duas
# ordens de grandeza mais barato que varrer detalhes — por isso esta aba
# nao precisa do cuidado que a de OS tem com periodos largos.
#
# DUAS DIVERGENCIAS DA DOC, verificadas na resposta real do servico.
# Cada uma custaria um campo vazio na tela, sem erro nenhum para avisar:
#
# 1. A doc lista <dataInicialEventoOS> e <dataFinalEventoOS>. O servico
#    manda <dataInicioEventoOS> e <dataFimEventoOS>. Lemos os dois
#    nomes, o real primeiro: se um dia alinharem servico e doc, nada
#    aqui quebra.
# 2. O XML de exemplo da doc abre as tags de periodo onde deveria
#    fecha-las e ainda repete o par. E erro de digitacao da doc; o corpo
#    real fecha as tags, como _montar_parametros_eventos_atf faz.
#
# O que o servico NAO manda: matricula, nome de fiscal, nem qualquer
# outra chave de pessoa. Ver get_dashboard_eventos (main.py) para o
# efeito disso na visibilidade.

_SEM_GERENCIA_ATF = "Sem gerencia informada"
_SEM_EQUIPE = "Sem equipe fiscal"
_SEM_PROCEDIMENTO = "Sem procedimento informado"
_SEM_INCLUSAO = "Sem data de inclusao"

# A gerencia vazia aqui tem rotulo diferente do corte de OS ("Sem
# gerencia cadastrada"): la o buraco e do NOSSO cadastro, que nao amarrou
# o fiscal a uma lotacao; aqui e do ATF, que mandou o evento sem
# gerencia. Sao falhas de origens diferentes e quem le o painel precisa
# saber com qual esta lidando.
_ROTULOS_VAZIOS_EVT = frozenset({
    _SEM_MODELO, _SEM_MOTIVO, _SEM_GERENCIA_ATF,
    _SEM_EQUIPE, _SEM_PROCEDIMENTO, _SEM_INCLUSAO,
})

# Limite que o servico impoe aos periodos ("Periodo informado ultrapassa
# um ano"). Conferido contra desenvolvimento em 02/09/2026.
_MAX_DIAS_PERIODO_EVT = 366


def _validar_periodos_eventos(
    data_abertura_ini: str | None, data_abertura_fim: str | None,
    data_inclusao_ini: str | None, data_inclusao_fim: str | None,
) -> None:
    """
    Aplica as duas regras da doc antes de sair do processo: pelo menos um
    periodo completo, e nenhum periodo maior que um ano.

    O ATF valida as duas por conta propria, e com mensagens boas. Isto
    aqui existe por dois motivos: o caminho MOCK nao tem ATF nenhum para
    validar — sem esta funcao a aba se comportaria de um jeito com o
    servico configurado e de outro sem ele — e a mensagem do servico vem
    em duas linhas, prefixada por "Nao foi possivel realizar a
    operacao.", que na tela so ocupa espaco.
    """
    periodos = [
        ("abertura", data_abertura_ini, data_abertura_fim),
        ("inclusao do evento", data_inclusao_ini, data_inclusao_fim),
    ]
    completos = [(nome, ini, fim) for nome, ini, fim in periodos if ini and fim]
    if not completos:
        raise ValueError(
            "Informe pelo menos um periodo completo (inicio e fim): "
            "abertura da OS ou inclusao do evento."
        )

    for nome, ini, fim in completos:
        try:
            d_ini = datetime.strptime(ini, "%Y-%m-%d").date()
            d_fim = datetime.strptime(fim, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(f"Periodo de {nome} invalido: use datas em YYYY-MM-DD.")
        if d_fim < d_ini:
            raise ValueError(f"No periodo de {nome}, o fim e anterior ao inicio.")
        if (d_fim - d_ini).days > _MAX_DIAS_PERIODO_EVT:
            raise ValueError(f"O periodo de {nome} passa de um ano, que e o limite do ATF.")


def _montar_parametros_eventos_atf(
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    gerencia: str | None = None,
    procedimento: str | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_inclusao_ini: str | None = None,
    data_inclusao_fim: str | None = None,
) -> str:
    """Monta o XML <parametros> do elementoEntrada (nomes da doc dos eventos)."""
    campos: list[str] = []

    def _add(tag: str, valor: Any) -> None:
        # Mesmo escape da listagem, pelo mesmo motivo: os valores vem da
        # query string do usuario e sem ele da para fechar a tag, injetar
        # outro filtro, ou fechar o CDATA e escrever direto no corpo SOAP.
        if valor not in (None, ""):
            campos.append(f"<{tag}>{_escape_xml(str(valor))}</{tag}>")

    _add("cdModeloOS", modelo)
    _add("cdMotivoAbertOS", motivo_abertura)
    _add("cdEquipeFisc", equipe_fiscal)
    _add("cdGerencia", gerencia)
    _add("cdProcedimento", procedimento)
    if data_abertura_ini and data_abertura_fim:
        _add("dataAberturaOSIni", _data_para_atf(data_abertura_ini))
        _add("dataAberturaOSFin", _data_para_atf(data_abertura_fim))
    if data_inclusao_ini and data_inclusao_fim:
        _add("dataInclusaoEvtOSIni", _data_para_atf(data_inclusao_ini))
        _add("dataInclusaoEvtOSFin", _data_para_atf(data_inclusao_fim))

    # Linha unica, como na listagem: o parser do ATF nao tolera quebra de
    # linha dentro do CDATA e responde "e necessario informar pelo menos
    # um filtro" como se nada tivesse sido enviado.
    return "<parametros>" + "".join(campos) + "</parametros>"


def _montar_envelope_eventos_soap(parametros_xml: str) -> str:
    """
    Envelope SOAP do servico de eventos.

    Unica diferenca para o da listagem e o nome da operacao. Ele nao saiu
    da doc e sim do ?wsdl de desenvolvimento, que declara
    listarEventosOrdemServicoRequest — a doc do detalhe ja custou uma
    investigacao por divergir do WSDL do ambiente.
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "    <soap:Body>\n"
        '        <ns:listarEventosOrdemServicoRequest xmlns:ns="http://www.receita.pb.gov.br">\n'
        f"            <ns:elementoEntrada><![CDATA[{parametros_xml}]]></ns:elementoEntrada>\n"
        "        </ns:listarEventosOrdemServicoRequest>\n"
        "    </soap:Body>\n"
        "</soap:Envelope>"
    )


def _parse_resposta_eventos_soap(xml_text: str) -> list[dict[str, Any]]:
    """
    Extrai a lista de eventos do retorno do servico de eventos.

    Contrato conferido contra a resposta real (desenvolvimento,
    02/09/2026):
        resultado (operacao, listaEventosOS | dsMensagemErro)
        listaEventosOS (eventoOS*)
        eventoOS (cdEventoAcompOS, nrOrdemServico, cdModeloOS, noModeloOS,
            cdMotivoAberturaOS, noMotivoAberturaOS, cdGerencia, sgGerencia,
            noGerencia, cdEquipeFisc, noEquipeFisc, cdProcedimento,
            noProcedimento, dataAberturaOS, dataInicioFiscalizacaoOS,
            dataInclusaoEventoOS, dataInicioEventoOS, dataFimEventoOS)
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)

    # Mesmo empacotamento da listagem: o XML de dados vem escapado dentro
    # de <retorno> e o ElementTree desfaz o escape no .text.
    retorno_el = next(
        (el for el in root.iter() if el.tag.lower().endswith("retorno")), None,
    )
    if retorno_el is not None and (retorno_el.text or "").strip():
        dados_root = ET.fromstring(_escapar_amp_solto(retorno_el.text.strip()))
    else:
        dados_root = root

    erro = dados_root.findtext(".//dsMensagemErro")
    if erro and erro.strip():
        # O servico manda a mensagem em duas linhas ("Nao foi possivel
        # realizar a operacao." + a causa). Vira uma linha so porque o
        # destino e o `detail` de um HTTP 400, que a tela exibe cru.
        raise ValueError("ATF: " + " ".join(erro.split()))

    def _txt(el: Any, tag: str) -> str:
        return (el.findtext(tag, "") or "").strip()

    eventos: list[dict[str, Any]] = []
    for e_el in dados_root.findall(".//eventoOS"):
        eventos.append({
            "codigo_evento": _int_ou_none(_txt(e_el, "cdEventoAcompOS")),
            "numero_os": _txt(e_el, "nrOrdemServico"),
            "modelo": _txt(e_el, "noModeloOS"),
            "modelo_codigo": _int_ou_none(_txt(e_el, "cdModeloOS")),
            "motivo_abertura": _txt(e_el, "noMotivoAberturaOS"),
            "motivo_abertura_codigo": _int_ou_none(_txt(e_el, "cdMotivoAberturaOS")),
            "gerencia": _txt(e_el, "noGerencia"),
            "gerencia_sigla": _txt(e_el, "sgGerencia"),
            "gerencia_codigo": _int_ou_none(_txt(e_el, "cdGerencia")),
            "equipe_fiscal": _txt(e_el, "noEquipeFisc"),
            "equipe_fiscal_codigo": _int_ou_none(_txt(e_el, "cdEquipeFisc")),
            "procedimento": _txt(e_el, "noProcedimento"),
            "procedimento_codigo": _int_ou_none(_txt(e_el, "cdProcedimento")),
            "data_abertura": _data_do_atf(_txt(e_el, "dataAberturaOS")) or None,
            "data_inicio_fiscalizacao": (
                _data_do_atf(_txt(e_el, "dataInicioFiscalizacaoOS")) or None
            ),
            "data_inclusao": _data_do_atf(_txt(e_el, "dataInclusaoEventoOS")) or None,
            # Nome real primeiro, nome da doc como reserva — ver a nota de
            # divergencia no topo desta secao.
            "data_inicial": (
                _data_do_atf(_txt(e_el, "dataInicioEventoOS"))
                or _data_do_atf(_txt(e_el, "dataInicialEventoOS"))
                or None
            ),
            "data_final": (
                _data_do_atf(_txt(e_el, "dataFimEventoOS"))
                or _data_do_atf(_txt(e_el, "dataFinalEventoOS"))
                or None
            ),
        })

    return eventos


def _chamar_eventos_atf_https(
    base_url: str,
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    gerencia: str | None = None,
    procedimento: str | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_inclusao_ini: str | None = None,
    data_inclusao_fim: str | None = None,
) -> list[dict[str, Any]]:
    """
    Chama o listarEventosOrdemServico via SOAP. Devolve a lista completa
    de eventos do periodo (o servico tambem nao pagina).
    """
    import requests

    base = base_url.rstrip("/")
    url = base if base.endswith("OrdemServico") else f"{base}{_atf_ws_path()}"

    parametros = _montar_parametros_eventos_atf(
        modelo=modelo, motivo_abertura=motivo_abertura,
        equipe_fiscal=equipe_fiscal, gerencia=gerencia, procedimento=procedimento,
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_inclusao_ini=data_inclusao_ini, data_inclusao_fim=data_inclusao_fim,
    )
    # A chave leva a URL junto: com ATF_EVENTOS_BASE_URL apontando para
    # outro ambiente, os mesmos parametros devolvem outro conjunto, e uma
    # chave so de parametros serviria a resposta do ambiente errado.
    chave = f"EVT|{url}|{parametros}"
    em_cache = _cache_atf.get(chave)
    if em_cache is not None:
        logger.debug("Cache ATF: reaproveitando %d eventos para %s", len(em_cache), parametros)
        return em_cache

    envelope = _montar_envelope_eventos_soap(parametros)

    try:
        resp = requests.post(
            url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=60,
            verify=config.ATF_SSL_VERIFY,
        )
        falha = _erro_soap(resp)
        if falha:
            # Aqui o Fault mais provavel e a operacao nao existir no
            # ambiente: em 02/09/2026 so desenvolvimento a publicava.
            raise ValueError(f"ATF: {falha}")
        resp.raise_for_status()
        eventos = _parse_resposta_eventos_soap(resp.text)
    except Exception:
        logger.exception("Erro ao chamar servico de eventos do ATF em %s", url)
        raise

    _cache_atf.set(chave, eventos)
    logger.debug("Cache ATF: %d eventos guardados para %s", len(eventos), parametros)
    return eventos


def url_base_eventos_atf() -> str:
    """
    URL do servico de eventos: a propria, se configurada; senao a da
    listagem. Vazia nos dois casos significa MOCK.
    """
    from .config import ATF_BASE_URL, ATF_EVENTOS_BASE_URL

    return ATF_EVENTOS_BASE_URL or ATF_BASE_URL


def eventos_em_outro_ambiente() -> bool:
    """
    Diz se os eventos estao vindo de um ambiente diferente do da listagem.

    Enquanto a operacao existir so em desenvolvimento, este sera o estado
    normal — e a aba precisa dizer isso na tela. Ambientes tem bancos
    diferentes: a contagem de eventos nao fecha com a contagem de OS ao
    lado, e ninguem deveria descobrir isso comparando os dois numeros
    numa reuniao.
    """
    from .config import ATF_BASE_URL, ATF_EVENTOS_BASE_URL

    if not ATF_EVENTOS_BASE_URL or not ATF_BASE_URL:
        return False
    return ATF_EVENTOS_BASE_URL.rstrip("/") != ATF_BASE_URL.rstrip("/")


def _mock_eventos_atf(
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_inclusao_ini: str | None = None,
    data_inclusao_fim: str | None = None,
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    gerencia: str | None = None,
    procedimento: str | None = None,
) -> list[dict[str, Any]]:
    """
    Eventos do MOCK, derivados das OS de exemplo.

    Reaproveita qtd_eventos e _EVENTOS_MOCK, os mesmos que o detalhe
    mockado usa, para que as duas telas contem a mesma coisa. A gerencia
    sai do orgao executor do mock, que e o campo com a mesma cara.
    """
    from datetime import timedelta

    def _codigo_gerencia_mock(nome: str) -> int | None:
        """Codigo estavel para a gerencia mockada, a partir do nome."""
        if not nome:
            return None
        return 900 + _ORGAOS_EXECUTORES.index(nome) if nome in _ORGAOS_EXECUTORES else 999

    def _sigla(nome: str) -> str:
        """
        Sigla do orgao a partir do nome do mock ("GEFIS - 1a GERENCIA
        REGIONAL" -> "GEFIS - 1a"). Cortar em N caracteres colava
        "GEFIS - 1a" e "GEFIS - 2a" numa gerencia so, e o corte do painel
        mostrava duas onde ha tres.
        """
        partes = [p.strip() for p in nome.split("-", 1)]
        if len(partes) == 2 and partes[1]:
            return f"{partes[0]} - {partes[1].split()[0]}"
        return partes[0]

    eventos: list[dict[str, Any]] = []
    for indice, os_item in enumerate(_MOCK_ATF_ORDENS):
        abertura = os_item.get("data_abertura")
        inicio_fisc_txt = os_item.get("data_inicio_fiscalizacao") or abertura
        if not inicio_fisc_txt:
            continue
        inicio_fisc = datetime.strptime(inicio_fisc_txt, "%Y-%m-%d").date()

        for n in range(os_item.get("qtd_eventos") or 0):
            # `no_procedimento`, e nao `procedimento`: este ultimo e o
            # PARAMETRO de filtro da funcao, e reatribui-lo aqui fazia o
            # filtro passar a valer o nome do ultimo procedimento gerado
            # — o mock inteiro voltava vazio.
            _, _, no_procedimento = _EVENTOS_MOCK[n % len(_EVENTOS_MOCK)]
            inicio_evento = inicio_fisc + timedelta(days=n * 2)
            fim_evento = inicio_evento + timedelta(days=1)
            eventos.append({
                "codigo_evento": indice * 100 + n,
                "numero_os": os_item["numero_os"],
                "modelo": os_item.get("modelo") or "",
                "modelo_codigo": os_item.get("modelo_codigo"),
                "motivo_abertura": os_item.get("motivo_abertura") or "",
                "motivo_abertura_codigo": os_item.get("motivo_abertura_codigo"),
                "gerencia": os_item.get("orgao_executor") or "",
                "gerencia_sigla": _sigla(os_item.get("orgao_executor") or ""),
                # Codigo derivado do nome, e nao copiado de
                # orgao_executor_codigo: no MOCK aquele campo e None, e
                # sem codigo o filtro de gerencia da aba nasceria vazio —
                # a dimensao ficaria intestavel sem o ATF.
                "gerencia_codigo": _codigo_gerencia_mock(os_item.get("orgao_executor") or ""),
                "equipe_fiscal": os_item.get("equipe_fiscal") or "",
                "equipe_fiscal_codigo": os_item.get("equipe_fiscal_codigo"),
                "procedimento": no_procedimento,
                "procedimento_codigo": n % len(_EVENTOS_MOCK) + 1,
                "data_abertura": abertura,
                "data_inicio_fiscalizacao": inicio_fisc_txt,
                # No mock o evento e "incluido" no dia em que termina —
                # e o unico dos dois que sempre existe.
                "data_inclusao": fim_evento.strftime("%Y-%m-%d"),
                "data_inicial": inicio_evento.strftime("%Y-%m-%d"),
                "data_final": fim_evento.strftime("%Y-%m-%d"),
            })

    def _no_periodo(valor: str | None, ini: str | None, fim: str | None) -> bool:
        if not (ini and fim):
            return True
        if not valor:
            return False
        return ini <= valor <= fim

    def _casa(valor: Any, filtro: str | None) -> bool:
        """Compara como texto: o filtro chega da query string, o dado e int."""
        if filtro in (None, ""):
            return True
        return str(valor) == str(filtro)

    # Os filtros de dimensao sao aplicados aqui tambem, e nao so no
    # caminho do ATF. Sem isto eles nao fariam NADA em modo MOCK — a tela
    # mostraria o filtro ativo e o mesmo total de antes, sem erro nenhum.
    # E o MOCK e justamente o modo em que se testa quando o ATF esta fora.
    return [
        e for e in eventos
        if _no_periodo(e["data_abertura"], data_abertura_ini, data_abertura_fim)
        and _no_periodo(e["data_inclusao"], data_inclusao_ini, data_inclusao_fim)
        and _casa(e["modelo_codigo"], modelo)
        and _casa(e["motivo_abertura_codigo"], motivo_abertura)
        and _casa(e["equipe_fiscal_codigo"], equipe_fiscal)
        and _casa(e["gerencia_codigo"], gerencia)
        and _casa(e["procedimento_codigo"], procedimento)
    ]


def listar_eventos_atf(
    modelo: str | None = None,
    motivo_abertura: str | None = None,
    equipe_fiscal: str | None = None,
    gerencia: str | None = None,
    procedimento: str | None = None,
    data_abertura_ini: str | None = None,
    data_abertura_fim: str | None = None,
    data_inclusao_ini: str | None = None,
    data_inclusao_fim: str | None = None,
) -> list[dict[str, Any]]:
    """
    Eventos de acompanhamento de OS em lote (doc dos eventos).

    Com o servico configurado, chama o ATF; sem ele, devolve o MOCK. As
    regras de periodo sao conferidas antes, nos dois caminhos — ver
    _validar_periodos_eventos.
    """
    _validar_periodos_eventos(
        data_abertura_ini, data_abertura_fim, data_inclusao_ini, data_inclusao_fim,
    )

    base_url = url_base_eventos_atf()
    if base_url:
        logger.debug("Chamando servico de eventos do ATF: %s", base_url)
        return _chamar_eventos_atf_https(
            base_url,
            modelo=modelo, motivo_abertura=motivo_abertura,
            equipe_fiscal=equipe_fiscal, gerencia=gerencia, procedimento=procedimento,
            data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
            data_inclusao_ini=data_inclusao_ini, data_inclusao_fim=data_inclusao_fim,
        )

    logger.debug("Servico de eventos nao configurado - usando MOCK")
    return _mock_eventos_atf(
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_inclusao_ini=data_inclusao_ini, data_inclusao_fim=data_inclusao_fim,
        modelo=modelo, motivo_abertura=motivo_abertura,
        equipe_fiscal=equipe_fiscal, gerencia=gerencia, procedimento=procedimento,
    )


# ─── Agregacao do bloco 2: quantidade de EVENTOS ────────────────────


def _duracao_evento(evento: dict[str, Any]) -> int | None:
    """Dias entre inicio e fim do evento. None quando falta uma das duas."""
    inicio, fim = evento.get("data_inicial"), evento.get("data_final")
    if not (inicio and fim):
        return None
    try:
        d_ini = datetime.strptime(inicio, "%Y-%m-%d").date()
        d_fim = datetime.strptime(fim, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    dias = (d_fim - d_ini).days
    return dias if dias >= 0 else None


def _resumo_eventos(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Quantidade de eventos, de OS distintas e duracao media de um grupo.

    `os` vai junto de `total` de proposito: sem ele nao da para saber se
    "40 eventos" sao 40 OS com um evento cada ou uma OS com 40 — que e a
    diferenca entre uma equipe espalhada e uma OS problematica.
    """
    duracoes = [d for d in (_duracao_evento(e) for e in eventos) if d is not None]
    os_distintas = {e["numero_os"] for e in eventos if e.get("numero_os")}
    return {
        "total": len(eventos),
        "os": len(os_distintas),
        "duracao_media": round(sum(duracoes) / len(duracoes), 1) if duracoes else None,
    }


def _agrupar_eventos(
    eventos: list[dict[str, Any]],
    chave_de: Callable[[dict[str, Any]], tuple[Any, str]],
) -> list[dict[str, Any]]:
    """
    Agrupa eventos por uma dimensao e devolve as linhas do corte, da
    maior para a menor.

    Ao contrario de _agrupar_os, a chave e UMA so: um evento pertence a
    exatamente uma gerencia, um procedimento, um mes. Nao ha o caso da OS
    com varios fiscais, entao a soma das linhas fecha com o total.
    """
    grupos: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for e in eventos:
        grupos[chave_de(e)].append(e)

    linhas = [
        {
            "id": ident,
            "rotulo": rotulo,
            "vazio": rotulo in _ROTULOS_VAZIOS_EVT,
            **_resumo_eventos(lista),
        }
        for (ident, rotulo), lista in grupos.items()
    ]
    linhas.sort(key=lambda linha: (-linha["total"], linha["rotulo"]))
    return linhas


def _chave_gerencia_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """
    Gerencia do evento — e esta vem do ATF, nao do nosso cadastro.

    E a diferenca que mais importa entre os dois blocos: no corte de OS a
    gerencia so existe se o admin tiver amarrado o fiscal a uma lotacao,
    e por isso sai quase toda vazia. Aqui o proprio servico manda
    cdGerencia/sgGerencia — 97% dos eventos na medicao de 02/09/2026.
    Rotula pela sigla, como o orgao executor, porque e assim que a
    gerencia e chamada.
    """
    rotulo = (
        (e.get("gerencia_sigla") or "").strip()
        or (e.get("gerencia") or "").strip()
        or _SEM_GERENCIA_ATF
    )
    return (e.get("gerencia_codigo"), rotulo)


def _chave_equipe_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """
    Equipe fiscal do evento.

    O preenchimento depende do PERIODO, nao do campo: medido no ambiente
    de desenvolvimento em 02/09/2026, a equipe veio em 0% dos eventos de
    janeiro/2026, 83% dos de julho e 31% do ano inteiro — ela foi sendo
    adotada ao longo de 2026. Uma janela antiga sai inteira em "Sem
    equipe fiscal", e isso e o dado, nao falha da integracao.

    O corte aparece mesmo vazio: escondido, viraria a impressao de que a
    dimensao nao foi pedida.
    """
    return (
        e.get("equipe_fiscal_codigo"),
        (e.get("equipe_fiscal") or "").strip() or _SEM_EQUIPE,
    )


def _chave_procedimento_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """Procedimento do evento (AUDITORIA NA ESCRITA FISCAL, etc.)."""
    return (
        e.get("procedimento_codigo"),
        (e.get("procedimento") or "").strip() or _SEM_PROCEDIMENTO,
    )


def _chave_modelo_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """Tipo da OS a que o evento pertence."""
    return (e.get("modelo_codigo"), (e.get("modelo") or "").strip() or _SEM_MODELO)


def _chave_motivo_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """Motivo de abertura da OS a que o evento pertence."""
    return (
        e.get("motivo_abertura_codigo"),
        (e.get("motivo_abertura") or "").strip() or _SEM_MOTIVO,
    )


def _chave_mes_inclusao_evt(e: dict[str, Any]) -> tuple[Any, str]:
    """
    Mes de INCLUSAO do evento, com id ordenavel (YYYY-MM).

    A serie e pela inclusao, e nao pela abertura da OS: o que se mede
    aqui e o trabalho registrado no periodo. Um evento de janeiro numa OS
    aberta em dezembro e trabalho de janeiro.
    """
    mes = (e.get("data_inclusao") or "")[:7]
    if len(mes) != 7:
        return (None, _SEM_INCLUSAO)
    ano, numero = mes.split("-")
    return (mes, f"{numero}/{ano}")


def gerar_dashboard_eventos(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Consolida os cortes de quantidade de eventos (bloco 2 da demanda de
    31/08/2026).

    Mesma divisao de trabalho do bloco 1: quem chama ja entregou o
    universo que o usuario pode ver, e a agregacao nao filtra nada por
    conta propria.
    """
    geral = _resumo_eventos(eventos)

    por_gerencia = _agrupar_eventos(eventos, _chave_gerencia_evt)
    por_equipe = _agrupar_eventos(eventos, _chave_equipe_evt)
    por_procedimento = _agrupar_eventos(eventos, _chave_procedimento_evt)
    por_motivo = _agrupar_eventos(eventos, _chave_motivo_evt)
    por_tipo = _agrupar_eventos(eventos, _chave_modelo_evt)

    # Serie no tempo: ordena pelo mes, nao pela quantidade. Os eventos sem
    # data de inclusao nao tem lugar na linha e vao para o fim.
    por_mes = sorted(
        _agrupar_eventos(eventos, _chave_mes_inclusao_evt),
        key=lambda linha: (linha["vazio"], linha["id"] or ""),
    )

    def _vazios(linhas: list[dict[str, Any]]) -> int:
        return next((l["total"] for l in linhas if l["vazio"]), 0)

    return {
        "visao_geral": {
            "total_eventos": geral["total"],
            "total_os": geral["os"],
            # Media por OS: quantos eventos, em media, cada OS tocada no
            # periodo recebeu. Nao confundir com mediaEventosModMot da
            # listagem, que e uma media historica por modelo+motivo.
            "media_por_os": (
                round(geral["total"] / geral["os"], 1) if geral["os"] else None
            ),
            "duracao_media": geral["duracao_media"],
            "total_gerencias": len([l for l in por_gerencia if not l["vazio"]]),
            "total_procedimentos": len([l for l in por_procedimento if not l["vazio"]]),
            # Os dois buracos que mudam como o painel deve ser lido.
            "eventos_sem_gerencia": _vazios(por_gerencia),
            "eventos_sem_equipe": _vazios(por_equipe),
        },
        "por_gerencia": por_gerencia,
        "por_equipe": por_equipe,
        "por_procedimento": por_procedimento,
        "por_motivo": por_motivo,
        "por_tipo": por_tipo,
        "por_mes": por_mes,
    }
