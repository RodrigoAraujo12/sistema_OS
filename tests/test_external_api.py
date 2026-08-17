"""
Testes unitarios para o modulo external_api.py – logica de OS e dashboard.

Cobre: montagem do envelope SOAP, cache das respostas do ATF,
filtragem hierarquica, geracao de alertas e dashboard.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from backend.external_api import (
    _chamar_atf_https,
    _filtrar_por_hierarquia,
    _montar_envelope_soap,
    _montar_parametros_atf,
    filtrar_atf_por_matriculas,
    gerar_alertas,
    gerar_dashboard,
    limpar_cache_atf,
    listar_ordens_servico,
)


def _resposta_soap(numeros_e_matriculas: dict[str, str]) -> str:
    """Monta uma resposta do ATF com as OS informadas (numero -> matricula)."""
    ordens = "".join(
        f"<ordemServico><nrOrdemServico>{n}</nrOrdemServico>"
        f"<fiscais><fiscal><matricula>{m}</matricula><nome>F {m}</nome></fiscal></fiscais>"
        f"</ordemServico>"
        for n, m in numeros_e_matriculas.items()
    )
    return (
        "<resultado><listaOrdemServico>"
        f"{ordens}"
        "</listaOrdemServico></resultado>"
    )


class TestCacheATF(unittest.TestCase):
    """
    O ATF devolve a lista completa e nao pagina. Sem cache, cada troca de
    pagina ou de ordenacao refazia a consulta inteira.
    """

    def setUp(self):
        limpar_cache_atf()
        self.addCleanup(limpar_cache_atf)

    def _post_falso(self, xml: str) -> MagicMock:
        resp = MagicMock()
        resp.text = xml
        resp.raise_for_status = MagicMock()
        return resp

    def test_segunda_chamada_igual_nao_vai_na_rede(self):
        xml = _resposta_soap({"OS-1": "111", "OS-2": "222"})
        with patch("requests.post", return_value=self._post_falso(xml)) as post:
            a = _chamar_atf_https("https://atf.local", numero_os="X")
            b = _chamar_atf_https("https://atf.local", numero_os="X")
        self.assertEqual(post.call_count, 1, "a segunda chamada deveria vir do cache")
        self.assertEqual([o["numero_os"] for o in a], [o["numero_os"] for o in b])

    def test_filtro_diferente_e_consulta_diferente(self):
        xml = _resposta_soap({"OS-1": "111"})
        with patch("requests.post", return_value=self._post_falso(xml)) as post:
            _chamar_atf_https("https://atf.local", numero_os="X")
            _chamar_atf_https("https://atf.local", numero_os="Y")
        self.assertEqual(post.call_count, 2)

    def test_cache_devolve_copias_independentes(self):
        """
        Quem chama preenche dias_execucao nas OS. Se o cache devolvesse os
        mesmos dicionarios, uma requisicao alteraria o que a outra ve.
        """
        xml = _resposta_soap({"OS-1": "111"})
        with patch("requests.post", return_value=self._post_falso(xml)):
            primeira = _chamar_atf_https("https://atf.local", numero_os="X")
            primeira[0]["dias_execucao"] = 999
            segunda = _chamar_atf_https("https://atf.local", numero_os="X")
        self.assertIsNone(segunda[0]["dias_execucao"])

    def test_cache_nao_vaza_entre_hierarquias(self):
        """
        O cache guarda a resposta CRUA e a hierarquia e aplicada depois, por
        requisicao. Duas pessoas com equipes diferentes compartilham a ida
        ao ATF, mas nunca o resultado filtrado.
        """
        xml = _resposta_soap({"OS-A": "111", "OS-B": "222"})
        with patch("requests.post", return_value=self._post_falso(xml)) as post:
            bruto_1 = _chamar_atf_https("https://atf.local", numero_os="X")
            bruto_2 = _chamar_atf_https("https://atf.local", numero_os="X")
        self.assertEqual(post.call_count, 1)
        visao_1 = filtrar_atf_por_matriculas(bruto_1, {"111"})
        visao_2 = filtrar_atf_por_matriculas(bruto_2, {"222"})
        self.assertEqual([o["numero_os"] for o in visao_1], ["OS-A"])
        self.assertEqual([o["numero_os"] for o in visao_2], ["OS-B"])

    def test_erro_nao_e_guardado(self):
        """Falha de rede nao pode ficar grudada no cache durante o TTL."""
        ok = self._post_falso(_resposta_soap({"OS-1": "111"}))
        with patch("requests.post", side_effect=[ConnectionError("caiu"), ok]) as post:
            with self.assertRaises(ConnectionError):
                _chamar_atf_https("https://atf.local", numero_os="X")
            ordens = _chamar_atf_https("https://atf.local", numero_os="X")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(ordens), 1)

    def test_ttl_zero_desliga_o_cache(self):
        from backend.external_api import _cache_atf

        xml = _resposta_soap({"OS-1": "111"})
        with patch.object(_cache_atf, "_ttl", 0):
            with patch("requests.post", return_value=self._post_falso(xml)) as post:
                _chamar_atf_https("https://atf.local", numero_os="X")
                _chamar_atf_https("https://atf.local", numero_os="X")
        self.assertEqual(post.call_count, 2)


class TestEscapeParametrosATF(unittest.TestCase):
    """
    Os valores dos filtros vem da query string. Sem escape da para
    reescrever a consulta enviada ao ATF ou quebrar o CDATA do envelope.
    """

    def test_valor_normal_nao_e_alterado(self):
        p = _montar_parametros_atf(numero_os="93300008.12.00000001/2026-99")
        self.assertIn("<numeroOS>93300008.12.00000001/2026-99</numeroOS>", p)

    def test_nao_injeta_filtro_extra(self):
        """Fechar a tag no valor nao pode criar um segundo filtro."""
        p = _montar_parametros_atf(
            numero_os="X</numeroOS><cdOrgaoExec>629</cdOrgaoExec><numeroOS>"
        )
        root = ET.fromstring(p)
        self.assertEqual([el.tag for el in root], ["numeroOS"])
        self.assertIsNone(root.find("cdOrgaoExec"))
        # O valor chega inteiro do outro lado, so que como texto
        self.assertEqual(
            root.findtext("numeroOS"),
            "X</numeroOS><cdOrgaoExec>629</cdOrgaoExec><numeroOS>",
        )

    def test_nao_quebra_o_cdata(self):
        """']]>' no valor nao pode encerrar o CDATA do elementoEntrada."""
        envelope = _montar_envelope_soap(
            _montar_parametros_atf(ie="A]]><ns:injetado>oi</ns:injetado><![CDATA[")
        )
        # Um unico CDATA, fechado uma unica vez, no fim dos parametros
        self.assertEqual(envelope.count("]]>"), 1)
        self.assertIn("</parametros>]]>", envelope)
        # E o envelope continua sendo XML valido, sem a tag injetada
        root = ET.fromstring(envelope)
        self.assertIsNone(next((el for el in root.iter() if "injetado" in el.tag), None))

    def test_ampersand_sobrevive_ao_round_trip(self):
        p = _montar_parametros_atf(ie="A & B")
        self.assertEqual(ET.fromstring(p).findtext("inscrEstadual"), "A & B")


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
        visao = gerar_dashboard([], self.gerencias, self.supervisoes, self.users)["visao_geral"]
        self.assertEqual(visao["total_os"], 0)
        self.assertEqual(visao["os_abertas"], 0)
        self.assertEqual(visao["os_concluidas"], 0)
        self.assertEqual(visao["os_sem_ciencia"], 0)
        self.assertEqual(visao["taxa_conclusao"], 0)

    def test_os_sem_ciencia_count(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        self.assertEqual(result["visao_geral"]["os_sem_ciencia"], 1)

    def test_total_fiscais_e_supervisores(self):
        result = gerar_dashboard(self.ordens, self.gerencias, self.supervisoes, self.users)
        self.assertEqual(result["visao_geral"]["total_fiscais"], 2)
        self.assertEqual(result["visao_geral"]["total_supervisores"], 2)


if __name__ == "__main__":
    unittest.main()
