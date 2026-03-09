/**
 * GerenciasAdmin.jsx – Painel CRUD de Gerencias (admin).
 *
 * Gerencia seu proprio estado de formulario e edicao.
 * Chama onRefresh() apos operacoes para atualizar listas no App.
 */

import React, { useState } from "react";
import apiClient from "../api.js";

export default function GerenciasAdmin({ gerencias, onRefresh, onMessage, onError }) {
  const [createForm, setCreateForm] = useState({ name: "" });
  const [editId, setEditId] = useState(null);
  const [editName, setEditName] = useState("");

  async function handleCreate(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    try {
      await apiClient.createGerencia(createForm);
      setCreateForm({ name: "" });
      onMessage("Gerencia criada com sucesso.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleUpdate(id) {
    onError("");
    onMessage("");
    try {
      await apiClient.updateGerencia(id, { name: editName });
      setEditId(null);
      setEditName("");
      onMessage("Gerencia atualizada.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <div className="card">
      <h2>Gerencias</h2>
      <form onSubmit={handleCreate} className="form" style={{ maxWidth: 400, marginBottom: 20 }}>
        <label>
          Nome da gerencia
          <input
            value={createForm.name}
            onChange={(e) => setCreateForm({ name: e.target.value })}
            required
          />
        </label>
        <button type="submit">Criar Gerencia</button>
      </form>
      {gerencias.length === 0 ? (
        <p className="muted">Nenhuma gerencia cadastrada.</p>
      ) : (
        <ul className="list">
          {gerencias.map((item) => (
            <li key={item.id}>
              {editId === item.id ? (
                <div className="inline-form">
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                  <button className="small" onClick={() => handleUpdate(item.id)}>
                    Salvar
                  </button>
                  <button
                    className="small secondary"
                    onClick={() => { setEditId(null); setEditName(""); }}
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <>
                  <strong>{item.name}</strong>
                  <button
                    className="small ghost"
                    onClick={() => { setEditId(item.id); setEditName(item.name); }}
                  >
                    Editar
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
