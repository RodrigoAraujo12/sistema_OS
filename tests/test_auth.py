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


if __name__ == "__main__":
    unittest.main()
