/**
 * DashboardGeral.jsx – Aba "Visao Geral" do Dashboard.
 *
 * Contem: Termometro da Fiscalizacao, grafico de pizza (status),
 * evolucao mensal (linha) e comparativo por gerencia (barras agrupadas).
 */

import React from "react";
import { Bar, Doughnut, Line } from "react-chartjs-2";

const CHART_COLORS = {
  aberta: "#3b82f6",
  em_andamento: "#f59e0b",
  concluida: "#22c55e",
  cancelada: "#ef4444",
};

export default function DashboardGeral({
  dashboardData,
  gerenciaFilter,
  gerenciasFiltradas,
  onGerenciaSelect,
}) {
  const ranking = dashboardData.ranking_criticidade || [];

  // Dados do doughnut: filtrados ou totais
  const doughnutData = gerenciaFilter
    ? [
        gerenciasFiltradas.reduce((s, g) => s + g.abertas, 0),
        gerenciasFiltradas.reduce((s, g) => s + g.em_andamento, 0),
        gerenciasFiltradas.reduce((s, g) => s + g.concluidas, 0),
        gerenciasFiltradas.reduce((s, g) => s + (g.total_os - g.abertas - g.em_andamento - g.concluidas), 0),
      ]
    : [
        dashboardData.distribuicao_status.aberta,
        dashboardData.distribuicao_status.em_andamento,
        dashboardData.distribuicao_status.concluida,
        dashboardData.distribuicao_status.cancelada,
      ];

  const gerenciasParaChart = gerenciasFiltradas.length > 0
    ? gerenciasFiltradas
    : dashboardData.desempenho_gerencias;

  return (
    <>
      {/* ─── Termometro da Fiscalizacao ─── */}
      {ranking.length > 0 && !gerenciaFilter && (
        <div className="card termometro-panel">
          <div className="termometro-header">
            <h2>Termometro da Fiscalizacao</h2>
            <p className="muted">
              Indice de Saude por gerencia — identifique rapidamente onde atuar.
              Clique para detalhar.
            </p>
          </div>

          {/* Pior gerencia em destaque */}
          {(() => {
            const pior = ranking[0];
            if (!pior || pior.indice_saude >= 75) return null;
            return (
              <div className={`termometro-destaque termometro-destaque-${pior.nivel}`}>
                <div className="termometro-destaque-icon">
                  {pior.nivel === "emergencia" ? "\uD83D\uDEA8" : pior.nivel === "critico" ? "\u26A0\uFE0F" : "\uD83D\uDCCB"}
                </div>
                <div className="termometro-destaque-info">
                  <strong>{pior.nome}</strong> precisa de atencao
                  {pior.nivel === "emergencia" ? " URGENTE" : pior.nivel === "critico" ? " imediata" : ""}
                  <div className="termometro-destaque-problemas">
                    {pior.problemas.join(" \u00B7 ")}
                  </div>
                </div>
                <div className="termometro-destaque-score">
                  <span className={`termometro-score-value nivel-${pior.nivel}`}>
                    {pior.indice_saude}
                  </span>
                  <span className="termometro-score-label">/ 100</span>
                </div>
              </div>
            );
          })()}

          {/* Cards de cada gerencia */}
          <div className="termometro-grid">
            {ranking.map((g) => (
              <div
                key={g.id}
                className={`termometro-card termometro-card-${g.nivel}`}
                onClick={() => onGerenciaSelect(g.id)}
                title={`Clique para detalhar ${g.nome}`}
              >
                <div className="termometro-card-top">
                  <span className="termometro-card-nome">{g.nome.replace("Gerencia de ", "")}</span>
                  <span className={`termometro-badge nivel-${g.nivel}`}>
                    {g.nivel === "saudavel" ? "Saudavel" : g.nivel === "atencao" ? "Atencao" : g.nivel === "critico" ? "Critico" : "Emergencia"}
                  </span>
                </div>

                <div className="termometro-barra-container">
                  <div
                    className={`termometro-barra-fill nivel-${g.nivel}`}
                    style={{ width: `${g.indice_saude}%` }}
                  />
                </div>
                <div className="termometro-card-score">
                  <span className={`nivel-${g.nivel}`}>{g.indice_saude}</span>
                  <span className="termometro-score-label"> / 100</span>
                </div>

                <div className="termometro-card-metricas">
                  <div className="termometro-metrica">
                    <span className="termometro-metrica-valor">{g.total_os}</span>
                    <span className="termometro-metrica-label">OS</span>
                  </div>
                  <div className="termometro-metrica">
                    <span className={`termometro-metrica-valor ${g.pct_criticas > 20 ? "text-danger" : g.pct_criticas > 0 ? "text-warning" : ""}`}>{g.pct_criticas}%</span>
                    <span className="termometro-metrica-label">Criticas ({g.os_criticas})</span>
                  </div>
                  <div className="termometro-metrica">
                    <span className={`termometro-metrica-valor ${g.dias_parado_medio > 15 ? "text-danger" : g.dias_parado_medio > 7 ? "text-warning" : ""}`}>{g.dias_parado_medio}d</span>
                    <span className="termometro-metrica-label">Parado</span>
                  </div>
                  <div className="termometro-metrica">
                    <span className="termometro-metrica-valor">{g.taxa_conclusao}%</span>
                    <span className="termometro-metrica-label">Concluido</span>
                  </div>
                </div>

                {g.problemas.length > 0 && (
                  <div className="termometro-problemas">
                    {g.problemas.map((p, i) => (
                      <span key={i} className="termometro-problema-tag">{p}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Graficos lado a lado ─── */}
      <div className="dashboard-charts-row">
        {/* Grafico Pizza - Distribuicao por Status */}
        <div className="card dashboard-chart-card">
          <h2>Distribuicao por Status</h2>
          <div className="chart-container-sm">
            <Doughnut
              data={{
                labels: ["Abertas", "Em Andamento", "Concluidas", "Canceladas"],
                datasets: [{
                  data: doughnutData,
                  backgroundColor: [CHART_COLORS.aberta, CHART_COLORS.em_andamento, CHART_COLORS.concluida, CHART_COLORS.cancelada],
                  borderWidth: 2,
                  borderColor: "#fff",
                }],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { position: "bottom", labels: { padding: 16, usePointStyle: true } },
                  tooltip: {
                    callbacks: {
                      label: function (ctx) {
                        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : 0;
                        return `${ctx.label}: ${ctx.raw} (${pct}%)`;
                      },
                    },
                  },
                },
              }}
            />
          </div>
        </div>

        {/* Grafico Linha - Evolucao Mensal */}
        <div className="card dashboard-chart-card">
          <h2>Evolucao Mensal</h2>
          <div className="chart-container-sm">
            <Line
              data={{
                labels: dashboardData.evolucao_mensal.map((m) => {
                  const [ano, mes] = m.mes.split("-");
                  return `${mes}/${ano}`;
                }),
                datasets: [
                  {
                    label: "Abertas",
                    data: dashboardData.evolucao_mensal.map((m) => m.abertas),
                    borderColor: CHART_COLORS.aberta,
                    backgroundColor: "rgba(59,130,246,0.1)",
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                  },
                  {
                    label: "Concluidas",
                    data: dashboardData.evolucao_mensal.map((m) => m.concluidas),
                    borderColor: CHART_COLORS.concluida,
                    backgroundColor: "rgba(34,197,94,0.1)",
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                  legend: { position: "bottom", labels: { padding: 16, usePointStyle: true } },
                  tooltip: { mode: "index", intersect: false },
                },
                scales: {
                  y: { beginAtZero: true, ticks: { stepSize: 1 } },
                },
              }}
            />
          </div>
        </div>
      </div>

      {/* ─── Comparativo por Gerencia (barras agrupadas) ─── */}
      {dashboardData.desempenho_gerencias.length > 0 && (
        <div className="card">
          <h2>Comparativo por Gerencia (Status)</h2>
          <p className="muted" style={{ marginBottom: 16 }}>
            Distribuicao de OS por status em cada gerencia. Clique em uma barra para filtrar.
          </p>
          <div className="chart-container-md">
            <Bar
              data={{
                labels: gerenciasParaChart.map((g) => g.nome.replace("Gerencia de ", "")),
                datasets: [
                  {
                    label: "Abertas",
                    data: gerenciasParaChart.map((g) => g.abertas),
                    backgroundColor: CHART_COLORS.aberta,
                    borderRadius: 4,
                  },
                  {
                    label: "Em Andamento",
                    data: gerenciasParaChart.map((g) => g.em_andamento),
                    backgroundColor: CHART_COLORS.em_andamento,
                    borderRadius: 4,
                  },
                  {
                    label: "Concluidas",
                    data: gerenciasParaChart.map((g) => g.concluidas),
                    backgroundColor: CHART_COLORS.concluida,
                    borderRadius: 4,
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { position: "bottom", labels: { padding: 16, usePointStyle: true } },
                  tooltip: {
                    callbacks: {
                      afterBody: function (ctx) {
                        const idx = ctx[0].dataIndex;
                        const g = gerenciasParaChart[idx];
                        if (!g) return "";
                        return `Total: ${g.total_os} | Taxa: ${g.taxa_conclusao}%\nDias parado: ${g.dias_parado_medio} | Criticas: ${g.os_criticas}`;
                      },
                    },
                  },
                },
                scales: {
                  x: { stacked: false },
                  y: { stacked: false, beginAtZero: true, ticks: { stepSize: 1 } },
                },
                onClick: (evt, elements) => {
                  if (elements.length > 0 && !gerenciaFilter) {
                    const idx = elements[0].index;
                    const g = dashboardData.desempenho_gerencias[idx];
                    if (g) onGerenciaSelect(g.id);
                  }
                },
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}
