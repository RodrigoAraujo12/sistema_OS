/**
 * DashboardGerencias.jsx – Aba "Gerencias" do Dashboard.
 *
 * Grafico horizontal da taxa de encerramento e tabela de desempenho por
 * gerencia do cadastro, sobre a listagem do ATF, com as pendencias dos
 * alertas (sem ciencia e sem evento). Clique em uma linha para
 * filtrar/desfiltrar a gerencia.
 */

import React from "react";
import { Bar } from "react-chartjs-2";
import { formatarNumero } from "../dashboardShared.js";

/** Classe do badge pela taxa de encerramento. */
export function classeTaxa(taxa) {
  return taxa >= 50 ? "concluida" : taxa >= 25 ? "em_andamento" : "cancelada";
}

/** Classe do badge de uma pendencia dos alertas: qualquer uma ja pede olhar. */
export function classePendencia(quantidade) {
  return quantidade > 0 ? "cancelada" : "concluida";
}

export default function DashboardGerencias({
  gerenciasFiltradas,
  gerenciaFilter,
  prazos,
  onGerenciaToggle,
}) {
  const comOS = gerenciasFiltradas.filter((g) => g.total_os > 0);

  return (
    <div className="card">
      <h2>Desempenho por Gerencia</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Taxa de encerramento: encerradas sobre o total, sem as canceladas e substituidas.
        Sem ciencia e sem evento sao os alertas, com os prazos em vigor. Uma OS conta em cada
        gerencia que seus fiscais alcancam.
        {!gerenciaFilter && " Clique em uma linha para filtrar."}
      </p>

      {comOS.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: comOS.map((g) => g.nome),
              datasets: [{
                label: "Taxa de encerramento (%)",
                data: comOS.map((g) => g.taxa_encerramento),
                backgroundColor: comOS.map((g) =>
                  g.taxa_encerramento < 25 ? "#ef4444" : g.taxa_encerramento < 50 ? "#f59e0b" : "#22c55e"
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
                      const g = comOS[ctx.dataIndex];
                      if (!g) return "";
                      return `Total: ${g.total_os} | Em andamento: ${g.em_andamento}\nBloqueadas: ${g.bloqueadas} | Encerradas: ${g.encerradas}\nSem ciencia: ${g.os_sem_ciencia} | Sem evento: ${g.os_sem_eventos}`;
                    },
                  },
                },
              },
              scales: {
                x: { beginAtZero: true, max: 100, title: { display: true, text: "%" } },
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
              <th>Em andamento</th>
              <th>Bloqueadas</th>
              <th>Encerradas</th>
              <th>Canceladas</th>
              <th>Taxa de encerramento</th>
              <th>Sem ciencia (+{prazos.dias_sem_ciencia}d)</th>
              <th>Sem evento (+{prazos.dias_sem_eventos}d)</th>
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
                <td className={g.total_os ? undefined : "muted"}><strong>{g.nome}</strong></td>
                <td>{formatarNumero(g.total_os)}</td>
                <td>{formatarNumero(g.em_andamento)}</td>
                <td>{formatarNumero(g.bloqueadas)}</td>
                <td>{formatarNumero(g.encerradas)}</td>
                <td>{formatarNumero(g.canceladas)}</td>
                <td>
                  {g.total_os > 0 ? (
                    <span className={`badge ${classeTaxa(g.taxa_encerramento)}`}>{g.taxa_encerramento}%</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <span className={`badge ${classePendencia(g.os_sem_ciencia)}`}>
                    {formatarNumero(g.os_sem_ciencia)}
                  </span>
                </td>
                <td>
                  <span className={`badge ${classePendencia(g.os_sem_eventos)}`}>
                    {formatarNumero(g.os_sem_eventos)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
