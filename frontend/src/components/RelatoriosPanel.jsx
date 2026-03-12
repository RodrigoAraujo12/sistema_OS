/**
 * RelatoriosPanel.jsx – Gerador de relatorios sob demanda.
 *
 * Permite ao usuario configurar filtros e baixar relatorios
 * em formato CSV (Ordens de Servico e Dashboard).
 */

import React, { useState } from "react";
import apiClient from "../api.js";
import { statusLabels, tipoLabels } from "../constants.js";

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
  const [statusFilter, setStatusFilter] = useState("");
  const [tipoFilter, setTipoFilter] = useState("");
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
        status: statusFilter || undefined,
        tipo: tipoFilter || undefined,
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

  function handleLimparFiltrosOS() {
    setStatusFilter("");
    setTipoFilter("");
    setDataInicio("");
    setDataFim("");
    setSearch("");
  }

  return (
    <div className="relatorios-panel">
      <h2 className="section-title">Gerador de Relatorios</h2>
      <p className="section-subtitle">
        Selecione o tipo de relatorio, configure os filtros e clique em gerar para baixar o arquivo CSV.
      </p>

      {/* ─── Relatorio de OS ─── */}
      <div className="relatorio-card">
        <div className="relatorio-card-header">
          <h3>📋 Relatorio de Ordens de Servico</h3>
          <span className="relatorio-badge">CSV</span>
        </div>
        <p className="relatorio-desc">
          Exporta todas as OS visiveis com filtros aplicados. Inclui numero, tipo, IE, razao social,
          status, datas e dias parado.
        </p>

        <div className="relatorio-filters">
          <div className="filter-row">
            <div className="filter-group">
              <label>Status</label>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">Todos</option>
                {Object.entries(statusLabels).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>Tipo</label>
              <select value={tipoFilter} onChange={(e) => setTipoFilter(e.target.value)}>
                <option value="">Todos</option>
                {Object.entries(tipoLabels).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
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
            {loading ? "Gerando..." : "⬇ Gerar Relatorio de OS"}
          </button>
        </div>
      </div>

      {/* ─── Relatorio de Dashboard (admin only) ─── */}
      {authData.role === "admin" && (
        <div className="relatorio-card">
          <div className="relatorio-card-header">
            <h3>📊 Relatorio de Desempenho (Dashboard)</h3>
            <span className="relatorio-badge">CSV</span>
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
              {loading ? "Gerando..." : "⬇ Gerar Relatorio de Desempenho"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
