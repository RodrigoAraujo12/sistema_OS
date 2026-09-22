"""
A gerencia de cada equipe fiscal, deduzida do nome da equipe.

O ATF nao manda gerencia na listagem de OS: a unica ponte ate a OS sao as
matriculas em `fiscais[]`. Ate 22/09/2026 a ponte seguinte — matricula ate
gerencia — dependia de o admin lotar pessoa por pessoa, e como os 334
auditores foram importados sem lotacao, o corte por gerencia do painel
saia inteiro em "sem gerencia cadastrada".

Este modulo fecha a ponte por outro caminho: **o nome da equipe ja diz a
gerencia dela**. A regra foi confirmada pelo Rodrigo em 22/09/2026, com a
area fiscal:

- **`A - B` → o `B` e o nivel ACIMA do `A`.** A gerencia e sempre o lado
  ESQUERDO: `GOAC - GEFTE` e equipe da GOAC, que responde a GEFTE (o topo
  da hierarquia). Quando o lado direito e um assunto e nao uma unidade
  (`GOFE - VAREJO`, `GOAC - MALHAS`), e subdivisao interna — a gerencia
  continua sendo a esquerda, entao a mesma leitura serve para os dois.
- **Barra e outra coisa: em `GOFE/GR2` a gerencia e a GOFE**, nao a GR2 —
  a regional e so onde a equipe atua.

As siglas e codigos abaixo sao os da aba "Elementos Organizacionais" da
planilha da SEFAZ, e nao invencao nossa. Usar o codigo do elemento como
identidade da gerencia e o que deixa a aba de OS falar o mesmo vocabulario
da aba de Eventos, onde a gerencia vem pronta do ATF em `cdGerencia` —
indicio forte de que sao a mesma coisa: `cdGerencia 275` volta com
`sgGerencia GOFSE`, e 275 e o codigo do elemento GOFSE. A SEFAZ ainda
precisa confirmar isso por escrito (pergunta em aberto com o Pedro).

CUIDADO: o codigo da EQUIPE e outro espaco de numeracao. A equipe 412 e
`GOAC - GRUPO REVISAO DE FATURAS`; o elemento 412 e `GAECO`.
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger(__name__)

# (codigo do elemento organizacional, sigla, nome por extenso).
#
# Sao so as 10 gerencias que aparecem como dona de alguma equipe fiscal.
# A aba tem 595 elementos; o resto nao executa OS e nao tem por que virar
# cadastro. GR2, GR4 e GR5 ficam de fora de proposito: elas aparecem em
# `GOFE/GR2`, `GOFE/GR4` e `GOFE/GR5`, onde a gerencia e a GOFE.
GERENCIAS: tuple[tuple[int, str, str], ...] = (
    (3, "GR1", "Gerencia Regional da 1a Regiao"),
    (5, "GR3", "Gerencia Regional da 3a Regiao"),
    (254, "GOFE-GEFTE", "Ger. Operacional de Fiscalizacao de Estabelecimentos"),
    (275, "GOFSE", "Ger. Operacional de Fiscalizacao de Segmentos Especiais"),
    (339, "GOFMT", "Ger. Operacional de Fiscalizacao de Mercadorias em Transito"),
    (415, "GEFTE", "Ger. Executiva de Fiscalizacao de Tributos Estaduais"),
    (512, "GOFITCD/IPVA", "Ger. Operacional de Fiscalizacao de ITCD e IPVA"),
    (513, "GOAC", "Ger. Operacional de Acompanhamento de Contribuintes"),
    (575, "GOP-GEFTE", "Ger. Operacional de Planejamento da GEFTE"),
    (629, "GECOF", "Ger. Executiva de Combate a Fraude Fiscal"),
)

SIGLA_POR_CODIGO: dict[int, str] = {cod: sigla for cod, sigla, _ in GERENCIAS}

# Como o nome da equipe escreve a gerencia -> codigo do elemento.
#
# Nem sempre bate com a sigla oficial, e por isso este mapa existe em vez
# de um `==`: a planilha de equipes escreve "GOFSES" onde o elemento e
# "GOFSE", e escreve "GOFE"/"GOP" onde o elemento traz o sufixo da casa
# acima ("GOFE-GEFTE", "GOP-GEFTE").
_POR_PREFIXO: dict[str, int] = {
    "GR1": 3,
    "GR3": 5,
    "GOFE": 254,
    "GOFE-GEFTE": 254,
    "GOFSE": 275,
    "GOFSES": 275,
    "GOFMT": 339,
    "GEFTE": 415,
    "GOFITCD/IPVA": 512,
    "GOAC": 513,
    "GOP": 575,
    "GOP-GEFTE": 575,
    "GECOF": 629,
}

# A equipe 610 nao usa sigla nenhuma: e a GOFE escrita por extenso.
# Confirmado pelo Rodrigo em 22/09/2026.
_POR_NOME_INTEIRO: dict[str, int] = {
    "GERENCIA OPERACIONAL DE FISCALIZACAO DE ESTABELECIMENTOS": 254,
}

# Equipes que a area fiscal decidiu manter FORA do painel de OS
# (Rodrigo, 22/09/2026). Sao as duas unicas sem elemento organizacional
# correspondente — nao existe sigla "GEST" na aba — e nenhuma das duas
# tem OS no periodo medido. Ficam sem gerencia de proposito: nao sao
# lacuna a preencher depois.
EQUIPES_FORA_DO_PAINEL: frozenset[int] = frozenset({613, 614})


def _sem_acento(texto: str) -> str:
    return (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode()
        .upper()
        .strip()
    )


def gerencia_de_equipe(nome: str) -> int | None:
    """
    Codigo do elemento organizacional da gerencia dona da equipe.

    Devolve None quando o nome nao permite decidir — e ai o chamador
    trata como equipe sem gerencia, em vez de chutar uma.

    A ordem das tentativas importa e segue a regra: primeiro o nome
    inteiro (a equipe 610), depois o lado esquerdo do traco, e so entao
    os recortes desse lado — antes da barra (`GOFE/GR2` -> `GOFE`) e a
    primeira palavra (`GOFSES ST` -> `GOFSES`). Tentar a barra ANTES do
    nome cheio quebraria `GOFITCD/IPVA`, cuja sigla tem barra no meio.
    """
    n = _sem_acento(nome)
    if not n:
        return None
    if n in _POR_NOME_INTEIRO:
        return _POR_NOME_INTEIRO[n]

    cabeca = n.split(" - ")[0].strip()
    for candidato in (
        cabeca,
        cabeca.split("/")[0].strip(),
        cabeca.split()[0].strip() if cabeca.split() else "",
    ):
        if candidato in _POR_PREFIXO:
            return _POR_PREFIXO[candidato]
    return None


def gerencias_das_equipes(
    equipes: list[tuple[int, str]],
) -> tuple[dict[int, int], list[str]]:
    """
    Aplica a regra a uma lista de (codigo_equipe, nome) inteira.

    Devolve o mapa codigo_equipe -> codigo da gerencia e os avisos das
    que ficaram sem. As de `EQUIPES_FORA_DO_PAINEL` saem em silencio: a
    ausencia ali e decisao, nao falha de leitura.
    """
    mapa: dict[int, int] = {}
    avisos: list[str] = []
    for codigo, nome in equipes:
        if codigo in EQUIPES_FORA_DO_PAINEL:
            continue
        gerencia = gerencia_de_equipe(nome)
        if gerencia is None:
            avisos.append(
                f"equipe {codigo} ({nome!r}): nao consegui deduzir a gerencia pelo nome; "
                f"ela fica fora do corte por gerencia do painel"
            )
            continue
        mapa[codigo] = gerencia
    return mapa, avisos
