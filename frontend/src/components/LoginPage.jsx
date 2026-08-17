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
              placeholder="Seu usu&aacute;rio"
              autoComplete="username"
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              value={loginForm.password}
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
              placeholder="Sua senha"
              autoComplete="current-password"
            />
          </label>
          <button type="submit">Entrar</button>
        </form>
        {/* O bloco de credenciais de exemplo saiu daqui: nao existe mais
            senha padrao. Cada usuario recebe uma temporaria aleatoria, que
            o admin ve uma unica vez na criacao ou no reset. */}
        {error && <div className="alert error">{error}</div>}
      </div>
    </div>
  );
}
