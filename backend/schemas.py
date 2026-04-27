"""
schemas.py – Modelos Pydantic (request/response) do Sistema Sefaz.

Cada classe representa o formato de dados de um endpoint da API.
O FastAPI usa esses modelos para validacao automatica e geracao
da documentacao Swagger/OpenAPI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ─── Autenticacao ───────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Payload de login: usuario e senha."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Resposta do login com token, dados do usuario e flag de troca de senha."""
    token: str
    role: str
    user_id: int
    username: str
    must_change_password: bool
    matricula: str | None = None
    gerencia_id: int | None = None
    gerencia_name: str | None = None
    supervisao_id: int | None = None
    supervisao_name: str | None = None


# ─── Gerencias ──────────────────────────────────────────────────

class GerenciaCreateRequest(BaseModel):
    """Dados para criar uma gerencia."""
    name: str = Field(min_length=2)


class GerenciaUpdateRequest(BaseModel):
    """Dados para atualizar uma gerencia."""
    name: str = Field(min_length=2)


class GerenciaResponse(BaseModel):
    """Representa uma gerencia na resposta da API."""
    id: int
    name: str


# ─── Supervisoes ────────────────────────────────────────────────

class SupervisaoCreateRequest(BaseModel):
    """Dados para criar uma supervisao (vinculada a uma gerencia)."""
    name: str = Field(min_length=2)
    gerencia_id: int


class SupervisaoUpdateRequest(BaseModel):
    """Dados para atualizar uma supervisao."""
    name: str = Field(min_length=2)
    gerencia_id: int


class SupervisaoResponse(BaseModel):
    """Representa uma supervisao na resposta da API."""
    id: int
    name: str
    gerencia_id: int
    gerencia_name: str | None = None


# ─── Usuarios ───────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """Dados para criar um usuario (a senha padrao e atribuida pelo backend)."""
    username: str
    role: str
    gerencia_id: int
    supervisao_id: int
    matricula: str = Field(min_length=3)


class UserUpdateRequest(BaseModel):
    """Dados para editar um usuario existente."""
    username: str
    role: str
    gerencia_id: int
    supervisao_id: int
    matricula: str = Field(min_length=3)


class UserResponse(BaseModel):
    """Representa um usuario na resposta da API (sem senha)."""
    id: int
    username: str
    role: str
    matricula: str | None = None
    gerencia_id: int | None = None
    gerencia_name: str | None = None
    supervisao_id: int | None = None
    supervisao_name: str | None = None


# ─── Senha ──────────────────────────────────────────────────────

class PasswordChangeRequest(BaseModel):
    """Payload para troca de senha (usuario autenticado)."""
    current_password: str
    new_password: str = Field(min_length=6)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 6:
            errors.append("mínimo 6 caracteres")
        if not any(c.isupper() for c in v):
            errors.append("pelo menos 1 letra maiúscula")
        if not any(c.islower() for c in v):
            errors.append("pelo menos 1 letra minúscula")
        if not any(c.isdigit() for c in v):
            errors.append("pelo menos 1 número")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/~`" for c in v):
            errors.append("pelo menos 1 caractere especial")
        if errors:
            raise ValueError("Senha fraca: " + "; ".join(errors))
        return v


class PasswordResetResponse(BaseModel):
    """Resposta do reset de senha pelo admin."""
    temporary_password: str


# ─── Ordem de Servico (somente consulta - vem da API externa) ──

class OSResponse(BaseModel):
    """Dados de uma Ordem de Servico retornada pela API externa."""
    numero: str
    tipo: str
    ie: str
    razao_social: str
    matricula_supervisor: str
    fiscais: list[str]
    status: str
    prioridade: str = ""
    data_abertura: str
    data_ciencia: str | None = None
    data_ultima_movimentacao: str | None = None
    dias_parado: int = 0


class MovimentacaoResponse(BaseModel):
    """Uma movimentacao dentro de uma OS."""
    data: str
    tipo: str
    descricao: str
    responsavel: str


class OSDetalheResponse(OSResponse):
    """Dados detalhados de uma OS, incluindo movimentacoes e informacoes extras."""
    objeto: str = ""
    valor_estimado: float = 0
    endereco: str = ""
    cnpj: str = ""
    telefone: str = ""
    observacoes: str = ""
    movimentacoes: list[MovimentacaoResponse] = []


class AlertaResponse(BaseModel):
    """Alerta gerado automaticamente a partir das regras de negocio."""
    tipo: str
    severidade: str
    titulo: str
    descricao: str
    referencia: str
    data: str


# ─── Formato ATF (novo endpoint de listagem de OS) ──────────────

class FiscalATF(BaseModel):
    """Fiscal com ciencia registrada na OS."""
    matricula: str
    nome: str
    data_ciencia: str | None = None


class SituacaoATF(BaseModel):
    """Situacao da OS no ATF (codigo + descricao)."""
    codigo: int
    descricao: str


class OSListagemATF(BaseModel):
    """OS retornada pelo endpoint de listagem do ATF."""
    numero_os: str
    modelo: str
    ie: str
    cnpj: str | None = None
    razao_social: str
    fiscais: list[FiscalATF] = []
    situacao: SituacaoATF
    data_abertura: str


class PaginacaoATF(BaseModel):
    """Metadados de paginacao retornados pelo ATF."""
    pagina_atual: int
    limite_por_pagina: int
    total_paginas: int
    total_registros: int


class OrdensATFResponse(BaseModel):
    """Resposta completa do endpoint de listagem de OS (paginacao + lista)."""
    paginacao: PaginacaoATF
    ordens: list[OSListagemATF]
