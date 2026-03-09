/**
 * DashboardSupervisoes.jsx – Aba "Supervisoes" do Dashboard.
 *
 * Exibe grafico de barras agrupadas e tabela de desempenho por supervisao.
 * Clique em uma linha para ver os fiscais da supervisao.
 */

import React from "react";
import { Bar } from "react-chartjs-2";

export default function DashboardSupervisoes({
  supervisoesFiltradas,
  gerenciaFilter,
  supervisaoFilter,
  onGerenciaFilterChange,
  onSupervisaoSelect,
}) {
  return (
    <div className="card">
      <h2>Desempenho por Supervisao</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        {gerenciaFilter
          ? "Supervisoes da gerencia selecionada. Clique em uma linha para detalhar."
          : "Todas as supervisoes. Filtre por gerencia para refinar."}
      </p>

      {supervisoesFiltradas.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: supervisoesFiltradas.map((s) => s.nome.length > 20 ? s.nome.slice(0, 20) + "..." : s.nome),
              datasets: [
                {
                  label: "Abertas",
                  data: supervisoesFiltradas.map((s) => s.abertas),
                  backgroundColor: "#3b82f6",
                  borderRadius: 4,
                },
                {
                  label: "Em Andamento",
                  data: supervisoesFiltradas.map((s) => s.em_andamento),
                  backgroundColor: "#f59e0b",
                  borderRadius: 4,
                },
                {
                  label: "Concluidas",
                  data: supervisoesFiltradas.map((s) => s.concluidas),
                  backgroundColor: "#22c55e",
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
                      const s = supervisoesFiltradas[ctx[0].dataIndex];
                      if (!s) return "";
                      return `Gerencia: ${s.gerencia_nome}\nTotal: ${s.total_os} | Taxa: ${s.taxa_conclusao}%\nDias parado: ${s.dias_parado_medio} | Criticas: ${s.os_criticas}`;
                    },
                  },
                },
              },
              scales: {
                x: { stacked: false },
                y: { stacked: false, beginAtZero: true, ticks: { stepSize: 1 } },
              },
              onClick: (evt, elements) => {
                if (elements.length > 0) {
                  const idx = elements[0].index;
                  const s = supervisoesFiltradas[idx];
                  if (s) onSupervisaoSelect(s.id);
                }
              },
            }}
          />
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Supervisao</th>
              <th>Gerencia</th>
              <th>Total OS</th>
              <th>Abertas</th>
              <th>Andamento</th>
              <th>Concluidas</th>
              <th>Taxa Conclusao</th>
              <th>Dias Parado (media)</th>
              <th>OS Criticas</th>
            </tr>
          </thead>
          <tbody>
            {supervisoesFiltradas.map((s) => (
              <tr
                key={s.id}
                className={`dash-row-clickable ${String(supervisaoFilter) === String(s.id) ? "dash-row-selected" : ""}`}
                onClick={() => {
                  if (!gerenciaFilter) onGerenciaFilterChange(String(s.gerencia_id));
                  onSupervisaoSelect(s.id);
                }}
                title="Clique para ver os fiscais desta supervisao"
              >
                <td><strong>{s.nome}</strong></td>
                <td>{s.gerencia_nome}</td>
                <td>{s.total_os}</td>
                <td>{s.abertas}</td>
                <td>{s.em_andamento}</td>
                <td>{s.concluidas}</td>
                <td>
                  <span className={`badge ${s.taxa_conclusao >= 50 ? "concluida" : s.taxa_conclusao >= 25 ? "em_andamento" : "cancelada"}`}>
                    {s.taxa_conclusao}%
                  </span>
                </td>
                <td>
                  <span className={`badge ${s.dias_parado_medio > 15 ? "cancelada" : s.dias_parado_medio > 7 ? "em_andamento" : "concluida"}`}>
                    {s.dias_parado_medio} dias
                  </span>
                </td>
                <td>
                  {s.os_criticas > 0 ? (
                    <span className="badge cancelada">{s.os_criticas}</span>
                  ) : (
                    <span className="badge concluida">0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
