/**
 * SupervisoesAdmin.jsx – Painel CRUD de Supervisoes (admin).
 *
 * Gerencia seu proprio estado de formulario e edicao.
 * Chama onRefresh() apos operacoes para atualizar listas no App.
 */

import React, { useState } from "react";
import apiClient from "../api.js";

export default function SupervisoesAdmin({ supervisoes, gerencias, onRefresh, onMessage, onError }) {
  const [createForm, setCreateForm] = useState({ name: "", gerencia_id: "" });
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({ name: "", gerencia_id: "" });

  async function handleCreate(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    try {
      await apiClient.createSupervisao({
        name: createForm.name,
        gerencia_id: Number(createForm.gerencia_id),
      });
      setCreateForm({ name: "", gerencia_id: "" });
      onMessage("Supervisao criada com sucesso.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleUpdate(id) {
    onError("");
    onMessage("");
    try {
      await apiClient.updateSupervisao(id, {
        name: editForm.name,
        gerencia_id: Number(editForm.gerencia_id),
      });
      setEditId(null);
      setEditForm({ name: "", gerencia_id: "" });
      onMessage("Supervisao atualizada.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <div className="card">
      <h2>Supervisoes</h2>
      <form onSubmit={handleCreate} className="form" style={{ maxWidth: 500, marginBottom: 20 }}>
        <div className="form-row">
          <label>
            Nome da supervisao
            <input
              value={createForm.name}
              onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              required
            />
          </label>
          <label>
            Gerencia
            <select
              value={createForm.gerencia_id}
              onChange={(e) => setCreateForm({ ...createForm, gerencia_id: e.target.value })}
              required
            >
              <option value="">Selecione</option>
              {gerencias.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="submit">Criar Supervisao</button>
      </form>
      {supervisoes.length === 0 ? (
        <p className="muted">Nenhuma supervisao cadastrada.</p>
      ) : (
        <ul className="list">
          {supervisoes.map((item) => (
            <li key={item.id}>
              {editId === item.id ? (
                <div className="inline-form">
                  <input
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  />
                  <select
                    value={editForm.gerencia_id}
                    onChange={(e) => setEditForm({ ...editForm, gerencia_id: e.target.value })}
                  >
                    <option value="">Selecione</option>
                    {gerencias.map((g) => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                  <button className="small" onClick={() => handleUpdate(item.id)}>
                    Salvar
                  </button>
                  <button
                    className="small secondary"
                    onClick={() => { setEditId(null); setEditForm({ name: "", gerencia_id: "" }); }}
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <>
                  <div>
                    <strong>{item.name}</strong>
                    <div className="muted">{item.gerencia_name}</div>
                  </div>
                  <button
                    className="small ghost"
                    onClick={() => {
                      setEditId(item.id);
                      setEditForm({ name: item.name, gerencia_id: item.gerencia_id });
                    }}
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
