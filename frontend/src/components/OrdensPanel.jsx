/**
 * OrdensPanel.jsx – Painel de Ordens de Servico.
 *
 * Exibe OS com filtros (status, tipo, periodo, busca textual).
 * Gerencia seu proprio estado de filtros internamente.
 */

import React, { useMemo, useState } from "react";
import { statusLabels, tipoLabels, formatarData } from "../constants.js";

const PAGE_SIZE = 10;

export default function OrdensPanel({ ordens }) {
  const [statusFilter, setStatusFilter] = useState("");
  const [tipoFilter, setTipoFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [page, setPage] = useState(1);

  const { osAbertas, osAndamento, osConcluidas } = useMemo(() => ({
    osAbertas: ordens.filter((o) => o.status === "aberta").length,
    osAndamento: ordens.filter((o) => o.status === "em_andamento").length,
    osConcluidas: ordens.filter((o) => o.status === "concluida").length,
  }), [ordens]);

  const filteredOrdens = useMemo(() => {
    let result = ordens;
    if (statusFilter) result = result.filter((o) => o.status === statusFilter);
    if (tipoFilter) result = result.filter((o) => o.tipo === tipoFilter);
    if (searchText) {
      const term = searchText.toLowerCase();
      result = result.filter(
        (o) =>
          o.numero.toLowerCase().includes(term) ||
          o.razao_social.toLowerCase().includes(term) ||
          o.ie.toLowerCase().includes(term) ||
          (o.matricula_supervisor && o.matricula_supervisor.toLowerCase().includes(term)) ||
          (o.fiscais && o.fiscais.some((f) => f.toLowerCase().includes(term)))
      );
    }
    if (dataInicio) {
      result = result.filter((o) => o.data_abertura && o.data_abertura >= dataInicio);
    }
    if (dataFim) {
      result = result.filter((o) => o.data_abertura && o.data_abertura <= dataFim);
    }
    return result;
  }, [ordens, statusFilter, tipoFilter, searchText, dataInicio, dataFim]);

  const totalPages = Math.max(1, Math.ceil(filteredOrdens.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedOrdens = filteredOrdens.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function setFilter(setter) {
    return (e) => { setter(e.target.value); setPage(1); };
  }

  const hasFilters = statusFilter || tipoFilter || searchText || dataInicio || dataFim;

  function clearFilters() {
    setStatusFilter("");
    setTipoFilter("");
    setSearchText("");
    setDataInicio("");
    setDataFim("");
    setPage(1);
  }

  return (
    <>
      {/* Stats */}
      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{osAbertas}</div>
          <div className="stat-label">Abertas</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{osAndamento}</div>
          <div className="stat-label">Em Andamento</div>
        </div>
        <div className="stat-card concluida">
          <div className="stat-value">{osConcluidas}</div>
          <div className="stat-label">Concluidas</div>
        </div>
      </div>

      {/* Filters */}
      <div className="card filters-card">
        <div className="filters-header">
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Filtros</h3>
          {hasFilters && (
            <button className="small secondary" onClick={clearFilters}>
              Limpar Filtros
            </button>
          )}
        </div>

        {/* Search */}
        <div style={{ marginBottom: 12 }}>
          <input
            type="text"
            placeholder="Buscar por numero, razao social, IE, matricula ou fiscal..."
            value={searchText}
            onChange={(e) => { setSearchText(e.target.value); setPage(1); }}
            style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13 }}
          />
        </div>

        <div className="filters-grid">
          <div className="filter-group">
            <label className="filter-label">Status</label>
            <select value={statusFilter} onChange={setFilter(setStatusFilter)} className="filter-select">
              <option value="">Todos</option>
              {Object.entries(statusLabels).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <label className="filter-label">Tipo</label>
            <select value={tipoFilter} onChange={setFilter(setTipoFilter)} className="filter-select">
              <option value="">Todos</option>
              {Object.entries(tipoLabels).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <label className="filter-label">Data Inicio</label>
            <input type="date" value={dataInicio} onChange={setFilter(setDataInicio)} className="filter-select" />
          </div>

          <div className="filter-group">
            <label className="filter-label">Data Fim</label>
            <input type="date" value={dataFim} onChange={setFilter(setDataFim)} className="filter-select" />
          </div>
        </div>

        {/* Active filter tags */}
        {hasFilters && (
          <div className="active-filters">
            {searchText && (
              <span className="filter-tag">
                Busca: &quot;{searchText}&quot;
                <button onClick={() => setSearchText("")}>&times;</button>
              </span>
            )}
            {statusFilter && (
              <span className="filter-tag">
                Status: {statusLabels[statusFilter]}
                <button onClick={() => setStatusFilter("")}>&times;</button>
              </span>
            )}
            {tipoFilter && (
              <span className="filter-tag">
                Tipo: {tipoLabels[tipoFilter]}
                <button onClick={() => setTipoFilter("")}>&times;</button>
              </span>
            )}
            {dataInicio && (
              <span className="filter-tag">
                Data In&iacute;cio: {formatarData(dataInicio)}
                <button onClick={() => setDataInicio("")}>&times;</button>
              </span>
            )}
            {dataFim && (
              <span className="filter-tag">
                Data Fim: {formatarData(dataFim)}
                <button onClick={() => setDataFim("")}>&times;</button>
              </span>
            )}
          </div>
        )}
      </div>

      {/* OS Table */}
      <div className="card">
        <h2>Ordens de Servico ({filteredOrdens.length}) — pág. {safePage}/{totalPages}</h2>
        <p className="muted" style={{ marginBottom: 12 }}>
          Dados da API externa (servidor Informix). Somente consulta.
        </p>
        {filteredOrdens.length === 0 ? (
          <div className="empty-state">
            <p className="muted">Nenhuma ordem de servico encontrada.</p>
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Numero</th>
                  <th>Tipo</th>
                  <th>IE</th>
                  <th>Razao Social</th>
                  <th>Matr&iacute;cula Supervisor</th>
                  <th>Fiscais</th>
                  <th>Status</th>
                  <th>Abertura</th>
                  <th>Ciencia</th>
                  <th>Ult. Mov.</th>
                  <th>Parado</th>
                </tr>
              </thead>
              <tbody>
                {pagedOrdens.map((os) => (
                  <tr key={os.numero}>
                    <td><strong>{os.numero}</strong></td>
                    <td><span className="badge normal">{os.tipo}</span></td>
                    <td>{os.ie}</td>
                    <td>{os.razao_social}</td>
                    <td>{os.matricula_supervisor || "-"}</td>
                    <td>
                      {os.fiscais && os.fiscais.length > 0
                        ? os.fiscais.map((f, i) => (
                            <div key={i} style={{ fontSize: 12 }}>{f}</div>
                          ))
                        : "-"}
                    </td>
                    <td><span className={`badge ${os.status}`}>{statusLabels[os.status] || os.status}</span></td>
                    <td>{formatarData(os.data_abertura)}</td>
                    <td>{formatarData(os.data_ciencia)}</td>
                    <td>{formatarData(os.data_ultima_movimentacao)}</td>
                    <td>
                      {os.status !== "concluida" && os.status !== "cancelada" ? (
                        <span className={`badge ${os.dias_parado > 15 ? "cancelada" : os.dias_parado > 7 ? "urgente" : "normal"}`}>
                          {os.dias_parado} dias
                        </span>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination controls */}
        {totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
            <button className="small secondary" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
            <button className="small secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>‹ Anterior</button>
            <span style={{ fontSize: 13, color: "#6b7280" }}>
              {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filteredOrdens.length)} de {filteredOrdens.length}
            </span>
            <button className="small secondary" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>Próxima ›</button>
            <button className="small secondary" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
          </div>
        )}
      </div>
    </>
  );
}
