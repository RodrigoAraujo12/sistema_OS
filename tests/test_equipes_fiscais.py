"""
Testes das equipes fiscais do ATF: leitura da planilha da SEFAZ e o
repositorio que a armazena.

A visibilidade de OS por equipe (quem enxerga o que) e testada em
test_integration.py, junto com o resto do controle de acesso.
"""

from __future__ import annotations

import sqlite3
import unittest
import zipfile
from pathlib import Path

from backend.db import Database, EquipeFiscalRepository
from backend.importar_equipes import _numero, extrair

_MEMORY = Path(":memory:")


class InMemoryDatabase(Database):
    """Database que usa SQLite in-memory para testes (evita locks no Windows)."""

    def __init__(self):
        super().__init__(_MEMORY)
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    def connect(self):
        return self._conn


def _linha(codigo=None, grupo=None, matricula=None, nome=None) -> dict[str, str]:
    """Monta uma linha da aba no formato que _ler_aba devolve."""
    celulas = {}
    if codigo is not None:
        celulas["A"] = codigo
    if grupo is not None:
        celulas["B"] = grupo
    if matricula is not None:
        celulas["C"] = matricula
    if nome is not None:
        celulas["D"] = nome
    return celulas


class TestNumero(unittest.TestCase):
    """Conversao dos numeros que o Excel guarda com casa decimal."""

    def test_tira_casa_decimal(self):
        self.assertEqual(_numero("604.0"), "604")
        self.assertEqual(_numero("9000001.0"), "9000001")

    def test_aceita_inteiro_puro(self):
        self.assertEqual(_numero("427"), "427")

    def test_vazio_e_none(self):
        self.assertIsNone(_numero(None))
        self.assertIsNone(_numero(""))
        self.assertIsNone(_numero("   "))

    def test_descarta_nao_numerico(self):
        """Texto no lugar de matricula e descartado, nao adivinhado."""
        self.assertIsNone(_numero("Código"))
        self.assertIsNone(_numero("Atualizado em: 21/082026"))

    def test_descarta_fracionario(self):
        """Matricula com fracao e dado corrompido — melhor perder a linha."""
        self.assertIsNone(_numero("604.5"))


class TestExtrair(unittest.TestCase):
    """Limpeza das sujeiras da exportacao paginada da SEFAZ."""

    def test_caso_simples(self):
        equipes, membros, avisos = extrair([
            _linha("Código", "Grupo", "Matrícula", "Fiscal"),
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO DE TAL"),
        ])
        self.assertEqual(equipes, [(427, "GOFE - VAREJO")])
        self.assertEqual(membros, [(427, "9000001", "FULANO DE TAL")])
        self.assertEqual(avisos, [])

    def test_descarta_cabecalho_repetido(self):
        """
        A exportacao repete o cabecalho a cada pagina. Sem descartar,
        "Código/Grupo/Matrícula/Fiscal" viraria um auditor.
        """
        linhas = [_linha("Código", "Grupo", "Matrícula", "Fiscal")]
        for i in range(3):
            linhas.append(_linha("427.0", "GOFE - VAREJO", f"100{i}.0", f"FISCAL {i}"))
            linhas.append(_linha("Código", "Grupo", "Matrícula", "Fiscal"))

        equipes, membros, avisos = extrair(linhas)
        self.assertEqual(len(equipes), 1)
        self.assertEqual(len(membros), 3)
        self.assertEqual(avisos, [])
        self.assertNotIn("Fiscal", [nome for _, _, nome in membros])

    def test_descarta_rodape_sem_codigo(self):
        """A ultima linha da planilha e "Atualizado em: ...", so na coluna B."""
        equipes, membros, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
            _linha(grupo="Atualizado em: 21/082026"),
        ])
        self.assertEqual(len(equipes), 1)
        self.assertEqual(len(membros), 1)
        self.assertEqual(avisos, [])

    def test_auditor_em_duas_equipes_vira_dois_vinculos(self):
        """
        Cinco auditores da planilha real estao em duas equipes. Os dois
        vinculos sao legitimos: cada supervisor enxerga essa pessoa.
        """
        equipes, membros, _ = extrair([
            _linha("614.0", "GEST_ITCD_AUDITORES", "9000002.0", "BELTRANO DA SILVA"),
            _linha("554.0", "GOFITCD/IPVA - GEFTE", "9000002.0", "BELTRANO DA SILVA"),
        ])
        self.assertEqual(len(equipes), 2)
        self.assertEqual(len(membros), 2)
        self.assertEqual({cod for cod, _, _ in membros}, {614, 554})

    def test_linha_repetida_nao_duplica(self):
        """A mesma pessoa na mesma equipe duas vezes conta uma so."""
        _, membros, _ = extrair([
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
            _linha("427.0", "GOFE - VAREJO", "9000001.0", "FULANO"),
        ])
        self.assertEqual(len(membros), 1)

    def test_avisa_sobre_linha_sem_matricula(self):
        _, membros, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", None, "SEM MATRICULA"),
        ])
        self.assertEqual(membros, [])
        self.assertEqual(len(avisos), 1)
        self.assertIn("sem matricula", avisos[0])

    def test_avisa_sobre_equipe_com_dois_nomes(self):
        """Mesmo codigo com nomes diferentes e sinal de planilha inconsistente."""
        equipes, _, avisos = extrair([
            _linha("427.0", "GOFE - VAREJO", "1000.0", "A"),
            _linha("427.0", "GOFE - VAREJO (NOVO)", "1001.0", "B"),
        ])
        self.assertEqual(equipes, [(427, "GOFE - VAREJO")])
        self.assertEqual(len(avisos), 1)
        self.assertIn("dois nomes", avisos[0])

    def test_planilha_vazia(self):
        equipes, membros, avisos = extrair([])
        self.assertEqual((equipes, membros, avisos), ([], [], []))


class TestEquipeFiscalRepository(unittest.TestCase):
    """Armazenamento das equipes e seus membros."""

    def setUp(self):
        self.db = InMemoryDatabase()
        self.db.init_schema()
        self.repo = EquipeFiscalRepository(self.db)

    def test_schema_cria_tabelas(self):
        nomes = {
            t["name"]
            for t in self.db.connect().execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("equipes_fiscais", nomes)
        self.assertIn("equipe_membros", nomes)

    def test_substituir_e_ler(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")],
            [(427, "1000", "FULANO"), (427, "1001", "BELTRANO")],
        )
        self.assertEqual(self.repo.count_equipes(), 1)
        self.assertEqual(
            set(self.repo.get_matriculas_by_equipe(427)), {"1000", "1001"}
        )

    def test_substituir_apaga_o_que_saiu(self):
        """
        Carga nova substitui a anterior por completo. Se fosse merge,
        quem saiu da equipe continuaria visivel para o supervisor.
        """
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1000", "SAIU"), (427, "1001", "FICOU")]
        )
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1001", "FICOU")]
        )
        self.assertEqual(self.repo.get_matriculas_by_equipe(427), ["1001"])

    def test_equipe_extinta_some(self):
        self.repo.substituir_tudo([(427, "A"), (429, "B")], [])
        self.repo.substituir_tudo([(427, "A")], [])
        self.assertIsNone(self.repo.get_equipe(429))
        self.assertEqual(self.repo.get_matriculas_by_equipe(429), [])

    def test_equipe_inexistente_nao_da_acesso(self):
        """Codigo que nao existe devolve conjunto vazio, nunca 'tudo'."""
        self.assertEqual(self.repo.get_matriculas_by_equipe(9999), [])

    def test_mesma_matricula_em_duas_equipes(self):
        self.repo.substituir_tudo(
            [(614, "ITCD"), (554, "IPVA")],
            [(614, "9000002", "BELTRANO"), (554, "9000002", "BELTRANO")],
        )
        self.assertEqual(self.repo.get_matriculas_by_equipe(614), ["9000002"])
        self.assertEqual(self.repo.get_matriculas_by_equipe(554), ["9000002"])

    def test_list_equipes_conta_membros(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO"), (429, "GOAC - MALHAS")],
            [(427, "1000", "A"), (427, "1001", "B"), (429, "1002", "C")],
        )
        por_codigo = {e["codigo"]: e for e in self.repo.list_equipes()}
        self.assertEqual(por_codigo[427]["total_membros"], 2)
        self.assertEqual(por_codigo[429]["total_membros"], 1)

    def test_list_equipes_inclui_equipe_vazia(self):
        """Equipe sem ninguem ainda aparece na lista, com contagem zero."""
        self.repo.substituir_tudo([(427, "GOFE - VAREJO")], [])
        equipes = self.repo.list_equipes()
        self.assertEqual(len(equipes), 1)
        self.assertEqual(equipes[0]["total_membros"], 0)

    def test_get_membros_traz_nome(self):
        self.repo.substituir_tudo(
            [(427, "GOFE - VAREJO")], [(427, "1000", "ZEZINHO"), (427, "1001", "ANA")]
        )
        membros = self.repo.get_membros(427)
        self.assertEqual([m["nome"] for m in membros], ["ANA", "ZEZINHO"])


class TestPlanilhaReal(unittest.TestCase):
    """
    Le a planilha da SEFAZ, se ela estiver disponivel.

    Fica como skip no CI e na maquina de quem nao tem o arquivo: ele nao
    e versionado, por conter nome e matricula de servidor.
    """

    CAMINHOS = [
        Path.home() / "Downloads" / "DADOS_ORDEM_SERVICO.xlsx",
        Path(__file__).parent / "dados" / "DADOS_ORDEM_SERVICO.xlsx",
    ]

    def setUp(self):
        self.planilha = next((c for c in self.CAMINHOS if c.is_file()), None)
        if self.planilha is None:
            self.skipTest("planilha da SEFAZ nao disponivel nesta maquina")

    def test_le_a_aba_de_grupos(self):
        from backend.importar_equipes import ABA_GRUPOS, _ler_aba

        equipes, membros, avisos = extrair(_ler_aba(self.planilha, ABA_GRUPOS))
        self.assertGreater(len(equipes), 0)
        self.assertGreater(len(membros), len(equipes))
        self.assertEqual(avisos, [])
        # Nenhum cabecalho ou rodape sobreviveu a limpeza
        nomes = {nome for _, _, nome in membros}
        self.assertNotIn("Fiscal", nomes)
        self.assertTrue(all(m.isdigit() for _, m, _ in membros))

    def test_aba_inexistente_da_erro_util(self):
        from backend.importar_equipes import _ler_aba

        with self.assertRaises(ValueError) as ctx:
            _ler_aba(self.planilha, "Aba Que Nao Existe")
        self.assertIn("Abas na planilha", str(ctx.exception))

    def test_arquivo_invalido(self):
        from backend.importar_equipes import ABA_GRUPOS, _ler_aba

        with self.assertRaises(zipfile.BadZipFile):
            _ler_aba(Path(__file__), ABA_GRUPOS)


if __name__ == "__main__":
    unittest.main()
