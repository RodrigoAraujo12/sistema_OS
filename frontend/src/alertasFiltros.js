/**
 * alertasFiltros.js – Filtros da aba de alertas, por tipo e por gerencia.
 *
 * Fora do componente para poderem ser testados sem navegador
 * (alertasFiltros.test.js, `npm test`). Sao so de tela: os alertas ja
 * chegam todos de uma vez, e filtrar nao vai ao ATF.
 */

/** Rotulo de cada tipo, na ordem em que a OS anda. */
export const ROTULO_TIPO = {
  os_sem_designacao: "sem designacao",
  os_sem_ciencia: "sem ciencia",
  os_sem_eventos: "nenhum evento",
  os_sem_evento_novo: "sem evento novo",
};

export function rotuloTipo(tipo) {
  return ROTULO_TIPO[tipo] || tipo.replace(/_/g, " ");
}

/** Valor do filtro para as OS que nenhuma gerencia do cadastro alcanca. */
export const SEM_GERENCIA = "sem";

/** O alerta esta na gerencia do filtro? "" e todas. */
export function daGerencia(alerta, filtro) {
  if (!filtro) return true;
  const gerencias = alerta.gerencias || [];
  if (filtro === SEM_GERENCIA) return gerencias.length === 0;
  return gerencias.some((g) => String(g.id) === filtro);
}

/** O alerta e do tipo do filtro? "" e todos. */
export function doTipo(alerta, filtro) {
  return !filtro || alerta.tipo === filtro;
}

/**
 * Gerencias que tem alerta, em ordem de nome, e por ultimo as OS sem
 * gerencia — a ausencia e informacao, nao some da tela.
 */
export function opcoesGerencia(lista) {
  const porId = new Map();
  let semGerencia = false;
  for (const a of lista) {
    if (!a.gerencias?.length) semGerencia = true;
    for (const g of a.gerencias || []) porId.set(g.id, { valor: String(g.id), nome: g.nome });
  }
  const opcoes = [...porId.values()].sort((x, y) => x.nome.localeCompare(y.nome));
  if (semGerencia) opcoes.push({ valor: SEM_GERENCIA, nome: "Sem gerencia cadastrada" });
  return opcoes;
}

/** Tipos que tem alerta, na ordem de ROTULO_TIPO; um tipo novo vai no fim. */
export function opcoesTipo(lista) {
  const presentes = new Set(lista.map((a) => a.tipo));
  const ordem = [...Object.keys(ROTULO_TIPO), ...[...presentes].filter((t) => !(t in ROTULO_TIPO))];
  return ordem.filter((t) => presentes.has(t)).map((t) => {
    const rotulo = rotuloTipo(t);
    return { valor: t, nome: rotulo.charAt(0).toUpperCase() + rotulo.slice(1) };
  });
}

/**
 * Aplica os dois filtros ("" e todos) e monta as opcoes dos <select>.
 *
 * A contagem de cada opcao respeita o outro filtro: com "sem ciencia"
 * escolhido, cada gerencia mostra quantos alertas de sem ciencia tem, e
 * "todas" mostra o total deles. Uma OS de duas gerencias conta nas duas,
 * como no dashboard. `comGerencia` falso (quem nao e admin) nao monta as
 * opcoes de gerencia.
 */
export function filtrarAlertas(lista, { tipo = "", gerencia = "" } = {}, comGerencia = true) {
  const naGerencia = lista.filter((a) => daGerencia(a, gerencia));
  const noTipo = lista.filter((a) => doTipo(a, tipo));
  return {
    filtrados: naGerencia.filter((a) => doTipo(a, tipo)),
    tipos: opcoesTipo(lista).map((o) => ({
      ...o, total: naGerencia.filter((a) => doTipo(a, o.valor)).length,
    })),
    totalTipos: naGerencia.length,
    gerencias: comGerencia
      ? opcoesGerencia(lista).map((o) => ({ ...o, total: noTipo.filter((a) => daGerencia(a, o.valor)).length }))
      : [],
    totalGerencias: noTipo.length,
  };
}
