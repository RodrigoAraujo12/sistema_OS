/**
 * DashboardGerencias.jsx – Aba "Gerencias" do Dashboard.
 *
 * Exibe grafico horizontal de dias parado e tabela de desempenho.
 * Clique em uma linha para filtrar/desfiltrar a gerencia.
 */

import React from "react";
import { Bar } from "react-chartjs-2";

export default function DashboardGerencias({
  gerenciasFiltradas,
  gerenciaFilter,
  onGerenciaToggle,
}) {
  return (
    <div className="card">
      <h2>Desempenho por Gerencia</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Ranking por tempo medio de OS parada (maior = mais lenta).
        {!gerenciaFilter && " Clique em uma linha para filtrar."}
      </p>

      {gerenciasFiltradas.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: gerenciasFiltradas.map((g) => g.nome.replace("Gerencia de ", "")),
              datasets: [{
                label: "Dias Parado (media)",
                data: gerenciasFiltradas.map((g) => g.dias_parado_medio),
                backgroundColor: gerenciasFiltradas.map((g) =>
                  g.dias_parado_medio > 15 ? "#ef4444" : g.dias_parado_medio > 7 ? "#f59e0b" : "#22c55e"
                ),
                borderRadius: 6,
              }],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              indexAxis: "y",
              plugins: {
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    afterLabel: function (ctx) {
                      const g = gerenciasFiltradas[ctx.dataIndex];
                      if (!g) return "";
                      return `Total: ${g.total_os} | Abertas: ${g.abertas}\nAndamento: ${g.em_andamento} | Concluidas: ${g.concluidas}\nTaxa: ${g.taxa_conclusao}% | Criticas: ${g.os_criticas}`;
                    },
                  },
                },
              },
              scales: {
                x: { beginAtZero: true, title: { display: true, text: "Dias" } },
              },
            }}
          />
        </div>
      )}

      <div className="table-container" style={{ marginTop: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Gerencia</th>
              <th>Total OS</th>
              <th>Abertas</th>
              <th>Andamento</th>
              <th>Concluidas</th>
              <th>Taxa Conclusao</th>
              <th>Dias Parado (media)</th>
              <th>OS Criticas</th>
              <th>Tempo Med. Conclusao</th>
            </tr>
          </thead>
          <tbody>
            {gerenciasFiltradas.map((g) => (
              <tr
                key={g.id}
                className={`dash-row-clickable ${String(gerenciaFilter) === String(g.id) ? "dash-row-selected" : ""}`}
                onClick={() => onGerenciaToggle(g.id)}
                title="Clique para filtrar por esta gerencia"
              >
                <td><strong>{g.nome}</strong></td>
                <td>{g.total_os}</td>
                <td>{g.abertas}</td>
                <td>{g.em_andamento}</td>
                <td>{g.concluidas}</td>
                <td>
                  <span className={`badge ${g.taxa_conclusao >= 50 ? "concluida" : g.taxa_conclusao >= 25 ? "em_andamento" : "cancelada"}`}>
                    {g.taxa_conclusao}%
                  </span>
                </td>
                <td>
                  <span className={`badge ${g.dias_parado_medio > 15 ? "cancelada" : g.dias_parado_medio > 7 ? "em_andamento" : "concluida"}`}>
                    {g.dias_parado_medio} dias
                  </span>
                </td>
                <td>
                  {g.os_criticas > 0 ? (
                    <span className="badge cancelada">{g.os_criticas}</span>
                  ) : (
                    <span className="badge concluida">0</span>
                  )}
                </td>
                <td>{g.tempo_medio_conclusao} dias</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
