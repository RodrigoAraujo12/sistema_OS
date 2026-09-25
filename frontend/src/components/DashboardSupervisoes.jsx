/**
 * DashboardSupervisoes.jsx – Aba "Supervisoes" do Dashboard.
 *
 * Uma linha por EQUIPE FISCAL do ATF, com o(s) supervisor(es) que a
 * planilha da SEFAZ marca (ou que o admin amarrou a mao). Decisao do
 * Rodrigo em 25/09/2026: o cadastro local de supervisoes so tem as de
 * exemplo, e os supervisores reais chefiam equipes. A equipe conta as OS
 * pelas matriculas dos membros — o mesmo universo que o supervisor dela
 * enxerga na tela de Ordens de Servico.
 *
 * Clique em uma linha para ver a carga dos fiscais da equipe.
 */

import React from "react";
import { Bar } from "react-chartjs-2";
import { COR_GRUPO, TOPO_GRAFICO, formatarNumero } from "../dashboardShared.js";
import { classeTaxa } from "./DashboardGerencias.jsx";

export default function DashboardSupervisoes({
  equipesFiltradas,
  gerenciaFilter,
  equipeFilter,
  onEquipeSelect,
}) {
  // O grafico mostra as maiores; a tabela, todas — inclusive as que nao
  // tiveram OS no periodo, que sao metade das equipes da planilha.
  const topo = equipesFiltradas
    .filter((e) => e.total_os > 0)
    .sort((a, b) => b.total_os - a.total_os)
    .slice(0, TOPO_GRAFICO);

  return (
    <div className="card">
      <h2>Desempenho por Equipe Fiscal</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        {gerenciaFilter
          ? "Equipes da gerencia selecionada."
          : "Todas as equipes fiscais do ATF. Filtre por gerencia para refinar."}
        {" "}Cada equipe conta as OS dos seus membros, como o supervisor dela ve.
        Clique em uma linha para ver os fiscais.
      </p>

      {topo.length > 0 && (
        <div className="chart-container-md" style={{ marginBottom: 20 }}>
          <Bar
            data={{
              labels: topo.map((e) => (e.nome.length > 24 ? `${e.nome.slice(0, 24)}...` : e.nome)),
              datasets: [
                {
                  label: "Em andamento",
                  data: topo.map((e) => e.em_andamento),
                  backgroundColor: COR_GRUPO.em_andamento,
                  borderRadius: 4,
                },
                {
                  label: "Bloqueadas",
                  data: topo.map((e) => e.bloqueadas),
                  backgroundColor: COR_GRUPO.bloqueada,
                  borderRadius: 4,
                },
                {
                  label: "Encerradas",
                  data: topo.map((e) => e.encerradas),
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
                    title: (ctx) => topo[ctx[0].dataIndex]?.nome || "",
                    afterBody: function (ctx) {
                      const e = topo[ctx[0].dataIndex];
                      if (!e) return "";
                      return [
                        `Gerencia: ${e.gerencia_nome || "-"}`,
                        `Supervisor(es): ${e.supervisores.join(", ") || "-"}`,
                        `Total: ${e.total_os} | Taxa de encerramento: ${e.taxa_encerramento}%`,
                        `Sem ciencia: ${e.os_sem_ciencia}`,
                      ];
                    },
                  },
                },
              },
              scales: {
                x: { stacked: false },
                y: { stacked: false, beginAtZero: true, ticks: { precision: 0 } },
              },
              onClick: (evt, elements) => {
                if (elements.length > 0) {
                  const e = topo[elements[0].index];
                  if (e) onEquipeSelect(e.id);
                }
              },
            }}
          />
        </div>
      )}

      <div className="table-container" style={{ maxHeight: 520, overflowY: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Equipe</th>
              <th>Supervisor(es)</th>
              <th>Gerencia</th>
              <th>Total OS</th>
              <th>Em andamento</th>
              <th>Bloqueadas</th>
              <th>Encerradas</th>
              <th>Taxa de encerramento</th>
              <th>Sem Ciencia</th>
            </tr>
          </thead>
          <tbody>
            {equipesFiltradas.map((e) => (
              <tr
                key={e.id}
                className={`dash-row-clickable ${String(equipeFilter) === String(e.id) ? "dash-row-selected" : ""}`}
                onClick={() => onEquipeSelect(e.id)}
                title="Clique para ver os fiscais desta equipe"
              >
                <td className={e.total_os ? undefined : "muted"}><strong>{e.nome}</strong></td>
                <td className={e.supervisores.length ? undefined : "muted"}>
                  {e.supervisores.join(", ") || "Sem supervisor marcado"}
                </td>
                <td>{e.gerencia_nome || <span className="muted">—</span>}</td>
                <td>{formatarNumero(e.total_os)}</td>
                <td>{formatarNumero(e.em_andamento)}</td>
                <td>{formatarNumero(e.bloqueadas)}</td>
                <td>{formatarNumero(e.encerradas)}</td>
                <td>
                  {e.total_os > 0 ? (
                    <span className={`badge ${classeTaxa(e.taxa_encerramento)}`}>{e.taxa_encerramento}%</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <span className={`badge ${e.os_sem_ciencia > 0 ? "cancelada" : "concluida"}`}>
                    {formatarNumero(e.os_sem_ciencia)}
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
