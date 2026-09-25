/**
 * App.jsx – Componente raiz do Sistema Sefaz (SPA).
 *
 * Orquestra a navegacao entre telas e gerencia o estado
 * compartilhado (autenticacao, dados). Cada tela e um
 * componente isolado em src/components/.
 */

import React, { useEffect, useState } from "react";
import apiClient from "./api.js";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";

ChartJS.register(
  CategoryScale, LinearScale, BarElement, ArcElement,
  PointElement, LineElement, Title, Tooltip, Legend, Filler
);

import LoginPage from "./components/LoginPage.jsx";
import ChangePasswordPage from "./components/ChangePasswordPage.jsx";
import TopBar from "./components/TopBar.jsx";
import OrdensPanel from "./components/OrdensPanel.jsx";
import AlertasPanel from "./components/AlertasPanel.jsx";
import DashboardPanel from "./components/DashboardPanel.jsx";
import GerenciasAdmin from "./components/GerenciasAdmin.jsx";
import SupervisoesAdmin from "./components/SupervisoesAdmin.jsx";
import UsuariosAdmin from "./components/UsuariosAdmin.jsx";
import RelatoriosPanel from "./components/RelatoriosPanel.jsx";

export default function App() {
  // ─── Auth ───────────────────────────────────────────
  const [authData, setAuthData] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // ─── Data ───────────────────────────────────────────
  const [gerencias, setGerencias] = useState([]);
  const [supervisoes, setSupervisoes] = useState([]);
  const [equipes, setEquipes] = useState([]);
  const [users, setUsers] = useState([]);
  // null = ainda nao carregados. Os alertas descem ate o ATF (uma
  // listagem de 12 meses), entao so saem quando a aba e aberta ou no
  // botao de atualizar — nunca no login.
  const [alertas, setAlertas] = useState(null);
  const [alertasCarregando, setAlertasCarregando] = useState(false);

  // ─── Navigation ─────────────────────────────────────
  const [activeMenu, setActiveMenu] = useState("ordens");
  const [resetInfo, setResetInfo] = useState("");

  // ─── Auto-dismiss messages ──────────────────────────
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(""), 5000);
    return () => clearTimeout(t);
  }, [message]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(""), 8000);
    return () => clearTimeout(t);
  }, [error]);

  useEffect(() => {
    if (!resetInfo) return;
    const t = setTimeout(() => setResetInfo(""), 10000);
    return () => clearTimeout(t);
  }, [resetInfo]);

  // ─── Dark mode ──────────────────────────────────────
  const [darkMode, setDarkMode] = useState(() => {
    try { return localStorage.getItem("sefaz_dark_mode") === "true"; } catch { return false; }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    try { localStorage.setItem("sefaz_dark_mode", darkMode); } catch {}
  }, [darkMode]);

  useEffect(() => {
    if (!authData) return;
    apiClient.setToken(authData.token);
    setActiveMenu("ordens");
    // Com a troca de senha pendente o backend recusa todo o resto da API
    // (403), entao nao ha o que carregar ainda — os dados vem depois da
    // troca, quando este efeito roda de novo.
    if (!authData.must_change_password) refreshAllData();
  }, [authData]);

  // ─── Data fetching ──────────────────────────────────

  /** Carrega todos os dados (login inicial). */
  async function refreshAllData() {
    if (!authData) return;
    setError("");
    try {
      // Nada aqui vai ao ATF: dashboard e alertas consultam sob demanda,
      // cada um na propria tela.
      if (authData.role === "admin") {
        const [gerenciasData, supervisoesData, usersData, equipesData] = await Promise.all([
          apiClient.listGerencias(),
          apiClient.listSupervisoes(),
          apiClient.listUsers(),
          apiClient.listEquipesFiscais()
        ]);
        setGerencias(gerenciasData);
        setSupervisoes(supervisoesData);
        setUsers(usersData);
        setEquipes(equipesData);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  /** Consulta os alertas no ATF (aba de alertas e botao de atualizar). */
  async function carregarAlertas() {
    setAlertasCarregando(true);
    try {
      setAlertas(await apiClient.listarAlertas());
    } catch (err) {
      setError(err.message);
    } finally {
      setAlertasCarregando(false);
    }
  }

  // Primeira abertura da aba de alertas na sessao. As seguintes reusam o
  // que ja veio; quem quiser o estado de agora usa o botao de atualizar.
  useEffect(() => {
    if (activeMenu === "alertas" && alertas === null && !alertasCarregando) carregarAlertas();
  }, [activeMenu, alertas]);

  /** Recarrega apenas listas administrativas (apos CRUD). */
  async function refreshAdminLists() {
    try {
      const [gerenciasData, supervisoesData, usersData, equipesData] = await Promise.all([
        apiClient.listGerencias(),
        apiClient.listSupervisoes(),
        apiClient.listUsers(),
        apiClient.listEquipesFiscais()
      ]);
      setGerencias(gerenciasData);
      setSupervisoes(supervisoesData);
      setUsers(usersData);
      setEquipes(equipesData);
    } catch (err) {
      setError(err.message);
    }
  }

  // ─── Auth handlers ──────────────────────────────────

  function handleLogin(data) {
    setMessage("");
    setError("");
    setAuthData(data);
  }

  function handlePasswordChanged() {
    setAuthData((prev) => ({ ...prev, must_change_password: false }));
  }

  async function handleLogout() {
    // Revoga no servidor antes de limpar o token daqui — na ordem inversa
    // o cliente nao teria mais como se autenticar para pedir a revogacao.
    await apiClient.logout();
    setAuthData(null);
    apiClient.setToken(null);
    setGerencias([]);
    setSupervisoes([]);
    setUsers([]);
    setAlertas(null);
    setResetInfo("");
    setMessage("");
    setError("");
  }

  // ─── Render ─────────────────────────────────────────

  if (!authData) {
    return <LoginPage onLogin={handleLogin} />;
  }

  if (authData.must_change_password) {
    return <ChangePasswordPage onPasswordChanged={handlePasswordChanged} obrigatoria />;
  }

  return (
    <>
      <TopBar
        authData={authData}
        activeMenu={activeMenu}
        onMenuChange={setActiveMenu}
        alertCount={alertas ? alertas.length : 0}
        darkMode={darkMode}
        onDarkModeToggle={() => setDarkMode(!darkMode)}
        onLogout={handleLogout}
      />

      <div className="page-content">
        {message && <div className="alert success">{message}</div>}
        {error && <div className="alert error">{error}</div>}
        {resetInfo && <div className="alert info">{resetInfo}</div>}

        {authData.role === "admin" && activeMenu === "dashboard" && (
          <DashboardPanel onError={setError} />
        )}

        {activeMenu === "ordens" && (
          <OrdensPanel />
        )}

        {activeMenu === "alertas" && (
          <AlertasPanel
            alertas={alertas}
            carregando={alertasCarregando}
            onAtualizar={carregarAlertas}
          />
        )}

        {authData.role === "admin" && activeMenu === "gerencias" && (
          <GerenciasAdmin
            gerencias={gerencias}
            onRefresh={refreshAdminLists}
            onMessage={setMessage}
            onError={setError}
          />
        )}

        {authData.role === "admin" && activeMenu === "supervisoes" && (
          <SupervisoesAdmin
            supervisoes={supervisoes}
            gerencias={gerencias}
            onRefresh={refreshAdminLists}
            onMessage={setMessage}
            onError={setError}
          />
        )}

        {authData.role === "admin" && activeMenu === "usuarios" && (
          <UsuariosAdmin
            users={users}
            gerencias={gerencias}
            supervisoes={supervisoes}
            equipes={equipes}
            onRefresh={refreshAdminLists}
            onMessage={setMessage}
            onError={setError}
            onResetInfo={setResetInfo}
          />
        )}

        {activeMenu === "relatorios" && (
          <RelatoriosPanel
            authData={authData}
            onMessage={setMessage}
            onError={setError}
          />
        )}

        {activeMenu === "senha" && (
          <ChangePasswordPage onPasswordChanged={() => setMessage("Senha alterada com sucesso.")} />
        )}
      </div>
    </>
  );
}
