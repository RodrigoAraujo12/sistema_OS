/**
 * DashboardFiltros.jsx – Barra de filtros das abas de dados reais do ATF.
 *
 * Usada pela aba "Ordens de Servico" e pela aba "Eventos", que filtram
 * dimensoes diferentes mas do mesmo jeito: um <select> por dimensao, e a
 * consulta so sai quando se clica em Aplicar.
 *
 * POR QUE O BOTAO, e nao aplicar a cada troca de <select>: na aba de OS
 * cada consulta desce ate o ATF e custa de 5 a 16 segundos (medido em
 * producao, 02/09/2026). Aplicando a cada troca, montar um recorte de
 * tres dimensoes dispararia tres varreduras, e as duas primeiras seriam
 * jogadas fora. A aba de Eventos responde em menos de um segundo e nao
 * precisaria disso, mas duas abas vizinhas com comportamentos diferentes
 * confundem mais do que o clique extra atrapalha.
 *
 * O botao so habilita quando ha algo a aplicar — sem isso ele viraria um
 * jeito de repetir a consulta que ja esta na tela.
 */

import React from "react";

/**
 * @param {Array} campos  [{ chave, label, vazio, opcoes: [{value,label}] }]
 * @param {Object} valores        estado atual, por chave
 * @param {Function} onChange     (chave, valor) => void
 * @param {Function} onAplicar    dispara a consulta
 * @param {Function} onLimpar     zera tudo e consulta
 * @param {boolean} pendente      ha diferenca entre a tela e a consulta feita
 * @param {boolean} loading       consulta em voo
 * @param {string} rotuloAplicar  texto do botao; a aba de OS troca por
 *                                "Gerar dashboard" porque la o clique nao
 *                                reaplica um painel que ja esta na tela —
 *                                e o unico jeito de monta-lo.
 */
export default function DashboardFiltros({
  campos, valores, onChange, onAplicar, onLimpar, pendente, loading,
  rotuloAplicar = "Aplicar",
}) {
  const ativos = campos.filter((c) => valores[c.chave]).length;

  return (
    <div className="dash-filter-row">
      {campos.map((campo) => (
        <div className="dash-filter-group" key={campo.chave}>
          <label className="dash-filter-label">{campo.label}:</label>
          <select
            value={valores[campo.chave] || ""}
            onChange={(e) => onChange(campo.chave, e.target.value)}
            className="dash-filter-select"
            disabled={loading || campo.opcoes.length === 0}
          >
            <option value="">{campo.vazio}</option>
            {campo.opcoes.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      ))}

      <button
        className="btn btn-primary"
        onClick={onAplicar}
        disabled={loading || !pendente}
      >
        {rotuloAplicar}
      </button>

      {ativos > 0 && (
        <button
          className="btn btn-outline dash-filter-clear"
          onClick={onLimpar}
          disabled={loading}
        >
          Limpar {ativos} filtro{ativos > 1 ? "s" : ""}
        </button>
      )}
    </div>
  );
}

/**
 * Opcoes de um <select> a partir de um corte ja devolvido pelo painel.
 *
 * Serve as dimensoes que NAO tem tabela de dominio deste lado —
 * procedimento e a gerencia do ATF. A lista sai do proprio resultado, o
 * que tem uma vantagem: so aparece o que existe no periodo, com a
 * contagem ao lado.
 *
 * Os grupos "vazios" ("Sem gerencia informada") ficam de fora: sao a
 * ausencia do dado, e o ATF nao tem como filtrar por ausencia — mandar
 * um codigo em branco e o mesmo que nao mandar filtro nenhum.
 */
export function opcoesDoCorte(linhas) {
  return (linhas || [])
    .filter((l) => !l.vazio && l.id !== null && l.id !== undefined)
    .map((l) => ({ value: String(l.id), label: `${l.rotulo} (${l.total})` }));
}

/** Opcoes a partir de um mapa codigo => descricao (constants.js). */
export function opcoesDoMapa(mapa) {
  return Object.entries(mapa)
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
}
