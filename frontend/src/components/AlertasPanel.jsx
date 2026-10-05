/**
 * AlertasPanel.jsx – Painel de alertas automaticos.
 *
 * Exibe os alertas que o backend gera sobre as OS do ATF visiveis ao
 * usuario, abertas na janela configurada (GET /alertas). Quem consulta e
 * o App, ao abrir a aba ou no botao de atualizar: cada consulta e uma
 * listagem do ATF.
 *
 * Sem classificacao alta/media/baixa desde 05/10/2026, a pedido da area:
 * o que distingue um alerta do outro e o tipo.
 */

import React, { useEffect, useRef, useState } from "react";

/**
 * Com dados reais passa de mil alertas. Os alertas ja chegam todos de uma
 * vez, entao a paginacao e so de tela: trocar de pagina nao vai ao ATF.
 */
const POR_PAGINA = 20;

const ROTULO_TIPO = {
  os_sem_designacao: "sem designacao",
  os_sem_ciencia: "sem ciencia",
  os_sem_eventos: "sem evento",
};

/** As regras com os prazos em vigor, na ordem em que a OS anda. */
function descreverRegras(config, isAdmin) {
  if (!config) return "Gerados sobre as OS do ATF que voce enxerga.";
  const regras = [
    isAdmin && `OS sem fiscal designado ha mais de ${config.dias_sem_designacao} dias da abertura (so o admin ve)`,
    `fiscal sem ciencia ha mais de ${config.dias_sem_ciencia} dias da designacao`,
    `OS autorizada sem evento ha mais de ${config.dias_sem_eventos} dias, contando do ultimo evento, ou da ciencia quando ainda nao teve nenhum`,
  ].filter(Boolean);
  return (
    `Gerados sobre as OS do ATF que voce enxerga, abertas nos ultimos ${config.janela_dias} dias: `
    + regras.join("; ") + "."
  );
}

export default function AlertasPanel({ alertas, config, isAdmin, carregando, onAtualizar }) {
  const [pagina, setPagina] = useState(1);
  const topoRef = useRef(null);

  // Lista nova, recomeca da primeira pagina.
  useEffect(() => setPagina(1), [alertas]);

  const lista = alertas || [];
  const porTipo = lista.reduce((acc, a) => ({ ...acc, [a.tipo]: (acc[a.tipo] || 0) + 1 }), {});
  const totalPaginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
  const daPagina = lista.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);

  /** Troca de pagina e volta ao topo do painel: a nova pagina comeca la. */
  function irPara(p) {
    setPagina(Math.min(Math.max(1, p), totalPaginas));
    topoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="card" ref={topoRef}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2>Alertas {alertas ? `(${lista.length})` : ""}</h2>
        <button className="btn btn-outline" onClick={onAtualizar} disabled={carregando}>
          {carregando ? "Consultando o ATF..." : "Atualizar"}
        </button>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>
        {descreverRegras(config, isAdmin)}
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
            {daPagina.map((alerta, i) => (
              <div key={`${alerta.tipo}-${alerta.referencia}-${i}`} className="alerta-card">
                <div className="alerta-header">
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
          {totalPaginas > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
              <button className="small secondary" onClick={() => irPara(1)} disabled={pagina === 1}>«</button>
              <button className="small secondary" onClick={() => irPara(pagina - 1)} disabled={pagina === 1}>‹ Anterior</button>
              <span style={{ fontSize: 13, color: "#6b7280" }}>
                P&aacute;gina {pagina} de {totalPaginas} &mdash; {lista.length} alertas
              </span>
              <button className="small secondary" onClick={() => irPara(pagina + 1)} disabled={pagina === totalPaginas}>Pr&oacute;xima ›</button>
              <button className="small secondary" onClick={() => irPara(totalPaginas)} disabled={pagina === totalPaginas}>»</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
