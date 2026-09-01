"""
Testes unitarios para o modulo external_api.py – logica de OS e dashboard.

Cobre: montagem dos envelopes SOAP (listagem e detalhe), parse do
detalhe da OS, caches das respostas do ATF, filtragem hierarquica,
geracao de alertas e dashboard.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from xml.sax.saxutils import escape

from backend.external_api import (
    _chamar_atf_https,
    _chamar_detalhe_atf_https,
    _float_ou_none,
    _filtrar_por_hierarquia,
    _montar_envelope_detalhe_soap,
    _montar_envelope_soap,
    _montar_parametros_atf,
    _parse_detalhe_soap,
    detalhar_ordem_atf,
    detalhe_em_outro_ambiente,
    filtrar_atf_por_matriculas,
    gerar_alertas,
    gerar_dashboard,
    gerar_dashboard_os,
    limpar_cache_atf,
    listar_ordens_servico,
    mesclar_detalhe_os,
    url_base_detalhe_atf,
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


if __name__ == "__main__":
    unittest.main()
