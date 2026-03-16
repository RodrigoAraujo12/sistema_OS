/**
 * OrdensPanel.jsx – Painel de Ordens de Servico.
 *
 * Exibe OS com filtros (status, tipo, periodo, busca textual).
 * Gerencia seu proprio estado de filtros internamente.
 * Ao clicar em uma OS, exibe detalhes com movimentacoes.
 */

import React, { useMemo, useState } from "react";
import apiClient from "../api.js";
import { statusLabels, tipoLabels, formatarData } from "../constants.js";

const PAGE_SIZE = 10;

export default function OrdensPanel({ ordens }) {
  const [statusFilter, setStatusFilter] = useState("");
  const [tipoFilter, setTipoFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [page, setPage] = useState(1);

  // Detail modal state
  const [selectedOS, setSelectedOS] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

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

  async function handleOSClick(numero) {
    setLoadingDetail(true);
    setDetailError("");
    try {
      const detail = await apiClient.getOrdem(numero);
      setSelectedOS(detail);
    } catch (err) {
      setDetailError(err.message || "Erro ao carregar detalhes da OS");
    } finally {
      setLoadingDetail(false);
    }
  }

  function closeDetail() {
    setSelectedOS(null);
    setDetailError("");
  }

  async function handleDownloadPdf(numero) {
    try {
      const blob = await apiClient.downloadOrdemPdf(numero);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${numero}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDetailError(err.message || "Erro ao baixar PDF");
    }
  }

  function formatCurrency(value) {
    if (!value) return "R$ 0,00";
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
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
                  <tr key={os.numero} className="os-row-clickable" onClick={() => handleOSClick(os.numero)} title="Clique para ver detalhes">
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

      {/* Loading overlay */}
      {loadingDetail && (
        <div className="confirm-overlay">
          <div className="confirm-modal">
            <p>Carregando detalhes da OS...</p>
          </div>
        </div>
      )}

      {/* Error toast */}
      {detailError && !loadingDetail && (
        <div className="confirm-overlay" onClick={() => setDetailError("")}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-icon" data-variant="danger">!</div>
            <h3 className="confirm-title">Erro</h3>
            <p className="confirm-message">{detailError}</p>
            <div className="confirm-actions">
              <button className="small secondary" onClick={() => setDetailError("")}>Fechar</button>
            </div>
          </div>
        </div>
      )}

      {/* OS Detail Modal */}
      {selectedOS && (
        <div className="confirm-overlay" onClick={closeDetail}>
          <div className="os-detail-modal" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="os-detail-header">
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>{selectedOS.numero}</h2>
                <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: 13 }}>
                  {selectedOS.razao_social}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className={`badge ${selectedOS.status}`}>{statusLabels[selectedOS.status] || selectedOS.status}</span>
                <button className="small secondary" onClick={closeDetail} style={{ fontSize: 18, lineHeight: 1, padding: "4px 10px" }}>&times;</button>
              </div>
            </div>

            {/* Tabs: Info + Movimentacoes */}
            <div className="os-detail-body">
              {/* Informacoes da OS */}
              <div className="os-detail-section">
                <h3 className="os-detail-section-title">Informacoes da Ordem</h3>
                <div className="os-detail-grid">
                  <div className="os-detail-field">
                    <span className="os-detail-label">Tipo</span>
                    <span className="os-detail-value"><span className="badge normal">{selectedOS.tipo}</span></span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Prioridade</span>
                    <span className="os-detail-value">
                      <span className={`badge ${selectedOS.prioridade === "urgente" ? "cancelada" : selectedOS.prioridade === "alta" ? "urgente" : "normal"}`}>
                        {selectedOS.prioridade || "-"}
                      </span>
                    </span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">IE</span>
                    <span className="os-detail-value">{selectedOS.ie}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">CNPJ</span>
                    <span className="os-detail-value">{selectedOS.cnpj || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Endereco</span>
                    <span className="os-detail-value">{selectedOS.endereco || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Telefone</span>
                    <span className="os-detail-value">{selectedOS.telefone || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Valor Estimado</span>
                    <span className="os-detail-value">{formatCurrency(selectedOS.valor_estimado)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Supervisor</span>
                    <span className="os-detail-value">{selectedOS.matricula_supervisor || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Fiscais</span>
                    <span className="os-detail-value">{selectedOS.fiscais?.join(", ") || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Dias Parado</span>
                    <span className="os-detail-value">
                      {selectedOS.status !== "concluida" && selectedOS.status !== "cancelada" ? (
                        <span className={`badge ${selectedOS.dias_parado > 15 ? "cancelada" : selectedOS.dias_parado > 7 ? "urgente" : "normal"}`}>
                          {selectedOS.dias_parado} dias
                        </span>
                      ) : "-"}
                    </span>
                  </div>
                </div>

                {/* Datas */}
                <div className="os-detail-dates">
                  <div className="os-detail-field">
                    <span className="os-detail-label">Abertura</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_abertura)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Ciencia</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_ciencia)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Ult. Movimentacao</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_ultima_movimentacao)}</span>
                  </div>
                </div>

                {/* Objeto */}
                {selectedOS.objeto && (
                  <div style={{ marginTop: 16 }}>
                    <span className="os-detail-label">Objeto da Fiscalizacao</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>{selectedOS.objeto}</p>
                  </div>
                )}

                {/* Observacoes */}
                {selectedOS.observacoes && (
                  <div style={{ marginTop: 12 }}>
                    <span className="os-detail-label">Observacoes</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>{selectedOS.observacoes}</p>
                  </div>
                )}
              </div>

              {/* Movimentacoes */}
              <div className="os-detail-section">
                <h3 className="os-detail-section-title">
                  Movimentacoes ({selectedOS.movimentacoes?.length || 0})
                </h3>
                {selectedOS.movimentacoes && selectedOS.movimentacoes.length > 0 ? (
                  <div className="os-movimentacoes-timeline">
                    {selectedOS.movimentacoes.map((mov, idx) => (
                      <div key={idx} className="os-mov-item">
                        <div className="os-mov-dot" />
                        <div className="os-mov-content">
                          <div className="os-mov-header">
                            <span className="badge normal" style={{ fontSize: 11 }}>{mov.tipo}</span>
                            <span className="os-mov-date">{formatarData(mov.data)}</span>
                          </div>
                          <p className="os-mov-desc">{mov.descricao}</p>
                          <span className="os-mov-resp">Responsavel: {mov.responsavel}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted" style={{ fontSize: 13 }}>Nenhuma movimentacao registrada.</p>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="os-detail-footer">
              <button className="small secondary" onClick={closeDetail}>Fechar</button>
              <button className="small" style={{ background: "#1a3a6c", color: "#fff", border: "none" }} onClick={() => handleDownloadPdf(selectedOS.numero)}>
                &#128196; Baixar PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
