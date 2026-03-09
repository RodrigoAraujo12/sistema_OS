/**
 * LoginPage.jsx – Tela de login do Sistema Sefaz.
 *
 * Gerencia seu proprio estado de formulario e erro.
 * Ao autenticar com sucesso, chama onLogin(data) para o App.
 */

import React, { useState } from "react";
import apiClient from "../api.js";

export default function LoginPage({ onLogin }) {
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await apiClient.login(loginForm.username, loginForm.password);
      onLogin(data);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <img src="/sefaz-pb.png" alt="SEFAZ PB" className="login-logo" />
        <p className="subtitle">Sistema de Ordens de Servico</p>
        <form onSubmit={handleSubmit} className="form">
          <label>
            Usuario
            <input
              value={loginForm.username}
              onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
              placeholder="admin"
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              value={loginForm.password}
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
              placeholder="admin123"
            />
          </label>
          <button type="submit">Entrar</button>
        </form>
        {import.meta.env.DEV && (
          <div className="hint">
            <div>Admin: admin / admin123</div>
            <div>Supervisor: Patricia Oliveira / temp1234</div>
          </div>
        )}
        {error && <div className="alert error">{error}</div>}
      </div>
    </div>
  );
}
