/**
 * RelatoriosPanel.jsx – Gerador de relatorios sob demanda.
 *
 * Permite ao usuario configurar filtros e baixar relatorios
 * em formato CSV (Ordens de Servico e Dashboard).
 */

import React, { useState } from "react";
import apiClient from "../api.js";
import { situacaoLabels, modeloLabels, motivoLabels, orgaoExecutorOptions } from "../constants.js";
import { EMPTY_OS_FILTERS, validarFiltrosOS } from "../atfFilters.js";

const SITUACOES = Object.entries(situacaoLabels);
const MOTIVOS = Object.entries(motivoLabels);

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function RelatoriosPanel({ authData, onError, onMessage }) {
  const [loading, setLoading] = useState(false);

  // Filtros OS – mesmos do painel de Ordens de Servico + busca livre
  const [filters, setFilters] = useState({ ...EMPTY_OS_FILTERS, search: "" });
  const [filtroError, setFiltroError] = useState("");

  // Filtros Dashboard
  const [dashDataInicio, setDashDataInicio] = useState("");
  const [dashDataFim, setDashDataFim] = useState("");

  function handleFilterChange(e) {
    const { name, value } = e.target;
    setFilters(prev => ({ ...prev, [name]: value }));
  }

  function handleSituacaoToggle(codigo) {
    const cod = Number(codigo);
    setFilters(prev => ({
      ...prev,
      situacoes: prev.situacoes.includes(cod)
        ? prev.situacoes.filter(s => s !== cod)
        : [...prev.situacoes, cod],
    }));
  }

  /** Valida e baixa o relatorio de OS no formato pedido ("csv" ou "pdf"). */
  async function baixarRelatorioOrdens(formato) {
    const erro = validarFiltrosOS(filters);
    if (erro) {
      setFiltroError(erro);
      return;
    }
    setFiltroError("");
    setLoading(true);
    try {
      const blob = formato === "pdf"
        ? await apiClient.downloadRelatorioOrdensPdf(filters)
        : await apiClient.downloadRelatorioOrdens(filters);
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `relatorio_ordens_${today}.${formato}`);
      onMessage(`Relatorio de Ordens de Servico (${formato.toUpperCase()}) gerado com sucesso!`);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadDashboard() {
    setLoading(true);
    try {
      const blob = await apiClient.downloadRelatorioDashboard({
        dataInicio: dashDataInicio || undefined,
        dataFim: dashDataFim || undefined,
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `relatorio_dashboard_${today}.csv`);
      onMessage("Relatorio de Dashboard gerado com sucesso!");
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadDashboardPdf() {
    setLoading(true);
    try {
      const blob = await apiClient.downloadRelatorioDashboardPdf({
        dataInicio: dashDataInicio || undefined,
        dataFim: dashDataFim || undefined,
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `relatorio_dashboard_${today}.pdf`);
      onMessage("Relatorio PDF de Desempenho gerado com sucesso!");
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleLimparFiltrosOS() {
    setFilters({ ...EMPTY_OS_FILTERS, search: "" });
    setFiltroError("");
  }

  return (
    <div className="relatorios-panel">
      <h2 className="section-title">Gerador de Relatorios</h2>
      <p className="section-subtitle">
        Selecione o tipo de relatorio, configure os filtros e clique em gerar para baixar o arquivo CSV ou PDF.
      </p>

      {/* ─── Relatorio de OS ─── */}
      <div className="relatorio-card">
        <div className="relatorio-card-header">
          <h3>📋 Relatorio de Ordens de Servico</h3>
          <div style={{ display: "flex", gap: "6px" }}>
            <span className="relatorio-badge">CSV</span>
            <span className="relatorio-badge" style={{ background: "#dc2626" }}>PDF</span>
          </div>
        </div>
        <p className="relatorio-desc">
          Exporta as OS do ATF com os mesmos filtros do painel de Ordens de Servico.
          Inclui modelo, motivo, contribuinte, orgao, equipe, fiscais, datas e os
          campos calculados (dias de execucao e medias por Modelo/Motivo).
        </p>
        <p className="relatorio-desc" style={{ fontSize: 12 }}>
          <strong>Regras do ATF:</strong> informe ao menos um filtro. Modelo, Motivo,
          Situa&ccedil;&atilde;o, Equipe e &Oacute;rg&atilde;o exigem um per&iacute;odo preenchido
          (abertura ou encerramento). Busca apenas por per&iacute;odo &eacute; limitada a um ano.
        </p>

        <div className="relatorio-filters">
          <div className="filter-row">
            <div className="filter-group">
              <label>N&uacute;mero OS</label>
              <input type="text" name="numero" value={filters.numero}
                onChange={handleFilterChange} placeholder="Ex: 93300008.12.00000001/2026-99" />
            </div>
            <div className="filter-group">
              <label>Modelo</label>
              <select name="modelo" value={filters.modelo} onChange={handleFilterChange}>
                <option value="">Todos</option>
                {Object.entries(modeloLabels).map(([cod, label]) => (
                  <option key={cod} value={cod}>{cod} — {label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>IE</label>
              <input type="text" name="ie" value={filters.ie}
                onChange={handleFilterChange} placeholder="Inscricao Estadual" />
            </div>
            <div className="filter-group">
              <label>CNPJ / CPF</label>
              <input type="text" name="cnpj" value={filters.cnpj}
                onChange={handleFilterChange} placeholder="Documento do contribuinte" />
            </div>
          </div>

          <div className="filter-row">
            <div className="filter-group" style={{ flex: 2 }}>
              <label>Motivo de Abertura</label>
              <select name="motivo_abertura" value={filters.motivo_abertura} onChange={handleFilterChange}>
                <option value="">Todos</option>
                {MOTIVOS.map(([cod, label]) => (
                  <option key={cod} value={cod}>{cod} — {label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>
                Raz&atilde;o Social
                {filters.razao_social.length > 0 && filters.razao_social.length < 6 && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>
                    m&iacute;n. 6 ({filters.razao_social.length}/6)
                  </span>
                )}
              </label>
              <input type="text" name="razao_social" value={filters.razao_social}
                onChange={handleFilterChange} placeholder="Parte do nome (min. 6)" />
            </div>
          </div>

          <div className="filter-row">
            <div className="filter-group">
              <label>Matr&iacute;culas dos Fiscais</label>
              <input type="text" name="matriculas" value={filters.matriculas}
                onChange={handleFilterChange} placeholder="Ex: 1459376" />
            </div>
            <div className="filter-group">
              <label>Equipe Fiscal (c&oacute;digo)</label>
              <input type="text" name="equipe_fiscal" value={filters.equipe_fiscal}
                onChange={handleFilterChange} placeholder="Ex: 12" />
            </div>
            <div className="filter-group">
              <label>&Oacute;rg&atilde;o Executor</label>
              <select name="orgao_executor" value={filters.orgao_executor} onChange={handleFilterChange}>
                <option value="">Todos</option>
                {orgaoExecutorOptions.map(({ codigo, sigla }) => (
                  <option key={codigo} value={codigo}>{sigla} ({codigo})</option>
                ))}
              </select>
            </div>
          </div>

          <div className="filter-row">
            <div className="filter-group">
              <label>Abertura &mdash; In&iacute;cio</label>
              <input type="date" name="data_abertura_inicio" value={filters.data_abertura_inicio} onChange={handleFilterChange} />
            </div>
            <div className="filter-group">
              <label>Abertura &mdash; Fim</label>
              <input type="date" name="data_abertura_fim" value={filters.data_abertura_fim} onChange={handleFilterChange} />
            </div>
            <div className="filter-group">
              <label>Encerramento &mdash; In&iacute;cio</label>
              <input type="date" name="data_encerramento_inicio" value={filters.data_encerramento_inicio} onChange={handleFilterChange} />
            </div>
            <div className="filter-group">
              <label>Encerramento &mdash; Fim</label>
              <input type="date" name="data_encerramento_fim" value={filters.data_encerramento_fim} onChange={handleFilterChange} />
            </div>
          </div>

          <div className="filter-row">
            <div className="filter-group">
              <label>Ci&ecirc;ncia &mdash; In&iacute;cio</label>
              <input type="date" name="data_ciencia_inicio" value={filters.data_ciencia_inicio} onChange={handleFilterChange} />
            </div>
            <div className="filter-group">
              <label>Ci&ecirc;ncia &mdash; Fim</label>
              <input type="date" name="data_ciencia_fim" value={filters.data_ciencia_fim} onChange={handleFilterChange} />
            </div>
            <div className="filter-group filter-search" style={{ flex: 2 }}>
              <label>Busca livre (refina o resultado)</label>
              <input type="text" name="search" value={filters.search}
                onChange={handleFilterChange}
                placeholder="Numero, razao social, IE, motivo, matricula, fiscal..." />
            </div>
          </div>

          <div style={{ marginTop: 4 }}>
            <label style={{ display: "block", marginBottom: 6, fontSize: 12, fontWeight: 600 }}>
              Situa&ccedil;&atilde;o
            </label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
              {SITUACOES.map(([cod, desc]) => (
                <label key={cod} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, cursor: "pointer", userSelect: "none" }}>
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
        </div>

        {filtroError && (
          <div className="alert error" style={{ marginTop: 10 }}>{filtroError}</div>
        )}

        <div className="relatorio-actions">
          <button className="btn-secondary" onClick={handleLimparFiltrosOS} disabled={loading}>
            Limpar Filtros
          </button>
          <button className="btn-primary" onClick={() => baixarRelatorioOrdens("csv")} disabled={loading}>
            {loading ? "Gerando..." : "⬇ CSV"}
          </button>
          <button className="btn-primary" onClick={() => baixarRelatorioOrdens("pdf")} disabled={loading} style={{ background: "#dc2626" }}>
            {loading ? "Gerando..." : "⬇ PDF"}
          </button>
        </div>
      </div>

      {/* ─── Relatorio de Dashboard (admin only) ─── */}
      {authData.role === "admin" && (
        <div className="relatorio-card">
          <div className="relatorio-card-header">
            <h3>📊 Relatorio de Desempenho (Dashboard)</h3>
            <div style={{ display: "flex", gap: "6px" }}>
              <span className="relatorio-badge">CSV</span>
              <span className="relatorio-badge" style={{ background: "#dc2626" }}>PDF</span>
            </div>
          </div>
          <p className="relatorio-desc">
            Exporta o resumo geral, desempenho por gerencia, supervisao e carga por fiscal.
            Ideal para reunioes e acompanhamento gerencial.
          </p>

          <div className="relatorio-filters">
            <div className="filter-row">
              <div className="filter-group">
                <label>Data Inicio</label>
                <input type="date" value={dashDataInicio} onChange={(e) => setDashDataInicio(e.target.value)} />
              </div>
              <div className="filter-group">
                <label>Data Fim</label>
                <input type="date" value={dashDataFim} onChange={(e) => setDashDataFim(e.target.value)} />
              </div>
            </div>
          </div>

          <div className="relatorio-actions">
            <button
              className="btn-secondary"
              onClick={() => { setDashDataInicio(""); setDashDataFim(""); }}
              disabled={loading}
            >
              Limpar Filtros
            </button>
            <button className="btn-primary" onClick={handleDownloadDashboard} disabled={loading}>
              {loading ? "Gerando..." : "⬇ CSV"}
            </button>
            <button className="btn-primary" onClick={handleDownloadDashboardPdf} disabled={loading} style={{ background: "#dc2626" }}>
              {loading ? "Gerando..." : "⬇ PDF"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
