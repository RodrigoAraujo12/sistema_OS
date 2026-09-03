"""
Diagnostico do servico de EVENTOS de OS (doc dos eventos), isolado do resto.

Testa UMA coisa so: se o `listarEventosOrdemServico` responde e o que ele
devolve. Nao toca no banco, nao sobe o backend, nao depende de login.

Existe porque o servico chegou depois dos outros dois e, em 02/09/2026,
so estava publicado em desenvolvimento. Como esse ambiente e a MESMA base de
producao com o contribuinte mascarado (conferido campo a campo: datas,
modelo, motivo, orgao, procedimento, dias e ate as matriculas dos fiscais
batem), testar la vale como previa do que producao vai devolver.

    python -m backend.verificar_eventos                    # usa o .env
    python -m backend.verificar_eventos --url https://...  # ambiente especifico
    python -m backend.verificar_eventos --dias 30

E o mesmo comando a rodar no dia em que a SEFAZ implantar em producao:
apontando para la, ele diz em segundos se ja da para apagar o
ATF_EVENTOS_BASE_URL do .env.

Sai com 0 quando o servico responde, 1 quando nao.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from . import config
from .external_api import (
    _chamar_eventos_atf_https,
    gerar_dashboard_eventos,
    url_base_eventos_atf,
)

# A operacao, como o WSDL a declara. Procurada no ?wsdl antes de chamar:
# ausente ela, a resposta e um SOAP Fault generico que nao diz o porque.
_OPERACAO = "listarEventosOrdemServico"


def _wsdl_declara_a_operacao(url: str) -> bool | None:
    """
    Diz se o `?wsdl` do ambiente publica a operacao. None quando o WSDL
    nao pode ser lido — que ja e resposta suficiente para parar aqui.
    """
    import requests

    try:
        resp = requests.get(
            f"{url.rstrip('/')}?wsdl", timeout=30, verify=config.ATF_SSL_VERIFY,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  ! nao consegui ler o ?wsdl: {type(e).__name__}: {e}")
        return None
    return _OPERACAO in resp.text


def _pct(parte: int, total: int) -> str:
    return f"{parte}/{total} ({100 * parte // total if total else 0}%)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", default=None,
        help="URL do servico. Padrao: ATF_EVENTOS_BASE_URL ou ATF_BASE_URL do .env",
    )
    parser.add_argument(
        "--dias", type=int, default=15,
        help="Tamanho da janela de inclusao de evento, contada de hoje (padrao: 15)",
    )
    args = parser.parse_args(argv)

    url = args.url or url_base_eventos_atf()
    if not url:
        print("Nenhuma URL configurada (ATF_EVENTOS_BASE_URL / ATF_BASE_URL vazias).")
        print("O sistema roda em MOCK; nao ha servico para diagnosticar.")
        return 1

    fim = date.today()
    inicio = fim - timedelta(days=args.dias)

    print(f"Servico  : {_OPERACAO}")
    print(f"URL      : {url}")
    print(f"TLS      : verificacao {'LIGADA' if config.ATF_SSL_VERIFY else 'DESLIGADA'}")
    print(f"Periodo  : inclusao de evento entre {inicio} e {fim}")
    print()

    declara = _wsdl_declara_a_operacao(url)
    if declara is True:
        print(f"  OK   o ?wsdl declara {_OPERACAO}")
    elif declara is False:
        print(f"  FALHA o ?wsdl NAO declara {_OPERACAO} — o servico nao esta")
        print("        implantado neste ambiente. A chamada abaixo vai voltar")
        print('        "Message part [...] was not recognized".')
    print()

    try:
        eventos = _chamar_eventos_atf_https(
            url,
            data_inclusao_ini=inicio.isoformat(),
            data_inclusao_fim=fim.isoformat(),
        )
    except Exception as e:
        print(f"  FALHA {type(e).__name__}: {e}")
        print()
        print("Leitura rapida:")
        print("  - 'was not recognized'  -> operacao nao implantada neste ambiente")
        print("  - SSLError              -> cadeia TLS incompleta; use REQUESTS_CA_BUNDLE")
        print("  - 503 / ConnectionError -> ambiente fora do ar (costuma voltar sozinho)")
        return 1

    if not eventos:
        print("  OK   o servico respondeu, mas sem nenhum evento no periodo.")
        print("       Amplie a janela com --dias antes de concluir qualquer coisa.")
        return 0

    total = len(eventos)
    com_gerencia = sum(1 for e in eventos if e["gerencia_codigo"] or e["gerencia_sigla"])
    com_equipe = sum(1 for e in eventos if e["equipe_fiscal_codigo"] or e["equipe_fiscal"])
    com_datas = sum(1 for e in eventos if e["data_inicial"] and e["data_final"])

    dashboard = gerar_dashboard_eventos(eventos)
    visao = dashboard["visao_geral"]

    print(f"  OK   {total} eventos em {visao['total_os']} OS "
          f"({visao['media_por_os']} por OS)")
    print()
    print("Preenchimento dos campos que o painel corta:")
    print(f"  gerencia         {_pct(com_gerencia, total)}")
    print(f"  equipe fiscal    {_pct(com_equipe, total)}")
    print(f"  inicio e fim     {_pct(com_datas, total)}")
    print()

    # As datas do evento sao a divergencia conhecida entre a doc e o
    # servico (doc: dataInicialEventoOS/dataFinalEventoOS; servico:
    # dataInicioEventoOS/dataFimEventoOS). Zero aqui e o sintoma de o
    # parser ter perdido o nome — o unico erro desta integracao que nao
    # levanta excecao nenhuma.
    if com_datas == 0:
        print("  ATENCAO: nenhum evento trouxe inicio E fim. Se o servico mudou")
        print("  os nomes das tags de data, o parser precisa ser conferido —")
        print("  ver _parse_resposta_eventos_soap em external_api.py.")
        print()

    print("Maiores cortes:")
    for corte, titulo in (("por_gerencia", "gerencia"), ("por_procedimento", "procedimento")):
        linhas = dashboard[corte][:3]
        resumo = ", ".join(f"{l['rotulo']} ({l['total']})" for l in linhas)
        print(f"  {titulo:14s} {resumo}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
