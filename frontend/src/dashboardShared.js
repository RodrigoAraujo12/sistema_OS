/**
 * dashboardShared.js – O que as abas de dados reais do ATF tem em comum.
 *
 * Nasceu quando a aba de Eventos (bloco 2 da demanda de 31/08/2026) foi
 * escrita ao lado da de Ordens de Servico (bloco 1): datas, formatacao e
 * cores eram identicas nas duas, e cor duplicada e cor que diverge na
 * primeira vez que alguem mexe em uma sem lembrar da outra.
 *
 * O que NAO esta aqui, de proposito: a lista de periodos oferecidos. As
 * duas abas oferecem quase os mesmos, mas por motivos diferentes — a de
 * OS evita janelas largas porque a listagem custa dezenas de segundos, a
 * de Eventos porque o ATF recusa periodo maior que um ano.
 */

// ─── Cores dos cortes ───────────────────────────────────────────

export const COR_TOTAL = "#3b82f6";
export const COR_TEMPO = "#f59e0b";

/** Cinza do grupo "Sem <dimensao>": e um buraco no dado, nao uma
 *  categoria — pintar igual as outras o faria passar por uma. */
export const COR_VAZIO = "#94a3b8";

/** Paleta do grafico de tipo (4 modelos de OS no ATF, com folga). */
export const PALETA_TIPO = ["#1a3a6c", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#94a3b8"];

/**
 * Quantas barras cabem antes do grafico virar uma parede ilegivel.
 * Motivo tem ~100 valores ativos e fiscal passa de 300 — nesses dois o
 * grafico mostra o topo e a tabela logo abaixo mostra o resto.
 */
export const TOPO_GRAFICO = 15;

// ─── Datas ──────────────────────────────────────────────────────

/** Data em YYYY-MM-DD pelo relogio LOCAL. toISOString() converteria para
 *  UTC e, de tarde no fuso de Brasilia, mandaria o dia seguinte. */
export function iso(data) {
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return `${data.getFullYear()}-${mes}-${dia}`;
}

/** Converte a opcao de periodo no par de datas enviado ao backend. */
export function intervaloDe(periodo) {
  const hoje = new Date();
  if (periodo === "ano") {
    return { inicio: `${hoje.getFullYear()}-01-01`, fim: iso(hoje) };
  }
  const inicio = new Date(hoje);
  inicio.setDate(hoje.getDate() - parseInt(periodo, 10));
  return { inicio: iso(inicio), fim: iso(hoje) };
}

// ─── Formatacao ─────────────────────────────────────────────────

export function formatarDias(valor) {
  if (valor === null || valor === undefined) return "—";
  return `${valor.toLocaleString("pt-BR")} d`;
}

export function formatarNumero(valor) {
  return (valor ?? 0).toLocaleString("pt-BR");
}
