/**
 * DashboardPanel.jsx – Painel principal do Dashboard (admin).
 *
 * Gerencia filtros (gerencia, supervisao, periodo), KPIs computados
 * e roteia para as abas: Geral, Gerencias, Supervisoes, Fiscais.
 */

import React, { useMemo, useState } from "react";
import apiClient from "../api.js";
import DashboardGeral from "./DashboardGeral.jsx";
import DashboardGerencias from "./DashboardGerencias.jsx";
import DashboardSupervisoes from "./DashboardSupervisoes.jsx";
import DashboardFiscais from "./DashboardFiscais.jsx";

const PERIODO_OPTIONS = [
  { value: "todos", label: "Todos" },
  { value: "7", label: "7 dias" },
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "180", label: "6 meses" },
  { value: "365", label: "1 ano" },
  { value: "custom", label: "Personalizado" },
];

export default function DashboardPanel({ dashboardData, onDashboardDataChange, onError }) {
  // ─── Filtros ────────────────────────────────────────
  const [gerenciaFilter, setGerenciaFilter] = useState("");
  const [supervisaoFilter, setSupervisaoFilter] = useState("");
  const [view, setView] = useState("geral");

  // ─── Periodo ────────────────────────────────────────
  const [periodo, setPeriodo] = useState("todos");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [loading, setLoading] = useState(false);

  // ─── Dados filtrados (computados) ───────────────────
  const supervisoesPorGerencia = useMemo(() => {
    if (!gerenciaFilter) return dashboardData.desempenho_supervisoes;
    return dashboardData.desempenho_supervisoes.filter(
      (s) => String(s.gerencia_id) === String(gerenciaFilter)
    );
  }, [dashboardData, gerenciaFilter]);

  const gerenciasFiltradas = useMemo(() => {
    if (!gerenciaFilter) return dashboardData.desempenho_gerencias;
    return dashboardData.desempenho_gerencias.filter(
      (g) => String(g.id) === String(gerenciaFilter)
    );
  }, [dashboardData, gerenciaFilter]);

  const supervisoesFiltradas = useMemo(() => {
    let sups = supervisoesPorGerencia;
    if (supervisaoFilter) {
      sups = sups.filter((s) => String(s.id) === String(supervisaoFilter));
    }
    return sups;
  }, [supervisoesPorGerencia, supervisaoFilter]);

  const fiscaisFiltrados = useMemo(() => {
    let fiscais = dashboardData.carga_fiscais;
    if (gerenciaFilter) {
      const supIds = supervisoesPorGerencia.map((s) => String(s.id));
      fiscais = fiscais.filter((f) => supIds.includes(String(f.supervisao_id)));
    }
    if (supervisaoFilter) {
      fiscais = fiscais.filter((f) => String(f.supervisao_id) === String(supervisaoFilter));
    }
    return fiscais;
  }, [dashboardData, gerenciaFilter, supervisaoFilter, supervisoesPorGerencia]);

  // ─── KPIs recalculados ──────────────────────────────
  const kpis = useMemo(() => {
    if (!gerenciaFilter && !supervisaoFilter) return dashboardData.visao_geral;
    const gList = gerenciasFiltradas;
    const sList = supervisoesFiltradas;
    const fList = fiscaisFiltrados;
    const totalOS = gList.reduce((s, g) => s + g.total_os, 0);
    const abertas = gList.reduce((s, g) => s + g.abertas, 0);
    const emAndamento = gList.reduce((s, g) => s + g.em_andamento, 0);
    const concluidas = gList.reduce((s, g) => s + g.concluidas, 0);
    const osCriticas = gList.reduce((s, g) => s + g.os_criticas, 0);
    const diasParadoArr = gList.filter((g) => g.total_os > 0).map((g) => g.dias_parado_medio);
    const diasParadoMedio = diasParadoArr.length > 0
      ? Math.round(diasParadoArr.reduce((a, b) => a + b, 0) / diasParadoArr.length) : 0;
    const tmcArr = gList.filter((g) => g.concluidas > 0).map((g) => g.tempo_medio_conclusao);
    const tempoMedioConclusao = tmcArr.length > 0
      ? Math.round(tmcArr.reduce((a, b) => a + b, 0) / tmcArr.length) : 0;
    const osSemCiencia = Math.round(
      dashboardData.visao_geral.os_sem_ciencia * (totalOS / (dashboardData.visao_geral.total_os || 1))
    );
    return {
      total_os: totalOS,
      os_abertas: abertas,
      os_em_andamento: emAndamento,
      os_concluidas: concluidas,
      os_criticas: osCriticas,
      dias_parado_medio: diasParadoMedio,
      tempo_medio_conclusao: tempoMedioConclusao,
      os_sem_ciencia: osSemCiencia,
      total_fiscais: fList.length,
      total_supervisores: sList.length,
    };
  }, [dashboardData, gerenciaFilter, supervisaoFilter, gerenciasFiltradas, supervisoesFiltradas, fiscaisFiltrados]);

  // ─── Handlers de periodo ────────────────────────────
  async function handlePeriodoChange(novoPeriodo) {
    setPeriodo(novoPeriodo);
    if (novoPeriodo === "custom") return;
    setLoading(true);
    let di = "", df = "";
    if (novoPeriodo !== "todos") {
      const hoje = new Date();
      const inicio = new Date(hoje);
      inicio.setDate(hoje.getDate() - parseInt(novoPeriodo, 10));
      di = inicio.toISOString().slice(0, 10);
      df = hoje.toISOString().slice(0, 10);
    }
    setDataInicio(di);
    setDataFim(df);
    try {
      const dashData = await apiClient.getDashboard({ dataInicio: di || undefined, dataFim: df || undefined });
      onDashboardDataChange(dashData);
    } catch (err) {
      onError(err.message);
    }
    setLoading(false);
  }

  async function handleCustomPeriodoApply() {
    if (!dataInicio && !dataFim) return;
    setLoading(true);
    try {
      const dashData = await apiClient.getDashboard({
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
      });
      onDashboardDataChange(dashData);
    } catch (err) {
      onError(err.message);
    }
    setLoading(false);
  }

  // ─── Gerencia toggle (para aba Gerencias) ───────────
  function handleGerenciaToggle(id) {
    if (String(gerenciaFilter) === String(id)) {
      setGerenciaFilter("");
      setSupervisaoFilter("");
    } else {
      setGerenciaFilter(String(id));
      setSupervisaoFilter("");
    }
  }

  // ─── Comparativo mensal (deltas) ────────────────────
  const comp = dashboardData.comparativo_mensal || {};

  function renderDelta(key, invertColor) {
    const item = comp[key];
    if (!item || item.delta === 0) return null;
    const isUp = item.delta > 0;
    const isGood = invertColor ? !isUp : isUp;
    const arrow = isUp ? "\u25B2" : "\u25BC";
    const sign = isUp ? "+" : "";
    return (
      <span
        className={`kpi-delta ${isGood ? "kpi-delta-good" : "kpi-delta-bad"}`}
        title={`Mes anterior: ${item.anterior}`}
      >
        {arrow} {sign}{item.delta}
      </span>
    );
  }

  // ─── Render ─────────────────────────────────────────
  return (
    <>
      {/* ===== BARRA DE FILTROS ===== */}
      <div className="card dash-filter-bar">
        <div className="dash-filter-row">
          <div className="dash-filter-group">
            <label className="dash-filter-label">Gerencia:</label>
            <select
              value={gerenciaFilter}
              onChange={(e) => { setGerenciaFilter(e.target.value); setSupervisaoFilter(""); }}
              className="dash-filter-select"
            >
              <option value="">Todas as Gerencias</option>
              {dashboardData.desempenho_gerencias.map((g) => (
                <option key={g.id} value={g.id}>{g.nome}</option>
              ))}
            </select>
          </div>

          <div className="dash-filter-group">
            <label className="dash-filter-label">Supervisao:</label>
            <select
              value={supervisaoFilter}
              onChange={(e) => setSupervisaoFilter(e.target.value)}
              className="dash-filter-select"
              disabled={!gerenciaFilter}
            >
              <option value="">Todas as Supervisoes</option>
              {supervisoesPorGerencia.map((s) => (
                <option key={s.id} value={s.id}>{s.nome}</option>
              ))}
            </select>
          </div>

          {(gerenciaFilter || supervisaoFilter) && (
            <button
              className="btn btn-outline dash-filter-clear"
              onClick={() => { setGerenciaFilter(""); setSupervisaoFilter(""); }}
            >
              Limpar Filtros
            </button>
          )}
        </div>

        {/* Filtro por periodo */}
        <div className="dash-periodo-row">
          <label className="dash-filter-label">Periodo:</label>
          <div className="dash-periodo-btns">
            {PERIODO_OPTIONS.map((p) => (
              <button
                key={p.value}
                className={`dash-periodo-btn ${periodo === p.value ? "active" : ""}`}
                onClick={() => handlePeriodoChange(p.value)}
                disabled={loading}
              >
                {p.label}
              </button>
            ))}
          </div>
          {periodo === "custom" && (
            <div className="dash-periodo-custom">
              <input
                type="date"
                value={dataInicio}
                onChange={(e) => setDataInicio(e.target.value)}
                className="dash-periodo-date"
              />
              <span className="dash-periodo-sep">ate</span>
              <input
                type="date"
                value={dataFim}
                onChange={(e) => setDataFim(e.target.value)}
                className="dash-periodo-date"
              />
              <button
                className="btn btn-primary dash-periodo-apply"
                onClick={handleCustomPeriodoApply}
                disabled={loading || (!dataInicio && !dataFim)}
              >
                Aplicar
              </button>
            </div>
          )}
          {loading && <span className="dash-periodo-loading">Carregando...</span>}
        </div>

        {/* Filter tags */}
        {(gerenciaFilter || supervisaoFilter) && (
          <div className="dash-filter-tags">
            {gerenciaFilter && (
              <span className="filter-tag">
                Gerencia: {dashboardData.desempenho_gerencias.find((g) => String(g.id) === String(gerenciaFilter))?.nome || gerenciaFilter}
                <button onClick={() => { setGerenciaFilter(""); setSupervisaoFilter(""); }}>&times;</button>
              </span>
            )}
            {supervisaoFilter && (
              <span className="filter-tag">
                Supervisao: {dashboardData.desempenho_supervisoes.find((s) => String(s.id) === String(supervisaoFilter))?.nome || supervisaoFilter}
                <button onClick={() => setSupervisaoFilter("")}>&times;</button>
              </span>
            )}
          </div>
        )}

        {/* Abas de visualizacao */}
        <div className="dash-view-tabs">
          <button
            className={`dash-view-tab ${view === "geral" ? "active" : ""}`}
            onClick={() => setView("geral")}
          >
            Visao Geral
          </button>
          <button
            className={`dash-view-tab ${view === "gerencias" ? "active" : ""}`}
            onClick={() => setView("gerencias")}
          >
            Gerencias
          </button>
          <button
            className={`dash-view-tab ${view === "supervisoes" ? "active" : ""}`}
            onClick={() => setView("supervisoes")}
          >
            Supervisoes
          </button>
          <button
            className={`dash-view-tab ${view === "fiscais" ? "active" : ""}`}
            onClick={() => setView("fiscais")}
          >
            Fiscais
          </button>
        </div>
      </div>

      {/* ===== KPI CARDS ===== */}
      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{kpis.total_os} {renderDelta("total_os", false)}</div>
          <div className="stat-label">Total de OS</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{kpis.os_em_andamento} {renderDelta("em_andamento", true)}</div>
          <div className="stat-label">Em Andamento</div>
        </div>
        <div className="stat-card concluida">
          <div className="stat-value">{kpis.tempo_medio_conclusao} dias</div>
          <div className="stat-label">Tempo Medio Conclusao</div>
        </div>
        <div className="stat-card urgente">
          <div className="stat-value">{kpis.os_criticas} {renderDelta("os_criticas", true)}</div>
          <div className="stat-label">OS Criticas (&gt;15 dias)</div>
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{kpis.dias_parado_medio} dias {renderDelta("dias_parado_medio", true)}</div>
          <div className="stat-label">Media Dias Parado</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{kpis.os_sem_ciencia} {renderDelta("os_sem_ciencia", true)}</div>
          <div className="stat-label">OS Sem Ciencia</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{kpis.total_fiscais}</div>
          <div className="stat-label">Fiscais Ativos</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{kpis.total_supervisores}</div>
          <div className="stat-label">Supervisores</div>
        </div>
      </div>

      {/* ===== TAB CONTENT ===== */}
      {view === "geral" && (
        <DashboardGeral
          dashboardData={dashboardData}
          gerenciaFilter={gerenciaFilter}
          gerenciasFiltradas={gerenciasFiltradas}
          onGerenciaSelect={(id) => { setGerenciaFilter(String(id)); setView("gerencias"); }}
        />
      )}

      {view === "gerencias" && (
        <DashboardGerencias
          gerenciasFiltradas={gerenciasFiltradas}
          gerenciaFilter={gerenciaFilter}
          onGerenciaToggle={handleGerenciaToggle}
        />
      )}

      {view === "supervisoes" && (
        <DashboardSupervisoes
          supervisoesFiltradas={supervisoesFiltradas}
          gerenciaFilter={gerenciaFilter}
          supervisaoFilter={supervisaoFilter}
          onGerenciaFilterChange={setGerenciaFilter}
          onSupervisaoSelect={(id) => { setSupervisaoFilter(String(id)); setView("fiscais"); }}
        />
      )}

      {view === "fiscais" && (
        <DashboardFiscais
          fiscaisFiltrados={fiscaisFiltrados}
          gerenciaFilter={gerenciaFilter}
          supervisaoFilter={supervisaoFilter}
        />
      )}
    </>
  );
}
