/**
 * AlertasPanel.jsx – Painel de alertas automaticos.
 *
 * Exibe alertas gerados a partir das OS visiveis ao usuario.
 * Componente puramente apresentacional (sem estado interno).
 */

import React from "react";

export default function AlertasPanel({ alertas }) {
  return (
    <div className="card">
      <h2>Alertas ({alertas.length})</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Alertas gerados automaticamente a partir dos dados da API externa.
      </p>
      {alertas.length === 0 ? (
        <div className="empty-state">
          <p className="muted">Nenhum alerta no momento.</p>
        </div>
      ) : (
        <div className="alertas-list">
          {alertas.map((alerta, i) => (
            <div key={i} className={`alerta-card severidade-${alerta.severidade}`}>
              <div className="alerta-header">
                <span className={`badge ${alerta.severidade === "alta" ? "cancelada" : "em_andamento"}`}>
                  {alerta.severidade}
                </span>
                <span className="badge normal">{alerta.tipo.replace(/_/g, " ")}</span>
              </div>
              <h3 className="alerta-titulo">{alerta.titulo}</h3>
              <p className="alerta-descricao">{alerta.descricao}</p>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                Ref: {alerta.referencia}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
