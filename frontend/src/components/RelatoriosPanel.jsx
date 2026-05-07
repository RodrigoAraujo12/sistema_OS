/**
 * RelatoriosPanel.jsx – Gerador de relatorios sob demanda.
 *
 * Permite ao usuario configurar filtros e baixar relatorios
 * em formato CSV (Ordens de Servico e Dashboard).
 */

import React, { useState } from "react";
import apiClient from "../api.js";
import { situacaoLabels, modeloLabels } from "../constants.js";

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

  // Filtros OS
  const [situacaoFilter, setSituacaoFilter] = useState("");
  const [modeloFilter, setModeloFilter] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [search, setSearch] = useState("");

  // Filtros Dashboard
  const [dashDataInicio, setDashDataInicio] = useState("");
  const [dashDataFim, setDashDataFim] = useState("");

  async function handleDownloadOrdens() {
    setLoading(true);
    try {
      const blob = await apiClient.downloadRelatorioOrdens({
        situacao: situacaoFilter || undefined,
        modelo: modeloFilter || undefined,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        search: search || undefined,
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `relatorio_ordens_${today}.csv`);
      onMessage("Relatorio de Ordens de Servico gerado com sucesso!");
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

  async function handleDownloadOrdensPdf() {
    setLoading(true);
    try {
      const blob = await apiClient.downloadRelatorioOrdensPdf({
        situacao: situacaoFilter || undefined,
        modelo: modeloFilter || undefined,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        search: search || undefined,
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `relatorio_ordens_${today}.pdf`);
      onMessage("Relatorio PDF de Ordens de Servico gerado com sucesso!");
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
    setSituacaoFilter("");
    setModeloFilter("");
    setDataInicio("");
    setDataFim("");
    setSearch("");
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
          Exporta todas as OS visiveis com filtros aplicados. Inclui numero, tipo, IE, razao social,
          situacao e datas.
        </p>

        <div className="relatorio-filters">
          <div className="filter-row">
            <div className="filter-group">
              <label>Situa&ccedil;&atilde;o</label>
              <select value={situacaoFilter} onChange={(e) => setSituacaoFilter(e.target.value)}>
                <option value="">Todas</option>
                {Object.entries(situacaoLabels).map(([cod, desc]) => (
                  <option key={cod} value={cod}>{desc}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>Modelo</label>
              <select value={modeloFilter} onChange={(e) => setModeloFilter(e.target.value)}>
                <option value="">Todos</option>
                {Object.entries(modeloLabels).map(([cod, label]) => (
                  <option key={cod} value={cod}>{cod} — {label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>Data Inicio</label>
              <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
            </div>
            <div className="filter-group">
              <label>Data Fim</label>
              <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
            </div>
          </div>
          <div className="filter-row">
            <div className="filter-group filter-search">
              <label>Busca livre</label>
              <input
                type="text"
                placeholder="Numero, razao social, IE, matricula, fiscal..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="relatorio-actions">
          <button className="btn-secondary" onClick={handleLimparFiltrosOS} disabled={loading}>
            Limpar Filtros
          </button>
          <button className="btn-primary" onClick={handleDownloadOrdens} disabled={loading}>
            {loading ? "Gerando..." : "⬇ CSV"}
          </button>
          <button className="btn-primary" onClick={handleDownloadOrdensPdf} disabled={loading} style={{ background: "#dc2626" }}>
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
