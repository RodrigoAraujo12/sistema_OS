"""
auth.py – Servico de autenticacao do Sistema Sefaz.

Responsavel por:
- Hash e verificacao de senhas (PBKDF2-SHA256 com salt aleatorio)
- Tokens de sessao com prazo de validade e revogacao (em memoria)
- Limite de tentativas de login
- Registro de usuarios e troca/reset de senha

Nota: Os tokens e o contador de tentativas ficam em memoria (dict). Se o
servidor reiniciar, todas as sessoes sao perdidas e os bloqueios zeram.
Com mais de um processo, cada um tem os seus. Para producao com varias
instancias, considerar JWT ou Redis.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from threading import Lock
from time import monotonic
from typing import Any
from uuid import uuid4

from .config import (
    LOGIN_BLOQUEIO_MINUTOS,
    LOGIN_MAX_FALHAS_IP,
    LOGIN_MAX_FALHAS_USUARIO,
    SESSION_TTL_MINUTES,
)
from .db import UserRepository

logger = logging.getLogger("sefaz.auth")

# 9 bytes -> 12 caracteres em base64url (~72 bits de entropia)
_SENHA_TEMP_BYTES = 9


def gerar_senha_temporaria() -> str:
    """
    Senha aleatoria de uso unico, entregue ao admin na criacao ou no reset.

    Cada usuario recebe a sua. Uma senha padrao compartilhada abriria
    qualquer conta que ainda nao tivesse trocado a senha para quem
    conhecesse a string — e ela aparece no .env, no seed e na tela do admin.
    """
    return secrets.token_urlsafe(_SENHA_TEMP_BYTES)


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
    """
    Tokens de sessao em memoria, com prazo de validade e revogacao.

    Guarda token -> (user_id, expira_em). O prazo existe para que um token
    vazado nao valha indefinidamente; a revogacao, para que trocar a senha
    ou ter a conta resetada derrube as sessoes abertas.
    """

    def __init__(self, ttl_segundos: float = SESSION_TTL_MINUTES * 60) -> None:
        self._ttl = ttl_segundos
        self._tokens: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def create(self, user_id: int) -> str:
        """Cria um token associado ao user_id, valido pelo TTL configurado."""
        token = uuid4().hex
        with self._lock:
            self._descartar_vencidos()
            self._tokens[token] = (user_id, monotonic() + self._ttl)
        return token

    def get_user_id(self, token: str) -> int | None:
        """user_id do token, ou None se invalido, revogado ou vencido."""
        with self._lock:
            item = self._tokens.get(token)
            if item is None:
                return None
            user_id, expira_em = item
            if monotonic() >= expira_em:
                del self._tokens[token]
                return None
            return user_id

    def revoke(self, token: str) -> None:
        """Invalida um token (logout)."""
        with self._lock:
            self._tokens.pop(token, None)

    def revoke_user(self, user_id: int, exceto: str | None = None) -> int:
        """
        Invalida todas as sessoes do usuario e retorna quantas caíram.

        'exceto' preserva um token — usado na troca de senha voluntaria,
        onde derrubar as outras sessoes e desejavel mas deslogar quem
        acabou de trocar a senha so atrapalharia.
        """
        with self._lock:
            alvos = [
                t for t, (uid, _) in self._tokens.items()
                if uid == user_id and t != exceto
            ]
            for t in alvos:
                del self._tokens[t]
        return len(alvos)

    def _descartar_vencidos(self) -> None:
        """Limpa os tokens vencidos. Chamado com o lock ja adquirido."""
        agora = monotonic()
        for t in [t for t, (_, exp) in self._tokens.items() if agora >= exp]:
            del self._tokens[t]


class LimitadorLogin:
    """
    Bloqueio temporario apos falhas seguidas de login.

    Conta por usuario e por IP em janelas independentes. A verificacao
    acontece ANTES de conferir a senha, o que tambem evita que uma rajada
    de tentativas consuma CPU com PBKDF2 (120 mil iteracoes por tentativa).
    """

    def __init__(
        self,
        max_usuario: int = LOGIN_MAX_FALHAS_USUARIO,
        max_ip: int = LOGIN_MAX_FALHAS_IP,
        bloqueio_segundos: float = LOGIN_BLOQUEIO_MINUTOS * 60,
    ) -> None:
        self._max = {"usuario": max_usuario, "ip": max_ip}
        self._bloqueio = bloqueio_segundos
        self._falhas: dict[tuple[str, str], tuple[int, float]] = {}
        self._lock = Lock()

    def segundos_de_bloqueio(self, usuario: str, ip: str | None) -> int:
        """
        Quanto falta do bloqueio, em segundos. 0 significa liberado.

        Devolve o maior prazo entre usuario e IP, para que a mensagem
        mostre o tempo real de espera.
        """
        agora = monotonic()
        restante = 0.0
        with self._lock:
            for escopo, valor in (("usuario", usuario.lower()), ("ip", ip or "")):
                if escopo == "ip" and not ip:
                    continue
                item = self._falhas.get((escopo, valor))
                if item is None:
                    continue
                contagem, ultima = item
                if agora - ultima >= self._bloqueio:
                    del self._falhas[(escopo, valor)]
                    continue
                if contagem >= self._max[escopo]:
                    restante = max(restante, self._bloqueio - (agora - ultima))
        return int(restante) + 1 if restante > 0 else 0

    def registrar_falha(self, usuario: str, ip: str | None) -> None:
        """Soma uma falha ao usuario e ao IP, reiniciando a janela."""
        agora = monotonic()
        with self._lock:
            for escopo, valor in (("usuario", usuario.lower()), ("ip", ip or "")):
                if escopo == "ip" and not ip:
                    continue
                contagem, ultima = self._falhas.get((escopo, valor), (0, agora))
                # Janela expirada reinicia a contagem do zero
                if agora - ultima >= self._bloqueio:
                    contagem = 0
                self._falhas[(escopo, valor)] = (contagem + 1, agora)

    def registrar_sucesso(self, usuario: str) -> None:
        """
        Zera o contador do usuario. O do IP permanece de proposito: senao
        bastaria intercalar um login valido para reiniciar a rajada.
        """
        with self._lock:
            self._falhas.pop(("usuario", usuario.lower()), None)

    def limpar(self) -> None:
        with self._lock:
            self._falhas.clear()


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

    def revoke_token(self, token: str) -> None:
        """Invalida um token de sessao (logout)."""
        self._token_store.revoke(token)

    def change_password(self, user_id: int, new_password: str, manter_token: str | None = None) -> None:
        """
        Troca a senha, desativa must_change_password e derruba as outras
        sessoes do usuario.

        'manter_token' preserva a sessao de quem esta trocando: derrubar
        todas expulsaria a propria pessoa no instante seguinte. As demais
        caem porque, se a troca foi motivada por suspeita de vazamento,
        deixar as antigas de pe anularia a troca.
        """
        password_hash, salt = self._hasher.hash_password(new_password)
        self._user_repo.update_password(user_id, password_hash, salt)
        self._user_repo.set_must_change_password(user_id, False)
        derrubadas = self._token_store.revoke_user(user_id, exceto=manter_token)
        logger.debug(
            "Senha alterada para user_id=%d (%d sessao(oes) encerrada(s)).", user_id, derrubadas,
        )

    def reset_password(self, user_id: int, new_password: str) -> None:
        """
        Reseta a senha, ativa must_change_password e derruba TODAS as
        sessoes do usuario.

        Aqui nao ha token a preservar: quem reseta e o admin, e o dono da
        conta nao deve continuar com a sessao anterior valida.
        """
        password_hash, salt = self._hasher.hash_password(new_password)
        self._user_repo.update_password(user_id, password_hash, salt)
        self._user_repo.set_must_change_password(user_id, True)
        derrubadas = self._token_store.revoke_user(user_id)
        logger.debug(
            "Senha resetada para user_id=%d (must_change=True, %d sessao(oes) encerrada(s)).",
            user_id, derrubadas,
        )
