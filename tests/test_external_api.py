"""
Testes unitarios para o modulo external_api.py – logica de OS e dashboard.

Cobre: montagem dos envelopes SOAP (listagem e detalhe), parse do
detalhe da OS, caches das respostas do ATF, alertas e dashboards sobre
a listagem do ATF.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from xml.sax.saxutils import escape

from backend.external_api import (
    _chamar_atf_https,
    _chamar_detalhe_atf_https,
    _float_ou_none,
    _montar_envelope_detalhe_soap,
    _montar_envelope_soap,
    _montar_parametros_atf,
    _parse_detalhe_soap,
    detalhar_ordem_atf,
    detalhe_em_outro_ambiente,
    filtrar_atf_por_matriculas,
    gerar_alertas,
    gerar_dashboard_desempenho,
    gerar_dashboard_os,
    limpar_cache_atf,
    mesclar_detalhe_os,
    url_base_detalhe_atf,
    validar_periodo_abertura,
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



# ─── Detalhe da OS (doc do detalhe) ────────────────────────────────

def _resposta_detalhe(numero: str = "OS-1", matricula: str = "111") -> str:
    """Resposta minima do detalharOrdemServicoWebService."""
    return (
        "<resultado><operacao><codigo>0</codigo></operacao><ordServ>"
        f"<nrOrdemServico>{numero}</nrOrdemServico>"
        "<noModeloOrdServ>NORMAL</noModeloOrdServ>"
        "<tpSituacaoOS>1</tpSituacaoOS><noSituacaoOS>AUTORIZADA</noSituacaoOS>"
        "<cdModeloOS>1</cdModeloOS><cdMotivoAberturaOS>195</cdMotivoAberturaOS>"
        "<noMotivoAberturaOS>MALHA FISCAL</noMotivoAberturaOS>"
        "<outrasInfo><dtAbertura>10/01/2025</dtAbertura>"
        "<dtInicialFisc>13/01/2025</dtInicialFisc></outrasInfo>"
        "<contribuinte><noHumanoInst>EMPRESA TESTE LTDA</noHumanoInst>"
        "<nrInscrEstadual>16.123.456-7</nrInscrEstadual>"
        "<nrDocHumanoInst>12.345.678/0001-90</nrDocHumanoInst>"
        "<endereco><noLogradouro>EPITACIO PESSOA</noLogradouro>"
        "<sgTpLogradouro>AV</sgTpLogradouro><nrresidencia>1420</nrresidencia>"
        "<noBairro>TAMBAU</noBairro><noMunicipio>JOAO PESSOA</noMunicipio>"
        "<dsAbrevUf>PB</dsAbrevUf><nrCep>58039-000</nrCep></endereco>"
        "</contribuinte>"
        f"<listaFiscal><fiscal><nrMatFiscal>{matricula}</nrMatFiscal>"
        f"<noHumFiscal>F {matricula}</noHumFiscal><stFiscalOS>ATIVO</stFiscalOS>"
        "<dtCiencia>14/01/2025</dtCiencia><dtDesigna>11/01/2025</dtDesigna>"
        "<responsavel>SIM</responsavel></fiscal></listaFiscal>"
        "<listaEventos><eventos>"
        "<tpEventoAcompOS>4</tpEventoAcompOS>"
        "<dsTpEventoAcompOS>LEVANTAMENTO FISCAL</dsTpEventoAcompOS>"
        "<dtInicialEvento>03/02/2025</dtInicialEvento>"
        "<dtFinalEvento>20/02/2025</dtFinalEvento>"
        "<noProcedimento>CONTA MERCADORIAS</noProcedimento>"
        "<vlLevantado>18.450,75</vlLevantado>"
        "</eventos></listaEventos>"
        "<listaRecolhimentosOS><vlTotalRecolheOS>5.230,75</vlTotalRecolheOS>"
        "</listaRecolhimentosOS>"
        "</ordServ></resultado>"
    )


class TestEnvelopeDetalheATF(unittest.TestCase):
    """
    O envelope do detalhe difere do da listagem em dois pontos que o ATF
    nao perdoa: a operacao e <parametro> no singular.
    """

    def test_operacao_e_elemento_de_entrada(self):
        envelope = _montar_envelope_detalhe_soap("93300008.12.00005561/2025-59")
        self.assertIn("detalharOrdemServicoRequest", envelope)
        self.assertIn("<parametro><numeroOS>", envelope)
        self.assertIn("93300008.12.00005561/2025-59</numeroOS></parametro>", envelope)

    def test_usa_o_nome_de_operacao_da_doc(self):
        """
        Cada ambiente do ATF expoe a operacao do detalhe com um nome
        diferente (o de producao tem um infixo a mais). O envelope tem
        de sair com o nome da doc, exatamente; qualquer variante derruba
        a chamada com SOAP Fault de operacao desconhecida.

        Os nomes por ambiente estao em NOTAS-INTERNAS.md, fora do repo.
        """
        envelope = _montar_envelope_detalhe_soap("OS-1")
        self.assertIn("<ns:detalharOrdemServicoRequest ", envelope)
        self.assertNotIn("Lista", envelope)

    def test_numero_nao_quebra_o_cdata(self):
        """O numero vem da URL: sem escape da para sair do CDATA."""
        envelope = _montar_envelope_detalhe_soap("X]]><ns:outro>")
        corpo = envelope.split("<![CDATA[")[1].split("]]>")[0]
        self.assertNotIn("<ns:outro>", corpo)
        self.assertIn("&gt;", corpo)


class TestValorBrasileiro(unittest.TestCase):
    """
    Leitura dos numeros do servico, que vem em pt-BR ("1.234,56").

    O parser fazia replace(",", ".") sem tirar o ponto de milhar, entao
    TODO valor a partir de mil virava None e sumia da tela — os pequenos
    apareciam e os grandes nao, que e o pior jeito de falhar. Os valores
    abaixo sao sinteticos; o que importa e a FORMA (separador de milhar,
    virgula decimal), nao a grandeza.
    """

    def test_valor_abaixo_de_mil(self):
        self.assertEqual(_float_ou_none("12,34"), 12.34)
        self.assertEqual(_float_ou_none("999,99"), 999.99)

    def test_valor_a_partir_de_mil_nao_e_perdido(self):
        self.assertEqual(_float_ou_none("1.000,00"), 1000.0)
        self.assertEqual(_float_ou_none("1.234,56"), 1234.56)
        self.assertEqual(_float_ou_none("99.999,99"), 99999.99)

    def test_milhao_tem_dois_pontos(self):
        self.assertEqual(_float_ou_none("1.234.567,89"), 1234567.89)

    def test_negativo(self):
        self.assertEqual(_float_ou_none("-1.500,25"), -1500.25)

    def test_inteiro_agrupado_sem_decimais(self):
        """"12.345" e doze mil, nao 12 inteiros e 345 milesimos."""
        self.assertEqual(_float_ou_none("12.345"), 12345.0)

    def test_ponto_decimal_solitario_continua_valendo(self):
        """Se o servico um dia mandar formato ingles, nao inventar milhar."""
        self.assertEqual(_float_ou_none("1.5"), 1.5)

    def test_media_da_listagem(self):
        """As medias da listagem vem no mesmo formato dos valores."""
        self.assertEqual(_float_ou_none("12,50"), 12.5)

    def test_ausente_ou_invalido_vira_none(self):
        for entrada in (None, "", "   ", "-", "abc"):
            self.assertIsNone(_float_ou_none(entrada), entrada)


class TestParseDetalheATF(unittest.TestCase):
    """O parser do detalhe (doc do detalhe), incluindo os blocos aninhados."""

    def setUp(self):
        self.detalhe = _parse_detalhe_soap(_resposta_detalhe())

    def test_campos_repetem_os_nomes_da_listagem(self):
        """
        O front sobrepoe o detalhe a linha do grid campo a campo — se as
        chaves divergirem, o modal passa a mostrar dois valores para a
        mesma coisa.
        """
        for chave in (
            "numero_os", "modelo", "modelo_codigo", "motivo_abertura",
            "situacao", "data_abertura", "data_inicio_fiscalizacao",
            "fiscais", "ie", "cnpj", "razao_social",
        ):
            self.assertIn(chave, self.detalhe)
        self.assertEqual(self.detalhe["situacao"], {"codigo": 1, "descricao": "AUTORIZADA"})
        self.assertEqual(self.detalhe["data_abertura"], "2025-01-10")

    def test_contribuinte_e_endereco(self):
        contrib = self.detalhe["contribuinte"]
        self.assertEqual(contrib["nome"], "EMPRESA TESTE LTDA")
        self.assertEqual(contrib["endereco"]["logradouro"], "AV EPITACIO PESSOA")
        self.assertEqual(contrib["endereco"]["uf"], "PB")
        # Os mesmos dados tambem sobem para a raiz, como na listagem
        self.assertEqual(self.detalhe["razao_social"], "EMPRESA TESTE LTDA")
        self.assertEqual(self.detalhe["cnpj"], "12.345.678/0001-90")

    def test_eventos_com_valor_no_formato_brasileiro(self):
        evento = self.detalhe["eventos"][0]
        self.assertEqual(evento["valor_levantado"], 18450.75)
        self.assertEqual(evento["data_final"], "2025-02-20")
        self.assertEqual(self.detalhe["valor_total_recolhido"], 5230.75)

    def test_ultimo_evento_sai_da_lista(self):
        """Este servico nao tem dataUltimoEventoOS — a data vem dos eventos."""
        self.assertEqual(self.detalhe["data_ultimo_evento"], "2025-02-20")

    def test_fiscal_alimenta_o_filtro_de_hierarquia(self):
        """
        A permissao do detalhe e checada sobre a propria resposta, com
        filtrar_atf_por_matriculas — que le fiscais[].matricula.
        """
        self.assertEqual(self.detalhe["fiscais"][0]["matricula"], "111")
        self.assertEqual(filtrar_atf_por_matriculas([self.detalhe], {"111"}), [self.detalhe])
        self.assertEqual(filtrar_atf_por_matriculas([self.detalhe], {"222"}), [])

    def test_recolhimentos_e_denuncias_detalhados(self):
        """
        Blocos descritos na revisao da doc de 21/08/2026. Sinteticos de
        proposito: nenhuma das 40 OS varridas no ambiente de teste trouxe
        recolhimento ou denuncia preenchidos, entao a unica fonte do
        formato e o contrato.
        """
        xml = (
            "<resultado><ordServ><nrOrdemServico>OS-1</nrOrdemServico>"
            "<listaRecolhimentosOS><recolhimentoOS>"
            "<chaveRecolhimentoOS>2026000123</chaveRecolhimentoOS>"
            "<dsRecolhimentoOS>ICMS APURADO</dsRecolhimentoOS>"
            "<dtInclusao>15/03/2026</dtInclusao>"
            "<nrNossoNumero>00012345678</nrNossoNumero>"
            "<ref>A</ref><dpReferencia>02/2026</dpReferencia>"
            "<vlPrincipal>18.450,75</vlPrincipal>"
            "<cdReceitaSefin>1105</cdReceitaSefin>"
            "<noReceitaSefin>ICMS NORMAL</noReceitaSefin>"
            "<noSituacaoDebito>PAGO</noSituacaoDebito>"
            "<noSituacaoARR>QUITADO</noSituacaoARR>"
            "</recolhimentoOS>"
            "<vlTotalRecolheOS>18.450,75</vlTotalRecolheOS></listaRecolhimentosOS>"
            "<listaDenuncia><denuncia><dtDenuncia>02/01/2026</dtDenuncia>"
            "<dsDenuncia>Notas sem lastro.</dsDenuncia></denuncia></listaDenuncia>"
            "</ordServ></resultado>"
        )
        d = _parse_detalhe_soap(xml)

        rec = d["recolhimentos"][0]
        self.assertEqual(rec["chave"], "2026000123")
        self.assertEqual(rec["data_inclusao"], "2026-03-15")
        self.assertEqual(rec["referencia"], "02/2026")
        self.assertEqual(rec["valor_principal"], 18450.75)
        self.assertEqual(rec["receita_nome"], "ICMS NORMAL")
        self.assertEqual(rec["situacao_arr"], "QUITADO")
        # o total continua saindo do irmao vlTotalRecolheOS, nao da soma
        self.assertEqual(d["valor_total_recolhido"], 18450.75)

        self.assertEqual(d["denuncias"], [
            {"data": "2026-01-02", "descricao": "Notas sem lastro."},
        ])

    def test_dtInclusao_do_recolhimento_nao_vaza_para_a_descricao(self):
        """
        dtInclusao existe em recolhimentoOS e em descricaoComplementarOS.
        Cada leitura e feita a partir do seu proprio elemento; uma busca
        global pegaria a data errada.
        """
        xml = (
            "<resultado><ordServ><nrOrdemServico>OS-1</nrOrdemServico>"
            "<outrasInfo><descricoesComplementaresOS><descricaoComplementarOS>"
            "<dtInclusao>01/01/2026</dtInclusao><dsComplementarOS>Texto</dsComplementarOS>"
            "</descricaoComplementarOS></descricoesComplementaresOS></outrasInfo>"
            "<listaRecolhimentosOS><recolhimentoOS>"
            "<dtInclusao>15/03/2026</dtInclusao><dsRecolhimentoOS>ICMS</dsRecolhimentoOS>"
            "</recolhimentoOS></listaRecolhimentosOS>"
            "</ordServ></resultado>"
        )
        d = _parse_detalhe_soap(xml)
        self.assertEqual(d["descricoes_complementares"][0]["data_inclusao"], "2026-01-01")
        self.assertEqual(d["recolhimentos"][0]["data_inclusao"], "2026-03-15")

    def test_notificacoes_aceitam_as_duas_grafias_da_doc(self):
        xml = (
            "<resultado><ordServ><nrOrdemServico>OS-1</nrOrdemServico>"
            "<listaNotificacao><notificao>"
            "<cdnotificacao>9001</cdnotificacao><nonotificacao>N 9001</nonotificacao>"
            "</notificao></listaNotificacao>"
            "<listaNotificacaoSCAMF><notificacaoSCAMF>"
            "<cdnotificao>551</cdnotificao><nonotificacao>SCAMF 551</nonotificacao>"
            "</notificacaoSCAMF></listaNotificacaoSCAMF>"
            "</ordServ></resultado>"
        )
        d = _parse_detalhe_soap(xml)
        self.assertEqual(d["notificacoes"], [{"codigo": "9001", "nome": "N 9001"}])
        self.assertEqual(d["notificacoes_scamf"], [{"codigo": "551", "nome": "SCAMF 551"}])

    def test_dados_escapados_dentro_de_retorno(self):
        """Como na listagem, a resposta real vem escapada em <retorno>."""
        envelopada = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body><ns:detalharOrdemServicoResponse "
            'xmlns:ns="http://www.receita.pb.gov.br"><ns:retorno>'
            f"{escape(_resposta_detalhe())}"
            "</ns:retorno></ns:detalharOrdemServicoResponse></soap:Body></soap:Envelope>"
        )
        self.assertEqual(_parse_detalhe_soap(envelopada)["numero_os"], "OS-1")

    def test_os_inexistente_vira_none(self):
        semdados = "<resultado><operacao><codigo>1</codigo></operacao></resultado>"
        self.assertIsNone(_parse_detalhe_soap(semdados))

    def test_nenhum_registro_e_404_e_nao_erro(self):
        """
        "Nenhum registro satisfaz a pesquisa" e como o ATF diz que a OS
        nao existe — numa busca por numero isso e 404, nao erro.
        """
        self.assertIsNone(_parse_detalhe_soap(
            "<resultado><dsMensagemErro>Nenhum registro satisfaz a pesquisa."
            "</dsMensagemErro></resultado>",
        ))

    def test_erro_de_negocio_vira_excecao(self):
        with self.assertRaises(ValueError):
            _parse_detalhe_soap(
                "<resultado><dsMensagemErro>OS invalida</dsMensagemErro></resultado>",
            )


class TestCacheDetalheATF(unittest.TestCase):
    """Uma OS por clique — reabrir a mesma nao precisa de outra ida ao ATF."""

    def setUp(self):
        limpar_cache_atf()
        self.addCleanup(limpar_cache_atf)

    def _post_falso(self, xml: str) -> MagicMock:
        resp = MagicMock()
        resp.text = xml
        resp.raise_for_status = MagicMock()
        return resp

    def test_mesma_os_duas_vezes_vai_uma_vez_na_rede(self):
        xml = _resposta_detalhe("OS-1")
        with patch("requests.post", return_value=self._post_falso(xml)) as post:
            a = _chamar_detalhe_atf_https("https://atf.local", "OS-1")
            b = _chamar_detalhe_atf_https("https://atf.local", "OS-1")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(a["numero_os"], b["numero_os"])

    def test_os_diferente_e_consulta_diferente(self):
        with patch("requests.post", side_effect=[
            self._post_falso(_resposta_detalhe("OS-1")),
            self._post_falso(_resposta_detalhe("OS-2")),
        ]) as post:
            primeira = _chamar_detalhe_atf_https("https://atf.local", "OS-1")
            segunda = _chamar_detalhe_atf_https("https://atf.local", "OS-2")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(primeira["numero_os"], "OS-1")
        self.assertEqual(segunda["numero_os"], "OS-2")

    def test_com_url_configurada_vai_ao_servico_real(self):
        """detalhar_ordem_atf escolhe entre ATF e MOCK pela ATF_BASE_URL."""
        xml = _resposta_detalhe("OS-1")
        with patch("backend.config.ATF_BASE_URL", "https://atf.local"):
            with patch("requests.post", return_value=self._post_falso(xml)) as post:
                detalhe = detalhar_ordem_atf("OS-1")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(detalhe["numero_os"], "OS-1")
        self.assertIn("detalharOrdemServicoRequest", post.call_args.kwargs["data"].decode())

    def test_sem_url_configurada_usa_o_mock(self):
        with patch("backend.config.ATF_BASE_URL", ""):
            with patch("requests.post") as post:
                detalhe = detalhar_ordem_atf("OS-2026-001")
                inexistente = detalhar_ordem_atf("OS-9999")
        post.assert_not_called()
        self.assertEqual(detalhe["numero_os"], "OS-2026-001")
        self.assertIsNone(inexistente)

    def test_soap_fault_vira_mensagem_legivel(self):
        """
        SOAP Fault chega com HTTP 500. Olhando so o status, a mensagem —
        a unica que diz o que houve — se perderia.
        """
        fault = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body><soap:Fault><faultcode>soap:Client</faultcode>"
            "<faultstring>Message part was not recognized.</faultstring>"
            "</soap:Fault></soap:Body></soap:Envelope>"
        )
        resp = self._post_falso(fault)
        resp.raise_for_status.side_effect = AssertionError("nao deveria chegar aqui")
        with patch("requests.post", return_value=resp):
            with self.assertRaises(ValueError) as ctx:
                _chamar_detalhe_atf_https("https://atf.local", "OS-1")
        self.assertIn("Message part was not recognized.", str(ctx.exception))

    def test_fault_nao_e_guardado_no_cache(self):
        """Erro do servico nao pode ficar grudado durante o TTL."""
        fault = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body><soap:Fault><faultstring>caiu</faultstring>"
            "</soap:Fault></soap:Body></soap:Envelope>"
        )
        with patch("requests.post", side_effect=[
            self._post_falso(fault), self._post_falso(_resposta_detalhe("OS-1")),
        ]) as post:
            with self.assertRaises(ValueError):
                _chamar_detalhe_atf_https("https://atf.local", "OS-1")
            detalhe = _chamar_detalhe_atf_https("https://atf.local", "OS-1")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(detalhe["numero_os"], "OS-1")

    def test_cache_do_detalhe_nao_atrapalha_o_da_listagem(self):
        """Sao dois caches: limpar_cache_atf tem que esvaziar os dois."""
        with patch("requests.post", return_value=self._post_falso(_resposta_detalhe("OS-1"))):
            _chamar_detalhe_atf_https("https://atf.local", "OS-1")
            limpar_cache_atf()
        with patch("requests.post", return_value=self._post_falso(_resposta_detalhe("OS-1"))) as post:
            _chamar_detalhe_atf_https("https://atf.local", "OS-1")
        self.assertEqual(post.call_count, 1, "o cache deveria ter sido descartado")



class TestMesclarDetalheOS(unittest.TestCase):
    """
    Nenhum dos dois servicos do ATF e superconjunto do outro, entao a
    mesclagem nao pode deixar o detalhe apagar o que so a listagem tem.
    """

    def setUp(self):
        self.linha = {
            "numero_os": "OS-1",
            "razao_social": "NOME ANTIGO",
            "equipe_fiscal": "GOFE - VAREJO",
            "equipe_fiscal_codigo": 427,
            "procedimento": "MALHA FISCAL",
            "dias_execucao": 42,
            "tempo_medio_execucao_modelo_motivo": 65.4,
            "qtd_media_eventos_modelo_motivo": 2.5,
            "fiscais": [
                {"matricula": "111", "nome": "F 111", "status": "DESIGNADO",
                 "data_cancelamento": "2026-03-01"},
            ],
        }
        self.detalhe = {
            "numero_os": "OS-1",
            "razao_social": "NOME COMPLETO LTDA",
            "equipe_fiscal": "",
            "dias_execucao": None,
            "eventos": [{"tipo": "LEVANTAMENTO"}],
            "prorrogacoes": [],
            "contribuinte": {"nome": "NOME COMPLETO LTDA"},
            "fiscais": [
                {"matricula": "111", "nome": "FULANO 111", "status_codigo": "0",
                 "responsavel": "SIM", "data_cancelamento": None},
            ],
        }

    def test_campos_so_da_listagem_sobrevivem(self):
        """
        Equipe fiscal, procedimento, dias de execucao e as medias por
        Modelo/Motivo nao existem no detalhe. Uma copia crua os apagaria.
        """
        os_completa = mesclar_detalhe_os(self.linha, self.detalhe)
        self.assertEqual(os_completa["equipe_fiscal"], "GOFE - VAREJO")
        self.assertEqual(os_completa["equipe_fiscal_codigo"], 427)
        self.assertEqual(os_completa["procedimento"], "MALHA FISCAL")
        self.assertEqual(os_completa["dias_execucao"], 42)
        self.assertEqual(os_completa["tempo_medio_execucao_modelo_motivo"], 65.4)
        self.assertEqual(os_completa["qtd_media_eventos_modelo_motivo"], 2.5)

    def test_detalhe_manda_no_que_preenche(self):
        os_completa = mesclar_detalhe_os(self.linha, self.detalhe)
        self.assertEqual(os_completa["razao_social"], "NOME COMPLETO LTDA")
        self.assertEqual(os_completa["eventos"], [{"tipo": "LEVANTAMENTO"}])
        self.assertEqual(os_completa["contribuinte"], {"nome": "NOME COMPLETO LTDA"})

    def test_lista_vazia_nao_apaga(self):
        """prorrogacoes: [] no detalhe nao pode zerar o que ja existia."""
        linha = dict(self.linha, prorrogacoes=[{"dias": 30}])
        os_completa = mesclar_detalhe_os(linha, self.detalhe)
        self.assertEqual(os_completa["prorrogacoes"], [{"dias": 30}])

    def test_fiscal_casa_por_matricula(self):
        """
        O detalhe manda o CODIGO do status e nao devolve a data de
        cancelamento; os dois textos vem da listagem e nao podem sumir.
        """
        fiscal = mesclar_detalhe_os(self.linha, self.detalhe)["fiscais"][0]
        self.assertEqual(fiscal["nome"], "FULANO 111")
        self.assertEqual(fiscal["responsavel"], "SIM")
        self.assertEqual(fiscal["status"], "DESIGNADO")
        self.assertEqual(fiscal["status_codigo"], "0")
        self.assertEqual(fiscal["data_cancelamento"], "2026-03-01")

    def test_fiscal_novo_no_detalhe_entra_inteiro(self):
        detalhe = dict(self.detalhe, fiscais=[{"matricula": "999", "nome": "NOVO"}])
        fiscais = mesclar_detalhe_os(self.linha, detalhe)["fiscais"]
        self.assertEqual(len(fiscais), 1)
        self.assertEqual(fiscais[0]["matricula"], "999")

    def test_nao_altera_os_dicionarios_de_entrada(self):
        mesclar_detalhe_os(self.linha, self.detalhe)
        self.assertEqual(self.linha["razao_social"], "NOME ANTIGO")
        self.assertEqual(self.linha["fiscais"][0]["nome"], "F 111")


class TestAmbienteDoDetalheATF(unittest.TestCase):
    """
    Hoje a listagem esta em producao e o detalhe so responde em
    desenvolvimento, com bancos diferentes. ATF_DETALHE_BASE_URL separa
    os dois; quando ela for vazia, tudo volta a sair da mesma URL.
    """

    def test_sem_url_propria_usa_a_da_listagem(self):
        with patch("backend.config.ATF_BASE_URL", "https://prod.local"):
            with patch("backend.config.ATF_DETALHE_BASE_URL", ""):
                self.assertEqual(url_base_detalhe_atf(), "https://prod.local")
                self.assertFalse(detalhe_em_outro_ambiente())

    def test_url_propria_tem_prioridade(self):
        with patch("backend.config.ATF_BASE_URL", "https://prod.local"):
            with patch("backend.config.ATF_DETALHE_BASE_URL", "https://dev.local:8443"):
                self.assertEqual(url_base_detalhe_atf(), "https://dev.local:8443")
                self.assertTrue(detalhe_em_outro_ambiente())

    def test_mesma_url_nas_duas_nao_e_outro_ambiente(self):
        """Barra no fim nao muda o ambiente."""
        with patch("backend.config.ATF_BASE_URL", "https://prod.local"):
            with patch("backend.config.ATF_DETALHE_BASE_URL", "https://prod.local/"):
                self.assertFalse(detalhe_em_outro_ambiente())

    def test_detalhe_vai_para_a_url_propria(self):
        limpar_cache_atf()
        self.addCleanup(limpar_cache_atf)
        resp = MagicMock()
        resp.text = _resposta_detalhe("OS-1")
        resp.raise_for_status = MagicMock()
        with patch("backend.config.ATF_BASE_URL", "https://prod.local"):
            with patch("backend.config.ATF_DETALHE_BASE_URL", "https://dev.local:8443"):
                with patch("backend.config.ATF_WS_PATH", "/ws/Recurso"):
                    with patch("requests.post", return_value=resp) as post:
                        detalhar_ordem_atf("OS-1")
        self.assertEqual(post.call_args.args[0], "https://dev.local:8443/ws/Recurso")


def _os_atf(numero: str, situacao: int, fiscais=(), **campos) -> dict:
    """OS no formato da listagem do ATF, so com o que desempenho e alertas leem."""
    return {
        "numero_os": numero,
        "razao_social": f"Empresa {numero}",
        "ie": "123",
        "situacao": {"codigo": situacao, "descricao": ""},
        "fiscais": list(fiscais),
        **campos,
    }


def _fiscal(matricula: str, ciencia="2026-01-02", cancelamento=None, designacao="2026-01-01") -> dict:
    return {
        "matricula": matricula,
        "nome": f"Fiscal {matricula}",
        "data_designacao": designacao,
        "data_ciencia": ciencia,
        "data_cancelamento": cancelamento,
    }


class TestValidarPeriodoAbertura(unittest.TestCase):
    """
    Sem periodo, desempenho e relatorio varreriam a base inteira do ATF:
    o servidor recusa antes de sair do processo.
    """

    def test_exige_inicio_e_fim(self):
        for inicio, fim in ((None, None), ("2026-01-01", None), (None, "2026-01-31")):
            with self.subTest(inicio=inicio, fim=fim):
                with self.assertRaises(ValueError):
                    validar_periodo_abertura(inicio, fim)

    def test_aceita_um_ano_inteiro_mesmo_bissexto(self):
        validar_periodo_abertura("2024-01-01", "2025-01-01")

    def test_recusa_mais_de_um_ano(self):
        with self.assertRaisesRegex(ValueError, "um ano"):
            validar_periodo_abertura("2025-01-01", "2026-01-03")

    def test_recusa_inicio_depois_do_fim(self):
        with self.assertRaisesRegex(ValueError, "depois do fim"):
            validar_periodo_abertura("2026-02-01", "2026-01-01")

    def test_recusa_data_mal_formada(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            validar_periodo_abertura("01/01/2026", "2026-01-31")


class TestGerarAlertas(unittest.TestCase):
    """Alertas sobre a listagem do ATF: OS parada e fiscal sem ciencia."""

    HOJE = date(2026, 9, 25)

    def _tipos(self, *ordens):
        return [a["tipo"] for a in gerar_alertas(list(ordens), self.HOJE)]

    def test_autorizada_sem_evento_ha_mais_de_15_dias_vira_parada(self):
        alertas = gerar_alertas(
            [_os_atf("OS-1", 1, [_fiscal("1")], data_ultimo_evento="2026-09-01")], self.HOJE,
        )
        self.assertEqual([a["tipo"] for a in alertas], ["os_parada"])
        self.assertIn("24 dias", alertas[0]["titulo"])
        self.assertEqual(alertas[0]["data"], "2026-09-01")
        self.assertIn("01/09/2026", alertas[0]["descricao"])

    def test_evento_recente_nao_alerta(self):
        self.assertEqual(
            self._tipos(_os_atf("OS-1", 1, [_fiscal("1")], data_ultimo_evento="2026-09-20")), [],
        )

    def test_sem_evento_conta_do_inicio_da_fiscalizacao(self):
        alertas = gerar_alertas(
            [_os_atf("OS-1", 1, [_fiscal("1")], data_inicio_fiscalizacao="2026-08-01")], self.HOJE,
        )
        self.assertEqual([a["tipo"] for a in alertas], ["os_parada"])
        self.assertIn("inicio da fiscalizacao", alertas[0]["descricao"])

    def test_so_a_autorizada_vira_parada(self):
        """Suspensa, em analise e aguardando autorizacao nao esperam evento."""
        for situacao in (0, 6, 7):
            with self.subTest(situacao=situacao):
                self.assertEqual(
                    self._tipos(_os_atf("OS-1", situacao, [_fiscal("1")], data_ultimo_evento="2026-01-01")),
                    [],
                )

    def test_fiscal_sem_ciencia_vira_alerta_medio(self):
        alertas = gerar_alertas(
            [_os_atf("OS-1", 1, [_fiscal("1", ciencia=None)], data_ultimo_evento="2026-09-20")],
            self.HOJE,
        )
        self.assertEqual([(a["tipo"], a["severidade"]) for a in alertas], [("os_sem_ciencia", "media")])
        self.assertIn("Fiscal 1", alertas[0]["descricao"])

    def test_bloqueada_sem_ciencia_e_alta_e_aponta_o_supervisor(self):
        alertas = gerar_alertas([_os_atf("OS-1", 5, [_fiscal("1", ciencia=None)])], self.HOJE)
        self.assertEqual([(a["tipo"], a["severidade"]) for a in alertas], [("os_sem_ciencia", "alta")])
        self.assertIn("bloqueada", alertas[0]["titulo"])
        self.assertIn("supervisor", alertas[0]["descricao"])

    def test_designacao_cancelada_nao_deve_ciencia(self):
        self.assertEqual(
            self._tipos(_os_atf(
                "OS-1", 7, [_fiscal("1", ciencia=None, cancelamento="2026-01-05")],
            )),
            [],
        )

    def test_encerrada_e_cancelada_nao_alertam(self):
        for situacao in (2, 3, 4):
            with self.subTest(situacao=situacao):
                self.assertEqual(
                    self._tipos(_os_atf("OS-1", situacao, [_fiscal("1", ciencia=None)])), [],
                )

    def test_ordena_por_severidade_e_depois_pelo_mais_antigo(self):
        alertas = gerar_alertas([
            _os_atf("MEDIA", 1, [_fiscal("1", ciencia=None, designacao="2026-01-01")],
                    data_ultimo_evento="2026-09-24"),
            _os_atf("PARADA-NOVA", 1, [_fiscal("2")], data_ultimo_evento="2026-09-01"),
            _os_atf("PARADA-VELHA", 1, [_fiscal("3")], data_ultimo_evento="2026-05-01"),
        ], self.HOJE)
        self.assertEqual(
            [a["referencia"] for a in alertas], ["PARADA-VELHA", "PARADA-NOVA", "MEDIA"],
        )


class TestGerarDashboardDesempenho(unittest.TestCase):
    """
    Abas Visao Geral, Gerencias, Supervisoes (equipes) e Fiscais sobre a
    listagem do ATF.
    """

    def setUp(self):
        self.gerencias = [
            {"id": 1, "nome": "GOFE"}, {"id": 2, "nome": "GOAC"}, {"id": 3, "nome": "GECOF"},
        ]
        self.gerencia_por_matricula = {
            "10": {"id": 1, "nome": "GOFE"}, "20": {"id": 2, "nome": "GOAC"},
        }
        self.equipes = [
            {"codigo": 545, "nome": "GOFE/GR2 - ESTABELECIMENTOS", "gerencia_id": 1,
             "gerencia_nome": "GOFE", "supervisores": ["Chefe"], "matriculas": ["10", "11"]},
            {"codigo": 412, "nome": "GOAC - GRUPO", "gerencia_id": 2,
             "gerencia_nome": "GOAC", "supervisores": [], "matriculas": ["20"]},
        ]
        self.ordens = [
            _os_atf("A", 4, [_fiscal("10")], data_abertura="2026-01-10"),
            _os_atf("B", 1, [_fiscal("10", ciencia=None)], data_abertura="2026-01-15"),
            _os_atf("C", 5, [_fiscal("20", ciencia=None)], data_abertura="2026-02-01"),
            _os_atf("D", 2, [_fiscal("20")], data_abertura="2026-02-05"),
            _os_atf("E", 1, [_fiscal("99")], data_abertura="2026-02-10"),
            _os_atf("F", 1, [_fiscal("10"), _fiscal("20")], data_abertura="2026-02-11"),
        ]

    def _gerar(self, ordens=None):
        return gerar_dashboard_desempenho(
            self.ordens if ordens is None else ordens,
            self.gerencias, self.gerencia_por_matricula, self.equipes,
        )

    def test_visao_geral_pelos_grupos_de_situacao(self):
        v = self._gerar()["visao_geral"]
        self.assertEqual(
            (v["total_os"], v["em_andamento"], v["bloqueadas"], v["encerradas"], v["canceladas"]),
            (6, 3, 1, 1, 1),
        )
        self.assertEqual(v["os_sem_ciencia"], 2)
        # Cancelada sai do denominador: 1 encerrada em 5 validas.
        self.assertEqual(v["taxa_encerramento"], 20.0)

    def test_os_que_nenhum_cadastro_alcanca_sao_contadas(self):
        v = self._gerar()["visao_geral"]
        self.assertEqual((v["os_sem_gerencia"], v["os_sem_equipe"]), (1, 1))

    def test_gerencias_do_cadastro_inteiro_e_sem_os_no_fim(self):
        linhas = {g["nome"]: g for g in self._gerar()["desempenho_gerencias"]}
        self.assertEqual(set(linhas), {"GOFE", "GOAC", "GECOF"})
        # A OS F tem fiscais das duas gerencias e conta nas duas.
        self.assertEqual(linhas["GOFE"]["total_os"], 3)
        self.assertEqual(linhas["GOAC"]["total_os"], 3)
        self.assertEqual(self._gerar()["desempenho_gerencias"][-1]["nome"], "GECOF")

    def test_termometro_ignora_gerencia_sem_os(self):
        ranking = self._gerar()["ranking_criticidade"]
        self.assertEqual({r["nome"] for r in ranking}, {"GOFE", "GOAC"})
        self.assertEqual(ranking, sorted(ranking, key=lambda r: r["indice_saude"]))

    def test_equipe_conta_pelas_matriculas_dos_membros(self):
        linhas = {e["id"]: e for e in self._gerar()["desempenho_equipes"]}
        self.assertEqual(linhas[545]["total_os"], 3)
        self.assertEqual(linhas[545]["supervisores"], ["Chefe"])
        self.assertEqual(linhas[545]["gerencia_nome"], "GOFE")
        self.assertEqual(linhas[412]["total_os"], 3)

    def test_carga_conta_so_os_ativa_e_designacao_valida(self):
        ordens = self.ordens + [
            _os_atf("G", 1, [_fiscal("11", cancelamento="2026-02-20"), _fiscal("10")],
                    data_abertura="2026-02-12"),
        ]
        carga = {f["matricula"]: f for f in self._gerar(ordens)["carga_fiscais"]}
        # 10: B, F e G (A esta encerrada); 20: C (bloqueada) e F.
        self.assertEqual(carga["10"]["os_ativas"], 3)
        self.assertEqual(carga["20"]["os_ativas"], 2)
        self.assertNotIn("11", carga)
        self.assertEqual(carga["10"]["gerencia_id"], 1)
        self.assertEqual(carga["10"]["equipes"], [545])

    def test_por_situacao_fecha_com_o_total_e_usa_o_nome_do_servico(self):
        ordens = [_os_atf("X", 6, [], data_abertura="2026-01-01")]
        ordens[0]["situacao"]["descricao"] = "EM ANALISE DE ENCERRAMENTO"
        linhas = self._gerar(self.ordens + ordens)["por_situacao"]
        self.assertEqual(sum(l["total"] for l in linhas), 7)
        self.assertIn("EM ANALISE DE ENCERRAMENTO", [l["descricao"] for l in linhas])

    def test_evolucao_mensal_por_safra_de_abertura(self):
        self.assertEqual(self._gerar()["evolucao_mensal"], [
            {"mes": "2026-01", "abertas": 2, "encerradas": 1},
            {"mes": "2026-02", "abertas": 4, "encerradas": 0},
        ])

    def test_comparativo_entre_os_dois_ultimos_meses(self):
        comp = self._gerar()["comparativo_mensal"]
        self.assertEqual(comp["total_os"], {"atual": 4, "anterior": 2, "delta": 2})
        self.assertEqual(comp["_labels"], {"mes_atual": "2026-02", "mes_anterior": "2026-01"})

    def test_sem_os_nao_quebra(self):
        dados = self._gerar([])
        self.assertEqual(dados["visao_geral"]["total_os"], 0)
        self.assertEqual(dados["visao_geral"]["taxa_encerramento"], 0)
        self.assertEqual(dados["comparativo_mensal"], {})
        self.assertEqual(dados["ranking_criticidade"], [])


class TestGerarDashboardOS(unittest.TestCase):
    """
    Cortes de quantidade de OS sobre a listagem do ATF (demanda de
    31/08/2026). O que se testa aqui e o que o resto do painel nao
    consegue conferir sozinho: quem conta em qual grupo, e sobre que
    denominador sai o tempo medio.
    """

    def _os(self, numero, **campos):
        base = {
            "numero_os": numero,
            "modelo": "NORMAL",
            "modelo_codigo": 1,
            "motivo_abertura": "MONITORAMENTO",
            "motivo_abertura_codigo": 179,
            "orgao_executor": "GERENCIA REGIONAL 2",
            "orgao_executor_sigla": "GR2",
            "orgao_executor_codigo": 4,
            "data_abertura": "2026-01-10",
            "data_encerramento": None,
            "dias_execucao": None,
            "fiscais": [],
        }
        base.update(campos)
        return base

    def test_tempo_medio_ignora_os_em_execucao(self):
        """
        Numa OS aberta dias_execucao conta ate hoje e cresce sozinho: se
        entrasse na media, o numero mudaria de um dia para o outro sem
        nada ter acontecido.
        """
        ordens = [
            self._os("A", data_encerramento="2026-02-10", dias_execucao=30),
            self._os("B", data_encerramento="2026-02-20", dias_execucao=40),
            self._os("C", dias_execucao=900),  # em execucao: fora da media
        ]
        visao = gerar_dashboard_os(ordens)["visao_geral"]

        self.assertEqual(visao["total_os"], 3)
        self.assertEqual(visao["encerradas"], 2)
        self.assertEqual(visao["em_execucao"], 1)
        self.assertEqual(visao["tempo_medio"], 35.0)

    def test_tempo_medio_none_quando_nada_encerrou(self):
        """Sem encerrada no grupo nao ha media — e 0 seria mentira."""
        linhas = gerar_dashboard_os([self._os("A", dias_execucao=10)])["por_tipo"]
        self.assertIsNone(linhas[0]["tempo_medio"])
        self.assertEqual(linhas[0]["total"], 1)

    def test_os_conta_para_cada_fiscal_designado(self):
        """
        O corte por fiscal soma mais que o total de OS de proposito: a
        mesma OS aparece para os dois fiscais designados.
        """
        ordens = [self._os("A", fiscais=[
            {"matricula": "111", "nome": "ANA"},
            {"matricula": "222", "nome": "BRUNO"},
        ])]
        resultado = gerar_dashboard_os(ordens)

        self.assertEqual(resultado["visao_geral"]["total_os"], 1)
        self.assertEqual(sum(l["total"] for l in resultado["por_fiscal"]), 2)
        self.assertEqual(resultado["visao_geral"]["total_fiscais"], 2)

    def test_fiscal_repetido_na_mesma_os_conta_uma_vez(self):
        """
        O ATF repete o fiscal na lista quando ele e designado, cancelado
        e designado de novo — sem deduplicar, a OS contaria duas vezes
        para a mesma pessoa.
        """
        ordens = [self._os("A", fiscais=[
            {"matricula": "111", "nome": "ANA"},
            {"matricula": "111", "nome": "ANA"},
        ])]
        por_fiscal = gerar_dashboard_os(ordens)["por_fiscal"]

        self.assertEqual(len(por_fiscal), 1)
        self.assertEqual(por_fiscal[0]["total"], 1)

    def test_gerencia_sai_das_matriculas_dos_fiscais(self):
        """
        A gerencia nao existe no ATF: a unica ponte ate a OS sao as
        matriculas. Uma OS com fiscais de gerencias diferentes conta nas
        duas; a que nao alcanca nenhuma cai no grupo "sem gerencia".
        """
        mapa = {
            "111": {"id": 1, "nome": "GEFIS"},
            "222": {"id": 2, "nome": "GEAUD"},
        }
        ordens = [
            self._os("A", fiscais=[
                {"matricula": "111", "nome": "ANA"},
                {"matricula": "222", "nome": "BRUNO"},
            ]),
            self._os("B", fiscais=[{"matricula": "999", "nome": "SEM LOTACAO"}]),
        ]
        resultado = gerar_dashboard_os(ordens, mapa)
        por_gerencia = {l["rotulo"]: l["total"] for l in resultado["por_gerencia"]}

        self.assertEqual(por_gerencia["GEFIS"], 1)
        self.assertEqual(por_gerencia["GEAUD"], 1)
        self.assertEqual(por_gerencia["Sem gerencia cadastrada"], 1)
        self.assertEqual(resultado["visao_geral"]["os_sem_gerencia"], 1)
        self.assertEqual(resultado["visao_geral"]["total_gerencias"], 2)

    def test_dois_fiscais_da_mesma_gerencia_contam_uma_vez(self):
        """A OS entra uma vez por gerencia, nao uma vez por fiscal dela."""
        mapa = {
            "111": {"id": 1, "nome": "GEFIS"},
            "222": {"id": 1, "nome": "GEFIS"},
        }
        ordens = [self._os("A", fiscais=[
            {"matricula": "111", "nome": "ANA"},
            {"matricula": "222", "nome": "BRUNO"},
        ])]
        por_gerencia = gerar_dashboard_os(ordens, mapa)["por_gerencia"]

        self.assertEqual(len(por_gerencia), 1)
        self.assertEqual(por_gerencia[0]["total"], 1)

    def test_sem_mapa_tudo_cai_em_sem_gerencia(self):
        """
        Estado de hoje: ninguem tem lotacao. O corte diz isso em vez de
        sumir com as OS.
        """
        resultado = gerar_dashboard_os(
            [self._os("A", fiscais=[{"matricula": "111", "nome": "ANA"}])],
        )
        self.assertEqual(resultado["por_gerencia"][0]["rotulo"], "Sem gerencia cadastrada")
        self.assertEqual(resultado["visao_geral"]["os_sem_gerencia"], 1)
        self.assertEqual(resultado["visao_geral"]["total_gerencias"], 0)

    def test_orgao_executor_rotula_pela_sigla(self):
        """A area fiscal conhece o orgao pela sigla, nao pelo nome extenso."""
        por_orgao = gerar_dashboard_os([self._os("A")])["por_orgao_executor"]
        self.assertEqual(por_orgao[0]["rotulo"], "GR2")
        self.assertEqual(por_orgao[0]["id"], 4)

    def test_campos_em_branco_viram_grupo_proprio(self):
        """
        Orgao, motivo e modelo em branco nao podem sumir da contagem: o
        total do corte tem que fechar com o total de OS.
        """
        ordens = [self._os(
            "A",
            orgao_executor="", orgao_executor_sigla="", orgao_executor_codigo=None,
            motivo_abertura="", motivo_abertura_codigo=None,
            modelo="", modelo_codigo=None,
        )]
        resultado = gerar_dashboard_os(ordens)

        self.assertEqual(resultado["por_orgao_executor"][0]["rotulo"], "Sem orgao executor")
        self.assertEqual(resultado["por_motivo"][0]["rotulo"], "Sem motivo informado")
        self.assertEqual(resultado["por_tipo"][0]["rotulo"], "Sem modelo informado")
        self.assertEqual(resultado["visao_geral"]["total_orgaos"], 0)

    def test_os_sem_fiscal_designado(self):
        por_fiscal = gerar_dashboard_os([self._os("A")])["por_fiscal"]
        self.assertEqual(por_fiscal[0]["rotulo"], "Sem fiscal designado")
        self.assertTrue(por_fiscal[0]["vazio"])

    def test_grupo_vazio_e_marcado_pelo_rotulo_e_nao_pelo_id(self):
        """
        Um orgao pode vir do ATF com nome e sem cdOrgaoExec — o id fica
        None num grupo que existe de verdade. Contar "orgaos distintos"
        por id nulo sumia com ele; a marca e o rotulo.
        """
        ordens = [self._os(
            "A", orgao_executor="GEFIS - 1a REGIONAL",
            orgao_executor_sigla="", orgao_executor_codigo=None,
        )]
        resultado = gerar_dashboard_os(ordens)
        linha = resultado["por_orgao_executor"][0]

        self.assertEqual(linha["rotulo"], "GEFIS - 1a REGIONAL")
        self.assertIsNone(linha["id"])
        self.assertFalse(linha["vazio"])
        self.assertEqual(resultado["visao_geral"]["total_orgaos"], 1)

    def test_serie_mensal_em_ordem_cronologica(self):
        """
        Mes e o unico corte que nao se ordena pela quantidade: uma serie
        temporal fora de ordem nao e um grafico, e um borrao.
        """
        ordens = [
            self._os("A", data_abertura="2026-03-01"),
            self._os("B", data_abertura="2026-01-05"),
            self._os("C", data_abertura="2026-01-20"),
            self._os("D", data_abertura=""),
        ]
        por_mes = gerar_dashboard_os(ordens)["por_mes"]

        self.assertEqual([l["id"] for l in por_mes], ["2026-01", "2026-03", None])
        self.assertEqual([l["rotulo"] for l in por_mes[:2]], ["01/2026", "03/2026"])
        self.assertEqual(por_mes[0]["total"], 2)
        self.assertEqual(por_mes[-1]["rotulo"], "Sem data de abertura")

    def test_cortes_ordenados_do_maior_para_o_menor(self):
        ordens = [
            self._os("A", motivo_abertura="MALHA FISCAL", motivo_abertura_codigo=195),
            self._os("B", motivo_abertura="MONITORAMENTO", motivo_abertura_codigo=179),
            self._os("C", motivo_abertura="MONITORAMENTO", motivo_abertura_codigo=179),
        ]
        por_motivo = gerar_dashboard_os(ordens)["por_motivo"]
        self.assertEqual([l["rotulo"] for l in por_motivo], ["MONITORAMENTO", "MALHA FISCAL"])

    def test_universo_vazio_nao_quebra(self):
        resultado = gerar_dashboard_os([])
        self.assertEqual(resultado["visao_geral"]["total_os"], 0)
        self.assertIsNone(resultado["visao_geral"]["tempo_medio"])
        self.assertEqual(resultado["por_motivo"], [])
        self.assertEqual(resultado["por_mes"], [])



class TestSingleFlightEBuscaEmCache(unittest.TestCase):
    """
    Chamadas simultaneas com os mesmos parametros vao UMA vez ao ATF, e a
    OS que acabou de ser listada e encontrada pelo numero sem nova ida.
    """

    def setUp(self):
        limpar_cache_atf()
        self.addCleanup(limpar_cache_atf)

    def test_chamadas_simultaneas_iguais_vao_uma_vez_ao_atf(self):
        import threading
        import time

        from backend.external_api import _chamar_atf_https, buscar_os_em_cache

        xml = _resposta_soap({"OS-1": "111"})
        chamadas: list[int] = []

        def post_lento(*args, **kwargs):
            chamadas.append(1)
            time.sleep(0.3)
            resp = MagicMock()
            resp.text = xml
            resp.raise_for_status = MagicMock()
            return resp

        resultados: list = []
        with patch("requests.post", side_effect=post_lento):
            threads = [
                threading.Thread(
                    target=lambda: resultados.append(
                        _chamar_atf_https("https://atf.teste", numero_os="OS-1")
                    )
                )
                for _ in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(chamadas), 1, "cinco threads, uma ida ao ATF")
        self.assertEqual(len(resultados), 5)
        self.assertTrue(all(r[0]["numero_os"] == "OS-1" for r in resultados))

        # A OS listada e localizavel pelo numero sem nova chamada
        with patch("requests.post") as post:
            self.assertEqual(buscar_os_em_cache("OS-1")["numero_os"], "OS-1")
            self.assertIsNone(buscar_os_em_cache("OS-9"))
            post.assert_not_called()

    def test_falha_nao_fica_presa_na_trava(self):
        """Se a primeira chamada falhar, a seguinte tenta de novo (e nao espera para sempre)."""
        from backend.external_api import _chamar_atf_https

        ok = MagicMock()
        ok.text = _resposta_soap({"OS-2": "222"})
        ok.raise_for_status = MagicMock()
        with patch("requests.post", side_effect=[ConnectionError("caiu"), ok]) as post:
            with self.assertRaises(ConnectionError):
                _chamar_atf_https("https://atf.teste", numero_os="OS-2")
            self.assertEqual(_chamar_atf_https("https://atf.teste", numero_os="OS-2")[0]["numero_os"], "OS-2")
            self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
