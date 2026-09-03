"""
Testes do servico de EVENTOS de OS em lote (doc dos eventos) e do bloco 2 do
dashboard.

O que mais importa aqui esta em test_parse_usa_os_nomes_reais_do_servico:
a doc e a resposta real divergem em dois campos, e o modo de falhar e
silencioso — data vazia na tela, sem erro nenhum. O teste fixa os dois
nomes contra a resposta que o servico de desenvolvimento devolveu em
02/09/2026.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from xml.sax.saxutils import escape

from backend.external_api import (
    _chamar_eventos_atf_https,
    _montar_envelope_eventos_soap,
    _montar_parametros_eventos_atf,
    _parse_resposta_eventos_soap,
    _validar_periodos_eventos,
    gerar_dashboard_eventos,
)


def _envelope_de_resposta(corpo_interno: str) -> str:
    """Empacota o XML de dados como o ATF faz: escapado dentro de <retorno>."""
    return (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        '<listarEventosOrdemServicoResponse xmlns="http://www.receita.pb.gov.br">'
        f"<retorno>{escape(corpo_interno)}</retorno>"
        "</listarEventosOrdemServicoResponse>"
        "</soap:Body></soap:Envelope>"
    )


# Um evento com os nomes de tag REAIS, copiados da resposta de
# desenvolvimento de 02/09/2026.
_EVENTO_REAL = (
    "<eventoOS>"
    "<cdEventoAcompOS>335935</cdEventoAcompOS>"
    "<nrOrdemServico>93300008.12.00000002/2025-99</nrOrdemServico>"
    "<cdModeloOS>8</cdModeloOS><noModeloOS>ESPECIFICA</noModeloOS>"
    "<cdMotivoAberturaOS>233</cdMotivoAberturaOS>"
    "<noMotivoAberturaOS>EC 87/2015 DIFAL NAO CONTRIBUINTE</noMotivoAberturaOS>"
    "<cdGerencia>275</cdGerencia><sgGerencia>GOFSE</sgGerencia>"
    "<noGerencia>GERENCIA OPERACIONAL DE SEGMENTOS ESPECIAIS</noGerencia>"
    "<cdEquipeFisc/><noEquipeFisc/>"
    "<cdProcedimento>10</cdProcedimento>"
    "<noProcedimento>AUDITORIA NA ESCRITA FISCAL</noProcedimento>"
    "<dataAberturaOS>11/12/2025</dataAberturaOS>"
    "<dataInicioFiscalizacaoOS>13/12/2025</dataInicioFiscalizacaoOS>"
    "<dataInclusaoEventoOS>01/01/2026</dataInclusaoEventoOS>"
    "<dataInicioEventoOS>13/12/2025</dataInicioEventoOS>"
    "<dataFimEventoOS>31/12/2025</dataFimEventoOS>"
    "</eventoOS>"
)


class TestParametrosEEnvelope(unittest.TestCase):
    def test_parametros_em_linha_unica(self):
        """O parser do ATF nao tolera quebra de linha dentro do CDATA."""
        xml = _montar_parametros_eventos_atf(
            data_inclusao_ini="2026-01-01", data_inclusao_fim="2026-01-15",
        )
        self.assertNotIn("\n", xml)

    def test_datas_convertidas_para_o_formato_do_atf(self):
        xml = _montar_parametros_eventos_atf(
            data_inclusao_ini="2026-01-01", data_inclusao_fim="2026-01-15",
        )
        self.assertIn("<dataInclusaoEvtOSIni>01/01/2026</dataInclusaoEvtOSIni>", xml)
        self.assertIn("<dataInclusaoEvtOSFin>15/01/2026</dataInclusaoEvtOSFin>", xml)

    def test_periodo_pela_metade_nao_e_enviado(self):
        """A doc exige inicio E fim; meio periodo filtraria outra coisa."""
        xml = _montar_parametros_eventos_atf(data_abertura_ini="2026-01-01")
        self.assertEqual(xml, "<parametros></parametros>")

    def test_valores_do_usuario_sao_escapados(self):
        """Sem escape da para fechar a tag e injetar outro filtro."""
        xml = _montar_parametros_eventos_atf(
            gerencia="1</cdGerencia><cdModeloOS>9",
            data_inclusao_ini="2026-01-01", data_inclusao_fim="2026-01-15",
        )
        self.assertNotIn("<cdModeloOS>9", xml)
        self.assertIn("&lt;", xml)

    def test_envelope_usa_a_operacao_do_wsdl(self):
        env = _montar_envelope_eventos_soap("<parametros></parametros>")
        self.assertIn("ns:listarEventosOrdemServicoRequest", env)
        self.assertIn("<![CDATA[", env)


class TestParse(unittest.TestCase):
    def test_parse_usa_os_nomes_reais_do_servico(self):
        """
        A doc lista dataInicialEventoOS/dataFinalEventoOS; o servico manda
        dataInicioEventoOS/dataFimEventoOS. Codificar pela doc deixaria as
        duas datas vazias sem erro nenhum para avisar.
        """
        xml = _envelope_de_resposta(f"<resultado><listaEventosOS>{_EVENTO_REAL}</listaEventosOS></resultado>")
        eventos = _parse_resposta_eventos_soap(xml)

        self.assertEqual(len(eventos), 1)
        e = eventos[0]
        self.assertEqual(e["data_inicial"], "2025-12-13")
        self.assertEqual(e["data_final"], "2025-12-31")
        self.assertEqual(e["data_inclusao"], "2026-01-01")
        self.assertEqual(e["codigo_evento"], 335935)
        self.assertEqual(e["gerencia_sigla"], "GOFSE")
        self.assertEqual(e["gerencia_codigo"], 275)
        self.assertEqual(e["procedimento"], "AUDITORIA NA ESCRITA FISCAL")
        # Equipe vem auto-fechada na resposta real
        self.assertEqual(e["equipe_fiscal"], "")
        self.assertIsNone(e["equipe_fiscal_codigo"])

    def test_parse_aceita_tambem_os_nomes_da_doc(self):
        """Se um dia alinharem servico e doc, o parser continua lendo."""
        evento_doc = (
            "<eventoOS><nrOrdemServico>1</nrOrdemServico>"
            "<dataInicialEventoOS>01/02/2026</dataInicialEventoOS>"
            "<dataFinalEventoOS>05/02/2026</dataFinalEventoOS></eventoOS>"
        )
        xml = _envelope_de_resposta(f"<resultado><listaEventosOS>{evento_doc}</listaEventosOS></resultado>")
        e = _parse_resposta_eventos_soap(xml)[0]
        self.assertEqual(e["data_inicial"], "2026-02-01")
        self.assertEqual(e["data_final"], "2026-02-05")

    def test_erro_de_negocio_vira_value_error_em_uma_linha(self):
        """O ATF manda a mensagem em duas linhas; o destino e um HTTP 400."""
        corpo = (
            "<resultado><dsMensagemErro>Nao foi possivel realizar a operacao.\n"
            "Periodo informado ultrapassa um ano.</dsMensagemErro></resultado>"
        )
        with self.assertRaises(ValueError) as ctx:
            _parse_resposta_eventos_soap(_envelope_de_resposta(corpo))
        self.assertNotIn("\n", str(ctx.exception))
        self.assertIn("ultrapassa um ano", str(ctx.exception))

    def test_lista_vazia_nao_e_erro(self):
        xml = _envelope_de_resposta("<resultado><listaEventosOS></listaEventosOS></resultado>")
        self.assertEqual(_parse_resposta_eventos_soap(xml), [])


class TestValidacaoDePeriodo(unittest.TestCase):
    def test_sem_periodo_nenhum(self):
        with self.assertRaises(ValueError):
            _validar_periodos_eventos(None, None, None, None)

    def test_periodo_pela_metade_nao_conta(self):
        with self.assertRaises(ValueError):
            _validar_periodos_eventos("2026-01-01", None, None, None)

    def test_periodo_maior_que_um_ano(self):
        with self.assertRaises(ValueError) as ctx:
            _validar_periodos_eventos(None, None, "2025-01-01", "2026-12-31")
        self.assertIn("um ano", str(ctx.exception))

    def test_fim_antes_do_inicio(self):
        with self.assertRaises(ValueError):
            _validar_periodos_eventos(None, None, "2026-03-01", "2026-01-01")

    def test_um_periodo_completo_basta(self):
        _validar_periodos_eventos(None, None, "2026-01-01", "2026-01-15")
        _validar_periodos_eventos("2026-01-01", "2026-01-15", None, None)

    def test_doze_meses_cabem_no_limite(self):
        """O botao "12 meses" da tela nao pode esbarrar na regra do ATF."""
        _validar_periodos_eventos(None, None, "2025-09-02", "2026-09-02")


class TestChamadaHttp(unittest.TestCase):
    def test_cache_separa_eventos_de_ordens(self):
        """
        A chave do cache leva prefixo e URL: sem eles, uma consulta de
        eventos poderia servir a resposta guardada para a listagem de OS,
        ou a de outro ambiente.
        """
        corpo = f"<resultado><listaEventosOS>{_EVENTO_REAL}</listaEventosOS></resultado>"
        resp = MagicMock(status_code=200, text=_envelope_de_resposta(corpo))

        with patch("requests.post", return_value=resp) as post:
            a = _chamar_eventos_atf_https(
                "https://exemplo/servico",
                data_inclusao_ini="2026-01-01", data_inclusao_fim="2026-01-15",
            )
            b = _chamar_eventos_atf_https(
                "https://outro-ambiente/servico",
                data_inclusao_ini="2026-01-01", data_inclusao_fim="2026-01-15",
            )

        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        # Mesmos parametros, URLs diferentes: duas idas de verdade.
        self.assertEqual(post.call_count, 2)


def _evt(**campos):
    """Evento minimo para os testes de agregacao."""
    base = {
        "codigo_evento": 1, "numero_os": "OS-1",
        "modelo": "NORMAL", "modelo_codigo": 1,
        "motivo_abertura": "MONITORAMENTO", "motivo_abertura_codigo": 2,
        "gerencia": "GERENCIA UM", "gerencia_sigla": "G1", "gerencia_codigo": 10,
        "equipe_fiscal": "", "equipe_fiscal_codigo": None,
        "procedimento": "AUDITORIA", "procedimento_codigo": 5,
        "data_abertura": "2026-01-05", "data_inicio_fiscalizacao": "2026-01-06",
        "data_inclusao": "2026-01-10",
        "data_inicial": "2026-01-06", "data_final": "2026-01-08",
    }
    base.update(campos)
    return base


class TestDashboardEventos(unittest.TestCase):
    def test_conta_eventos_e_os_distintas(self):
        """
        Tres eventos em duas OS: o painel precisa dizer os dois numeros.
        So "3 eventos" nao distingue tres OS tranquilas de uma OS
        problematica.
        """
        eventos = [
            _evt(codigo_evento=1, numero_os="OS-1"),
            _evt(codigo_evento=2, numero_os="OS-1"),
            _evt(codigo_evento=3, numero_os="OS-2"),
        ]
        d = gerar_dashboard_eventos(eventos)
        self.assertEqual(d["visao_geral"]["total_eventos"], 3)
        self.assertEqual(d["visao_geral"]["total_os"], 2)
        self.assertEqual(d["visao_geral"]["media_por_os"], 1.5)

    def test_soma_dos_cortes_fecha_com_o_total(self):
        """
        Diferente do corte de OS por fiscal, aqui cada evento cai em um
        grupo so — se a soma passar do total, alguem duplicou chave.
        """
        eventos = [
            _evt(codigo_evento=1, gerencia_sigla="G1", gerencia_codigo=10),
            _evt(codigo_evento=2, gerencia_sigla="G2", gerencia_codigo=20),
            _evt(codigo_evento=3, gerencia_sigla="G2", gerencia_codigo=20),
        ]
        d = gerar_dashboard_eventos(eventos)
        self.assertEqual(sum(l["total"] for l in d["por_gerencia"]), 3)
        self.assertEqual(sum(l["total"] for l in d["por_procedimento"]), 3)

    def test_gerencia_ausente_vira_grupo_marcado_como_vazio(self):
        eventos = [_evt(codigo_evento=1, gerencia="", gerencia_sigla="", gerencia_codigo=None)]
        d = gerar_dashboard_eventos(eventos)
        linha = d["por_gerencia"][0]
        self.assertTrue(linha["vazio"])
        self.assertEqual(d["visao_geral"]["eventos_sem_gerencia"], 1)
        self.assertEqual(d["visao_geral"]["total_gerencias"], 0)

    def test_equipe_vazia_e_contada_e_nao_escondida(self):
        """
        Janelas antigas saem inteiras sem equipe: o campo foi sendo
        adotado ao longo de 2026 (0% em janeiro, 83% em julho). Esconder
        o corte faria parecer que a dimensao nao foi atendida.
        """
        d = gerar_dashboard_eventos([_evt(), _evt(codigo_evento=2)])
        self.assertEqual(d["visao_geral"]["eventos_sem_equipe"], 2)
        self.assertTrue(d["por_equipe"][0]["vazio"])

    def test_duracao_media_ignora_evento_sem_uma_das_datas(self):
        eventos = [
            _evt(codigo_evento=1, data_inicial="2026-01-01", data_final="2026-01-05"),
            _evt(codigo_evento=2, data_inicial="2026-01-01", data_final=None),
        ]
        d = gerar_dashboard_eventos(eventos)
        self.assertEqual(d["visao_geral"]["duracao_media"], 4.0)

    def test_serie_mensal_ordena_pelo_mes_e_nao_pela_quantidade(self):
        eventos = [
            _evt(codigo_evento=1, data_inclusao="2026-03-10"),
            _evt(codigo_evento=2, data_inclusao="2026-01-10"),
            _evt(codigo_evento=3, data_inclusao="2026-01-20"),
        ]
        d = gerar_dashboard_eventos(eventos)
        self.assertEqual([l["rotulo"] for l in d["por_mes"]], ["01/2026", "03/2026"])

    def test_evento_sem_data_de_inclusao_vai_para_o_fim_da_serie(self):
        eventos = [
            _evt(codigo_evento=1, data_inclusao=None),
            _evt(codigo_evento=2, data_inclusao="2026-01-10"),
        ]
        d = gerar_dashboard_eventos(eventos)
        self.assertFalse(d["por_mes"][0]["vazio"])
        self.assertTrue(d["por_mes"][-1]["vazio"])

    def test_sem_eventos_nao_quebra(self):
        d = gerar_dashboard_eventos([])
        self.assertEqual(d["visao_geral"]["total_eventos"], 0)
        self.assertIsNone(d["visao_geral"]["media_por_os"])
        self.assertEqual(d["por_gerencia"], [])


if __name__ == "__main__":
    unittest.main()
