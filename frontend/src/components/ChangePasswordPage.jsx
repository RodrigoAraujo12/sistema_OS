/**
 * ChangePasswordPage.jsx – Troca de senha.
 *
 * Dois modos:
 * - obrigatoria (must_change_password = true): ocupa a tela inteira, com
 *   barra propria e sem saida — o backend recusa o resto da API mesmo.
 * - voluntaria: entra como painel dentro do layout normal, pelo menu
 *   "Trocar Senha".
 *
 * Gerencia seu proprio estado de formulario, mensagem e erro.
 * Inclui checklist de requisitos de senha com feedback em tempo real.
 */

import React, { useState, useMemo } from "react";
import apiClient from "../api.js";

const PASSWORD_RULES = [
  { key: "length", label: "Mínimo 6 caracteres", test: (v) => v.length >= 6 },
  { key: "upper", label: "Letra maiúscula (A-Z)", test: (v) => /[A-Z]/.test(v) },
  { key: "lower", label: "Letra minúscula (a-z)", test: (v) => /[a-z]/.test(v) },
  { key: "digit", label: "Número (0-9)", test: (v) => /\d/.test(v) },
  { key: "special", label: "Caractere especial (!@#$%...)", test: (v) => /[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/~`]/.test(v) },
];

export default function ChangePasswordPage({ onPasswordChanged, obrigatoria = false }) {
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const ruleResults = useMemo(
    () => PASSWORD_RULES.map((r) => ({ ...r, passed: r.test(form.new_password) })),
    [form.new_password]
  );
  const allPassed = ruleResults.every((r) => r.passed);
  const hasTyped = form.new_password.length > 0;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    if (!allPassed) {
      setError("A senha não atende todos os requisitos.");
      return;
    }
    try {
      await apiClient.changePassword(form);
      setForm({ current_password: "", new_password: "" });
      setMessage("Senha atualizada com sucesso.");
      onPasswordChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  const cartao = (
    <>
      <div className="card">
        <h2>Alterar Senha</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          {obrigatoria
            ? "Sua senha é temporária. Atualize para continuar."
            : "Escolha uma nova senha para a sua conta."}
        </p>
        <form onSubmit={handleSubmit} className="form" style={{ maxWidth: 400 }}>
          <label>
            Senha atual
            <input
              type="password"
              value={form.current_password}
              onChange={(e) => setForm({ ...form, current_password: e.target.value })}
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            Nova senha
            <input
              type="password"
              value={form.new_password}
              onChange={(e) => setForm({ ...form, new_password: e.target.value })}
              autoComplete="new-password"
              required
            />
          </label>

          <ul className="pwd-rules">
            {ruleResults.map((r) => (
              <li key={r.key} className={hasTyped ? (r.passed ? "passed" : "failed") : ""}>
                <span className="pwd-rules-icon">{hasTyped ? (r.passed ? "✔" : "✖") : "○"}</span>
                {r.label}
              </li>
            ))}
          </ul>

          <button type="submit" disabled={!allPassed}>
            Atualizar Senha
          </button>
        </form>
      </div>
      {message && <div className="alert success">{message}</div>}
      {error && <div className="alert error">{error}</div>}
    </>
  );

  // No modo voluntario o App ja fornece a TopBar e o .page-content; so a
  // troca obrigatoria monta a sua propria moldura, porque ela substitui a
  // aplicacao inteira.
  if (!obrigatoria) return cartao;

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <img src="/sefaz-pb.png" alt="SEFAZ PB" className="topbar-logo-img" />
        </div>
      </div>
      <div className="page-content">{cartao}</div>
    </>
  );
}
