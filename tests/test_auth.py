"""
Testes unitarios para o modulo auth.py – autenticacao do Sistema Sefaz.

Cobre: hash de senha, verificacao, criacao de token, autenticacao,
registro de usuario, troca e reset de senha.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.auth import AuthService, PasswordHasher, TokenStore


class TestPasswordHasher(unittest.TestCase):
    """Testes para a classe PasswordHasher."""

    def setUp(self):
        self.hasher = PasswordHasher()

    def test_hash_returns_tuple(self):
        h, s = self.hasher.hash_password("senha123")
        self.assertIsInstance(h, str)
        self.assertIsInstance(s, str)
        self.assertTrue(len(h) > 0)
        self.assertTrue(len(s) > 0)

    def test_same_password_different_salt_different_hash(self):
        h1, s1 = self.hasher.hash_password("senha123")
        h2, s2 = self.hasher.hash_password("senha123")
        self.assertNotEqual(s1, s2, "Salts devem ser diferentes")
        self.assertNotEqual(h1, h2, "Hashes com salts diferentes devem ser diferentes")

    def test_same_password_same_salt_same_hash(self):
        h1, _ = self.hasher.hash_password("senha123", salt="fixedsalt")
        h2, _ = self.hasher.hash_password("senha123", salt="fixedsalt")
        self.assertEqual(h1, h2)

    def test_verify_correct_password(self):
        h, s = self.hasher.hash_password("minha_senha")
        self.assertTrue(self.hasher.verify_password("minha_senha", h, s))

    def test_verify_wrong_password(self):
        h, s = self.hasher.hash_password("minha_senha")
        self.assertFalse(self.hasher.verify_password("senha_errada", h, s))

    def test_verify_empty_password(self):
        h, s = self.hasher.hash_password("")
        self.assertTrue(self.hasher.verify_password("", h, s))
        self.assertFalse(self.hasher.verify_password("x", h, s))


class TestTokenStore(unittest.TestCase):
    """Testes para a classe TokenStore."""

    def setUp(self):
        self.store = TokenStore()

    def test_create_returns_string(self):
        token = self.store.create(1)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_get_user_id(self):
        token = self.store.create(42)
        self.assertEqual(self.store.get_user_id(token), 42)

    def test_invalid_token_returns_none(self):
        self.assertIsNone(self.store.get_user_id("token_invalido"))

    def test_multiple_tokens_different_users(self):
        t1 = self.store.create(1)
        t2 = self.store.create(2)
        self.assertNotEqual(t1, t2)
        self.assertEqual(self.store.get_user_id(t1), 1)
        self.assertEqual(self.store.get_user_id(t2), 2)


class TestAuthService(unittest.TestCase):
    """Testes para a classe AuthService (com mocks)."""

    def setUp(self):
        self.mock_repo = MagicMock()
        self.hasher = PasswordHasher()
        self.token_store = TokenStore()
        self.service = AuthService(self.mock_repo, self.hasher, self.token_store)

    def test_authenticate_valid_user(self):
        h, s = self.hasher.hash_password("admin123")
        self.mock_repo.get_user_by_username.return_value = {
            "id": 1, "username": "admin", "password_hash": h, "salt": s, "role": "admin"
        }
        result = self.service.authenticate_user("admin", "admin123")
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "admin")

    def test_authenticate_wrong_password(self):
        h, s = self.hasher.hash_password("admin123")
        self.mock_repo.get_user_by_username.return_value = {
            "id": 1, "username": "admin", "password_hash": h, "salt": s, "role": "admin"
        }
        result = self.service.authenticate_user("admin", "errada")
        self.assertIsNone(result)

    def test_authenticate_nonexistent_user(self):
        self.mock_repo.get_user_by_username.return_value = None
        result = self.service.authenticate_user("naoexiste", "qualquer")
        self.assertIsNone(result)

    def test_create_and_validate_token(self):
        self.mock_repo.get_user_by_id.return_value = {
            "id": 1, "username": "admin", "role": "admin"
        }
        token = self.service.create_token(1)
        user = self.service.get_user_from_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], 1)

    def test_invalid_token_returns_none(self):
        user = self.service.get_user_from_token("invalido")
        self.assertIsNone(user)

    def test_register_user(self):
        self.mock_repo.create_user.return_value = 10
        user_id = self.service.register_user("novo", "senha", "fiscal")
        self.assertEqual(user_id, 10)
        self.mock_repo.create_user.assert_called_once()

    def test_change_password(self):
        self.service.change_password(1, "nova_senha")
        self.mock_repo.update_password.assert_called_once()
        self.mock_repo.set_must_change_password.assert_called_once_with(1, False)

    def test_reset_password(self):
        self.service.reset_password(1, "temp_senha")
        self.mock_repo.update_password.assert_called_once()
        self.mock_repo.set_must_change_password.assert_called_once_with(1, True)



class TestHashVersionadoERehash(unittest.TestCase):
    """
    O hash carrega o numero de iteracoes; o formato antigo (so o hex,
    120 mil iteracoes) continua valido e e refeito no login.
    """

    SALT = "abc123"
    SENHA = "Senha@123"

    def setUp(self):
        self.hasher = PasswordHasher()

    def _hash_legado(self, senha: str) -> str:
        import hashlib

        return hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), self.SALT.encode("utf-8"), 120_000,
        ).hex()

    def test_hash_novo_carrega_algoritmo_e_iteracoes(self):
        h, _ = self.hasher.hash_password(self.SENHA)
        self.assertTrue(h.startswith(f"pbkdf2_sha256${self.hasher.PBKDF2_ITERATIONS}$"))
        self.assertFalse(self.hasher.precisa_rehash(h))

    def test_hash_legado_continua_valido_e_pede_rehash(self):
        legado = self._hash_legado(self.SENHA)
        self.assertTrue(self.hasher.verify_password(self.SENHA, legado, self.SALT))
        self.assertFalse(self.hasher.verify_password("outra", legado, self.SALT))
        self.assertTrue(self.hasher.precisa_rehash(legado))

    def test_formato_desconhecido_nao_autentica(self):
        self.assertFalse(self.hasher.verify_password("x", "md5$1$abc", "s"))
        self.assertFalse(self.hasher.verify_password("x", "pbkdf2_sha256$abc$def", "s"))

    def test_iteracoes_de_producao_verificam(self):
        """Os testes rodam com PBKDF2_ITERATIONS baixo; este confere o valor real uma vez."""

        class Producao(PasswordHasher):
            PBKDF2_ITERATIONS = 600_000

        hasher = Producao()
        h, s = hasher.hash_password(self.SENHA)
        self.assertTrue(h.startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(hasher.verify_password(self.SENHA, h, s))

    def test_login_refaz_hash_legado(self):
        repo = MagicMock()
        repo.get_user_by_username.return_value = {
            "id": 7, "username": "u", "password_hash": self._hash_legado(self.SENHA),
            "salt": self.SALT, "role": "fiscal",
        }
        service = AuthService(repo, self.hasher, TokenStore())

        self.assertIsNone(service.authenticate_user("u", "errada"))
        repo.update_password.assert_not_called()

        user = service.authenticate_user("u", self.SENHA)
        self.assertIsNotNone(user)
        repo.update_password.assert_called_once()
        user_id, novo_hash, novo_salt = repo.update_password.call_args[0]
        self.assertEqual(user_id, 7)
        self.assertTrue(self.hasher.verify_password(self.SENHA, novo_hash, novo_salt))
        self.assertFalse(self.hasher.precisa_rehash(novo_hash))

    def test_usuario_inexistente_nao_devolve_na_hora(self):
        """Mesmo custo de PBKDF2 para usuario inexistente: o tempo nao entrega logins."""
        repo = MagicMock()
        repo.get_user_by_username.return_value = None
        hasher = MagicMock(wraps=self.hasher)
        service = AuthService(repo, hasher, TokenStore())
        self.assertIsNone(service.authenticate_user("fantasma", "x"))
        hasher.gastar_tempo_de_verificacao.assert_called_once()


class TestLimitadorLoginTeto(unittest.TestCase):
    """O contador de falhas nao cresce sem limite com usernames inventados."""

    def test_respeita_o_teto_e_preserva_bloqueio_em_vigor(self):
        from backend.auth import LimitadorLogin

        lim = LimitadorLogin(max_usuario=3, max_ip=100, bloqueio_segundos=900, max_entradas=50)
        for _ in range(3):
            lim.registrar_falha("alvo", None)
        self.assertGreater(lim.segundos_de_bloqueio("alvo", None), 0)

        for i in range(500):
            lim.registrar_falha(f"fantasma{i}", None)

        self.assertLessEqual(len(lim._falhas), 50)
        # O bloqueio real foi a ultima coisa a ceder lugar: continua de pe
        self.assertGreater(lim.segundos_de_bloqueio("alvo", None), 0)


if __name__ == "__main__":
    unittest.main()
