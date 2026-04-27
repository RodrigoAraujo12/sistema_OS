import React, { useState } from "react";
import apiClient from "../api.js";
import { situacaoLabels, modeloLabels, formatarData } from "../constants.js";

const LIMITE_POR_PAGINA = 20;
const SITUACOES = Object.entries(situacaoLabels); // [[0, "AGUARDANDO..."], ...]

const EMPTY_FILTERS = {
  numero: "",
  modelo: "",
  ie: "",
  cnpj: "",
  razao_social: "",
  matriculas: "",
  situacoes: [],
  data_abertura_inicio: "",
  data_abertura_fim: "",
  data_ciencia_inicio: "",
  data_ciencia_fim: "",
};

export default function OrdensPanel() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [ordens, setOrdens] = useState(null); // null = ainda nao pesquisou
  const [paginacao, setPaginacao] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");

  const [selectedOS, setSelectedOS] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  function handleFilterChange(e) {
    const { name, value } = e.target;
    setFilters(prev => ({ ...prev, [name]: value }));
  }

  function handleSituacaoToggle(codigo) {
    const cod = Number(codigo);
    setFilters(prev => {
      const already = prev.situacoes.includes(cod);
      return {
        ...prev,
        situacoes: already
          ? prev.situacoes.filter(s => s !== cod)
          : [...prev.situacoes, cod],
      };
    });
  }

  function validate() {
    const f = filters;

    const hasFilter =
      f.numero ||
      f.modelo ||
      f.ie ||
      f.cnpj ||
      (f.razao_social && f.razao_social.length >= 6) ||
      f.matriculas ||
      f.situacoes.length > 0 ||
      f.data_abertura_inicio ||
      f.data_abertura_fim ||
      f.data_ciencia_inicio ||
      f.data_ciencia_fim;

    if (!hasFilter) return "Informe ao menos um filtro para pesquisar.";
    if (f.razao_social && f.razao_social.length < 6)
      return "Razão Social: mínimo de 6 caracteres.";
    if (f.modelo && (!f.data_abertura_inicio || !f.data_abertura_fim))
      return "Ao informar o Modelo, o período de abertura (início e fim) é obrigatório.";

    return null;
  }

  async function fetchOrdens(page) {
    const error = validate();
    if (error) {
      setSearchError(error);
      return;
    }

    setLoading(true);
    setSearchError("");
    try {
      const data = await apiClient.listOrdens({
        numero: filters.numero || null,
        modelo: filters.modelo || null,
        ie: filters.ie || null,
        cnpj: filters.cnpj || null,
        razao_social: filters.razao_social || null,
        matriculas: filters.matriculas || null,
        situacoes: filters.situacoes.length > 0 ? filters.situacoes : null,
        data_abertura_inicio: filters.data_abertura_inicio || null,
        data_abertura_fim: filters.data_abertura_fim || null,
        data_ciencia_inicio: filters.data_ciencia_inicio || null,
        data_ciencia_fim: filters.data_ciencia_fim || null,
        pagina: page,
        limite: LIMITE_POR_PAGINA,
      });
      setOrdens(data.ordens ?? data);
      setPaginacao(data.paginacao ?? null);
      setCurrentPage(page);
    } catch (err) {
      setSearchError(err.message || "Erro ao buscar ordens");
      setOrdens([]);
      setPaginacao(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(e) {
    e.preventDefault();
    fetchOrdens(1);
  }

  function handlePageChange(newPage) {
    fetchOrdens(newPage);
  }

  function handleClear() {
    setFilters(EMPTY_FILTERS);
    setOrdens(null);
    setPaginacao(null);
    setCurrentPage(1);
    setSearchError("");
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

  function renderFiscais(fiscais) {
    if (!fiscais || fiscais.length === 0) return "-";
    return fiscais.map((f, i) => (
      <div key={i} style={{ fontSize: 12, lineHeight: 1.5 }}>
        {typeof f === "object"
          ? `${f.nome} (${f.matricula})${f.data_ciencia ? ` — ${formatarData(f.data_ciencia)}` : ""}`
          : f}
      </div>
    ));
  }

  function renderSituacao(os) {
    if (os.situacao) {
      return <span className="badge normal">{os.situacao.codigo} — {os.situacao.descricao}</span>;
    }
    return <span className="badge normal">{os.status || "-"}</span>;
  }

  const totalPages = paginacao?.total_paginas ?? (ordens ? 1 : 1);
  const totalRegistros = paginacao?.total_registros ?? (ordens?.length ?? 0);

  return (
    <>
      {/* Filtros */}
      <div className="card filters-card">
        <div className="filters-header">
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Filtros de Pesquisa</h3>
          <button className="small secondary" type="button" onClick={handleClear}>Limpar</button>
        </div>

        <form onSubmit={handleSearch}>
          {/* Linha 1: numero, modelo, ie, cnpj */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">N&uacute;mero OS</label>
              <input
                type="text"
                name="numero"
                value={filters.numero}
                onChange={handleFilterChange}
                placeholder="Ex: OS-2026-001"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">
                Modelo
                {filters.modelo && (!filters.data_abertura_inicio || !filters.data_abertura_fim) && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>*requer período de abertura</span>
                )}
              </label>
              <select name="modelo" value={filters.modelo} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {Object.entries(modeloLabels).map(([code, label]) => (
                  <option key={code} value={code}>{code} — {label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">IE</label>
              <input
                type="text"
                name="ie"
                value={filters.ie}
                onChange={handleFilterChange}
                placeholder="Inscri&ccedil;&atilde;o Estadual"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">CNPJ</label>
              <input
                type="text"
                name="cnpj"
                value={filters.cnpj}
                onChange={handleFilterChange}
                placeholder="CNPJ do contribuinte"
                className="filter-select"
              />
            </div>
          </div>

          {/* Linha 2: razao_social, matriculas */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">
                Raz&atilde;o Social
                {filters.razao_social.length > 0 && filters.razao_social.length < 6 && (
                  <span style={{ color: "#e53e3e", marginLeft: 8, fontSize: 11 }}>
                    m&iacute;n. 6 caracteres ({filters.razao_social.length}/6)
                  </span>
                )}
              </label>
              <input
                type="text"
                name="razao_social"
                value={filters.razao_social}
                onChange={handleFilterChange}
                placeholder="Parte do nome (m&iacute;n. 6 chars)"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">Matr&iacute;culas dos Fiscais</label>
              <input
                type="text"
                name="matriculas"
                value={filters.matriculas}
                onChange={handleFilterChange}
                placeholder="Ex: 123456, 789012"
                className="filter-select"
              />
            </div>
          </div>

          {/* Linha 3: datas */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">
                Abertura — In&iacute;cio
                {filters.modelo && !filters.data_abertura_inicio && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>*obrigat&oacute;rio</span>
                )}
              </label>
              <input type="date" name="data_abertura_inicio" value={filters.data_abertura_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">
                Abertura — Fim
                {filters.modelo && !filters.data_abertura_fim && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>*obrigat&oacute;rio</span>
                )}
              </label>
              <input type="date" name="data_abertura_fim" value={filters.data_abertura_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Ci&ecirc;ncia — In&iacute;cio</label>
              <input type="date" name="data_ciencia_inicio" value={filters.data_ciencia_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Ci&ecirc;ncia — Fim</label>
              <input type="date" name="data_ciencia_fim" value={filters.data_ciencia_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
          </div>

          {/* Situacoes: checkboxes */}
          <div style={{ marginBottom: 14 }}>
            <label className="filter-label" style={{ display: "block", marginBottom: 6 }}>Situa&ccedil;&atilde;o</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
              {SITUACOES.map(([cod, desc]) => (
                <label
                  key={cod}
                  style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, cursor: "pointer", userSelect: "none" }}
                >
                  <input
                    type="checkbox"
                    checked={filters.situacoes.includes(Number(cod))}
                    onChange={() => handleSituacaoToggle(cod)}
                  />
                  <span>{cod} — {desc}</span>
                </label>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              disabled={loading}
              style={{ background: "#1a3a6c", color: "#fff", border: "none", padding: "8px 24px", borderRadius: 6, fontWeight: 600, fontSize: 13, cursor: loading ? "not-allowed" : "pointer" }}
            >
              {loading ? "Pesquisando..." : "Pesquisar"}
            </button>
          </div>
        </form>

        {searchError && (
          <div className="alert error" style={{ marginTop: 10 }}>{searchError}</div>
        )}
      </div>

      {/* Resultado */}
      <div className="card">
        {ordens === null ? (
          <div className="empty-state">
            <p className="muted">Preencha os filtros acima e clique em <strong>Pesquisar</strong> para carregar as ordens.</p>
          </div>
        ) : (
          <>
            <h2>
              Ordens de Servi&ccedil;o ({totalRegistros} registros) &mdash; p&aacute;g. {currentPage}/{totalPages}
            </h2>
            <p className="muted" style={{ marginBottom: 12 }}>
              Dados do Informix. Somente consulta.
            </p>
            {ordens.length === 0 ? (
              <div className="empty-state">
                <p className="muted">Nenhuma ordem de servi&ccedil;o encontrada para os filtros informados.</p>
              </div>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>N&uacute;mero</th>
                      <th>Modelo</th>
                      <th>IE</th>
                      <th>CNPJ</th>
                      <th>Raz&atilde;o Social</th>
                      <th>Fiscais (matr&iacute;cula / ci&ecirc;ncia)</th>
                      <th>Situa&ccedil;&atilde;o</th>
                      <th>Abertura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ordens.map((os) => {
                      const numeroOS = os.numero_os || os.numero;
                      return (
                        <tr
                          key={numeroOS}
                          className="os-row-clickable"
                          onClick={() => handleOSClick(numeroOS)}
                          title="Clique para ver detalhes"
                        >
                          <td><strong>{numeroOS}</strong></td>
                          <td>{os.modelo || os.tipo || "-"}</td>
                          <td>{os.ie}</td>
                          <td>{os.cnpj || "-"}</td>
                          <td>{os.razao_social}</td>
                          <td>{renderFiscais(os.fiscais)}</td>
                          <td>{renderSituacao(os)}</td>
                          <td>{formatarData(os.data_abertura)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
                <button className="small secondary" onClick={() => handlePageChange(1)} disabled={currentPage === 1 || loading}>«</button>
                <button className="small secondary" onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1 || loading}>‹ Anterior</button>
                <span style={{ fontSize: 13, color: "#6b7280" }}>
                  P&aacute;gina {currentPage} de {totalPages} &mdash; {totalRegistros} registros
                </span>
                <button className="small secondary" onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages || loading}>Pr&oacute;xima ›</button>
                <button className="small secondary" onClick={() => handlePageChange(totalPages)} disabled={currentPage === totalPages || loading}>»</button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Loading overlay detalhes */}
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
                <h2 style={{ margin: 0, fontSize: 18 }}>{selectedOS.numero_os || selectedOS.numero}</h2>
                <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: 13 }}>
                  {selectedOS.razao_social}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {selectedOS.situacao
                  ? <span className="badge normal">{selectedOS.situacao.codigo} — {selectedOS.situacao.descricao}</span>
                  : <span className="badge normal">{selectedOS.status || "-"}</span>
                }
                <button className="small secondary" onClick={closeDetail} style={{ fontSize: 18, lineHeight: 1, padding: "4px 10px" }}>&times;</button>
              </div>
            </div>

            {/* Body */}
            <div className="os-detail-body">
              <div className="os-detail-section">
                <h3 className="os-detail-section-title">Informa&ccedil;&otilde;es da Ordem</h3>
                <div className="os-detail-grid">
                  <div className="os-detail-field">
                    <span className="os-detail-label">Modelo</span>
                    <span className="os-detail-value">{selectedOS.modelo || selectedOS.tipo || "-"}</span>
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
                    <span className="os-detail-label">Endere&ccedil;o</span>
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
                    <span className="os-detail-value">
                      {selectedOS.fiscais?.length > 0
                        ? selectedOS.fiscais.map((f, i) => (
                            <div key={i}>
                              {typeof f === "object"
                                ? `${f.nome} — Mat. ${f.matricula}${f.data_ciencia ? ` (ci&ecirc;ncia: ${formatarData(f.data_ciencia)})` : ""}`
                                : f}
                            </div>
                          ))
                        : "-"}
                    </span>
                  </div>
                </div>

                <div className="os-detail-dates">
                  <div className="os-detail-field">
                    <span className="os-detail-label">Abertura</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_abertura)}</span>
                  </div>
                </div>

                {selectedOS.objeto && (
                  <div style={{ marginTop: 16 }}>
                    <span className="os-detail-label">Objeto da Fiscaliza&ccedil;&atilde;o</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>{selectedOS.objeto}</p>
                  </div>
                )}
                {selectedOS.observacoes && (
                  <div style={{ marginTop: 12 }}>
                    <span className="os-detail-label">Observa&ccedil;&otilde;es</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>{selectedOS.observacoes}</p>
                  </div>
                )}
              </div>

              {/* Movimentacoes — exibidas apenas se o endpoint de detalhe retornar */}
              {selectedOS.movimentacoes && selectedOS.movimentacoes.length > 0 && (
                <div className="os-detail-section">
                  <h3 className="os-detail-section-title">
                    Movimenta&ccedil;&otilde;es ({selectedOS.movimentacoes.length})
                  </h3>
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
                          <span className="os-mov-resp">Respons&aacute;vel: {mov.responsavel}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="os-detail-footer">
              <button className="small secondary" onClick={closeDetail}>Fechar</button>
              <button
                className="small"
                style={{ background: "#1a3a6c", color: "#fff", border: "none" }}
                onClick={() => handleDownloadPdf(selectedOS.numero_os || selectedOS.numero)}
              >
                &#128196; Baixar PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
