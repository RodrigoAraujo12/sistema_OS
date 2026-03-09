"""
Testes unitarios para os schemas Pydantic do Sistema Sefaz.

Cobre: validacao de campos obrigatorios, campos opcionais,
valores default, min_length e serializacao.
"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from backend.schemas import (
    AlertaResponse,
    GerenciaCreateRequest,
    GerenciaResponse,
    LoginRequest,
    LoginResponse,
    OSResponse,
    PasswordChangeRequest,
    PasswordResetResponse,
    SupervisaoCreateRequest,
    SupervisaoResponse,
    UserCreateRequest,
    UserResponse,
)


class TestLoginSchemas(unittest.TestCase):
    """Testes para LoginRequest e LoginResponse."""

    def test_login_request_valid(self):
        req = LoginRequest(username="admin", password="admin123")
        self.assertEqual(req.username, "admin")

    def test_login_response_valid(self):
        resp = LoginResponse(
            token="abc", role="admin", user_id=1, username="admin",
            must_change_password=False,
        )
        self.assertEqual(resp.role, "admin")
        self.assertIsNone(resp.matricula)

    def test_login_response_with_optionals(self):
        resp = LoginResponse(
            token="abc", role="supervisor", user_id=2, username="sup",
            must_change_password=True, matricula="12345",
            gerencia_id=1, gerencia_name="Ger A",
            supervisao_id=2, supervisao_name="Sup B",
        )
        self.assertEqual(resp.matricula, "12345")


class TestGerenciaSchemas(unittest.TestCase):

    def test_create_valid(self):
        req = GerenciaCreateRequest(name="Gerencia X")
        self.assertEqual(req.name, "Gerencia X")

    def test_create_min_length(self):
        with self.assertRaises(ValidationError):
            GerenciaCreateRequest(name="X")

    def test_response(self):
        resp = GerenciaResponse(id=1, name="Gerencia Y")
        self.assertEqual(resp.id, 1)


class TestSupervisaoSchemas(unittest.TestCase):

    def test_create_valid(self):
        req = SupervisaoCreateRequest(name="Supervisao A", gerencia_id=1)
        self.assertEqual(req.gerencia_id, 1)

    def test_response_optional_gerencia_name(self):
        resp = SupervisaoResponse(id=1, name="Sup A", gerencia_id=1)
        self.assertIsNone(resp.gerencia_name)


class TestUserSchemas(unittest.TestCase):

    def test_create_valid(self):
        req = UserCreateRequest(
            username="joao", role="fiscal", gerencia_id=1,
            supervisao_id=1, matricula="12345",
        )
        self.assertEqual(req.role, "fiscal")

    def test_create_matricula_min_length(self):
        with self.assertRaises(ValidationError):
            UserCreateRequest(
                username="joao", role="fiscal", gerencia_id=1,
                supervisao_id=1, matricula="12",
            )

    def test_response(self):
        resp = UserResponse(
            id=1, username="admin", role="admin",
        )
        self.assertIsNone(resp.matricula)


class TestOSResponse(unittest.TestCase):

    def test_full_os(self):
        os = OSResponse(
            numero="OS-001", tipo="Normal", ie="123", razao_social="Empresa",
            matricula_supervisor="111", fiscais=["Carlos"], status="aberta",
            prioridade="alta", data_abertura="2026-01-01",
            data_ciencia="2026-01-02", data_ultima_movimentacao="2026-01-03",
            dias_parado=5,
        )
        self.assertEqual(os.numero, "OS-001")
        self.assertEqual(os.dias_parado, 5)

    def test_os_sem_prioridade(self):
        os = OSResponse(
            numero="OS-002", tipo="Normal", ie="456", razao_social="Empresa",
            matricula_supervisor="222", fiscais=["Ana"], status="aberta",
            data_abertura="2026-01-01",
        )
        self.assertEqual(os.prioridade, "")
        self.assertEqual(os.dias_parado, 0)

    def test_os_optional_dates(self):
        os = OSResponse(
            numero="OS-003", tipo="Simplificado", ie="789", razao_social="Emp",
            matricula_supervisor="333", fiscais=[], status="aberta",
            prioridade="normal", data_abertura="2026-01-01",
        )
        self.assertIsNone(os.data_ciencia)
        self.assertIsNone(os.data_ultima_movimentacao)


class TestAlertaResponse(unittest.TestCase):

    def test_valid(self):
        a = AlertaResponse(
            tipo="os_urgente", severidade="alta", titulo="Titulo",
            descricao="Descricao", referencia="OS-001", data="2026-01-01",
        )
        self.assertEqual(a.tipo, "os_urgente")


class TestPasswordSchemas(unittest.TestCase):

    def test_change_valid(self):
        req = PasswordChangeRequest(current_password="old", new_password="new1234")
        self.assertEqual(req.new_password, "new1234")

    def test_change_min_length(self):
        with self.assertRaises(ValidationError):
            PasswordChangeRequest(current_password="old", new_password="123")

    def test_reset_response(self):
        resp = PasswordResetResponse(temporary_password="temp1234")
        self.assertEqual(resp.temporary_password, "temp1234")


if __name__ == "__main__":
    unittest.main()
