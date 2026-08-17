import React, { useState } from "react";
import apiClient from "../api.js";
import { situacaoLabels, modeloLabels, motivoLabels, orgaoExecutorOptions, formatarData } from "../constants.js";
import { EMPTY_OS_FILTERS, validarFiltrosOS, filtrosParaPayload } from "../atfFilters.js";

const LIMITE_POR_PAGINA = 20;
const SITUACOES = Object.entries(situacaoLabels); // [[0, "AGUARDANDO..."], ...]
const MOTIVOS = Object.entries(motivoLabels);

const EMPTY_FILTERS = EMPTY_OS_FILTERS;

// Colunas da listagem. A chave e o nome que o backend aceita em
// ordenar_por (_ORDENACAO_ATF); o tipo define o alinhamento e a direcao
// inicial do clique — texto comeca em A-Z, data e numero comecam do maior
// para o menor, que e o que interessa ver primeiro (mais recente, mais
// dias parado).
const COLUNAS = [
  { key: "numero_os", label: "Número", tipo: "texto" },
  { key: "razao_social", label: "Razão Social", tipo: "texto" },
  { key: "modelo", label: "Modelo", tipo: "texto" },
  { key: "motivo_abertura", label: "Motivo", tipo: "texto" },
  { key: "procedimento", label: "Procedimento", tipo: "texto" },
  { key: "situacao", label: "Situação", tipo: "texto" },
  { key: "data_abertura", label: "Abertura", tipo: "data" },
  { key: "dias_execucao", label: "Dias Exec.", tipo: "numero" },
  { key: "data_ultimo_evento", label: "Último Evento", tipo: "data" },
  { key: "dias_sem_evento", label: "Dias s/ Evento", tipo: "numero" },
];

const IconeCopiar = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

const IconeCheck = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

export default function OrdensPanel() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [ordens, setOrdens] = useState(null); // null = ainda nao pesquisou
  const [paginacao, setPaginacao] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [ordenacao, setOrdenacao] = useState({ campo: null, dir: "asc" });
  const [copiedOS, setCopiedOS] = useState(null);

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

  // A ordenacao vai por parametro (e nao lida do state) porque handleSort
  // precisa buscar ja com o criterio novo — o setState so vale no proximo
  // render.
  async function fetchOrdens(page, ord = ordenacao) {
    const error = validarFiltrosOS(filters);
    if (error) {
      setSearchError(error);
      return;
    }

    setLoading(true);
    setSearchError("");
    try {
      const data = await apiClient.listOrdens({
        ...filtrosParaPayload(filters),
        pagina: page,
        limite: LIMITE_POR_PAGINA,
        ordenar_por: ord.campo,
        ordem: ord.dir,
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

  /**
   * Clique no cabecalho: primeira vez ordena pela direcao natural do tipo,
   * cliques seguintes invertem. Volta sempre para a pagina 1 — manter a
   * pagina atual mostraria um recorte do meio de uma lista que acabou de
   * mudar de ordem.
   */
  function handleSort(coluna) {
    const nova = ordenacao.campo === coluna.key
      ? { campo: coluna.key, dir: ordenacao.dir === "asc" ? "desc" : "asc" }
      : { campo: coluna.key, dir: coluna.tipo === "texto" ? "asc" : "desc" };
    setOrdenacao(nova);
    fetchOrdens(1, nova);
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

  /**
   * Copia o numero da OS. O stopPropagation e essencial: a linha inteira e
   * clicavel e abre o modal de detalhes — copiar nao pode disparar isso.
   * navigator.clipboard so existe em contexto seguro (https ou localhost);
   * em intranet http o fallback do textarea + execCommand ainda funciona.
   */
  async function handleCopyNumero(e, numero) {
    e.stopPropagation();
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(numero);
      } else {
        const ta = document.createElement("textarea");
        ta.value = numero;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setCopiedOS(numero);
      setTimeout(() => setCopiedOS(atual => (atual === numero ? null : atual)), 1500);
    } catch {
      // Sem clipboard disponivel: o numero continua selecionavel na tela.
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
      a.download = `${numero.replace(/\//g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDetailError(err.message || "Erro ao baixar PDF");
    }
  }

  function renderSituacao(os) {
    if (os.situacao) {
      return <span className="badge normal">{os.situacao.codigo} — {os.situacao.descricao}</span>;
    }
    return <span className="badge normal">{os.status || "-"}</span>;
  }

  /**
   * Formata "codigo — texto" no mesmo padrao usado pela situacao.
   * O ATF manda os dois separados; quando um dos lados falta, mostra o
   * que existir em vez de deixar um travessao solto.
   */
  function comCodigo(codigo, texto) {
    const temCodigo = codigo !== null && codigo !== undefined && codigo !== "";
    if (temCodigo && texto) return `${codigo} — ${texto}`;
    if (temCodigo) return String(codigo);
    return texto || "-";
  }

  /**
   * Dias corridos entre a data (YYYY-MM-DD) e hoje.
   * Retorna null quando nao ha data: o ATF so manda dataUltimoEventoOS
   * quando existe ao menos um evento lancado na OS — a maioria das OS em
   * aberto nao tem nenhum, e ai nao ha o que contar.
   */
  function diasDesde(dataISO) {
    if (!dataISO) return null;
    const d = new Date(`${dataISO}T00:00:00`);
    if (Number.isNaN(d.getTime())) return null;
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    return Math.floor((hoje - d) / 86400000);
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
                {filters.modelo &&
                  !((filters.data_abertura_inicio && filters.data_abertura_fim) ||
                    (filters.data_encerramento_inicio && filters.data_encerramento_fim)) && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>*requer per&iacute;odo de abertura ou encerramento</span>
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

          {/* Linha 2: motivo abertura, equipe fiscal, orgao executor */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group" style={{ gridColumn: "span 2" }}>
              <label className="filter-label">Motivo de Abertura</label>
              <select name="motivo_abertura" value={filters.motivo_abertura} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {MOTIVOS.map(([code, label]) => (
                  <option key={code} value={code}>{code} — {label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">Equipe Fiscal (c&oacute;digo)</label>
              <input
                type="text"
                name="equipe_fiscal"
                value={filters.equipe_fiscal}
                onChange={handleFilterChange}
                placeholder="Ex: 12"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">&Oacute;rg&atilde;o Executor</label>
              <select name="orgao_executor" value={filters.orgao_executor} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {orgaoExecutorOptions.map(({ codigo, sigla }) => (
                  <option key={codigo} value={codigo}>{sigla} ({codigo})</option>
                ))}
              </select>
            </div>
          </div>

          {/* Linha 3: razao_social, matriculas */}
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

          {/* Linha 4: periodos de abertura e encerramento */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">Abertura — In&iacute;cio</label>
              <input type="date" name="data_abertura_inicio" value={filters.data_abertura_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Abertura — Fim</label>
              <input type="date" name="data_abertura_fim" value={filters.data_abertura_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Encerramento — In&iacute;cio</label>
              <input type="date" name="data_encerramento_inicio" value={filters.data_encerramento_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Encerramento — Fim</label>
              <input type="date" name="data_encerramento_fim" value={filters.data_encerramento_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
          </div>

          {/* Linha 5: periodo de ciencia */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
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
                  <span>{desc}</span>
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
              Dados do ATF. Somente consulta.
            </p>
            {ordens.length === 0 ? (
              <div className="empty-state">
                <p className="muted">Nenhuma ordem de servi&ccedil;o encontrada para os filtros informados.</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="tabela-ordens">
                  <thead>
                    <tr>
                      {COLUNAS.map((c) => {
                        const ativa = ordenacao.campo === c.key;
                        return (
                          <th
                            key={c.key}
                            className={`th-sortable${ativa ? " th-sorted" : ""}`}
                            style={c.tipo === "numero" ? { textAlign: "center" } : undefined}
                            title={`Ordenar por ${c.label}`}
                            onClick={() => handleSort(c)}
                          >
                            {c.label}
                            <span className="sort-arrow">
                              {ativa ? (ordenacao.dir === "asc" ? "▲" : "▼") : "↕"}
                            </span>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {ordens.map((os) => {
                      const numeroOS = os.numero_os || os.numero;
                      const diasSemEvento = diasDesde(os.data_ultimo_evento);
                      return (
                        <tr
                          key={numeroOS}
                          className="os-row-clickable"
                          onClick={() => handleOSClick(numeroOS)}
                          title="Clique para ver detalhes"
                        >
                          <td>
                            <span className="os-numero-cell">
                              <strong>{numeroOS}</strong>
                              <button
                                type="button"
                                className="btn-copiar-os"
                                title={copiedOS === numeroOS ? "Copiado!" : "Copiar número da OS"}
                                aria-label={`Copiar número da OS ${numeroOS}`}
                                onClick={(e) => handleCopyNumero(e, numeroOS)}
                              >
                                {copiedOS === numeroOS ? <IconeCheck /> : <IconeCopiar />}
                              </button>
                            </span>
                          </td>
                          <td>{os.razao_social || "-"}</td>
                          <td>{os.modelo || "-"}</td>
                          <td>{os.motivo_abertura || "-"}</td>
                          <td>{os.procedimento || "-"}</td>
                          <td>{renderSituacao(os)}</td>
                          <td>{formatarData(os.data_abertura)}</td>
                          <td style={{ textAlign: "center" }}>{os.dias_execucao ?? "-"}</td>
                          <td>{formatarData(os.data_ultimo_evento)}</td>
                          <td style={{ textAlign: "center" }}>{diasSemEvento ?? "-"}</td>
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
                    <span className="os-detail-value">
                      {comCodigo(selectedOS.modelo_codigo, selectedOS.modelo)}
                    </span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Motivo de Abertura</span>
                    <span className="os-detail-value">
                      {comCodigo(selectedOS.motivo_abertura_codigo, selectedOS.motivo_abertura)}
                    </span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Procedimento</span>
                    <span className="os-detail-value">{selectedOS.procedimento || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">IE</span>
                    <span className="os-detail-value">{selectedOS.ie || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">CNPJ / CPF</span>
                    <span className="os-detail-value">{selectedOS.cnpj || "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">&Oacute;rg&atilde;o Executor</span>
                    {/* Codigo + sigla + nome: o nome sozinho passa de 150
                        chars, a sigla da o reconhecimento imediato. */}
                    <span className="os-detail-value">
                      {comCodigo(
                        selectedOS.orgao_executor_codigo,
                        [selectedOS.orgao_executor_sigla, selectedOS.orgao_executor]
                          .filter(Boolean).join(" — "),
                      )}
                    </span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Equipe Fiscal</span>
                    <span className="os-detail-value">
                      {comCodigo(selectedOS.equipe_fiscal_codigo, selectedOS.equipe_fiscal)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="os-detail-section">
                <h3 className="os-detail-section-title">Datas e Execu&ccedil;&atilde;o</h3>
                <div className="os-detail-grid">
                  <div className="os-detail-field">
                    <span className="os-detail-label">Abertura</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_abertura)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">In&iacute;cio da Fiscaliza&ccedil;&atilde;o</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_inicio_fiscalizacao)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Encerramento</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_encerramento)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">&Uacute;ltimo Evento</span>
                    <span className="os-detail-value">{formatarData(selectedOS.data_ultimo_evento)}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Dias de Execu&ccedil;&atilde;o</span>
                    <span className="os-detail-value">{selectedOS.dias_execucao ?? "-"}</span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">Tempo M&eacute;dio (Modelo/Motivo)</span>
                    <span className="os-detail-value">
                      {selectedOS.tempo_medio_execucao_modelo_motivo != null
                        ? `${selectedOS.tempo_medio_execucao_modelo_motivo} dias`
                        : "-"}
                    </span>
                  </div>
                  <div className="os-detail-field">
                    <span className="os-detail-label">M&eacute;dia de Eventos (Modelo/Motivo)</span>
                    <span className="os-detail-value">
                      {selectedOS.qtd_media_eventos_modelo_motivo ?? "-"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="os-detail-section">
                <h3 className="os-detail-section-title">
                  Fiscais ({selectedOS.fiscais?.length ?? 0})
                </h3>
                {selectedOS.fiscais?.length > 0 ? (
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Matr&iacute;cula</th>
                          <th>Nome</th>
                          <th>Status</th>
                          <th>Designa&ccedil;&atilde;o</th>
                          <th>Ci&ecirc;ncia</th>
                          <th>Cancelamento</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.fiscais.map((f, i) => (
                          <tr key={i}>
                            <td>{f.matricula}</td>
                            <td>{f.nome}</td>
                            <td>{f.status || "-"}</td>
                            <td>{formatarData(f.data_designacao)}</td>
                            <td>{formatarData(f.data_ciencia)}</td>
                            <td>{formatarData(f.data_cancelamento)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                    Nenhum fiscal designado.
                  </p>
                )}
              </div>
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
