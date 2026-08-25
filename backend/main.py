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
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fpdf import FPDF
from sqlite3 import IntegrityError
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import seed
from .auth import (
    AuthService,
    LimitadorLogin,
    PasswordHasher,
    TokenStore,
    gerar_senha_temporaria,
)
from .config import ADMIN_PASSWORD, APP_TITLE, CORS_ORIGINS, setup_logging
from .db import (
    DB_PATH,
    Database,
    EquipeFiscalRepository,
    GerenciaRepository,
    SupervisaoRepository,
    UserRepository,
)
from .external_api import (
    detalhar_ordem_atf,
    detalhe_em_outro_ambiente,
    filtrar_atf_por_matriculas,
    gerar_alertas,
    gerar_dashboard,
    listar_ordens_atf,
    listar_ordens_servico,
    mesclar_detalhe_os,
)
from .schemas import (
    AlertaResponse,
    EquipeFiscalResponse,
    EquipeMembroResponse,
    GerenciaCreateRequest,
    GerenciaResponse,
    GerenciaUpdateRequest,
    LoginRequest,
    LoginResponse,
    OrdensATFResponse,
    OSDetalheCompletoResponse,
    OSDetalheResponse,
    PasswordChangeRequest,
    PasswordResetResponse,
    SupervisaoCreateRequest,
    SupervisaoResponse,
    SupervisaoUpdateRequest,
    UserCreateRequest,
    UserCreatedResponse,
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
equipe_repo = EquipeFiscalRepository(database)
auth_service = AuthService(user_repo, PasswordHasher(), TokenStore())
limitador_login = LimitadorLogin()

# Cargos permitidos para usuarios comuns (admin e criado automaticamente)
ALLOWED_ROLES = {"gerente", "supervisor", "fiscal"}


def _validate_user_payload(
    role: str, gerencia_id: int, supervisao_id: int, equipe_codigo: int | None = None,
) -> None:
    """Valida campos de cargo e lotacao para criacao/edicao de usuario."""
    if equipe_codigo is not None and not equipe_repo.get_equipe(equipe_codigo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Equipe fiscal invalida ou nao importada",
        )
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

    # O admin e verificado por si, e nao por "o banco esta vazio": os
    # importadores em lote criam usuarios sem passar por aqui, e um banco
    # so com auditores importados ficaria sem ninguem capaz de administra-lo.
    if user_repo.get_user_by_username("admin") is None:
        # A senha do admin vem do .env; sem ela, gera uma aleatoria e
        # registra no log. Em nenhum caso ha credencial fixa no codigo.
        admin_password = ADMIN_PASSWORD or gerar_senha_temporaria()
        auth_service.register_user("admin", admin_password, "admin")
        if not ADMIN_PASSWORD:
            logger.warning(
                "ADMIN_PASSWORD nao definido no .env. Senha gerada para 'admin': %s "
                "— anote agora, ela nao sera exibida de novo.",
                admin_password,
            )

    # Alem do admin ja existe gente: banco em uso, nada a semear.
    if user_repo.count_users() > 1:
        logger.info("Banco ja possui usuarios – seed de exemplo ignorado.")
        return

    # Banco sem usuarios mas com equipes importadas e um banco que ja foi
    # preparado com dados reais da SEFAZ. Encher de gente ficticia ali so
    # atrapalharia: as matriculas de exemplo nao existem em equipe alguma
    # e nunca casariam com uma OS do ATF.
    if equipe_repo.count_equipes() > 0:
        logger.info(
            "Equipes fiscais ja importadas – criado so o admin, sem dados de exemplo. "
            "Use 'python -m backend.importar_usuarios' para cadastrar os auditores."
        )
        return

    logger.info("Banco vazio – criando dados iniciais (admin + seed)...")

    gerencias = [gerencia_repo.create_gerencia(nome) for nome in seed.GERENCIAS]
    supervisoes = [
        supervisao_repo.create_supervisao(nome, gerencias[idx_ger])
        for nome, idx_ger in seed.SUPERVISOES
    ]
    # Mapa supervisao -> gerencia, para lotar cada usuario nas duas
    sup_ger = {i: gerencias[idx_ger] for i, (_, idx_ger) in enumerate(seed.SUPERVISOES)}

    # Os usuarios do seed nascem com senha aleatoria individual, que e
    # descartada: ninguem precisa dela. O acesso se da pelo admin, que
    # usa "Resetar Senha" e recebe uma senha nova na hora.

    for nome, mat, idx_ger in seed.GERENTES:
        auth_service.register_user_with_options(
            username=nome,
            password=gerar_senha_temporaria(),
            role="gerente",
            gerencia_id=gerencias[idx_ger],
            supervisao_id=None,
            must_change_password=True,
            matricula=mat,
        )

    for cargo, pessoas in (("supervisor", seed.SUPERVISORES), ("fiscal", seed.FISCAIS)):
        for nome, mat, idx_sup in pessoas:
            auth_service.register_user_with_options(
                username=nome,
                password=gerar_senha_temporaria(),
                role=cargo,
                gerencia_id=sup_ger[idx_sup],
                supervisao_id=supervisoes[idx_sup],
                must_change_password=True,
                matricula=mat,
            )

    logger.info(
        "Dados iniciais criados com sucesso (%d gerentes, %d supervisores, %d fiscais).",
        len(seed.GERENTES), len(seed.SUPERVISORES), len(seed.FISCAIS),
    )


# ─── Auth helpers ───────────────────────────────────────────────
# Dependencias reutilizaveis do FastAPI para proteger endpoints.


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """
    Extrai e valida o token Bearer do header Authorization.

    NAO verifica must_change_password — use apenas em endpoints que o
    usuario precisa alcancar justamente para trocar a senha. Todo o resto
    da API depende de get_active_user.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    token = authorization.split(" ", 1)[1]
    user = auth_service.get_user_from_token(token)
    if not user:
        logger.warning("Tentativa de acesso com token invalido, revogado ou vencido.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao invalida ou expirada. Entre novamente.",
        )
    # O token acompanha o usuario para que logout e troca de senha possam
    # revogar sessoes sem reabrir o header.
    user["token_sessao"] = token
    return user


def get_active_user(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """
    Usuario autenticado E com a senha ja definida.

    O bloqueio precisa estar aqui, no backend: a tela de troca de senha do
    frontend nao protege nada contra quem chama a API direto com o token
    devolvido pelo login, que e emitido normalmente mesmo com a flag ativa.
    """
    if user.get("must_change_password"):
        logger.info("Acesso bloqueado – troca de senha pendente (user=%s).", user["username"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Troca de senha obrigatoria antes de usar o sistema.",
        )
    return user


def require_admin(user: dict[str, Any]) -> None:
    """Verifica se o usuario autenticado possui cargo admin."""
    if user["role"] != "admin":
        logger.warning("Acesso admin negado para usuario '%s' (role=%s)", user["username"], user["role"])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


# ─── Auth ───────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """
    Autentica o usuario e retorna um token de acesso.

    O bloqueio por tentativas e conferido antes de verificar a senha: alem
    de conter forca bruta, evita que uma rajada gaste CPU com PBKDF2.
    """
    ip = request.client.host if request.client else None
    espera = limitador_login.segundos_de_bloqueio(payload.username, ip)
    if espera:
        logger.warning(
            "Login bloqueado por excesso de tentativas (usuario='%s', ip=%s).",
            payload.username, ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas. Tente novamente em {espera // 60 + 1} minuto(s).",
            headers={"Retry-After": str(espera)},
        )

    user = auth_service.authenticate_user(payload.username, payload.password)
    if not user:
        limitador_login.registrar_falha(payload.username, ip)
        logger.info("Login falhou para usuario '%s' (ip=%s).", payload.username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas")

    limitador_login.registrar_sucesso(payload.username)
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
        equipe_codigo=user.get("equipe_codigo"),
        equipe_nome=user.get("equipe_nome"),
    )


@app.post("/auth/change-password")
def change_password(
    payload: PasswordChangeRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, str]:
    """
    Permite que o usuario autenticado troque sua propria senha.

    Unico endpoint em get_current_user em vez de get_active_user: quem tem
    must_change_password pendente precisa justamente chegar aqui.
    """
    if not auth_service.authenticate_user(user["username"], payload.current_password):
        logger.info("Troca de senha falhou – senha atual incorreta (user=%s).", user["username"])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual invalida")
    auth_service.change_password(
        int(user["id"]), payload.new_password, manter_token=user.get("token_sessao"),
    )
    logger.info("Senha alterada com sucesso para usuario '%s'.", user["username"])
    return {"status": "ok"}


@app.post("/auth/logout")
def logout(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """
    Encerra a sessao atual no servidor.

    Sem isto, sair da aplicacao apenas descartava o token no navegador — no
    backend ele continuava valido ate vencer.
    """
    auth_service.revoke_token(user["token_sessao"])
    logger.info("Logout de '%s'.", user["username"])
    return {"status": "ok"}


# ─── Gerencias ──────────────────────────────────────────────────

@app.post("/admin/gerencias", response_model=GerenciaResponse)
def create_gerencia(
    payload: GerenciaCreateRequest, user: dict[str, Any] = Depends(get_active_user)
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
def list_gerencias(user: dict[str, Any] = Depends(get_active_user)) -> list[GerenciaResponse]:
    """Lista todas as gerencias. Apenas admin."""
    require_admin(user)
    return [GerenciaResponse(**row) for row in gerencia_repo.list_gerencias()]


@app.put("/admin/gerencias/{gerencia_id}")
def update_gerencia(
    gerencia_id: int,
    payload: GerenciaUpdateRequest,
    user: dict[str, Any] = Depends(get_active_user),
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
    payload: SupervisaoCreateRequest, user: dict[str, Any] = Depends(get_active_user)
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
def list_supervisoes(user: dict[str, Any] = Depends(get_active_user)) -> list[SupervisaoResponse]:
    """Lista todas as supervisoes com nome da gerencia. Apenas admin."""
    require_admin(user)
    return [SupervisaoResponse(**row) for row in supervisao_repo.list_supervisoes()]


@app.get("/equipes-fiscais", response_model=list[EquipeFiscalResponse])
def list_equipes_fiscais(
    user: dict[str, Any] = Depends(get_active_user),
) -> list[EquipeFiscalResponse]:
    """
    Equipes fiscais do ATF, para o filtro de OS e para a tela de admin.

    Aberto a qualquer usuario autenticado, e nao so ao admin: o filtro
    "Equipe Fiscal" do painel monta o select com esta lista. Sao nomes de
    equipe, sem nenhum dado de pessoa.

    Volta vazio enquanto a planilha nao for importada — o painel entao
    cai no campo de codigo, que e o comportamento antigo.
    """
    return [EquipeFiscalResponse(**row) for row in equipe_repo.list_equipes()]


@app.get("/admin/equipes-fiscais/{codigo}/membros", response_model=list[EquipeMembroResponse])
def list_membros_equipe(
    codigo: int, user: dict[str, Any] = Depends(get_active_user)
) -> list[EquipeMembroResponse]:
    """
    Auditores de uma equipe fiscal. Apenas admin.

    Restrito porque aqui aparecem nome e matricula de servidor, ao
    contrario da lista de equipes. Serve para o admin conferir a quem
    esta dando visibilidade ao amarrar um supervisor a equipe.
    """
    require_admin(user)
    if not equipe_repo.get_equipe(codigo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipe nao encontrada"
        )
    return [EquipeMembroResponse(**row) for row in equipe_repo.get_membros(codigo)]


@app.put("/admin/supervisoes/{supervisao_id}")
def update_supervisao(
    supervisao_id: int,
    payload: SupervisaoUpdateRequest,
    user: dict[str, Any] = Depends(get_active_user),
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

@app.post("/admin/users", response_model=UserCreatedResponse)
def create_user(
    payload: UserCreateRequest, user: dict[str, Any] = Depends(get_active_user)
) -> UserCreatedResponse:
    """
    Cria um novo usuario com senha temporaria aleatoria. Apenas admin.

    A senha vai na resposta porque e a unica vez que ela existe em texto —
    o admin precisa repassa-la ao usuario, que sera obrigado a troca-la no
    primeiro acesso.
    """
    require_admin(user)
    _validate_user_payload(
        payload.role, payload.gerencia_id, payload.supervisao_id, payload.equipe_codigo
    )
    senha_temporaria = gerar_senha_temporaria()
    try:
        user_id = auth_service.register_user_with_options(
            username=payload.username,
            password=senha_temporaria,
            role=payload.role,
            gerencia_id=payload.gerencia_id,
            supervisao_id=payload.supervisao_id,
            must_change_password=True,
            matricula=payload.matricula,
            equipe_codigo=payload.equipe_codigo,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario ja existe") from exc
    logger.info("Usuario criado: id=%d, username='%s', role='%s'.", user_id, payload.username, payload.role)
    created = user_repo.get_user_by_id(user_id)
    return UserCreatedResponse(**created, temporary_password=senha_temporaria)


@app.put("/admin/users/{user_id}")
def update_user(
    user_id: int, payload: UserUpdateRequest, user: dict[str, Any] = Depends(get_active_user)
) -> dict[str, str]:
    """Atualiza dados de um usuario (exceto admin). Apenas admin."""
    require_admin(user)
    target = user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    if target["role"] == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edicao de admin nao permitida")
    _validate_user_payload(
        payload.role, payload.gerencia_id, payload.supervisao_id, payload.equipe_codigo
    )
    try:
        user_repo.update_user(
            user_id=user_id,
            username=payload.username,
            role=payload.role,
            gerencia_id=payload.gerencia_id,
            supervisao_id=payload.supervisao_id,
            matricula=payload.matricula,
            equipe_codigo=payload.equipe_codigo,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario ja existe") from exc
    logger.info("Usuario atualizado: id=%d.", user_id)
    return {"status": "ok"}


@app.get("/admin/users", response_model=list[UserResponse])
def list_users(user: dict[str, Any] = Depends(get_active_user)) -> list[UserResponse]:
    """
    Lista os usuarios com gerencia, supervisao e equipes. Apenas admin.

    Cada usuario leva duas informacoes de equipe, que sao coisas
    diferentes: `equipes_membro` sao as equipes a que ele PERTENCE, vindas
    da planilha da SEFAZ; `equipe_codigo` e a que ele CHEFIA, preenchida a
    mao aqui. A tela usa a primeira para sugerir a segunda.
    """
    require_admin(user)
    por_matricula = equipe_repo.get_equipes_por_matricula()
    return [
        UserResponse(
            **row,
            equipes_membro=por_matricula.get(str(row.get("matricula")), []),
        )
        for row in user_repo.list_users()
    ]


@app.post("/admin/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_user_password(
    user_id: int, user: dict[str, Any] = Depends(get_active_user)
) -> PasswordResetResponse:
    """Reseta a senha do usuario para uma temporaria aleatoria. Apenas admin."""
    require_admin(user)
    target = user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    senha_temporaria = gerar_senha_temporaria()
    auth_service.reset_password(user_id, senha_temporaria)
    logger.info("Senha resetada para usuario id=%d por admin '%s'.", user_id, user["username"])
    return PasswordResetResponse(temporary_password=senha_temporaria)


@app.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int, user: dict[str, Any] = Depends(get_active_user)
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
    """
    Parametros de filtragem hierarquica no formato interno legado.

    Usado so por /alertas, que consome o MOCK legado (com
    matricula_supervisor). A consulta de OS usa _matriculas_visiveis.
    """
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


def _matriculas_visiveis(user: dict[str, Any]) -> set[str] | None:
    """
    Matriculas cujas OS o usuario pode ver. None = admin, sem restricao.

    A OS no formato ATF so se liga as pessoas por fiscais[].matricula, entao
    a hierarquia vira um conjunto de matriculas resolvido no banco local:

    - fiscal:     apenas a propria
    - supervisor: a propria + a equipe fiscal do ATF que ele chefia,
                  se houver uma amarrada; senao, os lotados na sua
                  supervisao (cadastro local)
    - gerente:    a propria + os lotados na sua gerencia + as equipes
                  dos seus supervisores

    A equipe fiscal tem precedencia sobre a supervisao local por ser a
    fonte da verdade da SEFAZ, e cobre tambem os fiscais que ainda nao
    tem login aqui — com a supervisao local, um fiscal sem cadastro era
    invisivel para o proprio supervisor. O `equipe_codigo` e amarrado a
    mao pelo admin, entao ate ele existir vale o comportamento antigo.

    Quem nao tem matricula nem lotacao recebe um conjunto vazio e nao ve
    nenhuma OS. E o comportamento correto: um cadastro incompleto nao pode
    virar acesso irrestrito.
    """
    role = user["role"]
    if role == "admin":
        return None

    matriculas: set[str] = set()
    if user.get("matricula"):
        matriculas.add(str(user["matricula"]))

    if role == "supervisor":
        if user.get("equipe_codigo"):
            matriculas.update(equipe_repo.get_matriculas_by_equipe(int(user["equipe_codigo"])))
        elif user.get("supervisao_id"):
            matriculas.update(user_repo.get_matriculas_by_supervisao(int(user["supervisao_id"])))
    elif role == "gerente" and user.get("gerencia_id"):
        gerencia_id = int(user["gerencia_id"])
        matriculas.update(user_repo.get_matriculas_by_gerencia(gerencia_id))
        # Somar as equipes dos supervisores mantem a hierarquia de pe: sem
        # isso um supervisor com equipe amarrada veria OS que o gerente
        # dele nao ve, porque a equipe do ATF alcanca fiscais que nem tem
        # login no sistema.
        matriculas.update(
            equipe_repo.get_matriculas_by_equipes(
                user_repo.get_equipe_codigos_by_gerencia(gerencia_id)
            )
        )

    return matriculas


@app.get("/ordens", response_model=OrdensATFResponse)
def list_os(
    numero_os: str | None = Query(default=None),
    modelo: str | None = Query(default=None),
    ie: str | None = Query(default=None),
    cnpj: str | None = Query(default=None),
    razao_social: str | None = Query(default=None, min_length=6),
    matriculas: str | None = Query(default=None),
    situacao: list[int] | None = Query(default=None),
    data_abertura_ini: str | None = Query(default=None),
    data_abertura_fim: str | None = Query(default=None),
    data_ciencia_ini: str | None = Query(default=None),
    data_ciencia_fim: str | None = Query(default=None),
    motivo_abertura: str | None = Query(default=None),
    equipe_fiscal: str | None = Query(default=None),
    orgao_executor: str | None = Query(default=None),
    data_encerramento_ini: str | None = Query(default=None),
    data_encerramento_fim: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=50),
    ordenar_por: str | None = Query(default=None),
    ordem: str = Query(default="asc", pattern="^(asc|desc)$"),
    user: dict[str, Any] = Depends(get_active_user),
) -> OrdensATFResponse:
    """Lista Ordens de Servico via API ATF (SOAP, doc da listagem) ou MOCK se ATF_BASE_URL nao configurado."""
    try:
        return listar_ordens_atf(
            numero_os=numero_os, modelo=modelo, ie=ie, cnpj=cnpj,
            razao_social=razao_social, matriculas=matriculas, situacoes=situacao,
            data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
            data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
            motivo_abertura=motivo_abertura, equipe_fiscal=equipe_fiscal,
            orgao_executor=orgao_executor,
            data_encerramento_ini=data_encerramento_ini,
            data_encerramento_fim=data_encerramento_fim,
            pagina=pagina, limite=limite,
            ordenar_por=ordenar_por, ordem=ordem,
            matriculas_visiveis=_matriculas_visiveis(user),
        )
    except ValueError as e:
        # Erros de negocio do ATF (dsMensagemErro) viram 400 com a mensagem
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _buscar_os_atf(numero: str, user: dict[str, Any]) -> dict[str, Any]:
    """
    Busca uma OS pelo numero no ATF, respeitando a hierarquia do usuario.

    O ATF nao tem servico de detalhe: usa-se o mesmo
    listarOrdensServicoWebService filtrando por numeroOS.

    A busca vai sem restricao e a visibilidade e checada depois, de
    proposito: assim da para distinguir "nao existe" (404) de "existe mas
    nao e sua" (403), o que uma busca ja filtrada tornaria indistinguivel.
    """
    try:
        resultado = listar_ordens_atf(numero_os=numero, pagina=1, limite=1)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    ordens = resultado.get("ordens", [])
    if not ordens:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")

    ordem = ordens[0]
    if not filtrar_atf_por_matriculas([ordem], _matriculas_visiveis(user)):
        logger.warning(
            "Acesso negado a OS %s para '%s' (role=%s): fora da sua equipe.",
            numero, user["username"], user["role"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta OS nao esta designada a voce nem a sua equipe.",
        )
    return ordem


# NOTA: o numero da OS contem barra (ex: 93300008.12.00000001/2026-99) e o
# servidor ASGI decodifica %2F antes do roteamento, entao as rotas abaixo
# precisam do conversor ":path". As rotas de detalhe e de PDF vem primeiro
# de proposito: rotas sao avaliadas na ordem de declaracao e "{numero:path}"
# tambem casaria com ".../detalhe" e ".../pdf".

def _buscar_detalhe_os_atf(numero: str, user: dict[str, Any]) -> dict[str, Any]:
    """
    Busca o detalhe completo de uma OS (doc do detalhe) com a hierarquia do usuario.

    Normalmente a permissao sai da propria resposta do detalhe, que traz
    listaFiscal — nao ha segunda ida ao ATF so para conferir acesso. Como
    em _buscar_os_atf, a consulta vai sem restricao e o filtro vem depois,
    para separar "nao existe" (404) de "existe mas nao e sua" (403).

    EXCECAO: quando o detalhe aponta para outro ambiente que a listagem
    (ATF_DETALHE_BASE_URL), quem autoriza e a listagem. Os dois bancos
    tem dados diferentes — a mesma OS volta com outros fiscais — e
    decidir acesso pelos fiscais de um ambiente de desenvolvimento
    liberaria OS que na base real nao sao do usuario.
    """
    autoriza_pela_listagem = detalhe_em_outro_ambiente()
    if autoriza_pela_listagem:
        # Levanta 404/403 por conta propria; o retorno nao interessa aqui.
        _buscar_os_atf(numero, user)

    try:
        detalhe = detalhar_ordem_atf(numero)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if detalhe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")

    if not autoriza_pela_listagem and not filtrar_atf_por_matriculas(
        [detalhe], _matriculas_visiveis(user),
    ):
        logger.warning(
            "Acesso negado ao detalhe da OS %s para '%s' (role=%s): fora da sua equipe.",
            numero, user["username"], user["role"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta OS nao esta designada a voce nem a sua equipe.",
        )
    return detalhe


@app.get("/ordens/{numero:path}/detalhe", response_model=OSDetalheCompletoResponse)
def get_os_detalhe(
    numero: str, user: dict[str, Any] = Depends(get_active_user)
) -> OSDetalheCompletoResponse:
    """
    Detalhe completo de UMA OS pelo detalharOrdemServicoWebService (doc do detalhe).

    E o que o painel chama ao abrir uma linha da listagem: uma OS por
    clique. Traz o que a listagem nao tem — contribuinte com endereco,
    eventos de acompanhamento, prorrogacoes, notificacoes, processos,
    justificativas e recolhimentos.
    """
    detalhe = _buscar_detalhe_os_atf(numero, user)
    return OSDetalheCompletoResponse(
        **detalhe, detalhe_de_outro_ambiente=detalhe_em_outro_ambiente(),
    )


def _os_completa_para_pdf(numero: str, user: dict[str, Any]) -> dict[str, Any]:
    """
    Monta a OS que vai para o PDF: a linha da listagem mais o detalhe.

    O PDF precisa sair com o mesmo conteudo do modal, e o modal mostra a
    juncao dos dois servicos. Aqui o servidor nao tem a linha em maos
    como o painel tem, entao busca as duas coisas — e por isso o PDF e
    mais lento que abrir o modal.

    _buscar_os_atf ja resolve 404 e 403; a autorizacao continua saindo da
    listagem, que e a fonte autoritativa.

    Se o detalhe falhar, o PDF sai so com a listagem em vez de nao sair:
    o servico de detalhe pode nao estar publicado no ambiente em uso (e o
    caso de producao hoje), e um relatorio menor e melhor que um erro.
    """
    ordem = _buscar_os_atf(numero, user)
    try:
        detalhe = detalhar_ordem_atf(numero)
    except Exception:
        logger.warning(
            "PDF da OS %s sai sem o detalhe (doc do detalhe): o servico falhou.",
            numero, exc_info=True,
        )
        return ordem

    if detalhe is None:
        logger.warning("PDF da OS %s sai sem o detalhe: OS nao encontrada no servico.", numero)
        return ordem
    return mesclar_detalhe_os(ordem, detalhe)


@app.get("/ordens/{numero:path}/pdf")
def get_os_pdf(
    numero: str, user: dict[str, Any] = Depends(get_active_user)
) -> Response:
    """
    Gera o PDF de uma OS com todo o conteudo do detalhamento.

    Mesmas secoes do modal, na mesma ordem, e sob a mesma regra: o
    usuario le nomes, nao codigos do ATF. Secoes sem dado sao omitidas em
    vez de sairem vazias.
    """
    ordem = _os_completa_para_pdf(numero, user)
    numero_os = ordem.get("numero_os", numero)

    pdf = _PDF(f"Ordem de Servico - {numero_os}")
    pdf.alias_nb_pages()
    pdf.add_page(orientation="P")

    # Largura util da pagina retrato com as margens padrao do FPDF.
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    # --- Cabecalho da OS ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _safe(numero_os), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(ordem.get("razao_social", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def _secao(titulo: str) -> None:
        # Sem espaco para o titulo mais uma linha de conteudo, comeca outra
        # pagina: titulo de secao sozinho no pe da folha nao ajuda ninguem.
        if pdf.get_y() > pdf.h - pdf.b_margin - 22:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(240, 240, 245)
        pdf.cell(0, 7, f"  {titulo}", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

    def _field(label: str, value: Any) -> None:
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(45, 5, label + ":")
        pdf.set_font("Helvetica", "", 8)
        texto = "-" if value in (None, "") else str(value)
        # multi_cell e nao cell: nome de orgao passa de 130 caracteres e
        # com cell() o texto vazaria a margem direita da pagina.
        pdf.multi_cell(largura - 45, 5, _safe(texto), new_x="LMARGIN", new_y="NEXT")

    def _texto_longo(value: Any) -> None:
        """Paragrafo que quebra em varias linhas (observacoes, justificativas)."""
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(largura, 4.2, _safe(value), new_x="LMARGIN", new_y="NEXT")

    def _tabela(headers: list[str], larguras: list[float], linhas: list[list[Any]]) -> None:
        """Tabela simples com cabecalho; cada celula e truncada a sua largura."""
        pdf.set_font("Helvetica", "B", 7)
        for i, h in enumerate(headers):
            pdf.cell(larguras[i], 6, _safe(h), border=1, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 7)
        for linha in linhas:
            for i, celula in enumerate(linha):
                texto = _safe("-" if celula in (None, "") else celula)
                # ~1.9 chars por mm na Helvetica 7 — corta o que nao couber
                limite = max(1, int(larguras[i] * 1.9))
                pdf.cell(larguras[i], 5, texto[:limite], border=1)
            pdf.ln()

    def _valor_br(valor: Any) -> str:
        """Formata valor monetario no padrao brasileiro."""
        if valor is None:
            return ""
        return f"R$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")

    def _periodo(inicio: Any, fim: Any, formatar=lambda v: v) -> str:
        ini = formatar(inicio) if inicio else ""
        f = formatar(fim) if fim else ""
        return f"{ini} a {f}" if ini and f else (ini or f)

    contribuinte = ordem.get("contribuinte") or {}
    endereco = contribuinte.get("endereco") or {}

    # --- Informacoes Gerais ---
    _secao("Informacoes Gerais")
    _field("Situacao", _fmt_situacao(ordem))
    _field("Modelo", ordem.get("modelo"))
    _field("Motivo de Abertura", ordem.get("motivo_abertura"))
    _field("Procedimento", ordem.get("procedimento"))
    periodo_fisc = ordem.get("periodo_fiscalizar") or {}
    _field("Periodo a Fiscalizar", _periodo(periodo_fisc.get("inicio"), periodo_fisc.get("fim")))
    _field("Orgao Executor", " - ".join(
        p for p in (ordem.get("orgao_executor_sigla"), ordem.get("orgao_executor")) if p))
    _field("Orgao de Origem", ordem.get("orgao_origem"))
    _field("Equipe Fiscal", ordem.get("equipe_fiscal"))
    _field("Tipo de Funcionario", ordem.get("tipo_funcionario"))
    _field("Termo da OS", ordem.get("termo_os_descricao") or ordem.get("termo_os"))
    _field("BD Fiscal", ordem.get("bd_fiscal"))
    pdf.ln(2)

    # --- Contribuinte ---
    _secao("Contribuinte")
    _field("Razao Social", ordem.get("razao_social"))
    _field("IE", ordem.get("ie"))
    _field("CNPJ/CPF", ordem.get("cnpj"))
    if endereco:
        rua = ", ".join(p for p in (endereco.get("logradouro"), endereco.get("numero")) if p)
        linha_end = " - ".join(p for p in (rua, endereco.get("complemento")) if p)
        _field("Endereco", endereco.get("nao_decodificado") or linha_end)
        _field("Bairro", endereco.get("bairro"))
        cidade = " / ".join(p for p in (endereco.get("municipio"), endereco.get("uf")) if p)
        _field("Municipio/UF", " - ".join(p for p in (cidade, endereco.get("cep")) if p))
        _field("Reparticao", endereco.get("reparticao"))
    pdf.ln(2)

    # --- Datas e execucao ---
    _secao("Datas e Execucao")
    _field("Abertura", _fmt_data_br(ordem.get("data_abertura")))
    _field("Emissao", _fmt_data_br(ordem.get("data_emissao")))
    _field("Inicio da Fiscalizacao", _fmt_data_br(ordem.get("data_inicio_fiscalizacao")))
    _field("Prazo Final", _fmt_data_br(ordem.get("data_prazo_final")))
    _field("Encerramento", _fmt_data_br(ordem.get("data_encerramento")))
    _field("Ultimo Evento", _fmt_data_br(ordem.get("data_ultimo_evento")))
    _field("Dias de Execucao", ordem.get("dias_execucao"))
    tempo_medio = ordem.get("tempo_medio_execucao_modelo_motivo")
    _field("Tempo Medio (Modelo/Motivo)", f"{tempo_medio} dias" if tempo_medio is not None else None)
    _field("Media de Eventos (Modelo/Motivo)", ordem.get("qtd_media_eventos_modelo_motivo"))
    _field("Exercicio", _periodo(
        ordem.get("data_inicio_exercicio"), ordem.get("data_final_exercicio"), _fmt_data_br,
    ))
    _field("Total Recolhido", _valor_br(ordem.get("valor_total_recolhido")))
    pdf.ln(2)

    # --- Cargas e autorizacao ---
    periodo_nf = ordem.get("periodo_nf") or {}
    periodo_efd = ordem.get("periodo_efd") or {}
    autorizacao = ordem.get("autorizacao") or {}
    if periodo_nf or periodo_efd or autorizacao:
        _secao("Cargas e Autorizacao")
        _field("Periodo de NF (emissao)", _periodo(
            periodo_nf.get("inicio"), periodo_nf.get("fim"), _fmt_data_br))
        _field("Periodo de EFD (referencia)", _periodo(
            periodo_efd.get("inicio"), periodo_efd.get("fim"), _fmt_data_br))
        _field("Autorizada em", _fmt_data_br(autorizacao.get("data")))
        _field("Autorizada por", " - ".join(
            p for p in (autorizacao.get("usuario"), autorizacao.get("matricula")) if p))
        pdf.ln(2)

    # --- Fiscais ---
    fiscais = ordem.get("fiscais", [])
    _secao(f"Fiscais ({len(fiscais)})")
    if fiscais:
        _tabela(
            ["Matricula", "Nome", "Resp.", "Status", "Designacao", "Ciencia", "Cancelamento"],
            [20, 48, 14, 24, 24, 24, 26],
            [[f.get("matricula"), f.get("nome"), f.get("responsavel"),
              f.get("status") or f.get("status_codigo"),
              _fmt_data_br(f.get("data_designacao")), _fmt_data_br(f.get("data_ciencia")),
              _fmt_data_br(f.get("data_cancelamento"))] for f in fiscais],
        )
    else:
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, "Nenhum fiscal designado.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Eventos de acompanhamento ---
    eventos = ordem.get("eventos") or []
    if eventos:
        _secao(f"Eventos de Acompanhamento ({len(eventos)})")
        for ev in eventos:
            pdf.set_font("Helvetica", "B", 8)
            titulo = ev.get("tipo") or ev.get("tipo_codigo") or "-"
            datas = _periodo(ev.get("data_inicial"), ev.get("data_final"), _fmt_data_br)
            pdf.cell(0, 5, _safe(f"{titulo}   {datas}"), new_x="LMARGIN", new_y="NEXT")
            if ev.get("procedimento"):
                _texto_longo(ev["procedimento"])
            if ev.get("observacao"):
                _texto_longo(ev["observacao"])
            rodape = "   ".join(p for p in (
                _periodo(ev.get("referencia_inicial"), ev.get("referencia_final")),
                f"Levantado: {_valor_br(ev['valor_levantado'])}" if ev.get("valor_levantado") is not None else "",
                ev.get("arquivo") or "",
            ) if p)
            if rodape:
                pdf.set_font("Helvetica", "I", 7)
                pdf.cell(0, 4, _safe(rodape), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        pdf.ln(1)

    # --- Prorrogacoes ---
    prorrogacoes = ordem.get("prorrogacoes") or []
    if prorrogacoes:
        _secao(f"Prorrogacoes ({len(prorrogacoes)})")
        _tabela(
            ["Dias", "Prazo Anterior", "Prazo Atual", "Situacao", "Status", "Solicitante", "Homologacao"],
            [14, 26, 26, 26, 22, 40, 26],
            [[p.get("dias"), _fmt_data_br(p.get("prazo_anterior")), _fmt_data_br(p.get("prazo_atual")),
              p.get("situacao_prazo"), p.get("status"), p.get("usuario"),
              _fmt_data_br(p.get("data_homologacao"))] for p in prorrogacoes],
        )
        for p in prorrogacoes:
            if p.get("justificativa"):
                pdf.ln(1)
                _texto_longo(f"Justificativa: {p['justificativa']}")
        pdf.ln(2)

    # --- Notificacoes ---
    notificacoes = [("ATF", n) for n in (ordem.get("notificacoes") or [])]
    notificacoes += [("SCAMF", n) for n in (ordem.get("notificacoes_scamf") or [])]
    if notificacoes:
        _secao(f"Notificacoes ({len(notificacoes)})")
        _tabela(
            ["Origem", "Codigo", "Notificacao"], [24, 30, 126],
            [[origem, n.get("codigo"), n.get("nome")] for origem, n in notificacoes],
        )
        pdf.ln(2)

    # --- Processos ---
    processos = ordem.get("processos") or []
    if processos:
        _secao(f"Processos ({len(processos)})")
        _tabela(
            ["Numero", "Tipo"], [50, 130],
            [[p.get("numero"), p.get("tipo")] for p in processos],
        )
        pdf.ln(2)

    # --- Recolhimentos ---
    recolhimentos = ordem.get("recolhimentos") or []
    if recolhimentos:
        _secao(f"Recolhimentos ({len(recolhimentos)})")
        _tabela(
            ["Inclusao", "Referencia", "Receita", "Nosso Numero", "Debito", "ARR", "Principal"],
            [22, 22, 40, 28, 24, 22, 22],
            [[_fmt_data_br(r.get("data_inclusao")), r.get("referencia"),
              r.get("receita_nome") or r.get("receita_codigo"), r.get("nosso_numero"),
              r.get("situacao_debito"), r.get("situacao_arr"),
              _valor_br(r.get("valor_principal"))] for r in recolhimentos],
        )
        pdf.ln(2)

    # --- Denuncias ---
    denuncias = ordem.get("denuncias") or []
    if denuncias:
        _secao(f"Denuncias ({len(denuncias)})")
        for den in denuncias:
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 5, _safe(_fmt_data_br(den.get("data")) or "-"),
                     new_x="LMARGIN", new_y="NEXT")
            if den.get("descricao"):
                _texto_longo(den["descricao"])
            pdf.ln(1)
        pdf.ln(1)

    # --- Justificativas de atraso ---
    justificativas = ordem.get("justificativas") or []
    if justificativas:
        _secao(f"Justificativas de Atraso ({len(justificativas)})")
        for j in justificativas:
            pdf.set_font("Helvetica", "B", 8)
            cabecalho = "   ".join(p for p in (
                j.get("tipo") or "-", _fmt_data_br(j.get("data_inclusao")), j.get("usuario") or "",
            ) if p)
            pdf.cell(0, 5, _safe(cabecalho), new_x="LMARGIN", new_y="NEXT")
            if j.get("descricao"):
                _texto_longo(j["descricao"])
            pdf.ln(1)
        pdf.ln(1)

    # --- Descricoes complementares ---
    descricoes = ordem.get("descricoes_complementares") or []
    if descricoes:
        _secao("Descricoes Complementares")
        for d in descricoes:
            pdf.set_font("Helvetica", "B", 8)
            cabecalho = "   ".join(p for p in (
                d.get("usuario") or "-", _fmt_data_br(d.get("data_inclusao")),
            ) if p)
            pdf.cell(0, 5, _safe(cabecalho), new_x="LMARGIN", new_y="NEXT")
            _texto_longo(d.get("descricao"))
            pdf.ln(1)

    pdf_bytes = bytes(pdf.output())
    filename = f"{numero_os.replace('/', '_')}.pdf"
    logger.info("PDF da OS %s gerado por '%s'.", numero, user["username"])

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/ordens/{numero:path}", response_model=OSDetalheResponse)
def get_os(
    numero: str, user: dict[str, Any] = Depends(get_active_user)
) -> OSDetalheResponse:
    """Busca uma OS por numero no ATF (mesmo servico da listagem)."""
    return OSDetalheResponse(**_buscar_os_atf(numero, user))


@app.get("/alertas", response_model=list[AlertaResponse])
def list_alertas(
    user: dict[str, Any] = Depends(get_active_user),
) -> list[AlertaResponse]:
    """Lista alertas gerados a partir das OS visiveis ao usuario."""
    filters = _build_hierarchy_filters(user)
    return [AlertaResponse(**a) for a in gerar_alertas(**filters)]


# ─── Dashboard (somente admin) ─────────────────────────────────

@app.get("/admin/dashboard")
def get_dashboard(
    user: dict[str, Any] = Depends(get_active_user),
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

def _fmt_data_br(valor: str | None) -> str:
    """Converte data ISO (YYYY-MM-DD) para formato brasileiro (DD/MM/YYYY)."""
    if not valor:
        return ""
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return valor


_STATUS_MAP = {
    "aberta": "Aberta",
    "em_andamento": "Em Andamento",
    "concluida": "Concluida",
    "cancelada": "Cancelada",
}


def _fmt_situacao(o: dict) -> str:
    """
    Descricao da situacao da OS, sem o codigo do ATF.

    Mesma regra da tela: o usuario le o nome; o codigo e chave de
    integracao e fica interno. So aparece quando o ATF manda o codigo sem
    a descricao — melhor que uma celula vazia.
    """
    sit = o.get("situacao")
    if sit and isinstance(sit, dict):
        descricao = (sit.get("descricao") or "").strip()
        if descricao:
            return descricao
        codigo = sit.get("codigo")
        return "" if codigo is None else str(codigo)
    return _STATUS_MAP.get(o.get("status", ""), o.get("status", ""))



# O ATF retorna a lista completa e a paginacao e feita neste backend;
# nos relatorios queremos todos os registros de uma vez.
_RELATORIO_LIMITE = 100_000


@dataclass
class FiltrosRelatorioOS:
    """Filtros do relatorio de OS (os mesmos do painel + busca livre)."""
    numero_os: str | None = None
    modelo: str | None = None
    motivo_abertura: str | None = None
    ie: str | None = None
    cnpj: str | None = None
    razao_social: str | None = None
    matriculas: str | None = None
    equipe_fiscal: str | None = None
    orgao_executor: str | None = None
    situacao: list[int] | None = None
    data_abertura_ini: str | None = None
    data_abertura_fim: str | None = None
    data_encerramento_ini: str | None = None
    data_encerramento_fim: str | None = None
    data_ciencia_ini: str | None = None
    data_ciencia_fim: str | None = None
    search: str | None = None


def filtros_relatorio_os(
    numero_os: str | None = Query(default=None),
    modelo: str | None = Query(default=None),
    motivo_abertura: str | None = Query(default=None),
    ie: str | None = Query(default=None),
    cnpj: str | None = Query(default=None),
    razao_social: str | None = Query(default=None, min_length=6),
    matriculas: str | None = Query(default=None),
    equipe_fiscal: str | None = Query(default=None),
    orgao_executor: str | None = Query(default=None),
    situacao: list[int] | None = Query(default=None),
    data_abertura_ini: str | None = Query(default=None),
    data_abertura_fim: str | None = Query(default=None),
    data_encerramento_ini: str | None = Query(default=None),
    data_encerramento_fim: str | None = Query(default=None),
    data_ciencia_ini: str | None = Query(default=None),
    data_ciencia_fim: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> FiltrosRelatorioOS:
    """Coleta os filtros de relatorio da query string (usada por CSV e PDF)."""
    return FiltrosRelatorioOS(
        numero_os=numero_os, modelo=modelo, motivo_abertura=motivo_abertura,
        ie=ie, cnpj=cnpj, razao_social=razao_social, matriculas=matriculas,
        equipe_fiscal=equipe_fiscal, orgao_executor=orgao_executor,
        situacao=situacao,
        data_abertura_ini=data_abertura_ini, data_abertura_fim=data_abertura_fim,
        data_encerramento_ini=data_encerramento_ini,
        data_encerramento_fim=data_encerramento_fim,
        data_ciencia_ini=data_ciencia_ini, data_ciencia_fim=data_ciencia_fim,
        search=search,
    )


def _filtrar_ordens(f: FiltrosRelatorioOS, user: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Busca as OS do relatorio no ATF, respeitando a hierarquia do usuario.

    Usa os mesmos filtros do painel de Ordens de Servico; 'search' e um
    refinamento adicional aplicado localmente sobre o resultado.
    """
    try:
        result = listar_ordens_atf(
            numero_os=f.numero_os, modelo=f.modelo, ie=f.ie, cnpj=f.cnpj,
            razao_social=f.razao_social, matriculas=f.matriculas,
            situacoes=f.situacao,
            data_abertura_ini=f.data_abertura_ini, data_abertura_fim=f.data_abertura_fim,
            data_ciencia_ini=f.data_ciencia_ini, data_ciencia_fim=f.data_ciencia_fim,
            motivo_abertura=f.motivo_abertura, equipe_fiscal=f.equipe_fiscal,
            orgao_executor=f.orgao_executor,
            data_encerramento_ini=f.data_encerramento_ini,
            data_encerramento_fim=f.data_encerramento_fim,
            pagina=1, limite=_RELATORIO_LIMITE,
            matriculas_visiveis=_matriculas_visiveis(user),
        )
    except ValueError as e:
        # Regras de negocio do ATF (ex.: filtro que exige periodo)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    rows = result.get("ordens", [])

    if f.search:
        term = f.search.lower()
        rows = [
            o for o in rows
            if term in o.get("numero_os", "").lower()
            or term in o.get("razao_social", "").lower()
            or term in o.get("ie", "").lower()
            or term in (o.get("cnpj") or "").lower()
            or term in (o.get("motivo_abertura") or "").lower()
            or any(term in fi.get("nome", "").lower() for fi in o.get("fiscais", []))
            or any(term in fi.get("matricula", "").lower() for fi in o.get("fiscais", []))
        ]
    return rows


def _fiscais_nomes(o: dict[str, Any]) -> str:
    return ", ".join(
        f"{f.get('nome', '')} ({f.get('matricula', '')})" for f in o.get("fiscais", [])
    )


@app.get("/relatorios/ordens")
def relatorio_ordens_csv(
    user: dict[str, Any] = Depends(get_active_user),
    filtros: FiltrosRelatorioOS = Depends(filtros_relatorio_os),
) -> StreamingResponse:
    """Gera relatorio CSV das Ordens de Servico com filtros."""
    rows = _filtrar_ordens(filtros, user)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Numero", "Modelo", "Motivo de Abertura", "Procedimento", "IE", "CNPJ/CPF",
        "Razao Social", "Sigla Orgao", "Orgao Executor", "Equipe Fiscal", "Fiscais",
        "Situacao", "Data Abertura", "Inicio Fiscalizacao", "Data Encerramento",
        "Ultimo Evento", "Dias de Execucao",
        "Tempo Medio Modelo/Motivo (dias)", "Media de Eventos Modelo/Motivo",
    ])
    for o in rows:
        writer.writerow([
            o.get("numero_os", ""),
            o.get("modelo", ""),
            o.get("motivo_abertura", ""),
            o.get("procedimento", ""),
            o.get("ie", ""),
            o.get("cnpj", "") or "",
            o.get("razao_social", ""),
            o.get("orgao_executor_sigla", ""),
            o.get("orgao_executor", ""),
            o.get("equipe_fiscal", ""),
            _fiscais_nomes(o),
            _fmt_situacao(o),
            _fmt_data_br(o.get("data_abertura")),
            _fmt_data_br(o.get("data_inicio_fiscalizacao")),
            _fmt_data_br(o.get("data_encerramento")),
            _fmt_data_br(o.get("data_ultimo_evento")),
            o.get("dias_execucao") if o.get("dias_execucao") is not None else "",
            o.get("tempo_medio_execucao_modelo_motivo") or "",
            o.get("qtd_media_eventos_modelo_motivo") or "",
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


_PDF_CHAR_MAP = str.maketrans({
    "—": "-", "–": "-",  # em dash, en dash
    "Á": "A", "Â": "A", "Ã": "A", "À": "A",
    "É": "E", "Ê": "E", "È": "E",
    "Í": "I", "Î": "I", "Ì": "I",
    "Ó": "O", "Ô": "O", "Õ": "O", "Ò": "O",
    "Ú": "U", "Û": "U", "Ù": "U",
    "Ç": "C",
    "á": "a", "â": "a", "ã": "a", "à": "a",
    "é": "e", "ê": "e", "è": "e",
    "í": "i", "î": "i", "ì": "i",
    "ó": "o", "ô": "o", "õ": "o", "ò": "o",
    "ú": "u", "û": "u", "ù": "u",
    "ç": "c",
})


def _safe(val) -> str:
    """Converte valor para string ASCII-segura para o PDF (Helvetica nao suporta Unicode)."""
    if val is None:
        return ""
    return str(val).translate(_PDF_CHAR_MAP)


@app.get("/relatorios/ordens/pdf")
def relatorio_ordens_pdf(
    user: dict[str, Any] = Depends(get_active_user),
    filtros: FiltrosRelatorioOS = Depends(filtros_relatorio_os),
) -> Response:
    """Gera relatorio PDF das Ordens de Servico."""
    rows = _filtrar_ordens(filtros, user)

    pdf = _PDF("Relatorio de Ordens de Servico")
    pdf.alias_nb_pages()
    pdf.add_page()

    # Cabecalho da tabela (A4 paisagem: ~277mm uteis)
    headers = [
        "Numero", "Modelo", "Motivo", "IE", "Razao Social",
        "Fiscais", "Situacao", "Abertura", "Encerram.", "Dias",
    ]
    col_widths = [40, 22, 34, 22, 44, 40, 30, 18, 18, 9]

    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align="C")
    pdf.ln()

    # Dados
    pdf.set_font("Helvetica", "", 6)
    for o in rows:
        sit = o.get("situacao") or {}
        vals = [
            _safe(o.get("numero_os")),
            _safe(o.get("modelo"))[:14],
            _safe(o.get("motivo_abertura"))[:24],
            _safe(o.get("ie")),
            _safe(o.get("razao_social"))[:30],
            _safe(_fiscais_nomes(o))[:28],
            _safe(sit.get("descricao", ""))[:20],
            _fmt_data_br(o.get("data_abertura")),
            _fmt_data_br(o.get("data_encerramento")),
            _safe(o.get("dias_execucao") if o.get("dias_execucao") is not None else "-"),
        ]
        for i, v in enumerate(vals):
            pdf.cell(col_widths[i], 5, v, border=1, align="C")
        pdf.ln()

    if not rows:
        pdf.set_font("Helvetica", "I", 8)
        pdf.ln(3)
        pdf.cell(0, 5, "Nenhuma ordem de servico encontrada para os filtros informados.",
                 new_x="LMARGIN", new_y="NEXT")

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
    user: dict[str, Any] = Depends(get_active_user),
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
                  "Canceladas", "Sem Ciencia", "Taxa (%)"]
    rg_vals = [
        visao.get("total_os", 0), visao.get("os_abertas", 0),
        visao.get("os_em_andamento", 0), visao.get("os_concluidas", 0),
        visao.get("os_canceladas", 0), visao.get("os_sem_ciencia", 0),
        visao.get("taxa_conclusao", 0),
    ]
    w = 38
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
                 "Taxa (%)", "Sem Ciencia"]
    g_widths = [65, 22, 24, 27, 27, 24, 30]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(g_headers):
        pdf.cell(g_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for g in dashboard.get("desempenho_gerencias", []):
        vals = [
            _safe(g.get("nome"))[:40], str(g.get("total_os", 0)),
            str(g.get("abertas", 0)), str(g.get("em_andamento", 0)),
            str(g.get("concluidas", 0)), str(g.get("taxa_conclusao", 0)),
            str(g.get("os_sem_ciencia", 0)),
        ]
        for i, v in enumerate(vals):
            pdf.cell(g_widths[i], 5, v, border=1, align="C")
        pdf.ln()
    pdf.ln(5)

    # ─── Supervisoes ───
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Desempenho por Supervisao", new_x="LMARGIN", new_y="NEXT")
    s_headers = ["Supervisao", "Gerencia", "Total", "Abertas", "Andamento",
                 "Concluidas", "Taxa (%)", "Sem Ciencia"]
    s_widths = [55, 55, 20, 22, 25, 25, 22, 28]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(s_headers):
        pdf.cell(s_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for s in dashboard.get("desempenho_supervisoes", []):
        vals = [
            _safe(s.get("nome"))[:35], _safe(s.get("gerencia_nome"))[:35],
            str(s.get("total_os", 0)), str(s.get("abertas", 0)),
            str(s.get("em_andamento", 0)), str(s.get("concluidas", 0)),
            str(s.get("taxa_conclusao", 0)), str(s.get("os_sem_ciencia", 0)),
        ]
        for i, v in enumerate(vals):
            pdf.cell(s_widths[i], 5, v, border=1, align="C")
        pdf.ln()
    pdf.ln(5)

    # ─── Fiscais ───
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Carga por Fiscal", new_x="LMARGIN", new_y="NEXT")
    f_headers = ["Fiscal", "OS Ativas"]
    f_widths = [140, 50]
    pdf.set_font("Helvetica", "B", 7)
    for i, h in enumerate(f_headers):
        pdf.cell(f_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 6.5)
    for f in dashboard.get("carga_fiscais", []):
        vals = [
            _safe(f.get("nome"))[:85], str(f.get("os_ativas", 0)),
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
    user: dict[str, Any] = Depends(get_active_user),
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
                      "OS Sem Ciencia", "Taxa Conclusao (%)"])
    writer.writerow([
        visao.get("total_os", 0),
        visao.get("os_abertas", 0),
        visao.get("os_em_andamento", 0),
        visao.get("os_concluidas", 0),
        visao.get("os_canceladas", 0),
        visao.get("os_sem_ciencia", 0),
        visao.get("taxa_conclusao", 0),
    ])
    writer.writerow([])

    # Por gerencia
    writer.writerow(["=== DESEMPENHO POR GERENCIA ==="])
    writer.writerow([
        "Gerencia", "Total OS", "Abertas", "Em Andamento", "Concluidas",
        "Taxa Conclusao (%)", "OS Sem Ciencia",
    ])
    for g in dashboard.get("desempenho_gerencias", []):
        writer.writerow([
            g.get("nome", ""),
            g.get("total_os", 0),
            g.get("abertas", 0),
            g.get("em_andamento", 0),
            g.get("concluidas", 0),
            g.get("taxa_conclusao", 0),
            g.get("os_sem_ciencia", 0),
        ])
    writer.writerow([])

    # Por supervisao
    writer.writerow(["=== DESEMPENHO POR SUPERVISAO ==="])
    writer.writerow([
        "Supervisao", "Gerencia", "Total OS", "Abertas", "Em Andamento",
        "Concluidas", "Taxa Conclusao (%)", "OS Sem Ciencia",
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
            s.get("os_sem_ciencia", 0),
        ])
    writer.writerow([])

    # Por fiscal
    writer.writerow(["=== CARGA POR FISCAL ==="])
    writer.writerow(["Fiscal", "OS Ativas"])
    for f in dashboard.get("carga_fiscais", []):
        writer.writerow([
            f.get("nome", ""),
            f.get("os_ativas", 0),
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
