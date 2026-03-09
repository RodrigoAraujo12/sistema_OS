/**
 * ChangePasswordPage.jsx – Tela de troca de senha obrigatoria.
 *
 * Exibida quando o usuario tem must_change_password = true.
 * Gerencia seu proprio estado de formulario, mensagem e erro.
 */

import React, { useState } from "react";
import apiClient from "../api.js";

export default function ChangePasswordPage({ onPasswordChanged }) {
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await apiClient.changePassword(form);
      setForm({ current_password: "", new_password: "" });
      setMessage("Senha atualizada com sucesso.");
      onPasswordChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <img src="/sefaz-pb.png" alt="SEFAZ PB" className="topbar-logo-img" />
        </div>
      </div>
      <div className="page-content">
        <div className="card">
          <h2>Alterar Senha</h2>
          <p className="muted" style={{ marginBottom: 16 }}>
            Sua senha e temporaria. Atualize para continuar.
          </p>
          <form onSubmit={handleSubmit} className="form" style={{ maxWidth: 400 }}>
            <label>
              Senha atual
              <input
                type="password"
                value={form.current_password}
                onChange={(e) => setForm({ ...form, current_password: e.target.value })}
                required
              />
            </label>
            <label>
              Nova senha
              <input
                type="password"
                value={form.new_password}
                onChange={(e) => setForm({ ...form, new_password: e.target.value })}
                required
                minLength={4}
              />
              <span className="muted" style={{ fontSize: 11 }}>Minimo 4 caracteres</span>
            </label>
            <button type="submit">Atualizar Senha</button>
          </form>
        </div>
        {message && <div className="alert success">{message}</div>}
        {error && <div className="alert error">{error}</div>}
      </div>
    </>
  );
}
