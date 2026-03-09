/**
 * DashboardFiscais.jsx – Aba "Fiscais" do Dashboard.
 *
 * Exibe grafico de barras e tabela de carga de trabalho por fiscal.
 */

import React from "react";
import { Bar } from "react-chartjs-2";

export default function DashboardFiscais({
  fiscaisFiltrados,
  gerenciaFilter,
  supervisaoFilter,
}) {
  return (
    <div className="card">
      <h2>Carga de Trabalho por Fiscal</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        {supervisaoFilter
          ? "Fiscais da supervisao selecionada (sobrecarregados primeiro)"
          : gerenciaFilter
          ? "Fiscais da gerencia selecionada (sobrecarregados primeiro)"
          : "Todos os fiscais (sobrecarregados primeiro)"}
      </p>

      {fiscaisFiltrados.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: fiscaisFiltrados.map((f) => f.nome),
              datasets: [{
                label: "OS Ativas",
                data: fiscaisFiltrados.map((f) => f.os_ativas),
                backgroundColor: fiscaisFiltrados.map((f) =>
                  f.os_ativas > 3 ? "#ef4444" : f.os_ativas > 1 ? "#f59e0b" : "#22c55e"
                ),
                borderRadius: 6,
              }],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    afterLabel: function (ctx) {
                      const f = fiscaisFiltrados[ctx.dataIndex];
                      if (!f) return "";
                      return `Dias parado (media): ${f.dias_parado_medio}\nOS Criticas: ${f.os_criticas}`;
                    },
                  },
                },
              },
              scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1 }, title: { display: true, text: "Qtd OS" } },
              },
            }}
          />
        </div>
      )}

      {fiscaisFiltrados.length === 0 && (
        <div className="alert info">Nenhum fiscal encontrado para os filtros selecionados.</div>
      )}

      {fiscaisFiltrados.length > 0 && (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Fiscal</th>
                <th>OS Ativas</th>
                <th>Dias Parado (media)</th>
                <th>OS Criticas</th>
              </tr>
            </thead>
            <tbody>
              {fiscaisFiltrados.map((f, i) => (
                <tr key={i}>
                  <td><strong>{f.nome}</strong></td>
                  <td>
                    <span className={`badge ${f.os_ativas > 3 ? "cancelada" : f.os_ativas > 1 ? "em_andamento" : "concluida"}`}>
                      {f.os_ativas}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${f.dias_parado_medio > 15 ? "cancelada" : f.dias_parado_medio > 7 ? "em_andamento" : "concluida"}`}>
                      {f.dias_parado_medio} dias
                    </span>
                  </td>
                  <td>
                    {f.os_criticas > 0 ? (
                      <span className="badge cancelada">{f.os_criticas}</span>
                    ) : (
                      <span className="badge concluida">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
