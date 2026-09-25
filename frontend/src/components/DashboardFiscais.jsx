/**
 * DashboardFiscais.jsx – Aba "Fiscais" do Dashboard.
 *
 * Carga de trabalho por fiscal: OS ativas (em andamento ou bloqueadas)
 * em que ele esta designado no ATF, sem contar designacao cancelada.
 */

import React from "react";
import { Bar } from "react-chartjs-2";
import { TOPO_GRAFICO, formatarNumero } from "../dashboardShared.js";

function classeCarga(osAtivas) {
  return osAtivas > 3 ? "cancelada" : osAtivas > 1 ? "em_andamento" : "concluida";
}

export default function DashboardFiscais({
  fiscaisFiltrados,
  gerenciaFilter,
  equipeFilter,
}) {
  // Sao centenas de fiscais: o grafico mostra os mais carregados e a
  // tabela logo abaixo, todos.
  const topo = fiscaisFiltrados.slice(0, TOPO_GRAFICO);

  return (
    <div className="card">
      <h2>Carga de Trabalho por Fiscal</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        {equipeFilter
          ? "Fiscais da equipe selecionada"
          : gerenciaFilter
          ? "Fiscais da gerencia selecionada"
          : "Todos os fiscais com OS ativa"}
        {" "}(mais carregados primeiro). Conta as OS em andamento ou bloqueadas abertas no periodo.
      </p>

      {topo.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: topo.map((f) => f.nome),
              datasets: [{
                label: "OS ativas",
                data: topo.map((f) => f.os_ativas),
                backgroundColor: topo.map((f) =>
                  f.os_ativas > 3 ? "#ef4444" : f.os_ativas > 1 ? "#f59e0b" : "#22c55e"
                ),
                borderRadius: 6,
              }],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { display: false } },
              scales: {
                y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Qtd OS" } },
              },
            }}
          />
        </div>
      )}

      {fiscaisFiltrados.length === 0 && (
        <div className="alert info">Nenhum fiscal com OS ativa para os filtros selecionados.</div>
      )}

      {fiscaisFiltrados.length > 0 && (
        <div className="table-container" style={{ maxHeight: 520, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Fiscal</th>
                <th>Matricula</th>
                <th>OS ativas</th>
              </tr>
            </thead>
            <tbody>
              {fiscaisFiltrados.map((f) => (
                <tr key={f.matricula || f.nome}>
                  <td><strong>{f.nome}</strong></td>
                  <td>{f.matricula || <span className="muted">—</span>}</td>
                  <td>
                    <span className={`badge ${classeCarga(f.os_ativas)}`}>
                      {formatarNumero(f.os_ativas)}
                    </span>
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
