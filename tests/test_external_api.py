"""
Testes unitarios para o modulo external_api.py – logica de OS e dashboard.

Cobre: calculo de dias_parado, enriquecimento de OS, filtragem hierarquica,
geracao de alertas, normalizacao de dados do Informix, e dashboard.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from backend.external_api import (
    _calcular_dias_parado,
    _enriquecer_os,
    _filtrar_por_hierarquia,
    _normalizar_row,
    gerar_alertas,
    gerar_dashboard,
    listar_ordens_servico,
)


class TestCalcularDiasParado(unittest.TestCase):
    """Testes para _calcular_dias_parado."""

    def test_data_recente(self):
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(_calcular_dias_parado(hoje), 0)

    def test_data_passada(self):
        passado = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        self.assertEqual(_calcular_dias_parado(passado), 10)

    def test_data_none(self):
        self.assertEqual(_calcular_dias_parado(None), 0)

    def test_data_invalida(self):
        self.assertEqual(_calcular_dias_parado("abc"), 0)

    def test_data_vazia(self):
        self.assertEqual(_calcular_dias_parado(""), 0)


class TestEnriquecerOS(unittest.TestCase):
    """Testes para _enriquecer_os."""

    def test_adiciona_dias_parado(self):
        os_dict = {"numero": "OS-001", "data_ultima_movimentacao": "2020-01-01"}
        result = _enriquecer_os(os_dict)
        self.assertIn("dias_parado", result)
        self.assertGreater(result["dias_parado"], 0)

    def test_sem_data_movimentacao(self):
        os_dict = {"numero": "OS-001"}
        result = _enriquecer_os(os_dict)
        self.assertEqual(result["dias_parado"], 0)

    def test_preserva_campos_originais(self):
        os_dict = {"numero": "OS-001", "status": "aberta", "data_ultima_movimentacao": None}
        result = _enriquecer_os(os_dict)
        self.assertEqual(result["numero"], "OS-001")
        self.assertEqual(result["status"], "aberta")


class TestNormalizarRow(unittest.TestCase):
    """Testes para _normalizar_row."""

    def test_fiscais_string_to_list(self):
        row = {"fiscais": "Carlos Mendes, Ana Ribeiro", "data_abertura": "2026-01-01"}
        result = _normalizar_row(row)
        self.assertEqual(result["fiscais"], ["Carlos Mendes", "Ana Ribeiro"])

    def test_fiscais_already_list(self):
        row = {"fiscais": ["Carlos"], "data_abertura": "2026-01-01"}
        result = _normalizar_row(row)
        self.assertEqual(result["fiscais"], ["Carlos"])

    def test_date_fields_from_datetime(self):
        from datetime import date
        row = {
            "fiscais": "A",
            "data_abertura": date(2026, 1, 15),
            "data_ciencia": None,
            "data_ultima_movimentacao": datetime(2026, 2, 1, 10, 30),
        }
        result = _normalizar_row(row)
        self.assertEqual(result["data_abertura"], "2026-01-15")
        self.assertIsNone(result["data_ciencia"])
        self.assertEqual(result["data_ultima_movimentacao"], "2026-02-01")


class TestFiltrarPorHierarquia(unittest.TestCase):
    """Testes para _filtrar_por_hierarquia."""

    def setUp(self):
        self.ordens = [
            {"numero": "OS-001", "matricula_supervisor": "111", "fiscais": ["Carlos"]},
            {"numero": "OS-002", "matricula_supervisor": "222", "fiscais": ["Ana"]},
            {"numero": "OS-003", "matricula_supervisor": "111", "fiscais": ["Carlos", "Ana"]},
        ]

    def test_admin_ve_tudo(self):
        result = _filtrar_por_hierarquia(self.ordens, user_role="admin")
        self.assertEqual(len(result), 3)

    def test_none_role_ve_tudo(self):
        result = _filtrar_por_hierarquia(self.ordens, user_role=None)
        self.assertEqual(len(result), 3)

    def test_fiscal_filtra_por_nome(self):
        result = _filtrar_por_hierarquia(self.ordens, user_role="fiscal", user_name="Ana")
        self.assertEqual(len(result), 2)
        numeros = {r["numero"] for r in result}
        self.assertIn("OS-002", numeros)
        self.assertIn("OS-003", numeros)

    def test_supervisor_filtra_por_matricula(self):
        result = _filtrar_por_hierarquia(
            self.ordens, user_role="supervisor", user_matricula="222"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["numero"], "OS-002")

    def test_gerente_filtra_por_matriculas(self):
        result = _filtrar_por_hierarquia(
            self.ordens, user_role="gerente", supervisor_matriculas=["111"]
        )
        self.assertEqual(len(result), 2)

    def test_gerente_sem_matriculas_retorna_vazio(self):
        result = _filtrar_por_hierarquia(
            self.ordens, user_role="gerente", supervisor_matriculas=None
        )
        self.assertEqual(len(result), 0)

    def test_fiscal_sem_nome_retorna_vazio(self):
        result = _filtrar_por_hierarquia(
            self.ordens, user_role="fiscal", user_name=None
        )
        self.assertEqual(len(result), 0)


class TestGerarAlertas(unittest.TestCase):
    """Testes para gerar_alertas."""

    @patch("backend.external_api.listar_ordens_servico")
    def test_alerta_os_urgente(self, mock_listar):
        mock_listar.return_value = [
            {
                "numero": "OS-001",
                "prioridade": "urgente",
                "status": "aberta",
                "razao_social": "Empresa X",
                "ie": "123",
                "dias_parado": 5,
                "data_ciencia": "2026-01-01",
                "data_abertura": "2026-01-01",
                "data_ultima_movimentacao": "2026-01-01",
            }
        ]
        alertas = gerar_alertas(user_role="admin")
        tipos = [a["tipo"] for a in alertas]
        self.assertIn("os_urgente", tipos)

    @patch("backend.external_api.listar_ordens_servico")
    def test_alerta_os_parada(self, mock_listar):
        mock_listar.return_value = [
            {
                "numero": "OS-002",
                "prioridade": "normal",
                "status": "em_andamento",
                "razao_social": "Empresa Y",
                "ie": "456",
                "dias_parado": 20,
                "data_ciencia": "2026-01-01",
                "data_abertura": "2026-01-01",
                "data_ultima_movimentacao": "2025-12-01",
            }
        ]
        alertas = gerar_alertas(user_role="admin")
        tipos = [a["tipo"] for a in alertas]
        self.assertIn("os_parada", tipos)

    @patch("backend.external_api.listar_ordens_servico")
    def test_alerta_os_sem_ciencia(self, mock_listar):
        mock_listar.return_value = [
            {
                "numero": "OS-003",
                "prioridade": "normal",
                "status": "aberta",
                "razao_social": "Empresa Z",
                "ie": "789",
                "dias_parado": 2,
                "data_ciencia": None,
                "data_abertura": "2026-02-01",
                "data_ultima_movimentacao": "2026-02-01",
            }
        ]
        alertas = gerar_alertas(user_role="admin")
        tipos = [a["tipo"] for a in alertas]
        self.assertIn("os_sem_ciencia", tipos)

    @patch("backend.external_api.listar_ordens_servico")
    def test_sem_alertas_os_normal(self, mock_listar):
        mock_listar.return_value = [
            {
                "numero": "OS-004",
                "prioridade": "normal",
                "status": "concluida",
                "razao_social": "Empresa W",
                "ie": "000",
                "dias_parado": 0,
                "data_ciencia": "2026-01-01",
                "data_abertura": "2026-01-01",
                "data_ultima_movimentacao": "2026-01-10",
            }
        ]
        alertas = gerar_alertas(user_role="admin")
        self.assertEqual(len(alertas), 0)


class TestGerarDashboard(unittest.TestCase):
    """Testes para gerar_dashboard."""

    def setUp(self):
        self.ordens = [
            {
                "numero": "OS-001", "status": "aberta", "prioridade": "normal",
                "matricula_supervisor": "111", "fiscais": ["Carlos"],
                "data_abertura": "2026-01-10", "data_ciencia": None,
                "data_ultima_movimentacao": "2026-01-10", "dias_parado": 5,
            },
            {
                "numero": "OS-002", "status": "em_andamento", "prioridade": "alta",
                "matricula_supervisor": "111", "fiscais": ["Carlos"],
                "data_abertura": "2026-01-05", "data_ciencia": "2026-01-07",
                "data_ultima_movimentacao": "2026-01-20", "dias_parado": 3,
            },
            {
                "numero": "OS-003", "status": "concluida", "prioridade": "normal",
                "matricula_supervisor": "222", "fiscais": ["Ana"],
                "data_abertura": "2025-12-01", "data_ciencia": "2025-12-03",
                "data_ultima_movimentacao": "2025-12-20", "dias_parado": 0,
            },
        ]
        self.gerencias = [{"id": 1, "name": "Gerencia A"}]
        self.supervisoes = [
            {"id": 10, "name": "Supervisao X", "gerencia_id": 1},
            {"id": 20, "name": "Supervisao Y", "gerencia_id": 1},
        ]
        self.users = [
            {"id": 1, "username": "admin", "role": "admin", "matricula": None, "supervisao_id": None},
            {"id": 2, "username": "Sup1", "role": "supervisor", "matricula": "111", "supervisao_id": 10},
            {"id": 3, "username": "Sup2", "role": "supervisor", "matricula": "222", "supervisao_id": 20},
            {"id": 4, "username": "Carlos", "role": "fiscal", "matricula": "333", "supervisao_id": 10},
            {"id": 5, "username": "Ana", "role": "fiscal", "matricula": "444", "supervisao_id": 20},
        ]

    def test_visao_geral_total(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        vg = result["visao_geral"]
        self.assertEqual(vg["total_os"], 3)
        self.assertEqual(vg["os_abertas"], 1)
        self.assertEqual(vg["os_em_andamento"], 1)
        self.assertEqual(vg["os_concluidas"], 1)

    def test_distribuicao_status(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        ds = result["distribuicao_status"]
        self.assertEqual(ds["aberta"], 1)
        self.assertEqual(ds["em_andamento"], 1)
        self.assertEqual(ds["concluida"], 1)
        self.assertEqual(ds["cancelada"], 0)

    def test_desempenho_gerencias_tem_id(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        for g in result["desempenho_gerencias"]:
            self.assertIn("id", g)
            self.assertIn("nome", g)

    def test_desempenho_supervisoes_tem_gerencia_id(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        for s in result["desempenho_supervisoes"]:
            self.assertIn("gerencia_id", s)
            self.assertIn("gerencia_nome", s)

    def test_carga_fiscais_tem_supervisao_id(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        for f in result["carga_fiscais"]:
            self.assertIn("supervisao_id", f)
            self.assertIn("os_ativas", f)

    def test_evolucao_mensal_ordenada(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        meses = [e["mes"] for e in result["evolucao_mensal"]]
        self.assertEqual(meses, sorted(meses))

    def test_dashboard_sem_os(self):
        result = gerar_dashboard([], self.gerencias, self.supervisoes, self.users)
        self.assertEqual(result["visao_geral"]["total_os"], 0)
        self.assertEqual(result["visao_geral"]["dias_parado_medio"], 0)
        self.assertEqual(result["visao_geral"]["tempo_medio_conclusao"], 0)

    def test_os_sem_ciencia_count(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        self.assertEqual(result["visao_geral"]["os_sem_ciencia"], 1)

    def test_total_fiscais_e_supervisores(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        self.assertEqual(result["visao_geral"]["total_fiscais"], 2)
        self.assertEqual(result["visao_geral"]["total_supervisores"], 2)


if __name__ == "__main__":
    unittest.main()
