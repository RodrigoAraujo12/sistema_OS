"""
Testes do seed de exemplo e da importacao de usuarios em lote.

O que esta em jogo aqui e o momento da virada: o banco deixa de ter gente
ficticia e passa a ter os auditores reais da SEFAZ. Se o seed voltar a
rodar nesse banco, ou se o admin deixar de ser criado, o sistema fica
inutilizavel — sao esses dois casos que os testes seguram.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.auth import AuthService, PasswordHasher, TokenStore
from backend.db import (
    Database,
    EquipeFiscalRepository,
    GerenciaRepository,
    SupervisaoRepository,
    UserRepository,
)
from backend.importar_usuarios import auditores
from backend.seed import matriculas_de_exemplo

ADMIN_SENHA = "Admin@Teste123"


class SeedTestBase(unittest.TestCase):
    """Prepara um banco temporario e aponta o main.py para ele."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "teste.db"

        import backend.main as main_module

        self.main = main_module
        self.database = Database(self.db_path)
        self.user_repo = UserRepository(self.database)
        self.equipe_repo = EquipeFiscalRepository(self.database)

        self._originais = {
            "database": main_module.database,
            "user_repo": main_module.user_repo,
            "gerencia_repo": main_module.gerencia_repo,
            "supervisao_repo": main_module.supervisao_repo,
            "equipe_repo": main_module.equipe_repo,
            "auth_service": main_module.auth_service,
            "ADMIN_PASSWORD": main_module.ADMIN_PASSWORD,
        }
        main_module.database = self.database
        main_module.user_repo = self.user_repo
        main_module.gerencia_repo = GerenciaRepository(self.database)
        main_module.supervisao_repo = SupervisaoRepository(self.database)
        main_module.equipe_repo = self.equipe_repo
        main_module.auth_service = AuthService(
            self.user_repo, PasswordHasher(), TokenStore()
        )
        main_module.ADMIN_PASSWORD = ADMIN_SENHA

    def tearDown(self):
        for nome, valor in self._originais.items():
            setattr(self.main, nome, valor)
        self._tmp.cleanup()

    def _matriculas(self) -> set[str]:
        return self.user_repo.get_matriculas_cadastradas()


class TestSeed(SeedTestBase):
    """Quando os dados de exemplo devem (e nao devem) ser criados."""

    def test_banco_vazio_cria_admin_e_exemplo(self):
        """O comportamento historico continua: demo abre com dados na tela."""
        self.main._seed_database()
        self.assertIsNotNone(self.user_repo.get_user_by_username("admin"))
        self.assertTrue(matriculas_de_exemplo() <= self._matriculas())

    def test_com_equipes_importadas_cria_so_o_admin(self):
        """
        Banco preparado com dados reais da SEFAZ nao recebe gente ficticia:
        as matriculas de exemplo nao existem em equipe alguma e nunca
        casariam com uma OS do ATF.
        """
        self.database.init_schema()
        self.equipe_repo.substituir_tudo([(427, "GOFE - VAREJO")], [])

        self.main._seed_database()

        self.assertIsNotNone(self.user_repo.get_user_by_username("admin"))
        self.assertEqual(self.user_repo.count_users(), 1)
        self.assertEqual(self._matriculas() & matriculas_de_exemplo(), set())

    def test_cria_o_admin_faltante_sem_ressuscitar_o_exemplo(self):
        """
        O caso que trancava o sistema: importar usuarios em lote num banco
        novo criava gente, mas nenhum admin — e o seed antigo, que so
        olhava "o banco esta vazio", nunca mais criava um.
        """
        self.database.init_schema()
        AuthService(self.user_repo, PasswordHasher(), TokenStore()).register_user_with_options(
            username="AUDITOR REAL", password="Senha@123", role="fiscal",
            gerencia_id=None, supervisao_id=None, must_change_password=True,
            matricula="9000001",
        )

        self.main._seed_database()

        self.assertIsNotNone(self.user_repo.get_user_by_username("admin"))
        self.assertEqual(self.user_repo.count_users(), 2)
        self.assertEqual(self._matriculas() & matriculas_de_exemplo(), set())

    def test_reexecucao_nao_duplica(self):
        self.main._seed_database()
        total = self.user_repo.count_users()
        self.main._seed_database()
        self.assertEqual(self.user_repo.count_users(), total)

    def test_admin_nao_tem_matricula(self):
        """
        Garante que remover usuarios por matricula nunca alcanca o admin —
        e o que impede --remover-seed de trancar o sistema.
        """
        self.main._seed_database()
        admin = self.user_repo.get_user_by_username("admin")
        self.assertIsNone(admin["matricula"])


class TestRemocaoDoSeed(SeedTestBase):
    """A limpeza dos usuarios de exemplo."""

    def test_remove_exemplo_e_preserva_admin_e_reais(self):
        self.main._seed_database()
        AuthService(self.user_repo, PasswordHasher(), TokenStore()).register_user_with_options(
            username="AUDITOR REAL", password="Senha@123", role="fiscal",
            gerencia_id=None, supervisao_id=None, must_change_password=True,
            matricula="9000001",
        )

        removidos = self.user_repo.delete_users_by_matricula(matriculas_de_exemplo())

        self.assertEqual(removidos, len(matriculas_de_exemplo()))
        self.assertIsNotNone(self.user_repo.get_user_by_username("admin"))
        self.assertEqual(self._matriculas(), {"9000001"})

    def test_conjunto_vazio_nao_apaga_nada(self):
        self.main._seed_database()
        total = self.user_repo.count_users()
        self.assertEqual(self.user_repo.delete_users_by_matricula(set()), 0)
        self.assertEqual(self.user_repo.count_users(), total)

    def test_matricula_do_admin_nao_o_apaga(self):
        """
        Mesmo que alguem passe a matricula de um admin, o DELETE tem
        `role != 'admin'` como segunda barreira.
        """
        self.database.init_schema()
        AuthService(self.user_repo, PasswordHasher(), TokenStore()).register_user_with_options(
            username="admin", password="Senha@123", role="admin",
            gerencia_id=None, supervisao_id=None, must_change_password=False,
            matricula="99999",
        )
        self.assertEqual(self.user_repo.delete_users_by_matricula({"99999"}), 0)
        self.assertIsNotNone(self.user_repo.get_user_by_username("admin"))


class TestAuditoresDaPlanilha(unittest.TestCase):
    """
    Extracao de (matricula, nome) a partir da planilha.

    Skip quando o arquivo nao esta na maquina: ele nao e versionado, por
    conter dado pessoal de servidor.
    """

    CAMINHOS = [
        Path.home() / "Downloads" / "DADOS_ORDEM_SERVICO.xlsx",
        Path(__file__).parent / "dados" / "DADOS_ORDEM_SERVICO.xlsx",
    ]

    def setUp(self):
        self.planilha = next((c for c in self.CAMINHOS if c.is_file()), None)
        if self.planilha is None:
            self.skipTest("planilha da SEFAZ nao disponivel nesta maquina")

    def test_uma_entrada_por_pessoa(self):
        """Quem esta em duas equipes vira um usuario so, nao dois."""
        pessoas = auditores(self.planilha)
        matriculas = [m for m, _ in pessoas]
        self.assertEqual(len(matriculas), len(set(matriculas)))

    def test_so_matricula_numerica_e_nome_preenchido(self):
        for matricula, nome in auditores(self.planilha):
            self.assertTrue(matricula.isdigit(), f"matricula suspeita: {matricula!r}")
            self.assertTrue(nome.strip(), f"nome vazio para {matricula}")

    def test_nao_traz_cabecalho_nem_rodape(self):
        nomes = {nome for _, nome in auditores(self.planilha)}
        self.assertNotIn("Fiscal", nomes)
        self.assertFalse(any(n.startswith("Atualizado em") for n in nomes))

    def test_nenhuma_matricula_de_exemplo(self):
        """
        As matriculas ficticias do seed nao podem aparecer na planilha —
        se aparecessem, --remover-seed apagaria gente de verdade.
        """
        reais = {m for m, _ in auditores(self.planilha)}
        self.assertEqual(reais & matriculas_de_exemplo(), set())


if __name__ == "__main__":
    unittest.main()
