"""
auth.py – Servico de autenticacao do Sistema Sefaz.

Responsavel por:
- Hash e verificacao de senhas (PBKDF2-SHA256 com salt aleatorio)
- Geracao e validacao de tokens de sessao (em memoria)
- Registro de usuarios e troca/reset de senha

Nota: Os tokens ficam em memoria (dict). Se o servidor reiniciar,
todas as sessoes sao perdidas. Para producao, considerar JWT ou Redis.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any
from uuid import uuid4

from .db import UserRepository

logger = logging.getLogger("sefaz.auth")


class PasswordHasher:
    """Gera e verifica hashes de senha usando PBKDF2-HMAC-SHA256."""

    PBKDF2_ITERATIONS = 120_000
    SALT_BYTES = 16

    def hash_password(self, password: str, salt: str | None = None) -> tuple[str, str]:
        """Retorna (hash_hex, salt_hex). Se salt nao for informado, gera um novo."""
        salt_value = salt or secrets.token_hex(self.SALT_BYTES)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt_value.encode("utf-8"), self.PBKDF2_ITERATIONS
        )
        return digest.hex(), salt_value

    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Compara a senha fornecida com o hash armazenado de forma segura."""
        check_hash, _ = self.hash_password(password, salt)
        return secrets.compare_digest(check_hash, password_hash)


class TokenStore:
    """Armazena tokens de sessao em memoria (mapeamento token -> user_id)."""

    def __init__(self) -> None:
        self._tokens: dict[str, int] = {}

    def create(self, user_id: int) -> str:
        """Cria um token UUID associado ao user_id."""
        token = uuid4().hex
        self._tokens[token] = user_id
        return token

    def get_user_id(self, token: str) -> int | None:
        """Retorna o user_id vinculado ao token, ou None se invalido."""
        return self._tokens.get(token)


class AuthService:
    """Orquestra autenticacao, registro e gerenciamento de senhas."""

    def __init__(
        self, user_repo: UserRepository, hasher: PasswordHasher, token_store: TokenStore
    ) -> None:
        self._user_repo = user_repo
        self._hasher = hasher
        self._token_store = token_store

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        """Valida credenciais. Retorna os dados do usuario ou None."""
        user = self._user_repo.get_user_by_username(username)
        if not user:
            return None
        if not self._hasher.verify_password(password, user["password_hash"], user["salt"]):
            return None
        return user

    def create_token(self, user_id: int) -> str:
        """Gera um novo token de sessao para o usuario."""
        return self._token_store.create(user_id)

    def get_user_from_token(self, token: str) -> dict[str, Any] | None:
        """Busca o usuario a partir de um token de sessao."""
        user_id = self._token_store.get_user_id(token)
        if not user_id:
            return None
        return self._user_repo.get_user_by_id(user_id)

    def register_user(self, username: str, password: str, role: str) -> int:
        """Atalho para registrar um usuario sem opcoes extras."""
        return self.register_user_with_options(
            username=username,
            password=password,
            role=role,
            gerencia_id=None,
            supervisao_id=None,
            must_change_password=False,
        )

    def register_user_with_options(
        self,
        username: str,
        password: str,
        role: str,
        gerencia_id: int | None,
        supervisao_id: int | None,
        must_change_password: bool,
        matricula: str | None = None,
    ) -> int:
        """Registra um usuario com todas as opcoes (cargo, lotacao, flag de troca)."""
        password_hash, salt = self._hasher.hash_password(password)
        user_id = self._user_repo.create_user(
            username,
            password_hash,
            salt,
            role,
            gerencia_id,
            supervisao_id,
            must_change_password,
            matricula,
        )
        logger.debug("Usuario registrado: id=%d, username='%s'.", user_id, username)
        return user_id

    def change_password(self, user_id: int, new_password: str) -> None:
        """Troca a senha e desativa a flag must_change_password."""
        password_hash, salt = self._hasher.hash_password(new_password)
        self._user_repo.update_password(user_id, password_hash, salt)
        self._user_repo.set_must_change_password(user_id, False)
        logger.debug("Senha alterada para user_id=%d.", user_id)

    def reset_password(self, user_id: int, new_password: str) -> None:
        """Reseta a senha e ativa a flag must_change_password (forcando troca no login)."""
        password_hash, salt = self._hasher.hash_password(new_password)
        self._user_repo.update_password(user_id, password_hash, salt)
        self._user_repo.set_must_change_password(user_id, True)
        logger.debug("Senha resetada para user_id=%d (must_change=True).", user_id)
