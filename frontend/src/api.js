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
  listOrdens(statusFilter = null, tipo = null) {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (tipo) params.set("tipo", tipo);
    const qs = params.toString();
    return this.request(`/ordens${qs ? `?${qs}` : ""}`);
  }

  getOrdem(numero) {
    return this.request(`/ordens/${encodeURIComponent(numero)}`);
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
}

const apiClient = new ApiClient(API_BASE);

export default apiClient;
