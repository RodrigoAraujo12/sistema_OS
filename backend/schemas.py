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
    equipe_codigo: int | None = None
    equipe_nome: str | None = None


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


# ─── Equipes fiscais (ATF) ──────────────────────────────────────

class EquipeFiscalResponse(BaseModel):
    """
    Equipe fiscal do ATF, com a contagem de membros importados.

    Somente leitura: a origem e a planilha da SEFAZ, carregada por
    `backend.importar_equipes`. O `codigo` e o `cdEquipeFisc` que a OS
    traz e que o filtro de OS aceita.
    """
    codigo: int
    nome: str
    total_membros: int = 0


class EquipeMembroResponse(BaseModel):
    """Auditor vinculado a uma equipe fiscal."""
    matricula: str
    nome: str


class EquipeVinculoResponse(BaseModel):
    """
    Equipe a que um usuario pertence, como aparece no cadastro dele.

    Vem da planilha da SEFAZ (`equipe_membros`), e nao do cadastro local:
    e informativo, o admin nao edita. Nao confundir com `equipe_codigo`
    do usuario, que e a equipe que um supervisor CHEFIA.
    """
    codigo: int
    nome: str


# ─── Usuarios ───────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """Dados para criar um usuario (a senha padrao e atribuida pelo backend)."""
    username: str
    role: str
    gerencia_id: int
    supervisao_id: int
    matricula: str = Field(min_length=3)
    equipe_codigo: int | None = None


class UserUpdateRequest(BaseModel):
    """Dados para editar um usuario existente."""
    username: str
    role: str
    gerencia_id: int
    supervisao_id: int
    matricula: str = Field(min_length=3)
    equipe_codigo: int | None = None


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
    equipe_codigo: int | None = None
    equipe_nome: str | None = None
    equipes_membro: list[EquipeVinculoResponse] = []


class UserCreatedResponse(UserResponse):
    """
    Resposta da criacao de usuario.

    Carrega a senha temporaria porque e o unico momento em que ela existe
    em texto: e gerada aleatoria e so o hash fica no banco.
    """
    temporary_password: str


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
    """Fiscal designado na OS (doc da listagem: matricula, nome, dataDesignacao,
    dataCiencia, dataCancelamento, status)."""
    matricula: str
    nome: str
    data_ciencia: str | None = None
    data_designacao: str | None = None
    data_cancelamento: str | None = None
    status: str | None = None


class SituacaoATF(BaseModel):
    """Situacao da OS no ATF (codigo + descricao)."""
    codigo: int
    descricao: str


class OSListagemATF(BaseModel):
    """
    OS retornada pelo listarOrdensServicoWebService (doc da listagem),
    ja com os campos calculados da demanda (dias de execucao e medias
    por Modelo/Motivo).
    """
    numero_os: str
    modelo: str = ""
    modelo_codigo: int | None = None
    motivo_abertura: str = ""
    motivo_abertura_codigo: int | None = None
    ie: str = ""
    cnpj: str | None = None
    razao_social: str = ""
    orgao_executor: str = ""
    orgao_executor_sigla: str = ""
    orgao_executor_codigo: int | None = None
    equipe_fiscal: str = ""
    equipe_fiscal_codigo: int | None = None
    # noProcedimento: campo novo na revisao de 13/08/2026 da doc da listagem.
    procedimento: str = ""
    fiscais: list[FiscalATF] = []
    situacao: SituacaoATF | None = None
    data_abertura: str = ""
    data_inicio_fiscalizacao: str | None = None
    data_encerramento: str | None = None
    data_ultimo_evento: str | None = None
    qtd_eventos: int | None = None
    dias_execucao: int | None = None
    tempo_medio_execucao_modelo_motivo: float | None = None
    qtd_media_eventos_modelo_motivo: float | None = None


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


class OSDetalheResponse(OSListagemATF):
    """
    Uma OS buscada pelo numero no servico de LISTAGEM (doc da listagem).

    Tem exatamente os campos da listagem, porque e a mesma consulta com
    filtro de numero. O detalhe que o painel abre ao clicar na linha vem
    do outro servico — ver OSDetalheCompletoResponse, abaixo.
    """


# ─── Detalhe completo da OS (doc do detalhe) ───────────────────────
#
# Segundo servico do ATF, chamado ao abrir uma OS na listagem — uma por
# vez. Traz blocos que a listagem nao tem: endereco do contribuinte,
# eventos de acompanhamento, prorrogacoes, notificacoes, processos,
# justificativas e recolhimentos.
#
# Todos os campos tem default: o servico omite bloco inteiro quando nao
# ha dado (uma OS sem prorrogacao nao devolve <listaProrrogacao>), e uma
# ausencia dessas nao pode virar erro de validacao no meio do caminho.

class PeriodoATF(BaseModel):
    """Par de datas/referencias (periodo a fiscalizar, cargas de NF/EFD)."""
    inicio: str = ""
    fim: str = ""


class EnderecoATF(BaseModel):
    """Endereco do contribuinte."""
    logradouro: str = ""
    numero: str | None = None
    complemento: str | None = None
    bairro: str = ""
    municipio: str = ""
    municipio_codigo: str | None = None
    municipio_ibge: str | None = None
    uf: str = ""
    cep: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    # dsEndNaoDecodifica: endereco que o cadastro nao conseguiu separar em
    # campos. Quando vem preenchido, e o unico texto util do bloco.
    nao_decodificado: str | None = None
    reparticao: str | None = None
    atualizado_em: str | None = None


class ContribuinteATF(BaseModel):
    """Contribuinte fiscalizado, com endereco."""
    nome: str = ""
    natureza: str | None = None
    ie: str = ""
    documento: str = ""
    tipo_documento: str | None = None
    endereco: EnderecoATF | None = None


class FiscalDetalheATF(FiscalATF):
    """
    Fiscal no detalhe: os mesmos campos da listagem, mais o indicador de
    responsavel pela OS e o codigo do status.

    Dois campos herdados ficam sempre vazios aqui: data_cancelamento,
    que a doc do detalhe nao devolve, e status — este servico manda o
    codigo (stFiscalOS), nao a descricao, entao ele vai em
    status_codigo para nao sobrepor o texto que vem da listagem.
    """
    responsavel: str | None = None
    status_codigo: str | None = None


class EventoOSATF(BaseModel):
    """Evento de acompanhamento da OS (listaEventos)."""
    tipo_codigo: str | None = None
    tipo: str = ""
    data_inicial: str | None = None
    data_final: str | None = None
    referencia_inicial: str | None = None
    referencia_final: str | None = None
    procedimento: str = ""
    valor_levantado: float | None = None
    observacao: str | None = None
    arquivo: str | None = None


class ProrrogacaoATF(BaseModel):
    """Pedido de prorrogacao de prazo da OS."""
    dias: int | None = None
    prazo_atual: str | None = None
    prazo_anterior: str | None = None
    situacao_prazo: str | None = None
    justificativa: str | None = None
    usuario: str | None = None
    data_homologacao: str | None = None
    usuario_homologacao: str | None = None
    status: str | None = None


class NotificacaoATF(BaseModel):
    """Notificacao vinculada a OS (lista normal ou SCAMF)."""
    codigo: str = ""
    nome: str = ""


class ProcessoATF(BaseModel):
    """Processo administrativo vinculado a OS."""
    numero: str = ""
    tipo: str | None = None


class JustificativaATF(BaseModel):
    """Justificativa de atraso registrada na OS."""
    tipo: str = ""
    descricao: str = ""
    usuario: str | None = None
    data_inclusao: str | None = None


class DescricaoComplementarATF(BaseModel):
    """Texto complementar incluido na OS."""
    data_inclusao: str | None = None
    usuario: str | None = None
    descricao: str = ""
    descricao_formatada: str | None = None


class RecolhimentoATF(BaseModel):
    """
    Recolhimento vinculado a OS (listaRecolhimentosOS/recolhimentoOS).

    Estrutura descrita na revisao da doc do detalhe de 21/08/2026 — antes
    dela so o total recolhido era documentado.
    """
    chave: str | None = None
    descricao: str = ""
    data_inclusao: str | None = None
    nosso_numero: str | None = None
    ref: str | None = None
    referencia: str | None = None
    valor_principal: float | None = None
    receita_codigo: str | None = None
    receita_nome: str = ""
    situacao_debito: str | None = None
    situacao_arr: str | None = None


class DenunciaATF(BaseModel):
    """Denuncia vinculada a OS (listaDenuncia/denuncia)."""
    data: str | None = None
    descricao: str = ""


class AutorizacaoATF(BaseModel):
    """Quem autorizou a OS e quando."""
    data: str | None = None
    usuario: str | None = None
    matricula: str | None = None


class OSDetalheCompletoResponse(BaseModel):
    """
    Resposta do detalharOrdemServicoWebService (doc do detalhe).

    Os campos que existem nos dois servicos usam os mesmos nomes da
    listagem (numero_os, modelo, situacao, data_abertura, fiscais...)
    para o painel sobrepor o detalhe a linha do grid campo a campo.

    O que a listagem tem e este servico nao — equipe fiscal, dias de
    execucao e as medias por Modelo/Motivo — nao aparece aqui de
    proposito: o front preserva esses valores da linha ao mesclar.
    """
    numero_os: str
    modelo: str = ""
    modelo_codigo: int | None = None
    motivo_abertura: str = ""
    motivo_abertura_codigo: int | None = None
    situacao: SituacaoATF | None = None
    termo_os: str | None = None
    termo_os_descricao: str | None = None
    tipo_funcionario: str | None = None
    periodo_fiscalizar: PeriodoATF | None = None

    # equipeFiscalizacao/noEquipe, tpBdFiscal e dsTpBdFiscal vem na
    # resposta mas nao constam da doc do detalhe.
    equipe_fiscal: str = ""
    bd_fiscal: str | None = None
    bd_fiscal_codigo: str | None = None

    orgao_origem: str | None = None
    orgao_origem_codigo: int | None = None
    orgao_executor: str = ""
    orgao_executor_sigla: str = ""
    orgao_executor_codigo: int | None = None

    data_abertura: str = ""
    data_emissao: str | None = None
    data_inicio_fiscalizacao: str | None = None
    data_prazo_final: str | None = None
    data_encerramento: str | None = None
    data_inicio_exercicio: str | None = None
    data_final_exercicio: str | None = None
    data_ultimo_evento: str | None = None
    situacao_prazo: str | None = None

    ie: str = ""
    cnpj: str | None = None
    razao_social: str = ""
    contribuinte: ContribuinteATF | None = None

    periodo_nf: PeriodoATF | None = None
    periodo_efd: PeriodoATF | None = None
    autorizacao: AutorizacaoATF | None = None

    fiscais: list[FiscalDetalheATF] = []
    eventos: list[EventoOSATF] = []
    qtd_eventos: int | None = None
    prorrogacoes: list[ProrrogacaoATF] = []
    notificacoes: list[NotificacaoATF] = []
    notificacoes_scamf: list[NotificacaoATF] = []
    processos: list[ProcessoATF] = []
    justificativas: list[JustificativaATF] = []
    recolhimentos: list[RecolhimentoATF] = []
    denuncias: list[DenunciaATF] = []
    descricoes_complementares: list[DescricaoComplementarATF] = []

    valor_total_recolhido: float | None = None
    id_os_gerou_banco: str | None = None

    # Verdadeiro quando o detalhe veio de um ambiente diferente do da
    # listagem (ATF_DETALHE_BASE_URL). Os bancos nao sao os mesmos: a
    # mesma OS volta com outro contribuinte e outros fiscais, e a tela
    # precisa avisar quem esta olhando em vez de exibir a mistura como
    # se fosse um registro so.
    detalhe_de_outro_ambiente: bool = False
