/**
 * prazosProcedimento.js – Quais procedimentos a tabela de prazos mostra
 * para uma supervisao (Cadastros -> Prazos dos alertas).
 *
 * Fora do componente para poder ser testado sem navegador
 * (prazosProcedimento.test.js, `npm test`).
 */

/**
 * Linhas da tabela de uma supervisao, em ordem alfabetica:
 * [{codigo, nome, eventos}].
 *
 * Pedido de 15/10/2026: a tabela mostra o que a supervisao lancou, e nao
 * todos os procedimentos do ATF.
 *
 * - `catalogo`: {codigo: nome} (procedimentoLabels). Procedimento lancado
 *   que ainda nao esta nele entra com o nome que o ATF mandou;
 * - `lancados`: [{procedimento_codigo, procedimento, eventos}] da
 *   supervisao nos ultimos 12 meses, ou null quando a lista nao veio
 *   (servico de eventos fora): ai mostra todos;
 * - `gravado` ({codigo: dias}) e `rascunho` ({codigo: "texto"}): o que
 *   tem prazo salvo ou digitado nunca some, mesmo sem evento no ano.
 *   Senao um prazo salvo continuaria valendo sem ninguem ver, nem poder
 *   apagar;
 * - `todos`: o "mostrar todos" da tela.
 */
export function linhasDaSupervisao({ catalogo, lancados, gravado = {}, rascunho = {}, todos = false }) {
  const nomes = new Map(Object.entries(catalogo).map(([codigo, nome]) => [Number(codigo), nome]));
  const eventos = new Map();
  for (const p of lancados || []) {
    eventos.set(p.procedimento_codigo, p.eventos);
    if (!nomes.has(p.procedimento_codigo)) {
      nomes.set(p.procedimento_codigo, p.procedimento || `Procedimento ${p.procedimento_codigo}`);
    }
  }

  const fixos = new Set(Object.keys(gravado).map(Number));
  for (const [codigo, valor] of Object.entries(rascunho)) {
    if (String(valor ?? "").trim() !== "") fixos.add(Number(codigo));
  }
  for (const codigo of fixos) {
    if (!nomes.has(codigo)) nomes.set(codigo, `Procedimento ${codigo}`);
  }

  const mostrar = (codigo) => todos || lancados == null || eventos.has(codigo) || fixos.has(codigo);
  return [...nomes.entries()]
    .filter(([codigo]) => mostrar(codigo))
    .map(([codigo, nome]) => ({ codigo, nome, eventos: eventos.get(codigo) ?? 0 }))
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}
