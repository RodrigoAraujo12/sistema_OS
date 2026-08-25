"""
importar_usuarios.py – Cadastra os auditores da planilha da SEFAZ como
usuarios do sistema, com a matricula real.

Uso:
    python -m backend.importar_usuarios CAMINHO/DADOS_ORDEM_SERVICO.xlsx
    python -m backend.importar_usuarios ... --dry-run
    python -m backend.importar_usuarios ... --remover-seed
    python -m backend.importar_usuarios ... --senha "Sefaz@2026"

Todos entram como **fiscal**, sem gerencia nem supervisao: e o unico
cargo que o modelo resolve so pela matricula (fiscal enxerga apenas as
proprias OS). Promover alguem a supervisor e amarra-lo a uma equipe e
feito depois, na tela de admin — a planilha nao diz quem chefia o que.

Reexecutar e seguro: quem ja tem a matricula cadastrada e pulado.

A planilha NAO deve ser versionada (nome e matricula de servidor), e o
CSV de senhas gerado aqui muito menos. Ver NOTAS-INTERNAS.md.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from sqlite3 import IntegrityError

from .auth import AuthService, PasswordHasher, TokenStore, gerar_senha_temporaria
from .db import DB_PATH, Database, UserRepository
from .importar_equipes import ABA_GRUPOS, _ler_aba, extrair
from .seed import matriculas_de_exemplo

logger = logging.getLogger("sefaz.importar_usuarios")

ARQUIVO_SENHAS = "senhas-iniciais.csv"


def auditores(planilha: Path) -> list[tuple[str, str]]:
    """
    (matricula, nome) de cada auditor da planilha, sem repetir.

    Reaproveita o parser das equipes, entao ja vem sem os cabecalhos
    repetidos e sem o rodape. Quem esta em duas equipes aparece uma vez
    so: aqui interessa a pessoa, nao o vinculo.
    """
    _, membros, avisos = extrair(_ler_aba(planilha, ABA_GRUPOS))
    for aviso in avisos:
        print(f"  aviso: {aviso}", file=sys.stderr)

    por_matricula: dict[str, str] = {}
    for _, matricula, nome in membros:
        por_matricula.setdefault(matricula, nome)
    return sorted(por_matricula.items(), key=lambda item: item[1])


def _gravar_senhas(destino: Path, linhas: list[tuple[str, str, str]]) -> None:
    """Grava matricula/nome/senha para o admin repassar a cada um."""
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["matricula", "usuario", "senha_temporaria"])
        escritor.writerows(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cadastra os auditores da planilha como usuarios."
    )
    parser.add_argument("planilha", type=Path, help="caminho do .xlsx da SEFAZ")
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra o que faria, sem gravar"
    )
    parser.add_argument(
        "--remover-seed",
        action="store_true",
        help="apaga antes os usuarios de exemplo (o admin nunca e tocado)",
    )
    parser.add_argument(
        "--senha",
        help="usa esta senha para todos, em vez de uma aleatoria por pessoa "
             "(so para ambiente de teste; a troca no 1o acesso continua exigida)",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH, help="banco alvo")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.planilha.is_file():
        print(f"Planilha nao encontrada: {args.planilha}", file=sys.stderr)
        return 1

    pessoas = auditores(args.planilha)
    if not pessoas:
        print("Nenhum auditor encontrado na planilha.", file=sys.stderr)
        return 1

    database = Database(args.db)
    database.init_schema()
    user_repo = UserRepository(database)
    auth_service = AuthService(user_repo, PasswordHasher(), TokenStore())

    cadastradas = user_repo.get_matriculas_cadastradas()
    do_seed = matriculas_de_exemplo() & cadastradas
    if args.remover_seed:
        cadastradas -= do_seed
    novos = [(mat, nome) for mat, nome in pessoas if mat not in cadastradas]

    print(f"{len(pessoas)} auditores na planilha")
    if args.remover_seed:
        print(f"{len(do_seed)} usuario(s) de exemplo a remover")
    if len(novos) < len(pessoas):
        print(f"{len(pessoas) - len(novos)} ja cadastrado(s), serao pulados")
    print(f"{len(novos)} usuario(s) a criar")

    if args.dry_run:
        for matricula, nome in novos[:10]:
            print(f"  {matricula:>9}  {nome}")
        if len(novos) > 10:
            print(f"  ... e mais {len(novos) - 10}")
        print("\n--dry-run: nada foi gravado.")
        return 0

    if args.remover_seed and do_seed:
        removidos = user_repo.delete_users_by_matricula(do_seed)
        print(f"Removidos {removidos} usuario(s) de exemplo.")

    criados: list[tuple[str, str, str]] = []
    for matricula, nome in novos:
        senha = args.senha or gerar_senha_temporaria()
        try:
            auth_service.register_user_with_options(
                username=nome,
                password=senha,
                role="fiscal",
                gerencia_id=None,
                supervisao_id=None,
                must_change_password=True,
                matricula=matricula,
            )
        except IntegrityError as exc:
            # Nome ja usado por outro usuario (username e UNIQUE). Segue
            # com os demais: uma colisao nao pode abortar a carga inteira.
            print(f"  falhou {matricula} ({nome}): {exc}", file=sys.stderr)
            continue
        criados.append((matricula, nome, senha))

    print(f"Criados {len(criados)} usuario(s) como fiscal, sem lotacao local.")

    if criados and not args.senha:
        destino = args.db.parent / ARQUIVO_SENHAS
        _gravar_senhas(destino, criados)
        print(
            f"Senhas temporarias em {destino} — repasse e apague. "
            "O arquivo NAO pode ser versionado."
        )
    elif criados:
        print("Todos com a senha informada; a troca no primeiro acesso continua exigida.")

    print(
        "\nProximo passo: na tela de Usuarios, promova quem for supervisor "
        "e amarre a equipe fiscal dele."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
