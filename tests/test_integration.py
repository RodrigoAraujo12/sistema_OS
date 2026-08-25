"""
Testes de integracao – Sistema Sefaz.

Usa o TestClient do FastAPI para exercitar os endpoints HTTP de ponta
a ponta (request -> middleware -> handler -> banco -> response), com
banco SQLite em memoria isolado por teste.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

# ─── Helpers ────────────────────────────────────────────────────

# Senha do admin nos testes (o seed real gera uma aleatoria).
ADMIN_PASSWORD_TESTE = "admin123"

# Senha atribuida aos usuarios do seed quando um teste precisa entrar como
# eles. Passa no validador de forca de PasswordChangeRequest.
SENHA_TESTE = "Teste@123"


def _create_app(db_path: str) -> TestClient:
    """
    Cria uma instancia isolada da aplicacao apontando para um banco
    SQLite temporario, executa o lifespan (seed) e retorna o TestClient.
    """
    # Precisa patchar DB_PATH e database/repos/auth_service ANTES
    # do import, pois main.py instancia tudo em nivel de modulo.
    # A abordagem mais limpa e recriar os objetos com o db temporario.

    from backend.auth import AuthService, PasswordHasher, TokenStore
    from backend.db import (
        Database,
        EquipeFiscalRepository,
        GerenciaRepository,
        SupervisaoRepository,
        UserRepository,
    )

    database = Database(db_path)
    user_repo = UserRepository(database)
    gerencia_repo = GerenciaRepository(database)
    supervisao_repo = SupervisaoRepository(database)
    equipe_repo = EquipeFiscalRepository(database)
    auth_service = AuthService(user_repo, PasswordHasher(), TokenStore())

    # Patcheia os objetos do modulo main com nossas instancias isoladas
    import backend.main as main_module

    main_module.database = database
    main_module.user_repo = user_repo
    main_module.gerencia_repo = gerencia_repo
    main_module.supervisao_repo = supervisao_repo
    main_module.equipe_repo = equipe_repo
    main_module.auth_service = auth_service
    # Sem isso o seed gera uma senha aleatoria para o admin e o teste nao
    # teria como entrar (e o proposito de nao existir senha fixa).
    main_module.ADMIN_PASSWORD = ADMIN_PASSWORD_TESTE

    client = TestClient(main_module.app)
    return client


class IntegrationTestBase(unittest.TestCase):
    """Base com setup/teardown que cria um banco isolado + TestClient."""

    def setUp(self):
        # ATF_BASE_URL vazio forca o caminho MOCK. Sem isso a suite chama o
        # servico real do ATF (o .env de desenvolvimento tem a URL), o que
        # deixa o resultado dependente da rede e de dados de terceiros.
        self._atf_patch = patch("backend.config.ATF_BASE_URL", "")
        self._atf_patch.start()
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self.client = _create_app(self.db_path)
        # Entra no context manager do TestClient para disparar o lifespan (seed)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._atf_patch.stop()
        try:
            Path(self._tmp.name).unlink(missing_ok=True)
        except OSError:
            pass

    # ── Helpers de conveniencia ─────────────────────────────────

    def _login(self, username: str = "admin", password: str = ADMIN_PASSWORD_TESTE) -> str:
        """Faz login e retorna o token."""
        r = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def _login_como(self, username: str) -> str:
        """
        Loga como um usuario do seed.

        Os usuarios do seed nascem com senha aleatoria que e descartada, e
        com must_change_password ativa. O teste define uma senha conhecida
        direto pelo servico — change_password tambem baixa a flag, que e o
        que permite chamar o resto da API.
        """
        import backend.main as main_module

        user = main_module.user_repo.get_user_by_username(username)
        self.assertIsNotNone(user, f"usuario '{username}' nao existe no seed")
        main_module.auth_service.change_password(int(user["id"]), SENHA_TESTE)
        return self._login(username, SENHA_TESTE)

    def _auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _admin_header(self) -> dict[str, str]:
        return self._auth_header(self._login())


# ═══════════════════════════════════════════════════════════════
# 1. Autenticacao
# ═══════════════════════════════════════════════════════════════


class TestAuthEndpoints(IntegrationTestBase):
    """Testa fluxo de login e troca de senha via HTTP."""

    def test_login_success(self):
        r = self.client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD_TESTE})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("token", body)
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["username"], "admin")

    def test_login_wrong_password(self):
        r = self.client.post("/auth/login", json={"username": "admin", "password": "errada"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Credenciais invalidas", r.json()["detail"])

    def test_login_nonexistent_user(self):
        r = self.client.post("/auth/login", json={"username": "naoexiste", "password": "x"})
        self.assertEqual(r.status_code, 401)

    def test_login_returns_seed_user_fields(self):
        """Garante que o seed cria gerentes com gerencia_name preenchido."""
        import backend.main as main_module

        user = main_module.user_repo.get_user_by_username("Roberto Santos")
        main_module.auth_service.reset_password(int(user["id"]), SENHA_TESTE)
        r = self.client.post(
            "/auth/login",
            json={"username": "Roberto Santos", "password": SENHA_TESTE},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["role"], "gerente")
        self.assertIsNotNone(body["gerencia_id"])
        self.assertIsNotNone(body["gerencia_name"])
        self.assertTrue(body["must_change_password"])

    def test_change_password_success(self):
        token = self._login()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": ADMIN_PASSWORD_TESTE, "new_password": "Nova@1234"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "ok")
        # Verifica que a nova senha funciona
        r2 = self.client.post("/auth/login", json={"username": "admin", "password": "Nova@1234"})
        self.assertEqual(r2.status_code, 200)

    def test_change_password_wrong_current(self):
        token = self._login()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": "errada", "new_password": "Nova@1234"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 400)

    def test_change_password_too_short(self):
        token = self._login()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": ADMIN_PASSWORD_TESTE, "new_password": "ab"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 422)  # validation error


# ═══════════════════════════════════════════════════════════════
# 2. Middleware / Autorizacao
# ═══════════════════════════════════════════════════════════════


class TestSessaoEToken(IntegrationTestBase):
    """Prazo de validade, revogacao e logout do token de sessao."""

    def test_logout_invalida_o_token_no_servidor(self):
        token = self._login()
        H = self._auth_header(token)
        self.assertEqual(self.client.get("/alertas", headers=H).status_code, 200)

        self.assertEqual(self.client.post("/auth/logout", headers=H).status_code, 200)
        r = self.client.get("/alertas", headers=H)
        self.assertEqual(r.status_code, 401, "o token deveria estar revogado")

    def test_token_vencido_e_recusado(self):
        import backend.main as main_module

        token = self._login()
        H = self._auth_header(token)
        self.assertEqual(self.client.get("/alertas", headers=H).status_code, 200)

        # Encurta o TTL e reposiciona o vencimento do token para o passado
        store = main_module.auth_service._token_store
        user_id, _ = store._tokens[token]
        store._tokens[token] = (user_id, 0.0)

        r = self.client.get("/alertas", headers=H)
        self.assertEqual(r.status_code, 401)
        self.assertIn("expirada", r.json()["detail"])

    def test_reset_pelo_admin_derruba_a_sessao_do_usuario(self):
        """
        Conta resetada administrativamente nao pode continuar aberta na
        maquina de quem estava usando.
        """
        token_fiscal = self._login_como("Carlos Mendes")
        H = self._auth_header(token_fiscal)
        self.assertEqual(self.client.get("/ordens", headers=H).status_code, 200)

        admin = self._admin_header()
        alvo = next(
            u for u in self.client.get("/admin/users", headers=admin).json()
            if u["username"] == "Carlos Mendes"
        )
        self.client.post(f"/admin/users/{alvo['id']}/reset-password", headers=admin)

        self.assertEqual(self.client.get("/ordens", headers=H).status_code, 401)

    def test_troca_de_senha_mantem_a_sessao_atual_e_derruba_as_outras(self):
        token_a = self._login()
        token_b = self._login()  # segunda sessao do mesmo usuario
        self.assertNotEqual(token_a, token_b)

        r = self.client.post(
            "/auth/change-password",
            json={"current_password": ADMIN_PASSWORD_TESTE, "new_password": "Nova@1234"},
            headers=self._auth_header(token_b),
        )
        self.assertEqual(r.status_code, 200, r.text)

        # A sessao que trocou continua; a outra caiu
        self.assertEqual(self.client.get("/alertas", headers=self._auth_header(token_b)).status_code, 200)
        self.assertEqual(self.client.get("/alertas", headers=self._auth_header(token_a)).status_code, 401)


class TestLimiteDeTentativasLogin(IntegrationTestBase):
    """Forca bruta em /auth/login e o custo de CPU que ela provocava."""

    def setUp(self):
        super().setUp()
        import backend.main as main_module

        main_module.limitador_login.limpar()
        self.addCleanup(main_module.limitador_login.limpar)

    def _tenta(self, senha: str):
        return self.client.post("/auth/login", json={"username": "admin", "password": senha})

    def test_bloqueia_apos_o_limite_de_falhas(self):
        for i in range(5):
            self.assertEqual(self._tenta("errada").status_code, 401, f"tentativa {i + 1}")
        r = self._tenta("errada")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        self.assertIn("Muitas tentativas", r.json()["detail"])

    def test_bloqueio_vale_mesmo_com_a_senha_certa(self):
        """
        Senao a rajada poderia continuar indefinidamente: bastaria a
        tentativa certa passar no meio para o atacante saber que acertou.
        """
        for _ in range(5):
            self._tenta("errada")
        self.assertEqual(self._tenta(ADMIN_PASSWORD_TESTE).status_code, 429)

    def test_login_valido_zera_o_contador_do_usuario(self):
        for _ in range(3):
            self._tenta("errada")
        self.assertEqual(self._tenta(ADMIN_PASSWORD_TESTE).status_code, 200)
        # Depois do sucesso, o orcamento de falhas comeca de novo
        for i in range(5):
            self.assertEqual(self._tenta("errada").status_code, 401, f"tentativa {i + 1}")

    def test_usuario_inexistente_tambem_conta(self):
        for _ in range(5):
            self.client.post("/auth/login", json={"username": "fantasma", "password": "x"})
        r = self.client.post("/auth/login", json={"username": "fantasma", "password": "x"})
        self.assertEqual(r.status_code, 429)


class TestAuthMiddleware(IntegrationTestBase):
    """Testa que rotas protegidas rejeitam acessos indevidos."""

    def test_no_token_returns_401(self):
        r = self.client.get("/admin/gerencias")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Token ausente", r.json()["detail"])

    def test_invalid_token_returns_401(self):
        r = self.client.get("/admin/gerencias", headers={"Authorization": "Bearer invalidtoken"})
        self.assertEqual(r.status_code, 401)
        # Mensagem unica para token inexistente, revogado ou vencido — nao
        # ha ganho em distinguir os casos para quem esta do lado de fora.
        self.assertIn("Sessao invalida ou expirada", r.json()["detail"])

    def test_non_admin_cannot_access_admin_routes(self):
        """Fiscal nao pode acessar /admin/*."""
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/admin/gerencias", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)
        self.assertIn("Acesso negado", r.json()["detail"])

    def test_gerente_cannot_access_admin_routes(self):
        token = self._login_como("Roberto Santos")
        r = self.client.get("/admin/users", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)


# ═══════════════════════════════════════════════════════════════
# 3. Gerencias CRUD
# ═══════════════════════════════════════════════════════════════


class TestGerenciasEndpoints(IntegrationTestBase):
    """Testa CRUD de gerencias via endpoints admin."""

    def test_list_gerencias(self):
        h = self._admin_header()
        r = self.client.get("/admin/gerencias", headers=h)
        self.assertEqual(r.status_code, 200)
        # Seed cria 3 gerencias
        self.assertEqual(len(r.json()), 3)

    def test_create_gerencia(self):
        h = self._admin_header()
        r = self.client.post("/admin/gerencias", json={"name": "Nova Gerencia"}, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Nova Gerencia")
        # Deve ter 4 agora
        r2 = self.client.get("/admin/gerencias", headers=h)
        self.assertEqual(len(r2.json()), 4)

    def test_create_gerencia_duplicate(self):
        h = self._admin_header()
        self.client.post("/admin/gerencias", json={"name": "Duplicada"}, headers=h)
        r = self.client.post("/admin/gerencias", json={"name": "Duplicada"}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("ja existe", r.json()["detail"])

    def test_create_gerencia_name_too_short(self):
        h = self._admin_header()
        r = self.client.post("/admin/gerencias", json={"name": "X"}, headers=h)
        self.assertEqual(r.status_code, 422)

    def test_update_gerencia(self):
        h = self._admin_header()
        gerencias = self.client.get("/admin/gerencias", headers=h).json()
        gid = gerencias[0]["id"]
        r = self.client.put(f"/admin/gerencias/{gid}", json={"name": "Nome Atualizado"}, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_update_gerencia_not_found(self):
        h = self._admin_header()
        r = self.client.put("/admin/gerencias/9999", json={"name": "Qualquer"}, headers=h)
        self.assertEqual(r.status_code, 404)


# ═══════════════════════════════════════════════════════════════
# 4. Supervisoes CRUD
# ═══════════════════════════════════════════════════════════════


class TestSupervisoesEndpoints(IntegrationTestBase):
    """Testa CRUD de supervisoes via endpoints admin."""

    def test_list_supervisoes(self):
        h = self._admin_header()
        r = self.client.get("/admin/supervisoes", headers=h)
        self.assertEqual(r.status_code, 200)
        # Seed cria 6 supervisoes (2 por gerencia)
        self.assertEqual(len(r.json()), 6)

    def test_create_supervisao(self):
        h = self._admin_header()
        gerencias = self.client.get("/admin/gerencias", headers=h).json()
        gid = gerencias[0]["id"]
        r = self.client.post(
            "/admin/supervisoes",
            json={"name": "Supervisao Nova", "gerencia_id": gid},
            headers=h,
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["name"], "Supervisao Nova")
        self.assertEqual(body["gerencia_id"], gid)

    def test_create_supervisao_invalid_gerencia(self):
        h = self._admin_header()
        r = self.client.post(
            "/admin/supervisoes",
            json={"name": "Sup X", "gerencia_id": 9999},
            headers=h,
        )
        self.assertEqual(r.status_code, 400)

    def test_update_supervisao(self):
        h = self._admin_header()
        supervisoes = self.client.get("/admin/supervisoes", headers=h).json()
        sid = supervisoes[0]["id"]
        gerencias = self.client.get("/admin/gerencias", headers=h).json()
        gid = gerencias[0]["id"]
        r = self.client.put(
            f"/admin/supervisoes/{sid}",
            json={"name": "Sup Renomeada", "gerencia_id": gid},
            headers=h,
        )
        self.assertEqual(r.status_code, 200)

    def test_update_supervisao_not_found(self):
        h = self._admin_header()
        gerencias = self.client.get("/admin/gerencias", headers=h).json()
        gid = gerencias[0]["id"]
        r = self.client.put(
            "/admin/supervisoes/9999",
            json={"name": "Inexistente", "gerencia_id": gid},
            headers=h,
        )
        self.assertEqual(r.status_code, 404)

    def test_update_supervisao_invalid_gerencia(self):
        h = self._admin_header()
        supervisoes = self.client.get("/admin/supervisoes", headers=h).json()
        sid = supervisoes[0]["id"]
        r = self.client.put(
            f"/admin/supervisoes/{sid}",
            json={"name": "Sup Teste", "gerencia_id": 9999},
            headers=h,
        )
        self.assertEqual(r.status_code, 400)


# ═══════════════════════════════════════════════════════════════
# 5. Users CRUD
# ═══════════════════════════════════════════════════════════════


class TestUsersEndpoints(IntegrationTestBase):
    """Testa CRUD de usuarios via endpoints admin."""

    def _get_valid_ids(self, headers: dict) -> tuple[int, int]:
        """Retorna (gerencia_id, supervisao_id) validos do seed."""
        supervisoes = self.client.get("/admin/supervisoes", headers=headers).json()
        s = supervisoes[0]
        return s["gerencia_id"], s["id"]

    def test_list_users(self):
        h = self._admin_header()
        r = self.client.get("/admin/users", headers=h)
        self.assertEqual(r.status_code, 200)
        # Seed cria: 1 admin + 3 gerentes + 6 supervisores + 15 fiscais = 25
        self.assertEqual(len(r.json()), 25)

    def test_create_user(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        r = self.client.post(
            "/admin/users",
            json={
                "username": "Novo Fiscal",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "99999",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["username"], "Novo Fiscal")
        self.assertEqual(body["role"], "fiscal")
        self.assertEqual(body["matricula"], "99999")

    def test_create_user_duplicate(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        payload = {
            "username": "Duplicado",
            "role": "fiscal",
            "gerencia_id": gid,
            "supervisao_id": sid,
            "matricula": "88888",
        }
        self.client.post("/admin/users", json=payload, headers=h)
        r = self.client.post("/admin/users", json=payload, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("ja existe", r.json()["detail"])

    def test_create_user_invalid_role(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        r = self.client.post(
            "/admin/users",
            json={
                "username": "X",
                "role": "admin",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "77777",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Cargo invalido", r.json()["detail"])

    def test_create_user_invalid_gerencia(self):
        h = self._admin_header()
        _, sid = self._get_valid_ids(h)
        r = self.client.post(
            "/admin/users",
            json={
                "username": "X",
                "role": "fiscal",
                "gerencia_id": 9999,
                "supervisao_id": sid,
                "matricula": "66666",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 400)

    def test_create_user_cascata_invalida(self):
        """Supervisao de outra gerencia deve dar erro de cascata."""
        h = self._admin_header()
        gerencias = self.client.get("/admin/gerencias", headers=h).json()
        supervisoes = self.client.get("/admin/supervisoes", headers=h).json()
        # Pega uma supervisao que NAO pertence a primeira gerencia
        gid = gerencias[0]["id"]
        wrong_sup = next(s for s in supervisoes if s["gerencia_id"] != gid)
        r = self.client.post(
            "/admin/users",
            json={
                "username": "Cascata",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": wrong_sup["id"],
                "matricula": "55555",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Cascata invalida", r.json()["detail"])

    def test_update_user(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        users = self.client.get("/admin/users", headers=h).json()
        # Pega um usuario nao-admin
        target = next(u for u in users if u["role"] != "admin")
        r = self.client.put(
            f"/admin/users/{target['id']}",
            json={
                "username": "Nome Atualizado",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": target["matricula"],
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_update_admin_forbidden(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        users = self.client.get("/admin/users", headers=h).json()
        admin_user = next(u for u in users if u["role"] == "admin")
        r = self.client.put(
            f"/admin/users/{admin_user['id']}",
            json={
                "username": "Hacked",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "00000",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 403)

    def test_update_user_not_found(self):
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        r = self.client.put(
            "/admin/users/9999",
            json={
                "username": "X",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "11111",
            },
            headers=h,
        )
        self.assertEqual(r.status_code, 404)

    def test_reset_password(self):
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        target = next(u for u in users if u["role"] != "admin")
        r = self.client.post(f"/admin/users/{target['id']}/reset-password", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertIn("temporary_password", r.json())

    def test_reset_password_not_found(self):
        h = self._admin_header()
        r = self.client.post("/admin/users/9999/reset-password", headers=h)
        self.assertEqual(r.status_code, 404)


# ═══════════════════════════════════════════════════════════════
# 6. Delete User
# ═══════════════════════════════════════════════════════════════


class TestDeleteUser(IntegrationTestBase):
    """Testa o endpoint DELETE /admin/users/{user_id}."""

    def test_delete_user_success(self):
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        target = next(u for u in users if u["role"] == "fiscal")
        r = self.client.delete(f"/admin/users/{target['id']}", headers=h)
        self.assertEqual(r.status_code, 204)
        # Confirma que foi removido
        users2 = self.client.get("/admin/users", headers=h).json()
        ids = [u["id"] for u in users2]
        self.assertNotIn(target["id"], ids)

    def test_delete_self_forbidden(self):
        token = self._login()
        login_data = self.client.post(
            "/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD_TESTE}
        ).json()
        admin_id = login_data["user_id"]
        r = self.client.delete(
            f"/admin/users/{admin_id}", headers=self._auth_header(token)
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("proprio", r.json()["detail"])

    def test_delete_admin_forbidden(self):
        """Mesmo que seja outro admin (hipotetico), nao pode deletar admin."""
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        admin_user = next(u for u in users if u["role"] == "admin")
        r = self.client.delete(f"/admin/users/{admin_user['id']}", headers=h)
        # Sera 400 (auto-delete) ou 403 (is admin) – ambos bloqueiam
        self.assertIn(r.status_code, (400, 403))

    def test_delete_not_found(self):
        h = self._admin_header()
        r = self.client.delete("/admin/users/9999", headers=h)
        self.assertEqual(r.status_code, 404)


# ═══════════════════════════════════════════════════════════════
# 7. Ordens de Servico (com mock da API externa)
# ═══════════════════════════════════════════════════════════════


_MOCK_OS_LIST = [
    {
        "numero": "OS-001",
        "tipo": "Fiscalizacao",
        "ie": "123456789",
        "razao_social": "Empresa Teste LTDA",
        "matricula_supervisor": "23456",
        "fiscais": ["Carlos Mendes"],
        "status": "Em andamento",
        "prioridade": "Urgente",
        "data_abertura": "2025-06-01",
        "data_ciencia": "2025-06-02",
        "data_ultima_movimentacao": "2025-06-10",
        "dias_parado": 5,
    },
    {
        "numero": "OS-002",
        "tipo": "Diligencia",
        "ie": "987654321",
        "razao_social": "Outra Empresa SA",
        "matricula_supervisor": "23458",
        "fiscais": ["Maria Santos"],
        "status": "Aberta",
        "prioridade": "",
        "data_abertura": "2025-07-01",
        "data_ciencia": None,
        "data_ultima_movimentacao": None,
        "dias_parado": 0,
    },
]


class TestOrdensEndpoints(IntegrationTestBase):
    """
    Testa /ordens contra o MOCK ATF (25 OS), cujas matriculas de fiscais
    (34567-34571) sao as mesmas dos fiscais criados pelo seed.
    """

    def _ordens(self, token: str, **params) -> dict:
        r = self.client.get("/ordens", headers=self._auth_header(token), params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_admin_ve_todas(self):
        body = self._ordens(self._login())
        self.assertEqual(body["paginacao"]["total_registros"], 25)

    def test_fiscal_so_ve_as_proprias(self):
        """Carlos Mendes (34567) nao pode ver OS de outro fiscal."""
        body = self._ordens(self._login_como("Carlos Mendes"), limite=50)
        self.assertGreater(len(body["ordens"]), 0, "o fiscal deveria ter OS no mock")
        for os_item in body["ordens"]:
            matriculas = {f["matricula"] for f in os_item["fiscais"]}
            self.assertIn("34567", matriculas, f"OS {os_item['numero_os']} nao e do fiscal")

    def test_supervisor_ve_a_equipe_e_nao_a_de_outra_supervisao(self):
        """
        Patricia Oliveira supervisiona a Supervisao Fiscal A (34567-34569).

        O criterio e "toda OS vista tem alguem da equipe designado", e nao
        "matricula de fora nunca aparece": uma OS pode ter fiscais das duas
        supervisoes — OS-2026-005 tem 34568 (equipe A) e 34571 (equipe B) —
        e nesse caso ela aparece corretamente para as duas.
        """
        body = self._ordens(self._login_como("Patricia Oliveira"), limite=50)
        equipe_a = {"23456", "34567", "34568", "34569"}
        numeros = set()
        for o in body["ordens"]:
            numeros.add(o["numero_os"])
            matriculas = {f["matricula"] for f in o["fiscais"]}
            self.assertTrue(
                matriculas & equipe_a,
                f"OS {o['numero_os']} nao tem ninguem da equipe A designado",
            )
        self.assertIn("OS-2026-005", numeros, "OS compartilhada deveria aparecer")
        # OS-2026-009 e exclusiva da Fernanda Costa (34571), da equipe B
        self.assertNotIn("OS-2026-009", numeros)

    def test_paginacao_conta_so_o_que_o_usuario_ve(self):
        """
        A contagem tem que sair do conjunto ja filtrado — se o filtro
        rodasse depois da paginacao, o total continuaria sendo 25 e as
        paginas viriam parcialmente vazias.
        """
        total_admin = self._ordens(self._login())["paginacao"]["total_registros"]
        body = self._ordens(self._login_como("Carlos Mendes"), limite=50)
        total_fiscal = body["paginacao"]["total_registros"]
        self.assertLess(total_fiscal, total_admin)
        self.assertEqual(total_fiscal, len(body["ordens"]))

    def test_get_os_de_outra_equipe_da_403(self):
        """OS-2026-004 e do Jose Almeida (34570), da outra supervisao."""
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/ordens/OS-2026-004", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)

    def test_get_os_propria_funciona(self):
        """OS-2026-003 tem o Carlos Mendes (34567) designado."""
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/ordens/OS-2026-003", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["numero_os"], "OS-2026-003")

    def test_get_os_inexistente_da_404(self):
        token = self._login()
        r = self.client.get("/ordens/OS-9999", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 404)

    # ── Detalhe completo da OS (doc do detalhe) ────────────────────

    def _detalhe(self, token: str, numero: str):
        return self.client.get(f"/ordens/{numero}/detalhe", headers=self._auth_header(token))

    def test_detalhe_traz_o_que_a_listagem_nao_tem(self):
        r = self._detalhe(self._login(), "OS-2026-003")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["numero_os"], "OS-2026-003")
        self.assertTrue(body["contribuinte"]["endereco"]["municipio"])
        self.assertGreater(len(body["eventos"]), 0)
        self.assertTrue(body["fiscais"][0]["responsavel"])

    def test_detalhe_e_uma_os_por_chamada(self):
        """
        Cada clique na listagem detalha a ordem clicada — a resposta nunca
        pode ser a da OS aberta antes.
        """
        token = self._login()
        for numero in ("OS-2026-003", "OS-2026-001", "OS-2026-003"):
            r = self._detalhe(token, numero)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["numero_os"], numero)

    def test_detalhe_de_outra_equipe_da_403(self):
        """A hierarquia vale para o detalhe como vale para a listagem."""
        r = self._detalhe(self._login_como("Carlos Mendes"), "OS-2026-004")
        self.assertEqual(r.status_code, 403)

    def test_detalhe_inexistente_da_404(self):
        r = self._detalhe(self._login(), "OS-9999")
        self.assertEqual(r.status_code, 404)

    def test_detalhe_exige_autenticacao(self):
        r = self.client.get("/ordens/OS-2026-003/detalhe")
        self.assertEqual(r.status_code, 401)

    # ── PDF de uma OS ───────────────────────────────────────────

    @staticmethod
    def _texto_do_pdf(conteudo: bytes) -> str:
        """Extrai o texto dos streams do PDF, sem dependencia externa."""
        import re
        import zlib

        partes: list[str] = []
        for bloco in re.finditer(rb"stream\r?\n(.*?)endstream", conteudo, re.S):
            try:
                fluxo = zlib.decompress(bloco.group(1))
            except zlib.error:
                continue
            partes += [t.decode("latin-1") for t in re.findall(rb"\((.*?)\)\s*Tj", fluxo, re.S)]
        return "\n".join(partes)

    def test_pdf_traz_o_conteudo_do_detalhamento(self):
        """
        O PDF sai com o mesmo conteudo do modal — nao so o que a listagem
        devolve. Ate a versao anterior ele parava nos fiscais.
        """
        r = self.client.get(
            "/ordens/OS-2026-003/pdf", headers=self._auth_header(self._login()),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        texto = self._texto_do_pdf(r.content)
        for secao in ("Informacoes Gerais", "Contribuinte", "Datas e Execucao",
                      "Cargas e Autorizacao", "Fiscais", "Eventos de Acompanhamento",
                      "Descricoes Complementares"):
            self.assertIn(secao, texto, f"secao '{secao}' faltando no PDF")

    def test_pdf_nao_mostra_codigo_da_situacao(self):
        """Mesma regra da tela: o usuario le o nome, o codigo fica interno."""
        r = self.client.get(
            "/ordens/OS-2026-003/pdf", headers=self._auth_header(self._login()),
        )
        texto = self._texto_do_pdf(r.content)
        self.assertIn("AUTORIZADA", texto)
        self.assertNotIn("1 - AUTORIZADA", texto)

    def test_pdf_sai_mesmo_se_o_detalhe_falhar(self):
        """
        O servico de detalhe pode nao estar publicado no ambiente em uso
        (e o caso de producao hoje). Nesse caso o PDF sai com o que a
        listagem tem, em vez de estourar um erro na cara do usuario.
        """
        with patch("backend.main.detalhar_ordem_atf", side_effect=ConnectionError("caiu")):
            r = self.client.get(
                "/ordens/OS-2026-003/pdf", headers=self._auth_header(self._login()),
            )
        self.assertEqual(r.status_code, 200, r.text)
        texto = self._texto_do_pdf(r.content)
        self.assertIn("Informacoes Gerais", texto)
        self.assertNotIn("Eventos de Acompanhamento", texto)

    def test_pdf_respeita_a_hierarquia(self):
        """OS-2026-004 e do Jose Almeida, de outra supervisao."""
        r = self.client.get(
            "/ordens/OS-2026-004/pdf",
            headers=self._auth_header(self._login_como("Carlos Mendes")),
        )
        self.assertEqual(r.status_code, 403)

    def test_relatorio_csv_respeita_a_hierarquia(self):
        """O CSV nao pode exportar o que a tela nao mostra."""
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/relatorios/ordens", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200, r.text)
        linhas = [ln for ln in r.text.splitlines() if ln.strip()]
        # OS-2026-004 e do Jose Almeida, nao pode estar no arquivo
        self.assertNotIn("OS-2026-004", r.text)
        self.assertGreater(len(linhas), 1, "deveria haver ao menos o cabecalho e uma OS")

    def test_list_os_no_token(self):
        r = self.client.get("/ordens")
        self.assertEqual(r.status_code, 401)


class TestTrocaDeSenhaObrigatoria(IntegrationTestBase):
    """
    A flag must_change_password precisa bloquear a API, nao so a tela: o
    login emite token normalmente com ela ativa.
    """

    def _token_com_troca_pendente(self) -> tuple[str, str]:
        h = self._admin_header()
        supervisoes = self.client.get("/admin/supervisoes", headers=h).json()
        s = supervisoes[0]
        criado = self.client.post(
            "/admin/users",
            json={
                "username": "Pendente",
                "role": "fiscal",
                "gerencia_id": s["gerencia_id"],
                "supervisao_id": s["id"],
                "matricula": "55555",
            },
            headers=h,
        ).json()
        temporaria = criado["temporary_password"]
        r = self.client.post(
            "/auth/login", json={"username": "Pendente", "password": temporaria}
        )
        self.assertTrue(r.json()["must_change_password"])
        return r.json()["token"], temporaria

    def test_api_bloqueada_enquanto_a_troca_esta_pendente(self):
        token, _ = self._token_com_troca_pendente()
        for rota in ("/ordens", "/alertas", "/relatorios/ordens"):
            with self.subTest(rota=rota):
                r = self.client.get(rota, headers=self._auth_header(token))
                self.assertEqual(r.status_code, 403, f"{rota}: {r.text}")
                self.assertIn("Troca de senha", r.json()["detail"])

    def test_troca_de_senha_continua_acessivel(self):
        token, temporaria = self._token_com_troca_pendente()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": temporaria, "new_password": "Nova@1234"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 200, r.text)
        # E depois da troca a API volta a responder, com o mesmo token
        r2 = self.client.get("/ordens", headers=self._auth_header(token))
        self.assertEqual(r2.status_code, 200, r2.text)

    def test_senha_temporaria_e_diferente_a_cada_usuario(self):
        """
        Nao pode existir uma senha padrao compartilhada: quem a conhecesse
        entraria em qualquer conta ainda nao trocada.
        """
        h = self._admin_header()
        s = self.client.get("/admin/supervisoes", headers=h).json()[0]
        senhas = set()
        for i in range(3):
            criado = self.client.post(
                "/admin/users",
                json={
                    "username": f"Aleatorio {i}",
                    "role": "fiscal",
                    "gerencia_id": s["gerencia_id"],
                    "supervisao_id": s["id"],
                    "matricula": f"6666{i}",
                },
                headers=h,
            ).json()
            senhas.add(criado["temporary_password"])
        self.assertEqual(len(senhas), 3)

    def test_reset_gera_senha_nova_a_cada_chamada(self):
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        alvo = next(u for u in users if u["role"] == "fiscal")
        primeira = self.client.post(
            f"/admin/users/{alvo['id']}/reset-password", headers=h
        ).json()["temporary_password"]
        segunda = self.client.post(
            f"/admin/users/{alvo['id']}/reset-password", headers=h
        ).json()["temporary_password"]
        self.assertNotEqual(primeira, segunda)
        # A ultima e que vale
        r = self.client.post(
            "/auth/login", json={"username": alvo["username"], "password": segunda}
        )
        self.assertEqual(r.status_code, 200)


# ═══════════════════════════════════════════════════════════════
# 8. Alertas
# ═══════════════════════════════════════════════════════════════


class TestAlertasEndpoints(IntegrationTestBase):
    """Testa endpoint de alertas com mock."""

    _MOCK_ALERTAS = [
        {
            "tipo": "os_urgente",
            "severidade": "alta",
            "titulo": "OS Urgente Parada",
            "descricao": "A OS OS-001 esta urgente e parada.",
            "referencia": "OS-001",
            "data": "2025-06-01",
        }
    ]

    @patch("backend.main.gerar_alertas", return_value=_MOCK_ALERTAS)
    def test_list_alertas(self, _mock_alertas):
        token = self._login()
        r = self.client.get("/alertas", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["tipo"], "os_urgente")


# ═══════════════════════════════════════════════════════════════
# 9. Dashboard (admin only)
# ═══════════════════════════════════════════════════════════════


class TestDashboardEndpoints(IntegrationTestBase):
    """Testa o endpoint de dashboard admin."""

    @patch("backend.main.listar_ordens_servico", return_value=_MOCK_OS_LIST)
    @patch("backend.main.gerar_dashboard", return_value={"total_os": 2, "resumo": {}})
    def test_dashboard_admin(self, _mock_dash, _mock_os):
        h = self._admin_header()
        r = self.client.get("/admin/dashboard", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_os"], 2)

    @patch("backend.main.listar_ordens_servico", return_value=_MOCK_OS_LIST)
    @patch("backend.main.gerar_dashboard", return_value={"total_os": 2})
    def test_dashboard_non_admin_forbidden(self, _mock_dash, _mock_os):
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/admin/dashboard", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)


# ═══════════════════════════════════════════════════════════════
# 10. Fluxos end-to-end
# ═══════════════════════════════════════════════════════════════


class TestEndToEndFlows(IntegrationTestBase):
    """Testa fluxos completos que combinam varios endpoints."""

    def test_create_user_then_login(self):
        """Admin cria usuario -> usuario faz login -> must_change_password = True."""
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        criado = self.client.post(
            "/admin/users",
            json={
                "username": "Teste E2E",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "44444",
            },
            headers=h,
        ).json()
        # Login com a senha temporaria devolvida na criacao
        r = self.client.post(
            "/auth/login",
            json={"username": "Teste E2E", "password": criado["temporary_password"]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["must_change_password"])

    def test_create_user_change_password_then_login(self):
        """Admin cria usuario -> usuario troca senha -> login com nova senha."""
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        criado = self.client.post(
            "/admin/users",
            json={
                "username": "Senha E2E",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "33333",
            },
            headers=h,
        ).json()
        temporaria = criado["temporary_password"]

        # Login do novo usuario
        r_login = self.client.post(
            "/auth/login", json={"username": "Senha E2E", "password": temporaria}
        )
        token = r_login.json()["token"]

        # Troca senha
        r_troca = self.client.post(
            "/auth/change-password",
            json={"current_password": temporaria, "new_password": "Segura@123"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r_troca.status_code, 200, r_troca.text)

        # Login com a nova senha
        r2 = self.client.post(
            "/auth/login", json={"username": "Senha E2E", "password": "Segura@123"}
        )
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["must_change_password"])

    def test_reset_password_then_login(self):
        """Admin reseta senha -> usuario loga com senha padrao."""
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        target = next(u for u in users if u["role"] == "fiscal")

        # Reset
        r = self.client.post(f"/admin/users/{target['id']}/reset-password", headers=h)
        temp_pw = r.json()["temporary_password"]

        # Login com a senha temporaria
        r2 = self.client.post(
            "/auth/login", json={"username": target["username"], "password": temp_pw}
        )
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["must_change_password"])

    def test_create_gerencia_supervisao_user_flow(self):
        """Admin cria gerencia -> supervisao -> usuario nessa hierarquia."""
        h = self._admin_header()

        # Cria gerencia
        r_g = self.client.post(
            "/admin/gerencias", json={"name": "Gerencia E2E"}, headers=h
        )
        gid = r_g.json()["id"]

        # Cria supervisao
        r_s = self.client.post(
            "/admin/supervisoes",
            json={"name": "Supervisao E2E", "gerencia_id": gid},
            headers=h,
        )
        sid = r_s.json()["id"]

        # Cria usuario
        r_u = self.client.post(
            "/admin/users",
            json={
                "username": "Fiscal E2E",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "22222",
            },
            headers=h,
        )
        self.assertEqual(r_u.status_code, 200)
        body = r_u.json()
        self.assertEqual(body["gerencia_name"], "Gerencia E2E")
        self.assertEqual(body["supervisao_name"], "Supervisao E2E")

    def test_delete_user_then_login_fails(self):
        """Admin deleta usuario -> usuario nao consegue mais logar."""
        h = self._admin_header()
        users = self.client.get("/admin/users", headers=h).json()
        target = next(u for u in users if u["role"] == "fiscal")

        # Deleta
        r = self.client.delete(f"/admin/users/{target['id']}", headers=h)
        self.assertEqual(r.status_code, 204)

        # Tenta logar
        r2 = self.client.post(
            "/auth/login",
            json={"username": target["username"], "password": SENHA_TESTE},
        )
        self.assertEqual(r2.status_code, 401)

    def _get_valid_ids(self, headers: dict) -> tuple[int, int]:
        supervisoes = self.client.get("/admin/supervisoes", headers=headers).json()
        s = supervisoes[0]
        return s["gerencia_id"], s["id"]


# ═══════════════════════════════════════════════════════════════
# 8. Visibilidade por equipe fiscal do ATF
# ═══════════════════════════════════════════════════════════════


class TestVisibilidadePorEquipeFiscal(IntegrationTestBase):
    """
    Quando o admin amarra um supervisor a uma equipe fiscal do ATF, e ela
    que passa a definir o que ele enxerga — no lugar da supervisao do
    cadastro local.

    O mock do ATF usa as matriculas 34567-34571; as equipes montadas aqui
    reagrupam essas mesmas pessoas de um jeito diferente do seed, que e
    justamente o que prova qual das duas fontes esta valendo.
    """

    def _importar(self, equipes, membros):
        import backend.main as main_module

        main_module.equipe_repo.substituir_tudo(equipes, membros)

    def _amarrar(self, username: str, codigo_equipe: int | None):
        """Amarra o supervisor a uma equipe pelo endpoint de admin."""
        h = self._admin_header()
        alvo = next(
            u for u in self.client.get("/admin/users", headers=h).json()
            if u["username"] == username
        )
        r = self.client.put(
            f"/admin/users/{alvo['id']}",
            headers=h,
            json={
                "username": alvo["username"],
                "role": alvo["role"],
                "gerencia_id": alvo["gerencia_id"],
                "supervisao_id": alvo["supervisao_id"],
                "matricula": alvo["matricula"],
                "equipe_codigo": codigo_equipe,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        return alvo

    def _numeros_vistos(self, username: str) -> set[str]:
        token = self._login_como(username)
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return {o["numero_os"] for o in r.json()["ordens"]}

    def test_equipe_amarrada_substitui_a_supervisao_local(self):
        """
        Patricia supervisiona 34567-34569 pelo cadastro local. Amarrada a
        uma equipe que so tem 34571, ela passa a ver as OS de 34571 — e
        deixa de ver as que so tinham gente da supervisao antiga.
        """
        self._importar(
            [(900, "EQUIPE SO DA FERNANDA")], [(900, "34571", "FERNANDA COSTA")]
        )

        antes = self._numeros_vistos("Patricia Oliveira")
        self._amarrar("Patricia Oliveira", 900)
        depois = self._numeros_vistos("Patricia Oliveira")

        self.assertNotEqual(antes, depois, "a equipe deveria ter mudado o que ela ve")
        # OS-2026-009 e exclusiva de 34571: invisivel antes, visivel agora.
        self.assertNotIn("OS-2026-009", antes)
        self.assertIn("OS-2026-009", depois)

    def test_toda_os_vista_tem_alguem_da_equipe(self):
        """A regra nao afrouxa: nada aparece sem um membro da equipe designado."""
        self._importar([(901, "EQUIPE DE TESTE")], [(901, "34570", "JOSE ALMEIDA")])
        self._amarrar("Patricia Oliveira", 901)

        token = self._login_como("Patricia Oliveira")
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        # A propria matricula do supervisor continua valendo, junto com a equipe
        permitidas = {"34570", "23456"}
        for o in r.json()["ordens"]:
            matriculas = {f["matricula"] for f in o["fiscais"]}
            self.assertTrue(
                matriculas & permitidas,
                f"OS {o['numero_os']} nao tem ninguem visivel designado",
            )

    def test_sem_equipe_amarrada_vale_a_supervisao_local(self):
        """
        O comportamento antigo tem que sobreviver: enquanto o admin nao
        amarrar ninguem, a visibilidade sai de gerencias/supervisoes.
        """
        self._importar([(902, "EQUIPE NAO USADA")], [(902, "34571", "FERNANDA")])
        vistas = self._numeros_vistos("Patricia Oliveira")
        self.assertIn("OS-2026-005", vistas)
        self.assertNotIn("OS-2026-009", vistas)

    def test_desamarrar_volta_para_a_supervisao(self):
        self._importar([(903, "EQUIPE X")], [(903, "34571", "FERNANDA")])
        original = self._numeros_vistos("Patricia Oliveira")
        self._amarrar("Patricia Oliveira", 903)
        self._amarrar("Patricia Oliveira", None)
        self.assertEqual(self._numeros_vistos("Patricia Oliveira"), original)

    def test_equipe_vazia_deixa_so_a_propria_matricula(self):
        """
        Falha fechado: equipe sem membros nao vira acesso amplo. O
        supervisor fica so com o que estiver designado a ele.
        """
        self._importar([(904, "EQUIPE VAZIA")], [])
        self._amarrar("Patricia Oliveira", 904)

        token = self._login_como("Patricia Oliveira")
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        for o in r.json()["ordens"]:
            matriculas = {f["matricula"] for f in o["fiscais"]}
            self.assertIn("23456", matriculas)

    def test_equipe_extinta_nao_amplia_acesso(self):
        """
        Se uma reimportacao apaga a equipe, o codigo orfao em users nao
        pode virar "ve tudo" — vira conjunto vazio.
        """
        self._importar([(905, "SOME DEPOIS")], [(905, "34571", "FERNANDA")])
        self._amarrar("Patricia Oliveira", 905)
        self.assertIn("OS-2026-009", self._numeros_vistos("Patricia Oliveira"))

        self._importar([(906, "OUTRA")], [(906, "34567", "CARLOS")])
        depois = self._numeros_vistos("Patricia Oliveira")
        self.assertNotIn("OS-2026-009", depois)
        token = self._login_como("Patricia Oliveira")
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        for o in r.json()["ordens"]:
            self.assertIn("23456", {f["matricula"] for f in o["fiscais"]})

    def test_fiscal_ignora_a_equipe(self):
        """Equipe so vale para supervisor; fiscal continua vendo so as suas."""
        self._importar([(907, "EQUIPE GRANDE")], [(907, "34571", "FERNANDA")])
        h = self._admin_header()
        alvo = next(
            u for u in self.client.get("/admin/users", headers=h).json()
            if u["username"] == "Carlos Mendes"
        )
        self.client.put(
            f"/admin/users/{alvo['id']}",
            headers=h,
            json={
                "username": alvo["username"],
                "role": alvo["role"],
                "gerencia_id": alvo["gerencia_id"],
                "supervisao_id": alvo["supervisao_id"],
                "matricula": alvo["matricula"],
                "equipe_codigo": 907,
            },
        )
        token = self._login_como("Carlos Mendes")
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        for o in r.json()["ordens"]:
            self.assertIn("34567", {f["matricula"] for f in o["fiscais"]})

    def test_amarrar_equipe_inexistente_da_400(self):
        self._importar([(908, "UNICA")], [])
        h = self._admin_header()
        alvo = next(
            u for u in self.client.get("/admin/users", headers=h).json()
            if u["username"] == "Patricia Oliveira"
        )
        r = self.client.put(
            f"/admin/users/{alvo['id']}",
            headers=h,
            json={
                "username": alvo["username"],
                "role": alvo["role"],
                "gerencia_id": alvo["gerencia_id"],
                "supervisao_id": alvo["supervisao_id"],
                "matricula": alvo["matricula"],
                "equipe_codigo": 99999,
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_gerente_ve_tudo_que_seus_supervisores_veem(self):
        """
        A hierarquia nao pode inverter: se o supervisor enxerga por uma
        equipe do ATF, o gerente dele tem que enxergar pelo menos o mesmo.

        O cenario usa Maria Santos, da Gerencia de Arrecadacao, amarrada a
        uma equipe cujo unico membro (34571, Fernanda Costa) e lotado na
        Gerencia de Fiscalizacao. Pelo cadastro local o gerente da
        Arrecadacao nunca alcanca 34571 — so somando as equipes dos seus
        supervisores. E o caso real: a equipe do ATF alcanca fiscais de
        outra lotacao, e ate quem nao tem login no sistema.
        """
        self._importar([(910, "EQUIPE DA MARIA")], [(910, "34571", "FERNANDA COSTA")])
        self._amarrar("Maria Santos", 910)

        h = self._admin_header()
        usuarios = self.client.get("/admin/users", headers=h).json()
        maria = next(u for u in usuarios if u["username"] == "Maria Santos")
        gerente = next(
            u for u in usuarios
            if u["role"] == "gerente" and u["gerencia_id"] == maria["gerencia_id"]
        )

        vistas_supervisor = self._numeros_vistos("Maria Santos")
        vistas_gerente = self._numeros_vistos(gerente["username"])

        # OS-2026-009 e exclusiva de 34571, de fora da gerencia da Maria
        self.assertIn("OS-2026-009", vistas_supervisor)
        self.assertTrue(
            vistas_supervisor <= vistas_gerente,
            "o gerente deveria ver tudo que a supervisora dele ve; "
            f"faltou: {sorted(vistas_supervisor - vistas_gerente)}",
        )

    def test_detalhe_de_os_fora_da_equipe_da_403(self):
        """A checagem de acesso ao detalhe usa o mesmo conjunto."""
        self._importar([(909, "SO FERNANDA")], [(909, "34571", "FERNANDA")])
        self._amarrar("Patricia Oliveira", 909)
        token = self._login_como("Patricia Oliveira")
        # OS-2026-004 e do Jose Almeida (34570), fora da equipe
        r = self.client.get("/ordens/OS-2026-004", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)


class TestEquipeDeQuemPertence(IntegrationTestBase):
    """
    As equipes que o usuario PERTENCE, expostas no cadastro.

    Sao um dado diferente de `equipe_codigo`, que e a equipe que um
    supervisor CHEFIA. A tela usa o primeiro para sugerir o segundo, e
    confundir os dois daria visibilidade a quem nao deve ter.
    """

    def _importar(self, equipes, membros):
        import backend.main as main_module

        main_module.equipe_repo.substituir_tudo(equipes, membros)

    def _usuario(self, username: str) -> dict:
        h = self._admin_header()
        return next(
            u for u in self.client.get("/admin/users", headers=h).json()
            if u["username"] == username
        )

    def test_traz_a_equipe_de_cada_um(self):
        self._importar(
            [(427, "GOFE - VAREJO")], [(427, "34567", "CARLOS MENDES")]
        )
        carlos = self._usuario("Carlos Mendes")
        self.assertEqual(
            carlos["equipes_membro"], [{"codigo": 427, "nome": "GOFE - VAREJO"}]
        )

    def test_quem_nao_esta_em_equipe_vem_vazio(self):
        self._importar([(427, "GOFE - VAREJO")], [])
        self.assertEqual(self._usuario("Carlos Mendes")["equipes_membro"], [])

    def test_quem_esta_em_duas_traz_as_duas(self):
        self._importar(
            [(614, "GEST_ITCD"), (554, "GOFITCD/IPVA")],
            [(614, "34567", "CARLOS"), (554, "34567", "CARLOS")],
        )
        nomes = {e["nome"] for e in self._usuario("Carlos Mendes")["equipes_membro"]}
        self.assertEqual(nomes, {"GEST_ITCD", "GOFITCD/IPVA"})

    def test_pertencer_a_equipe_nao_da_visibilidade(self):
        """
        O ponto critico: estar numa equipe nao faz ninguem enxergar a
        equipe toda. Isso so vem de `equipe_codigo`, preenchido pelo
        admin. Sem essa separacao, importar a planilha teria promovido
        334 auditores a supervisores de si mesmos.
        """
        self._importar(
            [(427, "GOFE - VAREJO")],
            [(427, "34567", "CARLOS"), (427, "34568", "ANA")],
        )
        carlos = self._usuario("Carlos Mendes")
        self.assertEqual(len(carlos["equipes_membro"]), 1)
        self.assertIsNone(carlos["equipe_codigo"])

        token = self._login_como("Carlos Mendes")
        r = self.client.get(
            "/ordens", headers=self._auth_header(token), params={"limite": 50}
        )
        for o in r.json()["ordens"]:
            matriculas = {f["matricula"] for f in o["fiscais"]}
            self.assertIn(
                "34567", matriculas,
                f"OS {o['numero_os']} apareceu para quem so PERTENCE a equipe",
            )

    def test_chefia_e_pertencimento_convivem(self):
        """Um supervisor pode chefiar uma equipe e pertencer a outra."""
        self._importar(
            [(427, "GOFE - VAREJO"), (429, "GOAC - MALHAS")],
            [(429, "23456", "PATRICIA")],
        )
        h = self._admin_header()
        patricia = self._usuario("Patricia Oliveira")
        self.client.put(
            f"/admin/users/{patricia['id']}",
            headers=h,
            json={
                "username": patricia["username"], "role": patricia["role"],
                "gerencia_id": patricia["gerencia_id"],
                "supervisao_id": patricia["supervisao_id"],
                "matricula": patricia["matricula"], "equipe_codigo": 427,
            },
        )
        atualizada = self._usuario("Patricia Oliveira")
        self.assertEqual(atualizada["equipe_codigo"], 427)
        self.assertEqual(atualizada["equipe_nome"], "GOFE - VAREJO")
        self.assertEqual(
            [e["nome"] for e in atualizada["equipes_membro"]], ["GOAC - MALHAS"]
        )

    def test_sem_importacao_ninguem_tem_equipe(self):
        for u in self.client.get("/admin/users", headers=self._admin_header()).json():
            self.assertEqual(u["equipes_membro"], [])


class TestEquipesFiscaisEndpoints(IntegrationTestBase):
    """Endpoints de consulta das equipes importadas."""

    def _importar(self, equipes, membros):
        import backend.main as main_module

        main_module.equipe_repo.substituir_tudo(equipes, membros)

    def test_lista_vazia_antes_de_importar(self):
        r = self.client.get("/equipes-fiscais", headers=self._admin_header())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_lista_com_contagem(self):
        self._importar(
            [(427, "GOFE - VAREJO")], [(427, "34567", "A"), (427, "34568", "B")]
        )
        r = self.client.get("/equipes-fiscais", headers=self._admin_header())
        self.assertEqual(
            r.json(), [{"codigo": 427, "nome": "GOFE - VAREJO", "total_membros": 2}]
        )

    def test_lista_e_aberta_a_nao_admin(self):
        """O filtro do painel precisa da lista; sao so nomes de equipe."""
        self._importar([(427, "GOFE - VAREJO")], [])
        token = self._login_como("Carlos Mendes")
        r = self.client.get("/equipes-fiscais", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200)

    def test_lista_exige_autenticacao(self):
        self.assertEqual(self.client.get("/equipes-fiscais").status_code, 401)

    def test_membros_so_para_admin(self):
        """Nome e matricula de servidor nao saem para usuario comum."""
        self._importar([(427, "GOFE - VAREJO")], [(427, "34567", "CARLOS")])
        token = self._login_como("Carlos Mendes")
        r = self.client.get(
            "/admin/equipes-fiscais/427/membros", headers=self._auth_header(token)
        )
        self.assertEqual(r.status_code, 403)

    def test_membros_para_admin(self):
        self._importar([(427, "GOFE - VAREJO")], [(427, "34567", "CARLOS MENDES")])
        r = self.client.get(
            "/admin/equipes-fiscais/427/membros", headers=self._admin_header()
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [{"matricula": "34567", "nome": "CARLOS MENDES"}])

    def test_membros_de_equipe_inexistente_da_404(self):
        r = self.client.get(
            "/admin/equipes-fiscais/99999/membros", headers=self._admin_header()
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
