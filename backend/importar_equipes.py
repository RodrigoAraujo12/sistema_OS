"""
importar_equipes.py – Carrega as equipes fiscais do ATF a partir da
planilha que a SEFAZ envia (aba "Grupos de Auditores").

Uso:
    python -m backend.importar_equipes CAMINHO/DADOS_ORDEM_SERVICO.xlsx
    python -m backend.importar_equipes ... --dry-run   # so relata

A planilha NAO deve ser versionada: ela tem nome e matricula de
servidores reais. Guarde-a fora do repositorio (ver NOTAS-INTERNAS.md).

Le .xlsx com a biblioteca padrao — um .xlsx e um zip de XML, e a carga
e rara o bastante para nao justificar openpyxl so por isso.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .db import DB_PATH, Database, EquipeFiscalRepository

logger = logging.getLogger("sefaz.importar_equipes")

ABA_GRUPOS = "Grupos de Auditores"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _ler_aba(caminho: Path, nome_aba: str) -> list[dict[str, str]]:
    """
    Devolve as linhas da aba como {coluna: valor}, ex. {"A": "604.0"}.

    Celulas vazias simplesmente nao aparecem no dicionario da linha — e
    assim que o proprio formato as representa.
    """
    with zipfile.ZipFile(caminho) as z:
        compartilhadas: list[str] = []
        try:
            raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
            compartilhadas = [
                "".join(t.text or "" for t in si.iter(_NS + "t"))
                for si in raiz.findall(_NS + "si")
            ]
        except KeyError:
            pass  # planilha sem strings compartilhadas: tudo inline

        alvos = {
            rel.get("Id"): rel.get("Target").lstrip("/")
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        }
        abas = ET.fromstring(z.read("xl/workbook.xml")).find(_NS + "sheets")
        destino = next(
            (alvos[a.get(_NS_REL + "id")] for a in abas if a.get("name") == nome_aba),
            None,
        )
        if destino is None:
            disponiveis = [a.get("name") for a in abas]
            raise ValueError(
                f"Aba {nome_aba!r} nao encontrada. Abas na planilha: {disponiveis}"
            )
        if not destino.startswith("xl/"):
            destino = "xl/" + destino

        dados = ET.fromstring(z.read(destino)).find(_NS + "sheetData")

    linhas: list[dict[str, str]] = []
    for linha in dados.findall(_NS + "row") if dados is not None else []:
        celulas: dict[str, str] = {}
        for c in linha.findall(_NS + "c"):
            coluna = re.match(r"[A-Z]+", c.get("r")).group()
            tipo, valor, inline = c.get("t"), c.find(_NS + "v"), c.find(_NS + "is")
            if tipo == "s" and valor is not None:
                celulas[coluna] = compartilhadas[int(valor.text)]
            elif tipo == "inlineStr" and inline is not None:
                celulas[coluna] = "".join(t.text or "" for t in inline.iter(_NS + "t"))
            elif valor is not None:
                celulas[coluna] = valor.text
        if celulas:
            linhas.append(celulas)
    return linhas


def _numero(valor: str | None) -> str | None:
    """
    "604.0" -> "604". O Excel guarda todo codigo como numero, entao
    matricula e codigo de equipe chegam com casa decimal.

    Devolve None para vazio ou para o que nao for inteiro: a matricula
    precisa casar exatamente com a que vem do ATF, e um valor duvidoso e
    melhor descartado (e relatado) do que adivinhado.
    """
    if valor is None:
        return None
    texto = valor.strip()
    if not texto:
        return None
    try:
        numero = float(texto)
    except ValueError:
        return None
    if numero != int(numero):
        return None
    return str(int(numero))


def extrair(
    linhas: list[dict[str, str]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str, str]], list[str]]:
    """
    Transforma as linhas da aba em (equipes, membros, avisos).

    A planilha vem de uma exportacao paginada e carrega tres sujeiras que
    um parser ingenuo importaria como se fossem gente:

    - a linha de cabecalho se repete a cada pagina (dezenas de vezes);
    - a ultima linha e um rodape "Atualizado em: ...", sem codigo;
    - alguns auditores aparecem em mais de uma equipe — esses sao
      legitimos e viram um vinculo em cada equipe.
    """
    equipes: dict[int, str] = {}
    membros: dict[tuple[int, str], str] = {}
    avisos: list[str] = []

    for i, celulas in enumerate(linhas, start=1):
        codigo_bruto = celulas.get("A")
        if codigo_bruto is not None and codigo_bruto.strip() == "Código":
            continue  # cabecalho, repetido a cada pagina da exportacao

        codigo = _numero(codigo_bruto)
        grupo = (celulas.get("B") or "").strip()
        matricula = _numero(celulas.get("C"))
        nome = (celulas.get("D") or "").strip()

        if codigo is None and not matricula:
            if grupo:
                logger.debug("Linha %d ignorada (rodape): %s", i, grupo)
            continue
        if codigo is None or not grupo:
            avisos.append(f"linha {i}: sem codigo ou nome de equipe, ignorada")
            continue
        if not matricula or not nome:
            avisos.append(f"linha {i}: equipe {grupo} sem matricula ou nome, ignorada")
            continue

        codigo_int = int(codigo)
        anterior = equipes.setdefault(codigo_int, grupo)
        if anterior != grupo:
            avisos.append(
                f"equipe {codigo_int} aparece com dois nomes "
                f"({anterior!r} e {grupo!r}); mantido o primeiro"
            )
        membros[(codigo_int, matricula)] = nome

    lista_equipes = sorted(equipes.items())
    lista_membros = sorted((cod, mat, nome) for (cod, mat), nome in membros.items())
    return lista_equipes, lista_membros, avisos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa equipes fiscais do ATF.")
    parser.add_argument("planilha", type=Path, help="caminho do .xlsx da SEFAZ")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que seria importado, sem gravar no banco",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH, help="banco alvo")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.planilha.is_file():
        print(f"Planilha nao encontrada: {args.planilha}", file=sys.stderr)
        return 1

    equipes, membros, avisos = extrair(_ler_aba(args.planilha, ABA_GRUPOS))

    for aviso in avisos:
        print(f"  aviso: {aviso}", file=sys.stderr)
    if not equipes:
        print("Nenhuma equipe encontrada na planilha.", file=sys.stderr)
        return 1

    matriculas = {m for _, m, _ in membros}
    print(f"{len(equipes)} equipes, {len(membros)} vinculos, {len(matriculas)} auditores")
    repetidos = len(membros) - len(matriculas)
    if repetidos:
        print(f"{repetidos} auditor(es) em mais de uma equipe (um vinculo em cada)")

    if args.dry_run:
        for codigo, nome in equipes:
            total = sum(1 for c, _, _ in membros if c == codigo)
            print(f"  {codigo:>6}  {nome:<50} {total:>3}")
        print("\n--dry-run: nada foi gravado.")
        return 0

    database = Database(args.db)
    database.init_schema()
    n_equipes, n_membros = EquipeFiscalRepository(database).substituir_tudo(
        equipes, membros
    )
    print(f"Importado em {args.db}: {n_equipes} equipes, {n_membros} vinculos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
