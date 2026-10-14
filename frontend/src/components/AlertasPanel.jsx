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
 *
 * Cada alerta mostra o fiscal que ele cobra e, no clique, abre o detalhe
 * da OS — o mesmo modal da tela de OS (DetalheOS).
 *
 * O admin recebe os alertas de todas as gerencias e pode filtrar por uma
 * (14/10/2026). Comeca em todas. O filtro e so de tela, como a paginacao:
 * a gerencia vem em cada alerta, pela mesma regra do dashboard.
 */

import React, { useEffect, useRef, useState } from "react";
import DetalheOS from "./DetalheOS.jsx";

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

/** Valor do filtro para as OS que nenhuma gerencia do cadastro alcanca. */
const SEM_GERENCIA = "sem";

/** O alerta esta na gerencia do filtro? "" e todas. */
function daGerencia(alerta, filtro) {
  if (!filtro) return true;
  const gerencias = alerta.gerencias || [];
  if (filtro === SEM_GERENCIA) return gerencias.length === 0;
  return gerencias.some((g) => String(g.id) === filtro);
}

/**
 * Opcoes do filtro: as gerencias que tem alerta, em ordem de nome, com
 * quantos alertas cada uma tem, e por ultimo as OS sem gerencia — a
 * ausencia e informacao, nao some da tela. Uma OS de duas gerencias conta
 * nas duas, como no dashboard.
 */
function opcoesGerencia(lista) {
  const porId = new Map();
  let semGerencia = 0;
  for (const a of lista) {
    if (!a.gerencias?.length) semGerencia += 1;
    for (const g of a.gerencias || []) {
      const atual = porId.get(g.id) || { valor: String(g.id), nome: g.nome, total: 0 };
      porId.set(g.id, { ...atual, total: atual.total + 1 });
    }
  }
  const opcoes = [...porId.values()].sort((x, y) => x.nome.localeCompare(y.nome));
  if (semGerencia) opcoes.push({ valor: SEM_GERENCIA, nome: "Sem gerencia cadastrada", total: semGerencia });
  return opcoes;
}

/** "Fiscal: FULANO", "Fiscais: A, B"; sem designacao nao ha ninguem. */
function textoFiscais(fiscais) {
  if (!fiscais?.length) return "Sem fiscal designado";
  return `${fiscais.length > 1 ? "Fiscais" : "Fiscal"}: ${fiscais.join(", ")}`;
}

/** As regras com os prazos em vigor, na ordem em que a OS anda. */
function descreverRegras(config, isAdmin) {
  if (!config) return "Gerados sobre as OS do ATF que voce enxerga.";
  const regras = [
    isAdmin && `OS sem fiscal designado ha mais de ${config.dias_sem_designacao} dias da abertura (so o admin ve)`,
    `fiscal sem ciencia ha mais de ${config.dias_sem_ciencia} dias da designacao`,
    `OS autorizada sem evento ha mais de ${config.dias_sem_eventos} dias, contando do ultimo evento, ou da ciencia quando ainda nao teve nenhum`
      + " (onde a gerencia deu prazo para o procedimento do ultimo evento, vale ele, e eventos seguidos do mesmo procedimento contam como um so)",
  ].filter(Boolean);
  return (
    `Gerados sobre as OS do ATF que voce enxerga, abertas nos ultimos ${config.janela_dias} dias: `
    + regras.join("; ") + "."
  );
}

export default function AlertasPanel({ alertas, config, isAdmin, carregando, onAtualizar }) {
  const [pagina, setPagina] = useState(1);
  // Filtro do admin: id da gerencia, SEM_GERENCIA ou "" (todas).
  const [gerencia, setGerencia] = useState("");
  // OS do alerta clicado ({ numero }); null = modal fechado.
  const [osAberta, setOsAberta] = useState(null);
  const topoRef = useRef(null);

  // Lista nova, recomeca da primeira pagina. O filtro fica, a nao ser que
  // a gerencia escolhida nao tenha mais alerta nenhum.
  useEffect(() => {
    setPagina(1);
    setGerencia((g) => (g && !opcoesGerencia(alertas || []).some((o) => o.valor === g) ? "" : g));
  }, [alertas]);

  const lista = alertas || [];
  const opcoes = isAdmin ? opcoesGerencia(lista) : [];
  const filtrados = lista.filter((a) => daGerencia(a, gerencia));
  const porTipo = filtrados.reduce((acc, a) => ({ ...acc, [a.tipo]: (acc[a.tipo] || 0) + 1 }), {});
  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
  const daPagina = filtrados.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);

  function trocarGerencia(valor) {
    setGerencia(valor);
    setPagina(1);
  }

  /** Troca de pagina e volta ao topo do painel: a nova pagina comeca la. */
  function irPara(p) {
    setPagina(Math.min(Math.max(1, p), totalPaginas));
    topoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /** Abre o detalhe da OS do alerta. Enter e espaco valem como clique. */
  function abrirOS(alerta, e) {
    if (e?.type === "keydown") {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
    }
    setOsAberta({ numero: alerta.referencia });
  }

  return (
    <div className="card" ref={topoRef}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2>Alertas {alertas ? `(${gerencia ? `${filtrados.length} de ${lista.length}` : lista.length})` : ""}</h2>
        <button className="btn btn-outline" onClick={onAtualizar} disabled={carregando}>
          {carregando ? "Consultando o ATF..." : "Atualizar"}
        </button>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>
        {descreverRegras(config, isAdmin)}
        {alertas && filtrados.length > 0 && (
          <> {Object.entries(porTipo).map(([tipo, n]) => `${n} ${ROTULO_TIPO[tipo] || tipo}`).join(" · ")}.</>
        )}
      </p>

      {opcoes.length > 0 && (
        <div className="dash-filter-row">
          <div className="dash-filter-group">
            <label className="dash-filter-label" htmlFor="alertas-gerencia">Gerencia:</label>
            <select
              id="alertas-gerencia"
              value={gerencia}
              onChange={(e) => trocarGerencia(e.target.value)}
              className="dash-filter-select"
            >
              <option value="">Todas as gerencias ({lista.length})</option>
              {opcoes.map((o) => (
                <option key={o.valor} value={o.valor}>{o.nome} ({o.total})</option>
              ))}
            </select>
          </div>
          {gerencia && (
            <button className="btn btn-outline dash-filter-clear" onClick={() => trocarGerencia("")}>
              Limpar filtro
            </button>
          )}
        </div>
      )}

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
            {daPagina.map((alerta, i) => {
              // Sem numero de OS nao ha o que abrir.
              const clicavel = Boolean(alerta.referencia);
              return (
                <div
                  key={`${alerta.tipo}-${alerta.referencia}-${i}`}
                  className={`alerta-card${clicavel ? " alerta-card-clicavel" : ""}`}
                  {...(clicavel && {
                    role: "button",
                    tabIndex: 0,
                    title: "Clique para ver os detalhes da OS",
                    onClick: (e) => abrirOS(alerta, e),
                    onKeyDown: (e) => abrirOS(alerta, e),
                  })}
                >
                  <div className="alerta-header">
                    <span className="badge normal">{ROTULO_TIPO[alerta.tipo] || alerta.tipo.replace(/_/g, " ")}</span>
                  </div>
                  <h3 className="alerta-titulo">{alerta.titulo}</h3>
                  <p className="alerta-fiscal"><strong>{textoFiscais(alerta.fiscais)}</strong></p>
                  <p className="alerta-descricao">{alerta.descricao}</p>
                  <div className="alerta-rodape">
                    <span className="muted">Ref: {alerta.referencia}</span>
                    {clicavel && <span className="alerta-ver-os">Ver detalhes da OS ›</span>}
                  </div>
                </div>
              );
            })}
          </div>
          {totalPaginas > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
              <button className="small secondary" onClick={() => irPara(1)} disabled={pagina === 1}>«</button>
              <button className="small secondary" onClick={() => irPara(pagina - 1)} disabled={pagina === 1}>‹ Anterior</button>
              <span style={{ fontSize: 13, color: "#6b7280" }}>
                P&aacute;gina {pagina} de {totalPaginas} &mdash; {filtrados.length} alertas
              </span>
              <button className="small secondary" onClick={() => irPara(pagina + 1)} disabled={pagina === totalPaginas}>Pr&oacute;xima ›</button>
              <button className="small secondary" onClick={() => irPara(totalPaginas)} disabled={pagina === totalPaginas}>»</button>
            </div>
          )}
        </>
      )}

      <DetalheOS alvo={osAberta} onClose={() => setOsAberta(null)} />
    </div>
  );
}
