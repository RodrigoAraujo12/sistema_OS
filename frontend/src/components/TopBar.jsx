/**
 * TopBar.jsx – Barra de navegacao superior do Sistema Sefaz.
 *
 * Exibe logo, menu de navegacao, toggle de dark mode,
 * informacoes do usuario e botao de logout.
 */

import React from "react";

export default function TopBar({
  authData,
  activeMenu,
  onMenuChange,
  alertCount,
  darkMode,
  onDarkModeToggle,
  onLogout,
}) {
  return (
    <div className="topbar">
      <div className="topbar-left">
        <img src="/sefaz-pb.png" alt="SEFAZ PB" className="topbar-logo-img" />
        <nav className="topbar-nav">
          {authData.role === "admin" && (
            <button
              className={activeMenu === "dashboard" ? "active" : ""}
              onClick={() => onMenuChange("dashboard")}
            >
              Dashboard
            </button>
          )}
          <button
            className={activeMenu === "ordens" ? "active" : ""}
            onClick={() => onMenuChange("ordens")}
          >
            Ordens de Servico
          </button>
          <button
            className={activeMenu === "alertas" ? "active" : ""}
            onClick={() => onMenuChange("alertas")}
          >
            Alertas
            {alertCount > 0 && (
              <span className="nav-badge">{alertCount}</span>
            )}
          </button>
          <button
            className={activeMenu === "relatorios" ? "active" : ""}
            onClick={() => onMenuChange("relatorios")}
          >
            Relatorios
          </button>
          {authData.role === "admin" && (
            <div className="dropdown">
              <button
                className={
                  ["gerencias", "supervisoes", "usuarios"].includes(activeMenu)
                    ? "active"
                    : ""
                }
              >
                Cadastros ▾
              </button>
              <div className="dropdown-menu">
                <button onClick={() => onMenuChange("gerencias")}>Gerencias</button>
                <button onClick={() => onMenuChange("supervisoes")}>Supervisoes</button>
                <button onClick={() => onMenuChange("usuarios")}>Usuarios</button>
              </div>
            </div>
          )}
        </nav>
      </div>
      <div className="topbar-right">
        <button
          className="dark-mode-toggle"
          onClick={onDarkModeToggle}
          title={darkMode ? "Modo Claro" : "Modo Escuro"}
        >
          {darkMode ? "\u2600\uFE0F" : "\uD83C\uDF19"}
        </button>
        <div className="user-info">
          <span>{authData.username}</span>
          <span className="user-badge">{authData.role}</span>
        </div>
        <button className="btn-logout" onClick={onLogout}>
          Sair
        </button>
      </div>
    </div>
  );
}
