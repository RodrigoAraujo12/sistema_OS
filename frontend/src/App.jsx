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
  const [ordens, setOrdens] = useState([]);
  const [gerencias, setGerencias] = useState([]);
  const [supervisoes, setSupervisoes] = useState([]);
  const [users, setUsers] = useState([]);
  const [alertas, setAlertas] = useState([]);
  const [dashboardData, setDashboardData] = useState(null);

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
    if (authData) {
      apiClient.setToken(authData.token);
      setActiveMenu("ordens");
      refreshAllData();
    }
  }, [authData]);

  // ─── Data fetching ──────────────────────────────────

  /** Carrega todos os dados (login inicial). */
  async function refreshAllData() {
    if (!authData) return;
    setError("");
    try {
      const [ordensData, alertasData] = await Promise.all([
        apiClient.listOrdens(),
        apiClient.listarAlertas()
      ]);
      setOrdens(ordensData);
      setAlertas(alertasData);

      if (authData.role === "admin") {
        const [gerenciasData, supervisoesData, usersData, dashData] = await Promise.all([
          apiClient.listGerencias(),
          apiClient.listSupervisoes(),
          apiClient.listUsers(),
          apiClient.getDashboard()
        ]);
        setGerencias(gerenciasData);
        setSupervisoes(supervisoesData);
        setUsers(usersData);
        setDashboardData(dashData);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  /** Recarrega apenas listas administrativas (apos CRUD). */
  async function refreshAdminLists() {
    try {
      const [gerenciasData, supervisoesData, usersData] = await Promise.all([
        apiClient.listGerencias(),
        apiClient.listSupervisoes(),
        apiClient.listUsers()
      ]);
      setGerencias(gerenciasData);
      setSupervisoes(supervisoesData);
      setUsers(usersData);
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

  function handleLogout() {
    setAuthData(null);
    apiClient.setToken(null);
    setOrdens([]);
    setGerencias([]);
    setSupervisoes([]);
    setUsers([]);
    setAlertas([]);
    setDashboardData(null);
    setResetInfo("");
    setMessage("");
    setError("");
  }

  // ─── Render ─────────────────────────────────────────

  if (!authData) {
    return <LoginPage onLogin={handleLogin} />;
  }

  if (authData.must_change_password) {
    return <ChangePasswordPage onPasswordChanged={handlePasswordChanged} />;
  }

  return (
    <>
      <TopBar
        authData={authData}
        activeMenu={activeMenu}
        onMenuChange={setActiveMenu}
        alertCount={alertas.length}
        darkMode={darkMode}
        onDarkModeToggle={() => setDarkMode(!darkMode)}
        onLogout={handleLogout}
      />

      <div className="page-content">
        {message && <div className="alert success">{message}</div>}
        {error && <div className="alert error">{error}</div>}
        {resetInfo && <div className="alert info">{resetInfo}</div>}

        {authData.role === "admin" && activeMenu === "dashboard" && dashboardData && (
          <DashboardPanel
            dashboardData={dashboardData}
            onDashboardDataChange={setDashboardData}
            onError={setError}
          />
        )}

        {activeMenu === "ordens" && (
          <OrdensPanel ordens={ordens} />
        )}

        {activeMenu === "alertas" && (
          <AlertasPanel alertas={alertas} />
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
      </div>
    </>
  );
}
