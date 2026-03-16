"""
main.py – Ponto de entrada da API FastAPI do Sistema Sefaz.

Define os endpoints REST, middlewares e inicializacao da aplicacao.
Os dados de Ordens de Servico vem de uma fonte externa (mock por ora).
Gerencias, Supervisoes e Usuarios ficam no banco SQLite local.
"""

from __future__ import annotations

import csv
import io
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fpdf import FPDF
from sqlite3 import IntegrityError
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth import AuthService, PasswordHasher, TokenStore
from .config import APP_TITLE, CORS_ORIGINS, DEFAULT_PASSWORD, setup_logging
from .db import (
    DB_PATH,
    Database,
    GerenciaRepository,
    SupervisaoRepository,
    UserRepository,
)
from .external_api import (
    _filtrar_por_hierarquia,
    consultar_os_por_numero,
    gerar_alertas,
    gerar_dashboard,
    listar_ordens_servico,
)
from .schemas import (
    AlertaResponse,
    GerenciaCreateRequest,
    GerenciaResponse,
    GerenciaUpdateRequest,
    LoginRequest,
    LoginResponse,
    OSDetalheResponse,
    OSResponse,
    PasswordChangeRequest,
    PasswordResetResponse,
    SupervisaoCreateRequest,
    SupervisaoResponse,
    SupervisaoUpdateRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)

# ─── Logging ────────────────────────────────────────────────────
# Configura o logger uma unica vez na inicializacao do modulo.
setup_logging()
logger = logging.getLogger("sefaz.main")

# ─── App FastAPI ────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Inicializa o banco de dados e popula dados de exemplo no primeiro uso."""
    _seed_database()
    yield


app = FastAPI(title=APP_TITLE, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Repositorios e servicos (instanciados uma vez) ────────────

database = Database(DB_PATH)
user_repo = UserRepository(database)
gerencia_repo = GerenciaRepository(database)
supervisao_repo = SupervisaoRepository(database)
auth_service = AuthService(user_repo, PasswordHasher(), TokenStore())

# Cargos permitidos para usuarios comuns (admin e criado automaticamente)
ALLOWED_ROLES = {"gerente", "supervisor", "fiscal"}


def _validate_user_payload(
    role: str, gerencia_id: int, supervisao_id: int,
) -> None:
    """Valida campos de cargo e lotacao para criacao/edicao de usuario."""
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cargo invalido")
    if not gerencia_repo.get_gerencia(gerencia_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gerencia invalida")
    supervisao = supervisao_repo.get_supervisao(supervisao_id)
    if not supervisao:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supervisao invalida")
    if int(supervisao["gerencia_id"]) != int(gerencia_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cascata invalida")


def _seed_database() -> None:
    """Inicializa o banco de dados e popula dados de exemplo no primeiro uso."""
    logger.info("Iniciando aplicacao – criando schema do banco...")
    database.init_schema()

    if user_repo.count_users() == 0:
        logger.info("Banco vazio – criando dados iniciais (admin + seed)...")
        auth_service.register_user("admin", "admin123", "admin")

        # Gerencias de exemplo
        gerencias = [
            gerencia_repo.create_gerencia("Gerencia de Fiscalizacao"),
            gerencia_repo.create_gerencia("Gerencia de Arrecadacao"),
            gerencia_repo.create_gerencia("Gerencia de Tributacao"),
        ]

        # Supervisoes vinculadas as gerencias (2 por gerencia)
        supervisoes = [
            supervisao_repo.create_supervisao("Supervisao Fiscal A", gerencias[0]),
            supervisao_repo.create_supervisao("Supervisao Fiscal B", gerencias[0]),
            supervisao_repo.create_supervisao("Supervisao Arrecadacao A", gerencias[1]),
            supervisao_repo.create_supervisao("Supervisao Arrecadacao B", gerencias[1]),
            supervisao_repo.create_supervisao("Supervisao Tributaria A", gerencias[2]),
            supervisao_repo.create_supervisao("Supervisao Tributaria B", gerencias[2]),
        ]

        # Mapa supervisao -> gerencia
        sup_ger = {
            0: gerencias[0], 1: gerencias[0],  # Fiscalizacao
            2: gerencias[1], 3: gerencias[1],  # Arrecadacao
            4: gerencias[2], 5: gerencias[2],  # Tributacao
        }

        # ── Gerentes (1 por gerencia, matriculas 12345-12347) ─────
        gerentes = [
            ("Roberto Santos", "12345", gerencias[0]),
            ("Helena Rodrigues", "12346", gerencias[1]),
            ("Sergio Barbosa", "12347", gerencias[2]),
        ]
        for nome, mat, gid in gerentes:
            auth_service.register_user_with_options(
                username=nome,
                password=DEFAULT_PASSWORD,
                role="gerente",
                gerencia_id=gid,
                supervisao_id=None,
                must_change_password=True,
                matricula=mat,
            )

        # ── Supervisores (1 por supervisao, matriculas 23456-23461) ─
        supervisores = [
            ("Patricia Oliveira", "23456"),
            ("Joao Silva", "23457"),
            ("Maria Santos", "23458"),
            ("Ricardo Pereira", "23459"),
            ("Lucia Costa", "23460"),
            ("Antonio Ferreira", "23461"),
        ]
        for index, (nome, mat) in enumerate(supervisores):
            auth_service.register_user_with_options(
                username=nome,
                password=DEFAULT_PASSWORD,
                role="supervisor",
                gerencia_id=sup_ger[index],
                supervisao_id=supervisoes[index],
                must_change_password=True,
                matricula=mat,
            )

        # ── Fiscais (2-3 por supervisao, matriculas 34567+) ────────
        fiscais = [
            # Supervisao Fiscal A (sup 0)
            ("Carlos Mendes", "34567", 0),
            ("Ana Ribeiro", "34568", 0),
            ("Pedro Nascimento", "34569", 0),
            # Supervisao Fiscal B (sup 1)
            ("Jose Almeida", "34570", 1),
            ("Fernanda Costa", "34571", 1),
            # Supervisao Arrecadacao A (sup 2)
            ("Marcos Silva", "34572", 2),
            ("Claudia Souza", "34573", 2),
            ("Rafael Lima", "34574", 2),
            # Supervisao Arrecadacao B (sup 3)
            ("Juliana Martins", "34575", 3),
            ("Bruno Araujo", "34576", 3),
            # Supervisao Tributaria A (sup 4)
            ("Tatiana Gomes", "34577", 4),
            ("Diego Cardoso", "34578", 4),
            ("Vanessa Rocha", "34579", 4),
            # Supervisao Tributaria B (sup 5)
            ("Leandro Pinto", "34580", 5),
            ("Camila Teixeira", "34581", 5),
        ]
        for nome, mat, sup_idx in fiscais:
            auth_service.register_user_with_options(
                username=nome,
                password=DEFAULT_PASSWORD,
                role="fiscal",
                gerencia_id=sup_ger[sup_idx],
                supervisao_id=supervisoes[sup_idx],
                must_change_password=True,
                matricula=mat,
            )
        logger.info("Dados iniciais criados com sucesso (3 gerentes, 6 supervisores, 15 fiscais).")
    else:
        logger.info("Banco ja possui dados – seed ignorado.")


# ─── Auth helpers ───────────────────────────────────────────────
# Dependencias reutilizaveis do FastAPI para proteger endpoints.


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Extrai e valida o token Bearer do header Authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    token = authorization.split(" ", 1)[1]
    user = auth_service.get_user_from_token(token)
    if not user:
        logger.warning("Tentativa de acesso com token invalido.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")
    return user


def require_admin(user: dict[str, Any]) -> None:
    """Verifica se o usuario autenticado possui cargo admin."""
    if user["role"] != "admin":
        logger.warning("Acesso admin negado para usuario '%s' (role=%s)", user["username"], user["role"])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


# ─── Auth ───────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Autentica o usuario e retorna um token de acesso."""
    user = auth_service.authenticate_user(payload.username, payload.password)
    if not user:
        logger.info("Login falhou para usuario '%s'.", payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas")
    token = auth_service.create_token(int(user["id"]))
    logger.info("Login bem-sucedido: usuario '%s' (role=%s).", user["username"], user["role"])
    return LoginResponse(
        token=token,
        role=str(user["role"]),
        user_id=int(user["id"]),
        username=str(user["username"]),
        must_change_password=bool(user.get("must_change_password") or 0),
        matricula=user.get("matricula"),
        gerencia_id=user.get("gerencia_id"),
        gerencia_name=user.get("gerencia_name"),
        supervisao_id=user.get("supervisao_id"),
        supervisao_name=user.get("supervisao_name"),
    )


@app.post("/auth/change-password")
def change_password(
    payload: PasswordChangeRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, str]:
    """Permite que o usuario autenticado troque sua propria senha."""
    if not auth_service.authenticate_user(user["username"], payload.current_password):
        logger.info("Troca de senha falhou – senha atual incorreta (user=%s).", user["username"])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual invalida")
    auth_service.change_password(int(user["id"]), payload.new_password)
    logger.info("Senha alterada com sucesso para usuario '%s'.", user["username"])
    return {"status": "ok"}


# ─── Gerencias ──────────────────────────────────────────────────

@app.post("/admin/gerencias", response_model=GerenciaResponse)
def create_gerencia(
    payload: GerenciaCreateRequest, user: dict[str, Any] = Depends(get_current_user)
) -> GerenciaResponse:
    """Cria uma nova gerencia. Apenas admin."""
    require_admin(user)
    try:
        gerencia_id = gerencia_repo.create_gerencia(payload.name)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gerencia ja existe") from exc
    logger.info("Gerencia criada: id=%d, name='%s'.", gerencia_id, payload.name)
    return GerenciaResponse(id=gerencia_id, name=payload.name)


@app.get("/admin/gerencias", response_model=list[GerenciaResponse])
def list_gerencias(user: dict[str, Any] = Depends(get_current_user)) -> list[GerenciaResponse]:
    """Lista todas as gerencias. Apenas admin."""
    require_admin(user)
    return [GerenciaResponse(**row) for row in gerencia_repo.list_gerencias()]


@app.put("/admin/gerencias/{gerencia_id}")
def update_gerencia(
    gerencia_id: int,
    payload: GerenciaUpdateRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Atualiza o nome de uma gerencia existente. Apenas admin."""
    require_admin(user)
    if not gerencia_repo.get_gerencia(gerencia_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gerencia nao encontrada")
    gerencia_repo.update_gerencia(gerencia_id, payload.name)
    logger.info("Gerencia atualizada: id=%d, novo_nome='%s'.", gerencia_id, payload.name)
    return {"status": "ok"}


# ─── Supervisoes ────────────────────────────────────────────────

@app.post("/admin/supervisoes", response_model=SupervisaoResponse)
def create_supervisao(
    payload: SupervisaoCreateRequest, user: dict[str, Any] = Depends(get_current_user)
) -> SupervisaoResponse:
    """Cria uma supervisao vinculada a uma gerencia. Apenas admin."""
    require_admin(user)
    if not gerencia_repo.get_gerencia(payload.gerencia_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gerencia invalida")
    supervisao_id = supervisao_repo.create_supervisao(payload.name, payload.gerencia_id)
    supervisao = supervisao_repo.get_supervisao(supervisao_id)
    logger.info("Supervisao criada: id=%d, name='%s', gerencia_id=%d.", supervisao_id, payload.name, payload.gerencia_id)
    return SupervisaoResponse(**supervisao)


@app.get("/admin/supervisoes", response_model=list[SupervisaoResponse])
def list_supervisoes(user: dict[str, Any] = Depends(get_current_user)) -> list[SupervisaoResponse]:
    """Lista todas as supervisoes com nome da gerencia. Apenas admin."""
    require_admin(user)
    return [SupervisaoResponse(**row) for row in supervisao_repo.list_supervisoes()]


@app.put("/admin/supervisoes/{supervisao_id}")
def update_supervisao(
    supervisao_id: int,
    payload: SupervisaoUpdateRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Atualiza nome e gerencia de uma supervisao. Apenas admin."""
    require_admin(user)
    if not supervisao_repo.get_supervisao(supervisao_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supervisao nao encontrada")
    if not gerencia_repo.get_gerencia(payload.gerencia_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gerencia invalida")
    supervisao_repo.update_supervisao(supervisao_id, payload.name, payload.gerencia_id)
    logger.info("Supervisao atualizada: id=%d.", supervisao_id)
    return {"status": "ok"}


# ─── Users ──────────────────────────────────────────────────────

@app.post("/admin/users", response_model=UserResponse)
def create_user(
    payload: UserCreateRequest, user: dict[str, Any] = Depends(get_current_user)
) -> UserResponse:
    """Cria um novo usuario com senha padrao temporaria. Apenas admin."""
    require_admin(user)
    _validate_user_payload(payload.role, payload.gerencia_id, payload.supervisao_id)
    try:
        user_id = auth_service.register_user_with_options(
            username=payload.username,
            password=DEFAULT_PASSWORD,
            role=payload.role,
            gerencia_id=payload.gerencia_id,
            supervisao_id=payload.supervisao_id,
            must_change_password=True,
            matricula=payload.matricula,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario ja existe") from exc
    logger.info("Usuario criado: id=%d, username='%s', role='%s'.", user_id, payload.username, payload.role)
    created = user_repo.get_user_by_id(user_id)
    return UserResponse(**created)


@app.put("/admin/users/{user_id}")
def update_user(
    user_id: int, payload: UserUpdateRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, str]:
    """Atualiza dados de um usuario (exceto admin). Apenas admin."""
    require_admin(user)
    target = user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    if target["role"] == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edicao de admin nao permitida")
    _validate_user_payload(payload.role, payload.gerencia_id, payload.supervisao_id)
    try:
        user_repo.update_user(
            user_id=user_id,
            username=payload.username,
            role=payload.role,
            gerencia_id=payload.gerencia_id,
            supervisao_id=payload.supervisao_id,
            matricula=payload.matricula,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario ja existe") from exc
    logger.info("Usuario atualizado: id=%d.", user_id)
    return {"status": "ok"}


@app.get("/admin/users", response_model=list[UserResponse])
def list_users(user: dict[str, Any] = Depends(get_current_user)) -> list[UserResponse]:
    """Lista todos os usuarios com suas gerencias e supervisoes. Apenas admin."""
    require_admin(user)
    return [UserResponse(**row) for row in user_repo.list_users()]


@app.post("/admin/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_user_password(
    user_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> PasswordResetResponse:
    """Reseta a senha do usuario para a senha padrao temporaria. Apenas admin."""
    require_admin(user)
    target = user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    auth_service.reset_password(user_id, DEFAULT_PASSWORD)
    logger.info("Senha resetada para usuario id=%d por admin '%s'.", user_id, user["username"])
    return PasswordResetResponse(temporary_password=DEFAULT_PASSWORD)


@app.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> Response:
    """Remove um usuario do sistema. Apenas admin. Nao permite auto-exclusao."""
    require_admin(user)
    if user["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nao e possivel excluir seu proprio usuario.",
        )
    target = user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado"
        )
    if target["role"] == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Nao e possivel excluir um admin.",
        )
    if not user_repo.delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado"
        )
    logger.info("Usuario id=%d removido por admin '%s'.", user_id, user["username"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Ordens de Servico (somente consulta - API externa) ────────

def _build_hierarchy_filters(user: dict[str, Any]) -> dict[str, Any]:
    """Monta os parametros de filtragem hierarquica a partir do usuario logado."""
    filters: dict[str, Any] = {
        "user_role": user["role"],
        "user_matricula": user.get("matricula"),
        "user_name": user.get("username"),
        "supervisor_matriculas": None,
    }
    if user["role"] == "gerente" and user.get("gerencia_id"):
        filters["supervisor_matriculas"] = user_repo.get_supervisor_matriculas_by_gerencia(
            int(user["gerencia_id"])
        )
    return filters


@app.get("/ordens", response_model=list[OSResponse])
def list_os(
    status_filter: str | None = Query(default=None, alias="status"),
    tipo: str | None = Query(default=None),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[OSResponse]:
    """Lista Ordens de Servico da API externa (Informix), filtradas pela hierarquia."""
    filters = _build_hierarchy_filters(user)
    rows = listar_ordens_servico(status_filter=status_filter, tipo=tipo, **filters)
    return [OSResponse(**row) for row in rows]


@app.get("/ordens/{numero}", response_model=OSDetalheResponse)
def get_os(
    numero: str, user: dict[str, Any] = Depends(get_current_user)
) -> OSDetalheResponse:
    """Busca OS por numero na API externa, verificando permissao hierarquica."""
    ordem = consultar_os_por_numero(numero)
    if not ordem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    # Verifica se o usuario tem permissao para ver esta OS
    filters = _build_hierarchy_filters(user)
    allowed = _filtrar_por_hierarquia([ordem], **filters)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissao para esta OS")
    return OSDetalheResponse(**ordem)


@app.get("/ordens/{numero}/pdf")
def get_os_pdf(
    numero: str, user: dict[str, Any] = Depends(get_current_user)
) -> Response:
    """Gera PDF detalhado de uma OS individual, incluindo movimentacoes."""
    ordem = consultar_os_por_numero(numero)
    if not ordem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    filters = _build_hierarchy_filters(user)
    allowed = _filtrar_por_hierarquia([ordem], **filters)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissao para esta OS")

    status_map = {
        "aberta": "Aberta", "em_andamento": "Em Andamento",
        "concluida": "Concluida", "cancelada": "Cancelada",
    }

    pdf = _PDF(f"Ordem de Servico - {ordem['numero']}")
    pdf.alias_nb_pages()
    pdf.add_page(orientation="P")

    # --- Cabecalho da OS ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, ordem["numero"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, ordem.get("razao_social", ""), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # --- Informacoes Gerais ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 245)
    pdf.cell(0, 7, "  Informacoes Gerais", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(2)

    def _field(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(45, 5, label + ":")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, _safe(value), new_x="LMARGIN", new_y="NEXT")

    _field("Status", status_map.get(ordem.get("status", ""), ordem.get("status", "")))
    _field("Tipo", ordem.get("tipo", ""))
    _field("Prioridade", ordem.get("prioridade", ""))
    _field("IE", ordem.get("ie", ""))
    _field("CNPJ", ordem.get("cnpj", ""))
    _field("Endereco", ordem.get("endereco", ""))
    _field("Telefone", ordem.get("telefone", ""))
    valor_est = ordem.get("valor_estimado", 0)
    _field("Valor Estimado", f"R$ {valor_est:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor_est else "-")
    _field("Supervisor", ordem.get("matricula_supervisor", ""))
    _field("Fiscais", ", ".join(ordem.get("fiscais", [])))
    pdf.ln(2)

    # --- Datas ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "  Datas", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(2)
    _field("Abertura", _fmt_data_br(ordem.get("data_abertura")))
    _field("Ciencia", _fmt_data_br(ordem.get("data_ciencia")))
    _field("Ultima Movimentacao", _fmt_data_br(ordem.get("data_ultima_movimentacao")))
    dias = _calcular_dias_parado(ordem.get("data_ultima_movimentacao"))
    if ordem.get("status") in ("aberta", "em_andamento"):
        _field("Dias Parado", str(dias))
    pdf.ln(2)

    # --- Objeto e Observacoes ---
    if ordem.get("objeto"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "  Objeto da Fiscalizacao", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(0, 5, _safe(ordem["objeto"]))
        pdf.ln(2)

    if ordem.get("observacoes"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "  Observacoes", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(0, 5, _safe(ordem["observacoes"]))
        pdf.ln(2)

    # --- Movimentacoes ---
    movs = ordem.get("movimentacoes", [])
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, f"  Movimentacoes ({len(movs)})", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(2)

    if movs:
        m_headers = ["Data", "Tipo", "Descricao", "Responsavel"]
        m_widths = [22, 25, 100, 40]
        pdf.set_font("Helvetica", "B", 7)
        for i, h in enumerate(m_headers):
            pdf.cell(m_widths[i], 6, h, border=1, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        for mov in movs:
            x_start = pdf.get_x()
            y_start = pdf.get_y()

            # Calcular altura necessaria para descricao (multi_cell)
            desc_text = _safe(mov.get("descricao", ""))
            # Estimar linhas necessarias
            desc_width = m_widths[2] - 2
            n_lines = max(1, len(desc_text) // 55 + 1)
            row_h = max(5, n_lines * 4.5)

            pdf.cell(m_widths[0], row_h, _fmt_data_br(mov.get("data")), border=1, align="C")
            pdf.cell(m_widths[1], row_h, _safe(mov.get("tipo", "")), border=1, align="C")
            pdf.cell(m_widths[2], row_h, desc_text[:70], border=1)
            pdf.cell(m_widths[3], row_h, _safe(mov.get("responsavel", "")), border=1, align="C")
            pdf.ln()
    else:
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, "Nenhuma movimentacao registrada.", new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = bytes(pdf.output())
    filename = f"{ordem['numero']}.pdf"
    logger.info("PDF da OS %s gerado por '%s'.", numero, user["username"])

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/alertas", response_model=list[AlertaResponse])
def list_alertas(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[AlertaResponse]:
    """Lista alertas gerados a partir das OS visiveis ao usuario."""
    filters = _build_hierarchy_filters(user)
    return [AlertaResponse(**a) for a in gerar_alertas(**filters)]


# ─── Dashboard (somente admin) ─────────────────────────────────

@app.get("/admin/dashboard")
def get_dashboard(
    user: dict[str, Any] = Depends(get_current_user),
    data_inicio: str | None = Query(None, description="Filtro data inicio (YYYY-MM-DD)"),
    data_fim: str | None = Query(None, description="Filtro data fim (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Retorna metricas consolidadas para o dashboard administrativo. Apenas admin."""
    require_admin(user)

    todas_os = listar_ordens_servico()

    # Filtro por periodo (baseado em data_abertura)
    if data_inicio or data_fim:
        filtradas = []
        for o in todas_os:
            dt_ab = o.get("data_abertura", "")
            if not dt_ab:
                continue
            if data_inicio and dt_ab < data_inicio:
                continue
            if data_fim and dt_ab > data_fim:
                continue
            filtradas.append(o)
        todas_os = filtradas

    gerencias_list = gerencia_repo.list_gerencias()
    supervisoes_list = supervisao_repo.list_supervisoes()
    users_list = user_repo.list_users()

    return gerar_dashboard(todas_os, gerencias_list, supervisoes_list, users_list)


# ─── Relatorios (sob demanda) ──────────────────────────────────

def _calcular_dias_parado(data_ult: str | None) -> int:
    """Retorna numero de dias desde a ultima movimentacao."""
    if not data_ult:
        return 0
    try:
        dt = datetime.strptime(data_ult, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return 0


def _fmt_data_br(valor: str | None) -> str:
    """Converte data ISO (YYYY-MM-DD) para formato brasileiro (DD/MM/YYYY)."""
    if not valor:
        return ""
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return valor


@app.get("/relatorios/ordens")
def relatorio_ordens_csv(
    user: dict[str, Any] = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    tipo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> StreamingResponse:
    """Gera relatorio CSV das Ordens de Servico visiveis ao usuario, com filtros."""
    filters = _build_hierarchy_filters(user)
    rows = listar_ordens_servico(status_filter=status_filter, tipo=tipo, **filters)

    # Filtro por periodo
    if data_inicio or data_fim:
        filtered = []
        for o in rows:
            dt_ab = o.get("data_abertura", "")
            if not dt_ab:
                continue
            if data_inicio and dt_ab < data_inicio:
                continue
            if data_fim and dt_ab > data_fim:
                continue
            filtered.append(o)
        rows = filtered

    # Filtro por texto livre
    if search:
        term = search.lower()
        rows = [
            o for o in rows
            if term in o.get("numero", "").lower()
            or term in o.get("razao_social", "").lower()
            or term in o.get("ie", "").lower()
            or term in o.get("matricula_supervisor", "").lower()
            or any(term in f.lower() for f in o.get("fiscais", []))
        ]

    # Gerar CSV com BOM para Excel reconhecer UTF-8
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Numero", "Tipo", "IE", "Razao Social", "Matricula Supervisor",
        "Fiscais", "Status", "Prioridade", "Data Abertura", "Data Ciencia",
        "Ultima Movimentacao", "Dias Parado",
    ])
    for o in rows:
        dias = _calcular_dias_parado(o.get("data_ultima_movimentacao"))
        writer.writerow([
            o.get("numero", ""),
            o.get("tipo", ""),
            o.get("ie", ""),
            o.get("razao_social", ""),
            o.get("matricula_supervisor", ""),
            ", ".join(o.get("fiscais", [])),
            o.get("status", ""),
            o.get("prioridade", ""),
            _fmt_data_br(o.get("data_abertura")),
            _fmt_data_br(o.get("data_ciencia")),
            _fmt_data_br(o.get("data_ultima_movimentacao")),
            dias,
        ])

    output.seek(0)
    today = date.today().strftime("%Y-%m-%d")
    filename = f"relatorio_ordens_{today}.csv"
    logger.info("Relatorio CSV gerado por '%s': %d registros.", user["username"], len(rows))

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _filtrar_ordens(user, status_filter, tipo, data_inicio, data_fim, search):
    """Aplica filtros comuns de OS para reuso entre CSV e PDF."""
    filters = _build_hierarchy_filters(user)
    rows = listar_ordens_servico(status_filter=status_filter, tipo=tipo, **filters)

    if data_inicio or data_fim:
        filtered = []
        for o in rows:
            dt_ab = o.get("data_abertura", "")
            if not dt_ab:
                continue
            if data_inicio and dt_ab < data_inicio:
                continue
            if data_fim and dt_ab > data_fim:
                continue
            filtered.append(o)
        rows = filtered

    if search:
        term = search.lower()
        rows = [
            o for o in rows
            if term in o.get("numero", "").lower()
            or term in o.get("razao_social", "").lower()
            or term in o.get("ie", "").lower()
            or term in o.get("matricula_supervisor", "").lower()
            or any(term in f.lower() for f in o.get("fiscais", []))
        ]
    return rows


class _PDF(FPDF):
    """PDF com cabecalho e rodape padrao."""

    def __init__(self, titulo: str):
        super().__init__(orientation="L", format="A4")
        self._titulo = titulo
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, self._titulo, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Gerado em {date.today().strftime('%d/%m/%Y')}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")


def _safe(val) -> str:
    """Converte valor para string segura para o PDF."""
    if val is None:
        return ""
    return str(val)


@app.get("/relatorios/ordens/pdf")
def relatorio_ordens_pdf(
    user: dict[str, Any] = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    tipo: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> Response:
    """Gera relatorio PDF das Ordens de Servico."""
    rows = _filtrar_ordens(user, status_filter, tipo, data_inicio, data_fim, search)

    pdf = _PDF("Relatorio de Ordens de Servico")
    pdf.alias_nb_pages()
    pdf.add_page()

    # Cabecalho da tabela
    headers = ["Numero", "Tipo", "IE", "Razao Social", "Status", "Prioridade",
               "Dt Abertura", "Dt Ciencia", "Ult. Mov.", "Dias Parado"]
    col_widths = [25, 18, 22, 60, 22, 20, 24, 24, 24, 20]

    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align="C")
    pdf.ln()

    # Dados
    pdf.set_font("Helvetica", "", 6.5)
    for o in rows:
        dias = _calcular_dias_parado(o.get("data_ultima_movimentacao"))
        vals = [
            _safe(o.get("numero")),
            _safe(o.get("tipo")),
            _safe(o.get("ie")),
            _safe(o.get("razao_social"))[:40],
            _safe(o.get("status")),
            _safe(o.get("prioridade")),
            _fmt_data_br(o.get("data_abertura")),
            _fmt_data_br(o.get("data_ciencia")),
            _fmt_data_br(o.get("data_ultima_movimentacao")),
            str(dias),
        ]
        for i, v in enumerate(vals):
            pdf.cell(col_widths[i], 5, v, border=1, align="C")
        pdf.ln()

    pdf_bytes = bytes(pdf.output())
    today = date.today().strftime("%Y-%m-%d")
    filename = f"relatorio_ordens_{today}.pdf"
    logger.info("Relatorio PDF OS gerado por '%s': %d registros.", user["username"], len(rows))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/relatorios/dashboard/pdf")
def relatorio_dashboard_pdf(
    user: dict[str, Any] = Depends(get_current_user),
    data_inicio: str | None = Query(None),
    data_fim: str | None = Query(None),
) -> Response:
    """Gera relatorio PDF do dashboard. Apenas admin."""
    require_admin(user)

    todas_os = listar_ordens_servico()
    if data_inicio or data_fim:
        todas_os = [
            o for o in todas_os
            if o.get("data_abertura")
            and (not data_inicio or o["data_abertura"] >= data_inicio)
            and (not data_fim or o["data_abertura"] <= data_fim)
        ]

    gerencias_list = gerencia_repo.list_gerencias()
    supervisoes_list = supervisao_repo.list_supervisoes()
    users_list = user_repo.list_users()
    dashboard = gerar_dashboard(todas_os, gerencias_list, supervisoes_list, users_list)

    pdf = _PDF("Relatorio de Desempenho - Dashboard")
    pdf.alias_nb_pages()
    pdf.add_page()

    # ─── Resumo Geral ───
    visao = dashboard.get("visao_geral", {})
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Resumo Geral", new_x="LMARGIN", new_y="NEXT")
    rg_headers = ["Total OS", "Abertas", "Em Andamento", "Concluidas",
                  "Canceladas", "Dias Parado Med.", "Criticas", "Sem Ciencia"]
    rg_vals = [
        visao.get("total_os", 0), visao.get("os_abertas", 0),
        visao.get("os_em_andamento", 0), visao.get("os_concluidas", 0),
        visao.get("os_canceladas", 0), visao.get("dias_parado_medio", 0),
        visao.get("os_criticas", 0), visao.get("os_sem_ciencia", 0),
    ]
    w = 33
    pdf.set_font("Helvetica", "B", 7)
    for h in rg_headers:
        pdf.cell(w, 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for v in rg_vals:
        pdf.cell(w, 5, str(v), border=1, align="C")
    pdf.ln(8)

    # ─── Gerencias ───
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Desempenho por Gerencia", new_x="LMARGIN", new_y="NEXT")
    g_headers = ["Gerencia", "Total", "Abertas", "Andamento", "Concluidas",
                 "Taxa (%)", "Dias Par. Med.", "Criticas", "Tempo Med."]
    g_widths = [55, 20, 22, 25, 25, 22, 30, 22, 30]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(g_headers):
        pdf.cell(g_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for g in dashboard.get("desempenho_gerencias", []):
        vals = [
            _safe(g.get("nome"))[:35], str(g.get("total_os", 0)),
            str(g.get("abertas", 0)), str(g.get("em_andamento", 0)),
            str(g.get("concluidas", 0)), str(g.get("taxa_conclusao", 0)),
            str(g.get("dias_parado_medio", 0)), str(g.get("os_criticas", 0)),
            str(g.get("tempo_medio_conclusao", 0)),
        ]
        for i, v in enumerate(vals):
            pdf.cell(g_widths[i], 5, v, border=1, align="C")
        pdf.ln()
    pdf.ln(5)

    # ─── Supervisoes ───
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Desempenho por Supervisao", new_x="LMARGIN", new_y="NEXT")
    s_headers = ["Supervisao", "Gerencia", "Total", "Abertas", "Andamento",
                 "Concluidas", "Taxa (%)", "Dias Par. Med.", "Criticas"]
    s_widths = [50, 50, 20, 22, 25, 25, 22, 30, 22]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(s_headers):
        pdf.cell(s_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for s in dashboard.get("desempenho_supervisoes", []):
        vals = [
            _safe(s.get("nome"))[:32], _safe(s.get("gerencia_nome"))[:32],
            str(s.get("total_os", 0)), str(s.get("abertas", 0)),
            str(s.get("em_andamento", 0)), str(s.get("concluidas", 0)),
            str(s.get("taxa_conclusao", 0)), str(s.get("dias_parado_medio", 0)),
            str(s.get("os_criticas", 0)),
        ]
        for i, v in enumerate(vals):
            pdf.cell(s_widths[i], 5, v, border=1, align="C")
        pdf.ln()
    pdf.ln(5)

    # ─── Fiscais ───
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Carga por Fiscal", new_x="LMARGIN", new_y="NEXT")
    f_headers = ["Fiscal", "OS Ativas", "Dias Parado Med.", "Criticas"]
    f_widths = [100, 40, 50, 40]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(f_headers):
        pdf.cell(f_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for f in dashboard.get("carga_fiscais", []):
        vals = [
            _safe(f.get("nome"))[:60], str(f.get("os_ativas", 0)),
            str(f.get("dias_parado_medio", 0)), str(f.get("os_criticas", 0)),
        ]
        for i, v in enumerate(vals):
            pdf.cell(f_widths[i], 5, v, border=1, align="C")
        pdf.ln()

    pdf_bytes = bytes(pdf.output())
    today = date.today().strftime("%Y-%m-%d")
    filename = f"relatorio_dashboard_{today}.pdf"
    logger.info("Relatorio Dashboard PDF gerado por '%s'.", user["username"])

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/relatorios/dashboard")
def relatorio_dashboard_csv(
    user: dict[str, Any] = Depends(get_current_user),
    data_inicio: str | None = Query(None),
    data_fim: str | None = Query(None),
) -> StreamingResponse:
    """Gera relatorio CSV do dashboard (desempenho por gerencia/supervisao). Apenas admin."""
    require_admin(user)

    todas_os = listar_ordens_servico()
    if data_inicio or data_fim:
        todas_os = [
            o for o in todas_os
            if o.get("data_abertura")
            and (not data_inicio or o["data_abertura"] >= data_inicio)
            and (not data_fim or o["data_abertura"] <= data_fim)
        ]

    gerencias_list = gerencia_repo.list_gerencias()
    supervisoes_list = supervisao_repo.list_supervisoes()
    users_list = user_repo.list_users()
    dashboard = gerar_dashboard(todas_os, gerencias_list, supervisoes_list, users_list)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")

    # Resumo geral
    visao = dashboard.get("visao_geral", {})
    writer.writerow(["=== RESUMO GERAL ==="])
    writer.writerow(["Total OS", "Abertas", "Em Andamento", "Concluidas", "Canceladas",
                      "Dias Parado Medio", "OS Criticas", "OS Sem Ciencia"])
    writer.writerow([
        visao.get("total_os", 0),
        visao.get("os_abertas", 0),
        visao.get("os_em_andamento", 0),
        visao.get("os_concluidas", 0),
        visao.get("os_canceladas", 0),
        visao.get("dias_parado_medio", 0),
        visao.get("os_criticas", 0),
        visao.get("os_sem_ciencia", 0),
    ])
    writer.writerow([])

    # Por gerencia
    writer.writerow(["=== DESEMPENHO POR GERENCIA ==="])
    writer.writerow([
        "Gerencia", "Total OS", "Abertas", "Em Andamento", "Concluidas",
        "Taxa Conclusao (%)", "Dias Parado Medio", "OS Criticas", "Tempo Med. Conclusao",
    ])
    for g in dashboard.get("desempenho_gerencias", []):
        writer.writerow([
            g.get("nome", ""),
            g.get("total_os", 0),
            g.get("abertas", 0),
            g.get("em_andamento", 0),
            g.get("concluidas", 0),
            g.get("taxa_conclusao", 0),
            g.get("dias_parado_medio", 0),
            g.get("os_criticas", 0),
            g.get("tempo_medio_conclusao", 0),
        ])
    writer.writerow([])

    # Por supervisao
    writer.writerow(["=== DESEMPENHO POR SUPERVISAO ==="])
    writer.writerow([
        "Supervisao", "Gerencia", "Total OS", "Abertas", "Em Andamento",
        "Concluidas", "Taxa Conclusao (%)", "Dias Parado Medio", "OS Criticas",
    ])
    for s in dashboard.get("desempenho_supervisoes", []):
        writer.writerow([
            s.get("nome", ""),
            s.get("gerencia_nome", ""),
            s.get("total_os", 0),
            s.get("abertas", 0),
            s.get("em_andamento", 0),
            s.get("concluidas", 0),
            s.get("taxa_conclusao", 0),
            s.get("dias_parado_medio", 0),
            s.get("os_criticas", 0),
        ])
    writer.writerow([])

    # Por fiscal
    writer.writerow(["=== CARGA POR FISCAL ==="])
    writer.writerow(["Fiscal", "OS Ativas", "Dias Parado Medio", "OS Criticas"])
    for f in dashboard.get("carga_fiscais", []):
        writer.writerow([
            f.get("nome", ""),
            f.get("os_ativas", 0),
            f.get("dias_parado_medio", 0),
            f.get("os_criticas", 0),
        ])

    output.seek(0)
    today = date.today().strftime("%Y-%m-%d")
    filename = f"relatorio_dashboard_{today}.csv"
    logger.info("Relatorio Dashboard CSV gerado por '%s'.", user["username"])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
