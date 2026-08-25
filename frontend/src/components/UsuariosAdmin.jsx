/**
 * UsuariosAdmin.jsx – Painel CRUD de Usuarios (admin).
 *
 * Gerencia criacao, edicao e reset de senha de usuarios.
 * Inclui selects em cascata (gerencia -> supervisao) e, para
 * supervisores, o vinculo com a equipe fiscal do ATF.
 */

import React, { useMemo, useState } from "react";
import apiClient from "../api.js";
import { roleOptions } from "../constants.js";
import ConfirmModal from "./ConfirmModal.jsx";

const PAGE_SIZE = 10;

/** Nomes das equipes a que o usuario pertence, como vieram da planilha. */
function nomesDasEquipes(item) {
  const equipes = item.equipes_membro || [];
  if (equipes.length === 0) return "-";
  return equipes.map((e) => e.nome).join(", ");
}

/**
 * Equipe a sugerir como chefia ao promover alguem a supervisor.
 *
 * So sugere quando nao ha duvida: quem pertence a duas equipes (cinco
 * pessoas, na planilha de 25/08/2026) fica sem sugestao, para o admin
 * escolher qual delas ele chefia.
 */
function equipeSugerida(item) {
  const equipes = item.equipes_membro || [];
  return equipes.length === 1 ? String(equipes[0].codigo) : "";
}

const emptyUserForm = {
  username: "",
  role: "supervisor",
  gerencia_id: "",
  supervisao_id: "",
  matricula: "",
  equipe_codigo: "",
};

export default function UsuariosAdmin({
  users,
  gerencias,
  supervisoes,
  equipes = [],
  onRefresh,
  onMessage,
  onError,
  onResetInfo,
}) {
  const [createForm, setCreateForm] = useState({ ...emptyUserForm });
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({ ...emptyUserForm });
  const [searchText, setSearchText] = useState("");
  const [page, setPage] = useState(1);
  const [confirmReset, setConfirmReset] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  // Cascata: supervisoes filtradas pela gerencia selecionada
  const createSupervisoesFiltradas = useMemo(() => {
    if (!createForm.gerencia_id) return supervisoes;
    return supervisoes.filter(
      (s) => String(s.gerencia_id) === String(createForm.gerencia_id)
    );
  }, [supervisoes, createForm.gerencia_id]);

  const editSupervisoesFiltradas = useMemo(() => {
    if (!editForm.gerencia_id) return supervisoes;
    return supervisoes.filter(
      (s) => String(s.gerencia_id) === String(editForm.gerencia_id)
    );
  }, [supervisoes, editForm.gerencia_id]);

  async function handleCreate(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    try {
      const criado = await apiClient.createUser({
        username: createForm.username,
        role: createForm.role,
        gerencia_id: Number(createForm.gerencia_id),
        supervisao_id: Number(createForm.supervisao_id),
        matricula: createForm.matricula,
        equipe_codigo: createForm.equipe_codigo ? Number(createForm.equipe_codigo) : null,
      });
      setCreateForm({ ...emptyUserForm });
      // Vai no aviso persistente (10s), nao na mensagem de 5s: e a unica
      // vez que essa senha aparece — o backend so guarda o hash.
      onResetInfo(
        `Usuario "${criado.username}" criado. Senha temporaria: ${criado.temporary_password} — anote e repasse, ela nao sera exibida de novo.`
      );
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleUpdate(userId) {
    onError("");
    onMessage("");
    try {
      await apiClient.updateUser(userId, {
        username: editForm.username,
        role: editForm.role,
        gerencia_id: Number(editForm.gerencia_id),
        supervisao_id: Number(editForm.supervisao_id),
        matricula: editForm.matricula,
        equipe_codigo: editForm.equipe_codigo ? Number(editForm.equipe_codigo) : null,
      });
      setEditId(null);
      setEditForm({ ...emptyUserForm });
      onMessage("Usuario atualizado.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleResetPassword(userId) {
    onError("");
    onMessage("");
    try {
      const data = await apiClient.resetUserPassword(userId);
      onResetInfo(
        `Senha redefinida: ${data.temporary_password} — anote e repasse, ela nao sera exibida de novo.`
      );
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleDeleteUser(userId) {
    onError("");
    onMessage("");
    try {
      await apiClient.deleteUser(userId);
      onMessage("Usuario removido.");
      onRefresh();
    } catch (err) {
      onError(err.message);
    }
  }

  const nonAdminUsers = useMemo(() => users.filter((u) => u.role !== "admin"), [users]);

  const filteredUsers = useMemo(() => {
    if (!searchText) return nonAdminUsers;
    const term = searchText.toLowerCase();
    return nonAdminUsers.filter(
      (u) =>
        u.username.toLowerCase().includes(term) ||
        (u.matricula && u.matricula.toLowerCase().includes(term)) ||
        (u.role && u.role.toLowerCase().includes(term)) ||
        (u.gerencia_name && u.gerencia_name.toLowerCase().includes(term)) ||
        (u.supervisao_name && u.supervisao_name.toLowerCase().includes(term))
    );
  }, [nonAdminUsers, searchText]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedUsers = filteredUsers.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  return (
    <div className="card">
      <h2>Usuarios ({filteredUsers.length})</h2>
      <form onSubmit={handleCreate} className="form" style={{ maxWidth: 600, marginBottom: 20 }}>
        <div className="form-row">
          <label>
            Usuario
            <input
              value={createForm.username}
              onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
              required
            />
          </label>
          <label>
            Matr&iacute;cula
            <input
              value={createForm.matricula}
              onChange={(e) => setCreateForm({ ...createForm, matricula: e.target.value })}
              required
              placeholder="Ex: 12345"
            />
          </label>
          <label>
            Cargo
            <select
              value={createForm.role}
              onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}
              required
            >
              {roleOptions.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label>
            Gerencia
            <select
              value={createForm.gerencia_id}
              onChange={(e) =>
                setCreateForm({ ...createForm, gerencia_id: e.target.value, supervisao_id: "" })
              }
              required
            >
              <option value="">Selecione</option>
              {gerencias.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </label>
          <label>
            Supervisao
            <select
              value={createForm.supervisao_id}
              onChange={(e) => setCreateForm({ ...createForm, supervisao_id: e.target.value })}
              required
            >
              <option value="">Selecione</option>
              {createSupervisoesFiltradas.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </label>
        </div>
        {/* So supervisor usa a equipe: e ela que define o que ele enxerga.
            Fiscal ve apenas as proprias OS e gerente ve pela gerencia. */}
        {createForm.role === "supervisor" && equipes.length > 0 && (
          <div className="form-row">
            <label style={{ flex: 1 }}>
              Equipe Fiscal (ATF)
              <select
                value={createForm.equipe_codigo}
                onChange={(e) => setCreateForm({ ...createForm, equipe_codigo: e.target.value })}
              >
                <option value="">Sem equipe — usa a supervisao local</option>
                {equipes.map((eq) => (
                  <option key={eq.codigo} value={eq.codigo}>
                    {eq.nome} ({eq.total_membros})
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <p className="muted">
          Uma senha tempor&aacute;ria ser&aacute; gerada e exibida ap&oacute;s a cria&ccedil;&atilde;o.
          O usu&aacute;rio ter&aacute; que troc&aacute;-la no primeiro acesso.
        </p>
        <button type="submit">Criar Usuario</button>
      </form>

      {/* Search */}
      <div style={{ marginBottom: 12, maxWidth: 400 }}>
        <input
          type="text"
          placeholder="Buscar por nome, matrícula, cargo, gerência..."
          value={searchText}
          onChange={(e) => { setSearchText(e.target.value); setPage(1); }}
          style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13 }}
        />
      </div>

      {filteredUsers.length === 0 ? (
        <p className="muted">Nenhum usuario encontrado.</p>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Matr&iacute;cula</th>
                <th>Cargo</th>
                <th>Gerencia</th>
                <th>Supervisao</th>
                <th>Equipe (ATF)</th>
                <th>Chefia</th>
                <th>Acoes</th>
              </tr>
            </thead>
            <tbody>
              {pagedUsers.map((item) => (
                  <tr key={item.id}>
                    {editId === item.id ? (
                      <>
                        <td>
                          <input
                            value={editForm.username}
                            onChange={(e) =>
                              setEditForm({ ...editForm, username: e.target.value })
                            }
                            style={{ width: "100%" }}
                          />
                        </td>
                        <td>
                          <input
                            value={editForm.matricula}
                            onChange={(e) =>
                              setEditForm({ ...editForm, matricula: e.target.value })
                            }
                            style={{ width: "100%" }}
                            placeholder="Matricula"
                          />
                        </td>
                        <td>
                          <select
                            value={editForm.role}
                            onChange={(e) => {
                              // Promover a supervisor: a equipe que ele
                              // chefia quase sempre e a que ele pertence,
                              // entao ja vem preenchida. Continua editavel.
                              const role = e.target.value;
                              setEditForm((prev) => ({
                                ...prev,
                                role,
                                equipe_codigo:
                                  role === "supervisor" && !prev.equipe_codigo
                                    ? equipeSugerida(item)
                                    : prev.equipe_codigo,
                              }));
                            }}
                          >
                            {roleOptions.map((r) => (
                              <option key={r.value} value={r.value}>{r.label}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            value={editForm.gerencia_id}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                gerencia_id: e.target.value,
                                supervisao_id: "",
                              })
                            }
                          >
                            <option value="">--</option>
                            {gerencias.map((g) => (
                              <option key={g.id} value={g.id}>{g.name}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            value={editForm.supervisao_id}
                            onChange={(e) =>
                              setEditForm({ ...editForm, supervisao_id: e.target.value })
                            }
                          >
                            <option value="">--</option>
                            {editSupervisoesFiltradas.map((s) => (
                              <option key={s.id} value={s.id}>{s.name}</option>
                            ))}
                          </select>
                        </td>
                        <td className="muted">{nomesDasEquipes(item)}</td>
                        <td>
                          {editForm.role === "supervisor" && equipes.length > 0 ? (
                            <select
                              value={editForm.equipe_codigo}
                              onChange={(e) =>
                                setEditForm({ ...editForm, equipe_codigo: e.target.value })
                              }
                            >
                              <option value="">--</option>
                              {equipes.map((eq) => (
                                <option key={eq.codigo} value={eq.codigo}>
                                  {eq.nome} ({eq.total_membros})
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="muted">-</span>
                          )}
                        </td>
                        <td>
                          <div className="row-actions">
                            <button className="small success" onClick={() => handleUpdate(item.id)}>
                              Salvar
                            </button>
                            <button
                              className="small secondary"
                              onClick={() => {
                                setEditId(null);
                                setEditForm({ ...emptyUserForm });
                              }}
                            >
                              Cancelar
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td><strong>{item.username}</strong></td>
                        <td>{item.matricula || "-"}</td>
                        <td><span className="badge normal">{item.role}</span></td>
                        <td>{item.gerencia_name || "-"}</td>
                        <td>{nomesDasEquipes(item)}</td>
                        <td>{item.equipe_nome || "-"}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="small ghost"
                              onClick={() => {
                                setEditId(item.id);
                                setEditForm({
                                  username: item.username,
                                  role: item.role,
                                  gerencia_id: item.gerencia_id || "",
                                  supervisao_id: item.supervisao_id || "",
                                  matricula: item.matricula || "",
                                  equipe_codigo:
                                    item.equipe_codigo ||
                                    (item.role === "supervisor" ? equipeSugerida(item) : ""),
                                });
                              }}
                            >
                              Editar
                            </button>
                            <button
                              className="small secondary"
                              onClick={() => setConfirmReset(item)}
                            >
                              Resetar Senha
                            </button>
                            <button
                              className="small danger"
                              onClick={() => setConfirmDelete(item)}
                            >
                              Excluir
                            </button>
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
          <button className="small secondary" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
          <button className="small secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>‹ Anterior</button>
          <span style={{ fontSize: 13, color: "#6b7280" }}>
            {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filteredUsers.length)} de {filteredUsers.length}
          </span>
          <button className="small secondary" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>Próxima ›</button>
          <button className="small secondary" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
        </div>
      )}

      {/* Confirm Reset Password Modal */}
      <ConfirmModal
        open={!!confirmReset}
        title="Resetar senha"
        message={confirmReset ? `Tem certeza que deseja resetar a senha de "${confirmReset.username}"? Uma senha temporária será gerada e exibida uma única vez.` : ""}
        confirmLabel="Resetar Senha"
        cancelLabel="Cancelar"
        variant="danger"
        onConfirm={() => {
          handleResetPassword(confirmReset.id);
          setConfirmReset(null);
        }}
        onCancel={() => setConfirmReset(null)}
      />

      {/* Confirm Delete User Modal */}
      <ConfirmModal
        open={!!confirmDelete}
        title="Excluir usuário"
        message={confirmDelete ? `Tem certeza que deseja excluir o usuário "${confirmDelete.username}"? Esta ação não pode ser desfeita.` : ""}
        confirmLabel="Excluir"
        cancelLabel="Cancelar"
        variant="danger"
        onConfirm={() => {
          handleDeleteUser(confirmDelete.id);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
