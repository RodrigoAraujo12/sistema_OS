/**
 * DashboardGeral.jsx – Aba "Visao Geral" do Dashboard.
 *
 * Contem: Termometro da Fiscalizacao, grafico de pizza (situacao da OS
 * no ATF), evolucao mensal (linha) e comparativo por gerencia (barras
 * agrupadas). Dados de GET /admin/dashboard, sobre a listagem do ATF.
 */

import React from "react";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import { COR_GRUPO, COR_SITUACAO, COR_VAZIO } from "../dashboardShared.js";

const ROTULO_NIVEL = {
  saudavel: "Saudavel", atencao: "Atencao", critico: "Critico", emergencia: "Emergencia",
};

export default function DashboardGeral({
  dados,
  gerenciaFilter,
  gerenciasFiltradas,
  onGerenciaSelect,
}) {
  const ranking = dados.ranking_criticidade || [];

  // Pizza: sem filtro, uma fatia por situacao do ATF. Com gerencia, a
  // linha dela so tem os quatro grupos — o backend nao abre situacao por
  // gerencia —, entao a pizza passa a ser dos grupos.
  const pizza = gerenciaFilter
    ? (() => {
        const g = gerenciasFiltradas[0] || {};
        return {
          labels: ["Em andamento", "Bloqueadas", "Encerradas", "Canceladas"],
          valores: [g.em_andamento, g.bloqueadas, g.encerradas, g.canceladas],
          cores: [COR_GRUPO.em_andamento, COR_GRUPO.bloqueada, COR_GRUPO.encerrada, COR_GRUPO.cancelada],
        };
      })()
    : {
        labels: dados.por_situacao.map((s) => s.descricao),
        valores: dados.por_situacao.map((s) => s.total),
        cores: dados.por_situacao.map((s) => COR_SITUACAO[s.codigo] || COR_VAZIO),
      };

  // Gerencia sem OS no periodo nao tem barra a mostrar.
  const gerenciasParaChart = gerenciasFiltradas.filter((g) => g.total_os > 0);

  return (
    <>
      {/* ─── Termometro da Fiscalizacao ─── */}
      {ranking.length > 0 && !gerenciaFilter && (
        <div className="card termometro-panel">
          <div className="termometro-header">
            <h2>Termometro da Fiscalizacao</h2>
            <p className="muted">
              Indice de Saude por gerencia, sobre a taxa de encerramento e as OS sem ciencia.
              Clique para detalhar. Em periodos recentes a taxa e baixa por natureza: as OS
              ainda nao tiveram tempo de encerrar.
            </p>
          </div>

          {/* Pior gerencia em destaque */}
          {(() => {
            const pior = ranking[0];
            if (!pior || pior.indice_saude >= 75) return null;
            return (
              <div className={`termometro-destaque termometro-destaque-${pior.nivel}`}>
                <div className="termometro-destaque-icon">
                  {pior.nivel === "emergencia" ? "🚨" : pior.nivel === "critico" ? "⚠️" : "📋"}
                </div>
                <div className="termometro-destaque-info">
                  <strong>{pior.nome}</strong> precisa de atencao
                  {pior.nivel === "emergencia" ? " URGENTE" : pior.nivel === "critico" ? " imediata" : ""}
                  <div className="termometro-destaque-problemas">
                    {pior.problemas.join(" · ")}
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
                  <span className="termometro-card-nome">{g.nome}</span>
                  <span className={`termometro-badge nivel-${g.nivel}`}>{ROTULO_NIVEL[g.nivel]}</span>
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
                    <span className={`termometro-metrica-valor ${g.pct_sem_ciencia > 20 ? "text-danger" : g.pct_sem_ciencia > 0 ? "text-warning" : ""}`}>{g.pct_sem_ciencia}%</span>
                    <span className="termometro-metrica-label">Sem Ciencia ({g.os_sem_ciencia})</span>
                  </div>
                  <div className="termometro-metrica">
                    <span className={`termometro-metrica-valor ${g.taxa_encerramento < 25 ? "text-danger" : g.taxa_encerramento < 50 ? "text-warning" : ""}`}>{g.taxa_encerramento}%</span>
                    <span className="termometro-metrica-label">Encerrado</span>
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
        {/* Grafico Pizza - Distribuicao por situacao */}
        <div className="card dashboard-chart-card">
          <h2>{gerenciaFilter ? "Distribuicao por grupo de situacao" : "Distribuicao por situacao"}</h2>
          <div className="chart-container-sm">
            <Doughnut
              data={{
                labels: pizza.labels,
                datasets: [{
                  data: pizza.valores,
                  backgroundColor: pizza.cores,
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
          <p className="muted" style={{ marginBottom: 8 }}>
            OS abertas em cada mes e quantas delas ja estao encerradas.
          </p>
          <div className="chart-container-sm">
            <Line
              data={{
                labels: dados.evolucao_mensal.map((m) => {
                  const [ano, mes] = m.mes.split("-");
                  return `${mes}/${ano}`;
                }),
                datasets: [
                  {
                    label: "Abertas",
                    data: dados.evolucao_mensal.map((m) => m.abertas),
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59,130,246,0.1)",
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                  },
                  {
                    label: "Ja encerradas",
                    data: dados.evolucao_mensal.map((m) => m.encerradas),
                    borderColor: COR_GRUPO.encerrada,
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
                  y: { beginAtZero: true, ticks: { precision: 0 } },
                },
              }}
            />
          </div>
        </div>
      </div>

      {/* ─── Comparativo por Gerencia (barras agrupadas) ─── */}
      {gerenciasParaChart.length > 0 && (
        <div className="card">
          <h2>Comparativo por Gerencia (Situacao)</h2>
          <p className="muted" style={{ marginBottom: 16 }}>
            OS de cada gerencia por grupo de situacao. Clique em uma barra para filtrar.
          </p>
          <div className="chart-container-md">
            <Bar
              data={{
                labels: gerenciasParaChart.map((g) => g.nome),
                datasets: [
                  {
                    label: "Em andamento",
                    data: gerenciasParaChart.map((g) => g.em_andamento),
                    backgroundColor: COR_GRUPO.em_andamento,
                    borderRadius: 4,
                  },
                  {
                    label: "Bloqueadas",
                    data: gerenciasParaChart.map((g) => g.bloqueadas),
                    backgroundColor: COR_GRUPO.bloqueada,
                    borderRadius: 4,
                  },
                  {
                    label: "Encerradas",
                    data: gerenciasParaChart.map((g) => g.encerradas),
                    backgroundColor: COR_GRUPO.encerrada,
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
                        const g = gerenciasParaChart[ctx[0].dataIndex];
                        if (!g) return "";
                        return `Total: ${g.total_os} | Taxa de encerramento: ${g.taxa_encerramento}%\nSem ciencia: ${g.os_sem_ciencia}`;
                      },
                    },
                  },
                },
                scales: {
                  x: { stacked: false },
                  y: { stacked: false, beginAtZero: true, ticks: { precision: 0 } },
                },
                onClick: (evt, elements) => {
                  if (elements.length > 0 && !gerenciaFilter) {
                    const g = gerenciasParaChart[elements[0].index];
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
