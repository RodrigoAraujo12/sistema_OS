"""
seed.py – Dados de exemplo criados no primeiro uso de um banco vazio.

Existem para o sistema abrir com algo na tela (demo, screenshots do
portfolio, testes de integracao). Nao sao dados reais: as matriculas
12345-12347 / 23456-23461 / 34567-34581 sao ficticias e escolhidas para
casar com o MOCK de OS em `external_api.py`.

Ficam aqui, e nao dentro de `main.py`, porque
`backend.importar_usuarios --remover-seed` precisa saber exatamente quem
e de exemplo para apagar — e uma lista duplicada nos dois lugares
divergiria na primeira alteracao.
"""

from __future__ import annotations

GERENCIAS = [
    "Gerencia de Fiscalizacao",
    "Gerencia de Arrecadacao",
    "Gerencia de Tributacao",
]

# (nome, indice da gerencia em GERENCIAS)
SUPERVISOES = [
    ("Supervisao Fiscal A", 0),
    ("Supervisao Fiscal B", 0),
    ("Supervisao Arrecadacao A", 1),
    ("Supervisao Arrecadacao B", 1),
    ("Supervisao Tributaria A", 2),
    ("Supervisao Tributaria B", 2),
]

# (nome, matricula, indice da gerencia)
GERENTES = [
    ("Roberto Santos", "12345", 0),
    ("Helena Rodrigues", "12346", 1),
    ("Sergio Barbosa", "12347", 2),
]

# (nome, matricula, indice da supervisao)
SUPERVISORES = [
    ("Patricia Oliveira", "23456", 0),
    ("Joao Silva", "23457", 1),
    ("Maria Santos", "23458", 2),
    ("Ricardo Pereira", "23459", 3),
    ("Lucia Costa", "23460", 4),
    ("Antonio Ferreira", "23461", 5),
]

# (nome, matricula, indice da supervisao)
FISCAIS = [
    ("Carlos Mendes", "34567", 0),
    ("Ana Ribeiro", "34568", 0),
    ("Pedro Nascimento", "34569", 0),
    ("Jose Almeida", "34570", 1),
    ("Fernanda Costa", "34571", 1),
    ("Marcos Silva", "34572", 2),
    ("Claudia Souza", "34573", 2),
    ("Rafael Lima", "34574", 2),
    ("Juliana Martins", "34575", 3),
    ("Bruno Araujo", "34576", 3),
    ("Tatiana Gomes", "34577", 4),
    ("Diego Cardoso", "34578", 4),
    ("Vanessa Rocha", "34579", 4),
    ("Leandro Pinto", "34580", 5),
    ("Camila Teixeira", "34581", 5),
]


def matriculas_de_exemplo() -> set[str]:
    """
    Matriculas de todos os usuarios de exemplo (sem o admin).

    E o criterio de "quem e do seed" usado para remove-los quando o banco
    passa a ter gente de verdade. O admin nunca entra: apagar o admin
    tranca o sistema.
    """
    return {
        matricula
        for _, matricula, _ in (*GERENTES, *SUPERVISORES, *FISCAIS)
    }
