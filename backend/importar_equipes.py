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

CUIDADO com a chefia: a planilha de 02/09/2026 passou a marcar quem
supervisiona cada grupo pintando a celula de amarelo, sem coluna nova.
Isso e formatacao, nao dado — uma reexportacao ou um "limpar formatacao"
apaga tudo sem deixar rastro. Por isso o importador avisa quando nao
encontra marca nenhuma, em vez de gravar zero chefias em silencio.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .db import DB_PATH, Database, EquipeFiscalRepository, UserRepository

logger = logging.getLogger("sefaz.importar_equipes")

ABA_GRUPOS = "Grupos de Auditores"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Cores de fundo da aba, sem o canal alfa (ver _rgb). O amarelo e a marca
# de chefia; a legenda e a propria celula A4, pintada ao lado do titulo
# "Supervisores do Grupo". O azul e so o cabecalho que se repete a cada
# grupo, e as linhas de cabecalho ja sao descartadas por outro caminho.
COR_SUPERVISOR = "FFF2CC"
COR_CABECALHO = "A4C2F4"


class Celula(str):
    """
    Texto da celula que carrega junto a cor de fundo.

    Subclasse de `str` de proposito: so a chefia depende da cor, e todo o
    resto do importador — e os testes — trata celula como texto puro e
    segue funcionando sem saber que a cor existe.
    """

    cor: str

    def __new__(cls, valor: str, cor: str = "") -> "Celula":
        celula = super().__new__(cls, valor)
        celula.cor = cor
        return celula


def _rgb(valor: str | None) -> str:
    """
    "FFFFF2CC" -> "FFF2CC". O Excel grava ARGB; o alfa nao interessa e so
    atrapalharia a comparacao com a cor que a SEFAZ usa.
    """
    if not valor:
        return ""
    return valor[2:] if len(valor) == 8 else valor


def _cores_por_estilo(z: zipfile.ZipFile) -> list[str]:
    """
    Cor de fundo de cada estilo de celula, indexada pelo atributo `s`.

    Uma celula aponta para um estilo (`cellXfs`), que aponta para um
    preenchimento (`fills`) — dois saltos ate a cor. Planilha sem estilos
    devolve lista vazia, e toda celula fica sem cor.
    """
    try:
        raiz = ET.fromstring(z.read("xl/styles.xml"))
    except KeyError:
        return []

    preenchimentos: list[str] = []
    for fill in raiz.iterfind(_NS + "fills/" + _NS + "fill"):
        padrao = fill.find(_NS + "patternFill")
        cor = padrao.find(_NS + "fgColor") if padrao is not None else None
        preenchimentos.append(_rgb(cor.get("rgb") if cor is not None else None))

    cores: list[str] = []
    for xf in raiz.iterfind(_NS + "cellXfs/" + _NS + "xf"):
        indice = int(xf.get("fillId", 0))
        cores.append(preenchimentos[indice] if indice < len(preenchimentos) else "")
    return cores


def _ler_aba(caminho: Path, nome_aba: str) -> list[dict[str, Celula]]:
    """
    Devolve as linhas da aba como {coluna: valor}, ex. {"A": "604.0"}.

    O valor e uma `Celula`: texto para todos os efeitos, com a cor de
    fundo pendurada para quem precisar dela (a chefia, em `extrair_supervisores`).

    Celulas vazias simplesmente nao aparecem no dicionario da linha — e
    assim que o proprio formato as representa.
    """
    with zipfile.ZipFile(caminho) as z:
        cores = _cores_por_estilo(z)
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

    linhas: list[dict[str, Celula]] = []
    for linha in dados.findall(_NS + "row") if dados is not None else []:
        celulas: dict[str, Celula] = {}
        for c in linha.findall(_NS + "c"):
            coluna = re.match(r"[A-Z]+", c.get("r")).group()
            estilo = int(c.get("s", 0))
            cor = cores[estilo] if estilo < len(cores) else ""
            tipo, valor, inline = c.get("t"), c.find(_NS + "v"), c.find(_NS + "is")
            if tipo == "s" and valor is not None:
                celulas[coluna] = Celula(compartilhadas[int(valor.text)], cor)
            elif tipo == "inlineStr" and inline is not None:
                texto = "".join(t.text or "" for t in inline.iter(_NS + "t"))
                celulas[coluna] = Celula(texto, cor)
            elif valor is not None:
                celulas[coluna] = Celula(valor.text, cor)
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


def extrair_supervisores(
    linhas: list[dict[str, Celula]], membros: list[tuple[int, str, str]],
) -> tuple[list[tuple[int, str, str]], list[str]]:
    """
    Quem chefia cada equipe, lido da cor de fundo das celulas.

    A planilha marca o supervisor pintando a matricula e o nome de
    amarelo dentro do bloco do grupo — nao ha coluna que diga isso. So
    entra quem ja passou por `extrair`, entao cabecalho repetido e rodape
    ficam de fora mesmo que venham pintados.

    Uma pessoa pode chefiar mais de uma equipe: a planilha de 02/09/2026
    tem dois casos. Sao vinculos distintos e ambos valem.

    Devolve [(codigo_equipe, matricula, nome)] e os avisos.
    """
    validos = {(codigo, matricula) for codigo, matricula, _ in membros}
    supervisores: dict[tuple[int, str], str] = {}
    desconhecidas: dict[str, int] = {}

    for celulas in linhas:
        codigo = _numero(celulas.get("A"))
        matricula = _numero(celulas.get("C"))
        if codigo is None or matricula is None:
            continue
        chave = (int(codigo), matricula)
        if chave not in validos:
            continue

        cores = {
            celula.cor
            for celula in celulas.values()
            if isinstance(celula, Celula) and celula.cor
        }
        if COR_SUPERVISOR in cores:
            supervisores[chave] = (celulas.get("D") or "").strip()
        for cor in cores - {COR_SUPERVISOR, COR_CABECALHO}:
            desconhecidas[cor] = desconhecidas.get(cor, 0) + 1

    avisos = [
        f"cor de fundo {cor} nao reconhecida em {total} linha(s) de dados; "
        f"se a SEFAZ mudou a marca de chefia, ajuste COR_SUPERVISOR"
        for cor, total in sorted(desconhecidas.items())
    ]
    if membros and not supervisores:
        avisos.append(
            "nenhuma chefia marcada na planilha — ate 25/08/2026 ela nao "
            "trazia essa informacao, mas tambem pode ser formatacao perdida "
            "numa reexportacao. Confira no Excel antes de gravar."
        )
    return sorted((cod, mat, nome) for (cod, mat), nome in supervisores.items()), avisos


def planejar_amarracao(
    user_repo: UserRepository,
    supervisores: list[tuple[int, str, str]],
    nomes_equipes: dict[int, str],
) -> tuple[list[tuple[str, str, int, str, str]], list[str], list[str]]:
    """
    Cruza a chefia da planilha com os usuarios do banco, sem gravar nada.

    Devolve (a_amarrar, ja_ok, impedidos). Cada item de `a_amarrar` e
    (matricula, nome, codigo_equipe, descricao_equipe, papel_atual).

    Quem chefia duas equipes entra com `codigo_equipe=None`: so o papel
    muda. `users.equipe_codigo` guarda um codigo so, e escolher um dos
    dois deixaria o supervisor cego para metade do que e dele — a chefia
    inteira dele ja vem de `equipe_membros.supervisor`, que a visibilidade
    soma.
    """
    equipes_por_matricula: dict[str, list[tuple[int, str]]] = {}
    for codigo, matricula, nome in supervisores:
        equipes_por_matricula.setdefault(matricula, []).append((codigo, nome))

    a_amarrar: list[tuple[str, str, int | None, str, str]] = []
    ja_ok: list[str] = []
    impedidos: list[str] = []

    for matricula, vinculos in sorted(
        equipes_por_matricula.items(), key=lambda item: item[1][0][1]
    ):
        nome = vinculos[0][1]
        multipla = len(vinculos) > 1
        codigo = None if multipla else vinculos[0][0]
        descricao = (
            ", ".join(
                nomes_equipes.get(cod, str(cod)) for cod, _ in sorted(vinculos)
            )
            if multipla
            else nomes_equipes.get(vinculos[0][0], "?")
        )

        usuario = user_repo.get_user_by_matricula(matricula)
        if usuario is None:
            impedidos.append(f"{matricula} {nome}: sem usuario cadastrado")
            continue
        if usuario["role"] in ("admin", "gerente"):
            impedidos.append(f"{matricula} {nome}: e {usuario['role']} no cadastro local")
            continue
        if usuario["role"] == "supervisor" and (
            multipla or usuario.get("equipe_codigo") == codigo
        ):
            ja_ok.append(f"{matricula} {nome}")
            continue
        a_amarrar.append((matricula, nome, codigo, descricao, usuario["role"]))
    return a_amarrar, ja_ok, impedidos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa equipes fiscais do ATF.")
    parser.add_argument("planilha", type=Path, help="caminho do .xlsx da SEFAZ")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que seria importado, sem gravar no banco",
    )
    parser.add_argument(
        "--amarrar-supervisores",
        action="store_true",
        help="alem das equipes, amarra em users.equipe_codigo a equipe que "
             "cada supervisor marcado chefia, promovendo-o de fiscal a "
             "supervisor (sem isso a chefia fica so no espelho da planilha)",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH, help="banco alvo")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.planilha.is_file():
        print(f"Planilha nao encontrada: {args.planilha}", file=sys.stderr)
        return 1

    linhas = _ler_aba(args.planilha, ABA_GRUPOS)
    equipes, membros, avisos = extrair(linhas)
    supervisores, avisos_chefia = extrair_supervisores(linhas, membros)

    for aviso in avisos + avisos_chefia:
        print(f"  aviso: {aviso}", file=sys.stderr)
    if not equipes:
        print("Nenhuma equipe encontrada na planilha.", file=sys.stderr)
        return 1

    matriculas = {m for _, m, _ in membros}
    print(f"{len(equipes)} equipes, {len(membros)} vinculos, {len(matriculas)} auditores")
    repetidos = len(membros) - len(matriculas)
    if repetidos:
        print(f"{repetidos} auditor(es) em mais de uma equipe (um vinculo em cada)")

    nomes_equipes = dict(equipes)
    com_chefia = {codigo for codigo, _, _ in supervisores}
    chefes = {matricula for _, matricula, _ in supervisores}
    print(
        f"{len(supervisores)} chefias marcadas em {len(com_chefia)} equipes "
        f"({len(chefes)} pessoas); {len(equipes) - len(com_chefia)} equipe(s) "
        f"sem supervisor marcado"
    )

    if args.dry_run:
        for codigo, nome in equipes:
            total = sum(1 for c, _, _ in membros if c == codigo)
            marca = sum(1 for c, _, _ in supervisores if c == codigo)
            print(f"  {codigo:>6}  {nome:<50} {total:>3}  chefia: {marca}")

        if supervisores:
            print("\n  --- supervisores marcados na planilha ---")
            for codigo in sorted(com_chefia, key=lambda c: nomes_equipes.get(c, "")):
                pessoas = "; ".join(
                    sorted(nome for c, _, nome in supervisores if c == codigo)
                )
                print(f"  {codigo:>6}  {nomes_equipes.get(codigo, '?')}: {pessoas}")

        sem_chefia = [(c, n) for c, n in equipes if c not in com_chefia]
        if sem_chefia:
            print(f"\n  --- {len(sem_chefia)} equipe(s) sem supervisor marcado ---")
            for codigo, nome in sem_chefia:
                print(f"  {codigo:>6}  {nome}")

    # O relatorio da amarracao so faz sentido no dry-run: no caminho que
    # grava, o plano e refeito depois da importacao, ja com as equipes
    # novas no banco — e la o banco pode ate nem existir ainda.
    if args.dry_run and args.amarrar_supervisores and supervisores:
        if not args.db.is_file():
            print(f"\nBanco nao encontrado: {args.db}", file=sys.stderr)
            return 1
        user_repo = UserRepository(Database(args.db))
        a_amarrar, ja_ok, impedidos = planejar_amarracao(
            user_repo, supervisores, nomes_equipes
        )
        print(
            f"\n{len(a_amarrar)} usuario(s) a amarrar, {len(ja_ok)} ja corretos, "
            f"{len(impedidos)} fora do alcance"
        )
        for matricula, nome, codigo, equipe, papel in a_amarrar:
            promocao = " (fiscal -> supervisor)" if papel == "fiscal" else ""
            destino = f"{codigo} {equipe}" if codigo else f"2 equipes: {equipe}"
            print(f"  {matricula:>9}  {nome:<42} -> {destino}{promocao}")
        for motivo in impedidos:
            print(f"  fora: {motivo}")

    if args.dry_run:
        print("\n--dry-run: nada foi gravado.")
        return 0

    database = Database(args.db)
    database.init_schema()
    n_equipes, n_membros = EquipeFiscalRepository(database).substituir_tudo(
        equipes, membros, {(cod, mat) for cod, mat, _ in supervisores}
    )
    print(
        f"Importado em {args.db}: {n_equipes} equipes, {n_membros} vinculos, "
        f"{len(supervisores)} chefias."
    )

    if args.amarrar_supervisores and supervisores:
        user_repo = UserRepository(database)
        a_amarrar, _, _ = planejar_amarracao(user_repo, supervisores, nomes_equipes)
        alterados = sum(
            1
            for matricula, _, codigo, _, _ in a_amarrar
            if user_repo.amarrar_equipe_por_matricula(matricula, codigo, promover=True)
        )
        print(f"{alterados} usuario(s) atualizados (promovidos e/ou amarrados a equipe).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
