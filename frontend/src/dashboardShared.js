/**
 * dashboardShared.js – O que as abas de dados reais do ATF tem em comum.
 *
 * Nasceu quando a aba de Eventos (bloco 2 da demanda de 31/08/2026) foi
 * escrita ao lado da de Ordens de Servico (bloco 1): datas, formatacao e
 * cores eram identicas nas duas, e cor duplicada e cor que diverge na
 * primeira vez que alguem mexe em uma sem lembrar da outra.
 *
 * A lista de periodos da aba de Eventos NAO esta aqui, de proposito: ela
 * oferece quase os mesmos, mas por outro motivo — o ATF recusa periodo
 * maior que um ano. Os de abertura (PERIODOS_ABERTURA) estao, porque
 * valem para toda aba sobre a listagem de OS, que custa dezenas de
 * segundos por janela larga.
 */

// ─── Cores dos cortes ───────────────────────────────────────────

export const COR_TOTAL = "#3b82f6";
export const COR_TEMPO = "#f59e0b";

/** Cinza do grupo "Sem <dimensao>": e um buraco no dado, nao uma
 *  categoria — pintar igual as outras o faria passar por uma. */
export const COR_VAZIO = "#94a3b8";

/** Paleta do grafico de tipo (4 modelos de OS no ATF, com folga). */
export const PALETA_TIPO = ["#1a3a6c", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#94a3b8"];

/** Os quatro grupos de situacao do painel de desempenho (ver
 *  _grupo_situacao, no backend). */
export const COR_GRUPO = {
  em_andamento: "#f59e0b",
  bloqueada: "#ef4444",
  encerrada: "#22c55e",
  cancelada: "#94a3b8",
};

/** Uma cor por situacao do ATF (statusOS), para a pizza separar as que
 *  caem no mesmo grupo — autorizada e suspensa sao ambas "em andamento". */
export const COR_SITUACAO = {
  0: "#a78bfa", // aguardando autorizacao
  1: "#3b82f6", // autorizada
  2: "#64748b", // cancelada
  3: "#cbd5e1", // substituida
  4: "#22c55e", // encerrada
  5: "#ef4444", // bloqueada
  6: "#14b8a6", // em analise para encerramento
  7: "#f59e0b", // execucao suspensa
};

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

// ─── Periodo de abertura ────────────────────────────────────────

/**
 * Atalhos de periodo. Sao so isso: preenchem as duas datas e NAO
 * consultam nada — a consulta sai no botao, como na tela de Ordens de
 * Servico. Valem para toda aba que le a LISTAGEM de OS do ATF (a de OS
 * e as de desempenho). Nenhum passa de um ano, que e o teto do periodo aqui.
 *
 * Nao ha "Todos" nem "Personalizado": os campos de data estao sempre na
 * tela, entao qualquer intervalo (dentro do teto) e digitavel, e a base
 * inteira nao cabe — a consulta desce ate o ATF e um ano ja sao milhares
 * de OS e dezenas de segundos de espera.
 */
export const PERIODOS_ABERTURA = [
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "180", label: "6 meses" },
  { value: "ano", label: "Ano atual" },
  { value: "365", label: "12 meses" },
];

/** Teto do periodo: um ano. 366 dias para o ano bissexto caber inteiro —
 *  mesmo numero da busca so por periodo em atfFilters.js. */
const LIMITE_DIAS = 366;

/**
 * Valida o periodo ANTES de gastar uma varredura no ATF.
 * Retorna a mensagem de erro, ou null se estiver tudo certo.
 *
 * As datas vem de <input type="date">, sempre em YYYY-MM-DD: comparar
 * como texto ja da a ordem certa, sem passar por Date.
 */
export function validarPeriodoAbertura(inicio, fim) {
  if (!inicio || !fim) return "Informe o periodo de abertura: inicio e fim.";
  if (inicio > fim) return "Periodo de abertura: o inicio nao pode ser depois do fim.";
  const dias = (new Date(fim) - new Date(inicio)) / 86400000;
  if (dias > LIMITE_DIAS) return "Periodo de abertura: no maximo um ano entre inicio e fim.";
  return null;
}

// ─── Formatacao ─────────────────────────────────────────────────

export function formatarDias(valor) {
  if (valor === null || valor === undefined) return "—";
  return `${valor.toLocaleString("pt-BR")} d`;
}

export function formatarNumero(valor) {
  return (valor ?? 0).toLocaleString("pt-BR");
}
