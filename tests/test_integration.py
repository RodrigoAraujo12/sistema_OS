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


def _create_app(db_path: str) -> TestClient:
    """
    Cria uma instancia isolada da aplicacao apontando para um banco
    SQLite temporario, executa o lifespan (seed) e retorna o TestClient.
    """
    # Precisa patchar DB_PATH e database/repos/auth_service ANTES
    # do import, pois main.py instancia tudo em nivel de modulo.
    # A abordagem mais limpa e recriar os objetos com o db temporario.

    from backend.auth import AuthService, PasswordHasher, TokenStore
    from backend.db import Database, GerenciaRepository, SupervisaoRepository, UserRepository

    database = Database(db_path)
    user_repo = UserRepository(database)
    gerencia_repo = GerenciaRepository(database)
    supervisao_repo = SupervisaoRepository(database)
    auth_service = AuthService(user_repo, PasswordHasher(), TokenStore())

    # Patcheia os objetos do modulo main com nossas instancias isoladas
    import backend.main as main_module

    main_module.database = database
    main_module.user_repo = user_repo
    main_module.gerencia_repo = gerencia_repo
    main_module.supervisao_repo = supervisao_repo
    main_module.auth_service = auth_service

    client = TestClient(main_module.app)
    return client


class IntegrationTestBase(unittest.TestCase):
    """Base com setup/teardown que cria um banco isolado + TestClient."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self.client = _create_app(self.db_path)
        # Entra no context manager do TestClient para disparar o lifespan (seed)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        try:
            Path(self._tmp.name).unlink(missing_ok=True)
        except OSError:
            pass

    # ── Helpers de conveniencia ─────────────────────────────────

    def _login(self, username: str = "admin", password: str = "admin123") -> str:
        """Faz login e retorna o token."""
        r = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

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
        r = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
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
        r = self.client.post(
            "/auth/login",
            json={"username": "Roberto Santos", "password": "temp1234"},
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
            json={"current_password": "admin123", "new_password": "nova1234"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        # Verifica que a nova senha funciona
        r2 = self.client.post("/auth/login", json={"username": "admin", "password": "nova1234"})
        self.assertEqual(r2.status_code, 200)

    def test_change_password_wrong_current(self):
        token = self._login()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": "errada", "new_password": "nova"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 400)

    def test_change_password_too_short(self):
        token = self._login()
        r = self.client.post(
            "/auth/change-password",
            json={"current_password": "admin123", "new_password": "ab"},
            headers=self._auth_header(token),
        )
        self.assertEqual(r.status_code, 422)  # validation error


# ═══════════════════════════════════════════════════════════════
# 2. Middleware / Autorizacao
# ═══════════════════════════════════════════════════════════════


class TestAuthMiddleware(IntegrationTestBase):
    """Testa que rotas protegidas rejeitam acessos indevidos."""

    def test_no_token_returns_401(self):
        r = self.client.get("/admin/gerencias")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Token ausente", r.json()["detail"])

    def test_invalid_token_returns_401(self):
        r = self.client.get("/admin/gerencias", headers={"Authorization": "Bearer invalidtoken"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Token invalido", r.json()["detail"])

    def test_non_admin_cannot_access_admin_routes(self):
        """Fiscal nao pode acessar /admin/*."""
        token = self._login("Carlos Mendes", "temp1234")
        r = self.client.get("/admin/gerencias", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)
        self.assertIn("Acesso negado", r.json()["detail"])

    def test_gerente_cannot_access_admin_routes(self):
        token = self._login("Roberto Santos", "temp1234")
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
            "/auth/login", json={"username": "admin", "password": "admin123"}
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
    """Testa endpoints de OS com dados mockados da API externa."""

    @patch("backend.main.listar_ordens_servico", return_value=_MOCK_OS_LIST)
    @patch("backend.main._filtrar_por_hierarquia", side_effect=lambda ordens, **kw: ordens)
    def test_list_os(self, _mock_filtrar, _mock_listar):
        token = self._login()
        r = self.client.get("/ordens", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

    @patch("backend.main.listar_ordens_servico", return_value=_MOCK_OS_LIST)
    @patch("backend.main._filtrar_por_hierarquia", side_effect=lambda ordens, **kw: ordens)
    def test_list_os_returns_fields(self, _mock_filtrar, _mock_listar):
        token = self._login()
        r = self.client.get("/ordens", headers=self._auth_header(token))
        os1 = r.json()[0]
        self.assertEqual(os1["numero"], "OS-001")
        self.assertEqual(os1["tipo"], "Fiscalizacao")
        self.assertEqual(os1["status"], "Em andamento")

    @patch("backend.main.consultar_os_por_numero", return_value=_MOCK_OS_LIST[0])
    @patch("backend.main._filtrar_por_hierarquia", side_effect=lambda ordens, **kw: ordens)
    def test_get_os_by_numero(self, _mock_filtrar, _mock_consultar):
        token = self._login()
        r = self.client.get("/ordens/OS-001", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["numero"], "OS-001")

    @patch("backend.main.consultar_os_por_numero", return_value=None)
    def test_get_os_not_found(self, _mock_consultar):
        token = self._login()
        r = self.client.get("/ordens/OS-999", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 404)

    @patch("backend.main.consultar_os_por_numero", return_value=_MOCK_OS_LIST[0])
    @patch("backend.main._filtrar_por_hierarquia", return_value=[])
    def test_get_os_no_permission(self, _mock_filtrar, _mock_consultar):
        """Fiscal sem permissao para a OS recebe 403."""
        token = self._login()
        r = self.client.get("/ordens/OS-001", headers=self._auth_header(token))
        self.assertEqual(r.status_code, 403)

    def test_list_os_no_token(self):
        r = self.client.get("/ordens")
        self.assertEqual(r.status_code, 401)


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
        token = self._login("Carlos Mendes", "temp1234")
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
        self.client.post(
            "/admin/users",
            json={
                "username": "Teste E2E",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "44444",
            },
            headers=h,
        )
        # Login com senha padrao
        r = self.client.post(
            "/auth/login", json={"username": "Teste E2E", "password": "temp1234"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["must_change_password"])

    def test_create_user_change_password_then_login(self):
        """Admin cria usuario -> usuario troca senha -> login com nova senha."""
        h = self._admin_header()
        gid, sid = self._get_valid_ids(h)
        self.client.post(
            "/admin/users",
            json={
                "username": "Senha E2E",
                "role": "fiscal",
                "gerencia_id": gid,
                "supervisao_id": sid,
                "matricula": "33333",
            },
            headers=h,
        )
        # Login do novo usuario
        r_login = self.client.post(
            "/auth/login", json={"username": "Senha E2E", "password": "temp1234"}
        )
        token = r_login.json()["token"]

        # Troca senha
        self.client.post(
            "/auth/change-password",
            json={"current_password": "temp1234", "new_password": "segura123"},
            headers=self._auth_header(token),
        )

        # Login com a nova senha
        r2 = self.client.post(
            "/auth/login", json={"username": "Senha E2E", "password": "segura123"}
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
            json={"username": target["username"], "password": "temp1234"},
        )
        self.assertEqual(r2.status_code, 401)

    def _get_valid_ids(self, headers: dict) -> tuple[int, int]:
        supervisoes = self.client.get("/admin/supervisoes", headers=headers).json()
        s = supervisoes[0]
        return s["gerencia_id"], s["id"]


if __name__ == "__main__":
    unittest.main()
