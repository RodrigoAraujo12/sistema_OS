/**
 * api.js – Cliente HTTP para comunicacao com o backend FastAPI.
 *
 * Encapsula todas as chamadas REST em uma classe unica (ApiClient),
 * adicionando automaticamente o token Bearer apos o login.
 *
 * Para trocar a URL da API (ex: producao), altere a variavel API_BASE.
 */

// URL da API – pode ser sobrescrita via define do bundler: --define:API_BASE_URL='\"https://...\"'
// Em desenvolvimento, aponta para localhost:8000
const API_BASE = typeof API_BASE_URL !== "undefined" ? API_BASE_URL : "http://localhost:8000";

class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.token = null;
  }

  /** Define o token JWT/session retornado pelo login. */
  setToken(token) {
    this.token = token;
  }

  /**
   * Metodo generico de requisicao.
   * Adiciona Content-Type JSON e o header Authorization automaticamente.
   * Lanca Error com a mensagem do backend em caso de falha.
   */
  async request(path, options = {}) {
    const { headers: customHeaders, ...rest } = options;

    const headers = {
      "Content-Type": "application/json",
      ...(customHeaders || {}),
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...rest,
      headers,
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const message = detail.detail || "Erro na requisicao";
      throw new Error(message);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  // Auth
  login(username, password) {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    });
  }

  changePassword(payload) {
    return this.request("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  /** Revoga a sessao no servidor. Falha em silencio: se a rede caiu ou o
   *  token ja venceu, o logout local acontece de qualquer forma. */
  async logout() {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } catch {
      /* sessao ja invalida do outro lado — nada a fazer */
    }
  }

  // Gerencias
  listGerencias() {
    return this.request("/admin/gerencias");
  }

  createGerencia(payload) {
    return this.request("/admin/gerencias", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  updateGerencia(gerenciaId, payload) {
    return this.request(`/admin/gerencias/${gerenciaId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  }

  // Supervisoes
  listSupervisoes() {
    return this.request("/admin/supervisoes");
  }

  createSupervisao(payload) {
    return this.request("/admin/supervisoes", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  updateSupervisao(supervisaoId, payload) {
    return this.request(`/admin/supervisoes/${supervisaoId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  }

  // Equipes fiscais (ATF)
  listEquipesFiscais() {
    return this.request("/equipes-fiscais");
  }

  listMembrosEquipe(codigo) {
    return this.request(`/admin/equipes-fiscais/${codigo}/membros`);
  }

  // Users
  listUsers() {
    return this.request("/admin/users");
  }

  createUser(payload) {
    return this.request("/admin/users", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  updateUser(userId, payload) {
    return this.request(`/admin/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  }

  resetUserPassword(userId) {
    return this.request(`/admin/users/${userId}/reset-password`, {
      method: "POST"
    });
  }

  deleteUser(userId) {
    return this.request(`/admin/users/${userId}`, {
      method: "DELETE"
    });
  }

  // Ordens de Servico (somente consulta - API externa)
  listOrdens({
    numero = null,
    modelo = null,
    ie = null,
    cnpj = null,
    razao_social = null,
    matriculas = null,
    situacoes = null,       // array de codigos numericos ex: [0, 1, 4]
    data_abertura_inicio = null,
    data_abertura_fim = null,
    data_ciencia_inicio = null,
    data_ciencia_fim = null,
    motivo_abertura = null,
    equipe_fiscal = null,
    orgao_executor = null,
    data_encerramento_inicio = null,
    data_encerramento_fim = null,
    pagina = 1,
    limite = 20,
    ordenar_por = null,
    ordem = null,
  } = {}) {
    const params = new URLSearchParams();
    if (numero) params.set("numero_os", numero);
    if (modelo) params.set("modelo", modelo);
    if (ie) params.set("ie", ie);
    if (cnpj) params.set("cnpj", cnpj);
    if (razao_social) params.set("razao_social", razao_social);
    if (matriculas) params.set("matriculas", matriculas);
    if (situacoes && situacoes.length > 0) situacoes.forEach(s => params.append("situacao", s));
    if (data_abertura_inicio) params.set("data_abertura_ini", data_abertura_inicio);
    if (data_abertura_fim) params.set("data_abertura_fim", data_abertura_fim);
    if (data_ciencia_inicio) params.set("data_ciencia_ini", data_ciencia_inicio);
    if (data_ciencia_fim) params.set("data_ciencia_fim", data_ciencia_fim);
    if (motivo_abertura) params.set("motivo_abertura", motivo_abertura);
    if (equipe_fiscal) params.set("equipe_fiscal", equipe_fiscal);
    if (orgao_executor) params.set("orgao_executor", orgao_executor);
    if (data_encerramento_inicio) params.set("data_encerramento_ini", data_encerramento_inicio);
    if (data_encerramento_fim) params.set("data_encerramento_fim", data_encerramento_fim);
    params.set("pagina", pagina);
    params.set("limite", limite);
    if (ordenar_por) {
      params.set("ordenar_por", ordenar_por);
      params.set("ordem", ordem || "asc");
    }
    return this.request(`/ordens?${params.toString()}`);
  }

  getOrdem(numero) {
    return this.request(`/ordens/${encodeURIComponent(numero)}`);
  }

  /** Detalhe completo de UMA OS (servico detalharOrdemServico, doc do detalhe).
   *  Chamado a cada clique numa linha da listagem — uma ordem por vez. */
  getOrdemDetalhe(numero) {
    return this.request(`/ordens/${encodeURIComponent(numero)}/detalhe`);
  }

  async downloadOrdemPdf(numero) {
    const headers = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/ordens/${encodeURIComponent(numero)}/pdf`, { headers });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Erro ao gerar PDF da OS");
    }
    return response.blob();
  }

  listarAlertas() {
    return this.request("/alertas");
  }

  // Dashboard (admin only)
  getDashboard({ dataInicio, dataFim } = {}) {
    const params = new URLSearchParams();
    if (dataInicio) params.set("data_inicio", dataInicio);
    if (dataFim) params.set("data_fim", dataFim);
    const qs = params.toString();
    return this.request(`/admin/dashboard${qs ? `?${qs}` : ""}`);
  }

  /** Monta a query string do relatorio de OS (mesmos filtros do painel). */
  _paramsRelatorioOrdens(f = {}) {
    const params = new URLSearchParams();
    if (f.numero) params.set("numero_os", f.numero);
    if (f.modelo) params.set("modelo", f.modelo);
    if (f.motivo_abertura) params.set("motivo_abertura", f.motivo_abertura);
    if (f.ie) params.set("ie", f.ie);
    if (f.cnpj) params.set("cnpj", f.cnpj);
    if (f.razao_social) params.set("razao_social", f.razao_social);
    if (f.matriculas) params.set("matriculas", f.matriculas);
    if (f.equipe_fiscal) params.set("equipe_fiscal", f.equipe_fiscal);
    if (f.orgao_executor) params.set("orgao_executor", f.orgao_executor);
    if (f.situacoes && f.situacoes.length > 0) f.situacoes.forEach(s => params.append("situacao", s));
    if (f.data_abertura_inicio) params.set("data_abertura_ini", f.data_abertura_inicio);
    if (f.data_abertura_fim) params.set("data_abertura_fim", f.data_abertura_fim);
    if (f.data_encerramento_inicio) params.set("data_encerramento_ini", f.data_encerramento_inicio);
    if (f.data_encerramento_fim) params.set("data_encerramento_fim", f.data_encerramento_fim);
    if (f.data_ciencia_inicio) params.set("data_ciencia_ini", f.data_ciencia_inicio);
    if (f.data_ciencia_fim) params.set("data_ciencia_fim", f.data_ciencia_fim);
    if (f.search) params.set("search", f.search);
    return params.toString();
  }

  // Relatorios (download CSV)
  async downloadRelatorioOrdens(filtros = {}) {
    const qs = this._paramsRelatorioOrdens(filtros);

    const headers = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/relatorios/ordens${qs ? `?${qs}` : ""}`, { headers });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Erro ao gerar relatorio");
    }
    return response.blob();
  }

  async downloadRelatorioDashboard({ dataInicio, dataFim } = {}) {
    const params = new URLSearchParams();
    if (dataInicio) params.set("data_inicio", dataInicio);
    if (dataFim) params.set("data_fim", dataFim);
    const qs = params.toString();

    const headers = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/relatorios/dashboard${qs ? `?${qs}` : ""}`, { headers });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Erro ao gerar relatorio");
    }
    return response.blob();
  }

  // Relatorios (download PDF)
  async downloadRelatorioOrdensPdf(filtros = {}) {
    const qs = this._paramsRelatorioOrdens(filtros);

    const headers = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/relatorios/ordens/pdf${qs ? `?${qs}` : ""}`, { headers });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Erro ao gerar relatorio PDF");
    }
    return response.blob();
  }

  async downloadRelatorioDashboardPdf({ dataInicio, dataFim } = {}) {
    const params = new URLSearchParams();
    if (dataInicio) params.set("data_inicio", dataInicio);
    if (dataFim) params.set("data_fim", dataFim);
    const qs = params.toString();

    const headers = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/relatorios/dashboard/pdf${qs ? `?${qs}` : ""}`, { headers });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Erro ao gerar relatorio PDF");
    }
    return response.blob();
  }
}

const apiClient = new ApiClient(API_BASE);

export default apiClient;
