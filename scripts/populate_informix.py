"""
populate_informix.py – Popula o banco Informix com 30 OS de teste.

Hierarquia completa:
  Gerencia de Fiscalizacao:
    Sup. Fiscal A     → Patricia Oliveira (23456) → Carlos Mendes, Ana Ribeiro, Pedro Nascimento
    Sup. Fiscal B     → Joao Silva (23457)        → Jose Almeida, Fernanda Costa
  Gerencia de Arrecadacao:
    Sup. Arrecadacao A → Maria Santos (23458)     → Marcos Silva, Claudia Souza, Rafael Lima
    Sup. Arrecadacao B → Ricardo Pereira (23459)  → Juliana Martins, Bruno Araujo
  Gerencia de Tributacao:
    Sup. Tributaria A  → Lucia Costa (23460)      → Tatiana Gomes, Diego Cardoso, Vanessa Rocha
    Sup. Tributaria B  → Antonio Ferreira (23461) → Leandro Pinto, Camila Teixeira

Uso:
    python -m scripts.populate_informix
    ou
    python scripts/populate_informix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o diretorio raiz do projeto esta no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.informix_db import get_informix_connection


# ── 30 Ordens de Servico distribuidas pelas 3 gerencias ────────

OS_DATA = [
    # ============================================================
    # GERENCIA DE FISCALIZACAO (supervisores 23456 e 23457)
    # ============================================================
    # Sup. Patricia Oliveira (23456) - 6 OS
    ("OS-2026-001", "Normal",       "12.345.678-9", "Distribuidora ABC Ltda",          "23456", "Carlos Mendes, Ana Ribeiro",  "em_andamento", "alta",    "2026-01-10", "2026-01-12", "2026-01-25"),
    ("OS-2026-003", "Simplificado", "55.667.778-3", "Transportes Rapido Ltda",         "23456", "Ana Ribeiro",                 "em_andamento", "normal",  "2026-01-05", "2026-01-08", "2026-01-20"),
    ("OS-2026-006", "Especifico",   "12.345.678-9", "Distribuidora ABC Ltda",          "23456", "Carlos Mendes",               "aberta",       "alta",    "2026-02-07", "2026-02-09", "2026-02-09"),
    ("OS-2026-007", "Normal",       "98.765.432-1", "Industria Delta S/A",             "23456", "Pedro Nascimento",            "em_andamento", "normal",  "2026-01-15", "2026-01-18", "2026-02-01"),
    ("OS-2026-010", "Normal",       "77.889.900-5", "Farmacia Popular Ltda",           "23456", "Ana Ribeiro, Pedro Nascimento","cancelada",   "alta",    "2026-01-20", "2026-01-22", "2026-02-05"),
    ("OS-2026-011", "Especifico",   "44.556.667-8", "Auto Pecas Nordeste Ltda",        "23456", "Carlos Mendes, Ana Ribeiro",  "aberta",       "urgente", "2026-02-15", None,         "2026-02-15"),

    # Sup. Joao Silva (23457) - 6 OS
    ("OS-2026-002", "Especifico",   "98.765.432-1", "Industria Delta S/A",             "23457", "Jose Almeida, Fernanda Costa","aberta",       "urgente", "2026-02-01", "2026-02-03", "2026-02-03"),
    ("OS-2026-004", "Normal",       "33.445.556-4", "Supermercado Central Ltda",       "23457", "Jose Almeida",                "aberta",       "alta",    "2026-02-05", None,         "2026-02-05"),
    ("OS-2026-005", "Simplificado", "77.889.900-5", "Farmacia Popular Ltda",           "23457", "Fernanda Costa",              "concluida",    "normal",  "2025-12-15", "2025-12-18", "2026-01-30"),
    ("OS-2026-008", "Simplificado", "33.445.556-4", "Supermercado Central Ltda",       "23457", "Jose Almeida",                "aberta",       "baixa",   "2025-12-01", "2025-12-05", "2025-12-10"),
    ("OS-2026-009", "Especifico",   "55.667.778-3", "Transportes Rapido Ltda",         "23457", "Fernanda Costa, Jose Almeida","aberta",       "urgente", "2026-02-08", None,         "2026-02-08"),
    ("OS-2026-012", "Normal",       "88.990.001-2", "Construtora Horizonte S/A",       "23457", "Fernanda Costa",              "concluida",    "normal",  "2025-11-20", "2025-11-22", "2025-12-28"),

    # ============================================================
    # GERENCIA DE ARRECADACAO (supervisores 23458 e 23459)
    # ============================================================
    # Sup. Maria Santos (23458) - 5 OS
    ("OS-2026-013", "Normal",       "11.222.333-4", "Comercio Atacadista Sol Ltda",    "23458", "Marcos Silva, Claudia Souza", "em_andamento", "alta",    "2025-12-20", "2025-12-23", "2026-01-10"),
    ("OS-2026-014", "Especifico",   "22.333.444-5", "Metalurgica Forte S/A",          "23458", "Rafael Lima",                 "aberta",       "urgente", "2026-01-28", "2026-01-30", "2026-01-30"),
    ("OS-2026-015", "Simplificado", "33.444.555-6", "Padaria Estrela do Norte Ltda",  "23458", "Claudia Souza",               "concluida",    "normal",  "2025-11-10", "2025-11-12", "2025-12-20"),
    ("OS-2026-016", "Normal",       "44.555.666-7", "Posto Combustivel Rota 101",     "23458", "Marcos Silva, Rafael Lima",   "em_andamento", "normal",  "2026-01-05", "2026-01-08", "2026-02-10"),
    ("OS-2026-017", "Especifico",   "55.666.777-8", "Textil Nordeste Industria Ltda", "23458", "Claudia Souza, Marcos Silva", "aberta",       "alta",    "2026-02-12", None,         "2026-02-12"),

    # Sup. Ricardo Pereira (23459) - 5 OS
    ("OS-2026-018", "Normal",       "66.777.888-9", "Grafica Express Print Ltda",     "23459", "Juliana Martins",             "em_andamento", "normal",  "2025-12-10", "2025-12-12", "2026-01-05"),
    ("OS-2026-019", "Simplificado", "77.888.999-0", "Loja Materiais Construcao JB",   "23459", "Bruno Araujo",                "concluida",    "baixa",   "2025-10-15", "2025-10-18", "2025-11-30"),
    ("OS-2026-020", "Especifico",   "88.999.000-1", "Hotel Beira Mar Palace",         "23459", "Juliana Martins, Bruno Araujo","aberta",      "alta",    "2026-02-01", "2026-02-04", "2026-02-04"),
    ("OS-2026-021", "Normal",       "99.000.111-2", "Restaurante Sabor & Arte Ltda",  "23459", "Bruno Araujo",                "aberta",       "normal",  "2026-01-20", "2026-01-23", "2026-01-23"),
    ("OS-2026-022", "Simplificado", "11.222.333-4", "Comercio Atacadista Sol Ltda",   "23459", "Juliana Martins",             "concluida",    "normal",  "2025-11-05", "2025-11-08", "2025-12-15"),

    # ============================================================
    # GERENCIA DE TRIBUTACAO (supervisores 23460 e 23461)
    # ============================================================
    # Sup. Lucia Costa (23460) - 4 OS
    ("OS-2026-023", "Normal",       "10.203.040-5", "Informatica Total Systems Ltda", "23460", "Tatiana Gomes, Diego Cardoso","em_andamento", "urgente", "2025-11-15", "2025-11-18", "2025-12-01"),
    ("OS-2026-024", "Especifico",   "20.304.050-6", "Agropecuaria Verde Campo S/A",  "23460", "Vanessa Rocha",               "aberta",       "alta",    "2026-01-10", None,         "2026-01-10"),
    ("OS-2026-025", "Simplificado", "30.405.060-7", "Clinica Saude Mais Ltda",       "23460", "Diego Cardoso",               "concluida",    "normal",  "2025-10-20", "2025-10-22", "2025-11-28"),
    ("OS-2026-026", "Normal",       "40.506.070-8", "Escola Futuro Brilhante Ltda",  "23460", "Tatiana Gomes, Vanessa Rocha","aberta",       "normal",  "2026-02-18", "2026-02-20", "2026-02-20"),

    # Sup. Antonio Ferreira (23461) - 4 OS
    ("OS-2026-027", "Especifico",   "50.607.080-9", "Imobiliaria Plano Alto Ltda",   "23461", "Leandro Pinto",               "em_andamento", "alta",    "2025-12-05", "2025-12-08", "2026-01-15"),
    ("OS-2026-028", "Simplificado", "60.708.090-0", "Papelaria Central Office Ltda", "23461", "Camila Teixeira",             "aberta",       "baixa",   "2026-01-25", "2026-01-28", "2026-01-28"),
    ("OS-2026-029", "Normal",       "70.809.010-1", "Academia Corpo em Forma Ltda",  "23461", "Leandro Pinto, Camila Teixeira","concluida",  "normal",  "2025-09-10", "2025-09-12", "2025-10-30"),
    ("OS-2026-030", "Especifico",   "80.900.120-2", "Pet Shop Amigo Fiel Ltda",      "23461", "Camila Teixeira",             "aberta",       "urgente", "2026-02-20", None,         "2026-02-20"),
]


def _build_insert(os_row: tuple) -> tuple[str, tuple]:
    """Monta o INSERT com MDY() para datas do Informix."""
    numero, tipo, ie, razao, mat_sup, fiscais, status, prior, dt_ab, dt_ci, dt_ult = os_row

    def to_mdy(date_str: str | None) -> str:
        if not date_str:
            return "NULL"
        y, m, d = date_str.split("-")
        return f"MDY({int(m)}, {int(d)}, {int(y)})"

    sql = (
        "INSERT INTO ordens_servico "
        "(numero, tipo, ie, razao_social, matricula_supervisor, fiscais, "
        "status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, {to_mdy(dt_ab)}, {to_mdy(dt_ci)}, {to_mdy(dt_ult)})"
    )
    params = (numero, tipo, ie, razao, mat_sup, fiscais, status, prior)
    return sql, params


def main() -> None:
    """Limpa e repopula a tabela ordens_servico no Informix."""
    conn = get_informix_connection()

    if not conn.is_configured():
        print("ERRO: Informix nao esta configurado. Verifique o .env")
        sys.exit(1)

    print(f"Conectando ao Informix: {conn.server} / {conn.database} ...")

    pyodbc_conn = conn.connect()
    if not pyodbc_conn:
        print("ERRO: Nao foi possivel conectar ao Informix.")
        sys.exit(1)

    cursor = pyodbc_conn.cursor()

    # Limpa dados existentes
    print("Limpando tabela ordens_servico ...")
    try:
        cursor.execute("DELETE FROM ordens_servico")
        pyodbc_conn.commit()
    except Exception as e:
        print(f"Aviso ao limpar: {e}")

    # Insere as 30 OS
    inseridas = 0
    erros = 0
    for os_row in OS_DATA:
        sql, params = _build_insert(os_row)
        try:
            cursor.execute(sql, params)
            inseridas += 1
        except Exception as e:
            print(f"  ERRO ao inserir {os_row[0]}: {e}")
            erros += 1

    pyodbc_conn.commit()
    cursor.close()

    print(f"\nResultado: {inseridas} OS inseridas, {erros} erros.")
    print("\nDistribuicao por supervisor:")
    rows = conn.execute_query(
        "SELECT matricula_supervisor, COUNT(*) as total "
        "FROM ordens_servico GROUP BY matricula_supervisor "
        "ORDER BY matricula_supervisor"
    )
    for r in rows:
        print(f"  Matricula {r['matricula_supervisor']}: {r['total']} OS")

    print("\nDistribuicao por status:")
    rows = conn.execute_query(
        "SELECT status, COUNT(*) as total "
        "FROM ordens_servico GROUP BY status "
        "ORDER BY status"
    )
    for r in rows:
        print(f"  {r['status']}: {r['total']} OS")

    conn.close()
    print("\nPopulacao concluida!")


if __name__ == "__main__":
    main()
