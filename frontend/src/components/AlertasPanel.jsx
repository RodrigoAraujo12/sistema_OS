/**
 * AlertasPanel.jsx – Painel de alertas automaticos.
 *
 * Exibe os alertas que o backend gera sobre as OS do ATF visiveis ao
 * usuario, abertas nos ultimos 12 meses (GET /alertas). Quem consulta e
 * o App, ao abrir a aba ou no botao de atualizar: cada consulta e uma
 * listagem do ATF.
 */

import React, { useEffect, useState } from "react";

/** Com dados reais sao centenas de alertas: a lista cresce aos poucos. */
const POR_PAGINA = 100;

const ROTULO_TIPO = {
  os_parada: "sem evento",
  os_sem_ciencia: "sem ciencia",
};

export default function AlertasPanel({ alertas, carregando, onAtualizar }) {
  const [visiveis, setVisiveis] = useState(POR_PAGINA);

  // Lista nova, recomeca do topo.
  useEffect(() => setVisiveis(POR_PAGINA), [alertas]);

  const lista = alertas || [];
  const porTipo = lista.reduce((acc, a) => ({ ...acc, [a.tipo]: (acc[a.tipo] || 0) + 1 }), {});

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2>Alertas {alertas ? `(${lista.length})` : ""}</h2>
        <button className="btn btn-outline" onClick={onAtualizar} disabled={carregando}>
          {carregando ? "Consultando o ATF..." : "Atualizar"}
        </button>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>
        Gerados sobre as OS do ATF que voce enxerga, abertas nos ultimos 12 meses: OS
        autorizada sem evento de acompanhamento ha mais de 15 dias, e fiscal designado que
        ainda nao deu ciencia (alta quando o ATF ja bloqueou a OS).
        {alertas && lista.length > 0 && (
          <> {Object.entries(porTipo).map(([tipo, n]) => `${n} ${ROTULO_TIPO[tipo] || tipo}`).join(" · ")}.</>
        )}
      </p>

      {!alertas ? (
        <div className="empty-state">
          <p className="muted">{carregando ? "Consultando o ATF..." : "Clique em Atualizar para consultar."}</p>
        </div>
      ) : lista.length === 0 ? (
        <div className="empty-state">
          <p className="muted">Nenhum alerta no momento.</p>
        </div>
      ) : (
        <>
          <div className="alertas-list">
            {lista.slice(0, visiveis).map((alerta, i) => (
              <div key={`${alerta.tipo}-${alerta.referencia}-${i}`} className={`alerta-card severidade-${alerta.severidade}`}>
                <div className="alerta-header">
                  <span className={`badge ${alerta.severidade === "alta" ? "cancelada" : "em_andamento"}`}>
                    {alerta.severidade}
                  </span>
                  <span className="badge normal">{ROTULO_TIPO[alerta.tipo] || alerta.tipo.replace(/_/g, " ")}</span>
                </div>
                <h3 className="alerta-titulo">{alerta.titulo}</h3>
                <p className="alerta-descricao">{alerta.descricao}</p>
                <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  Ref: {alerta.referencia}
                </div>
              </div>
            ))}
          </div>
          {visiveis < lista.length && (
            <div style={{ textAlign: "center", marginTop: 16 }}>
              <button className="btn btn-outline" onClick={() => setVisiveis(visiveis + POR_PAGINA)}>
                Mostrar mais ({lista.length - visiveis} restantes)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
