/**
 * constants.js – Constantes e utilitarios compartilhados entre componentes.
 */

/** Opcoes de cargo para criacao/edicao de usuarios. */
export const roleOptions = [
  { value: "gerente", label: "Gerente" },
  { value: "supervisor", label: "Supervisor" },
  { value: "fiscal", label: "Fiscal" },
];

/** Situacoes reais da OS no ATF (codigo => descricao). */
export const situacaoLabels = {
  0: "AGUARDANDO AUTORIZAÇÃO",
  1: "AUTORIZADA",
  2: "CANCELADA",
  3: "SUBSTITUÍDA",
  4: "ENCERRADA",
  5: "BLOQUEADA",
  6: "EM ANÁLISE PARA ENCERRAMENTO",
  7: "EXECUÇÃO SUSPENSA",
};

/** Modelos de OS com seus codigos numericos no ATF. */
export const modeloLabels = {
  1: "NORMAL",
  2: "SIMPLIFICADA",
  7: "ESPECIAL",
  8: "ESPECÍFICA",
};

/** Mantido para compatibilidade com componentes de dashboard. */
export const statusLabels = {
  aberta: "Aberta",
  em_andamento: "Em Andamento",
  concluida: "Concluida",
  cancelada: "Cancelada",
};

/** Mantido para compatibilidade com componentes de dashboard. */
export const tipoLabels = {
  Normal: "Normal",
  Especifico: "Especifico",
  Simplificado: "Simplificado",
};

/** Formata data de YYYY-MM-DD para DD/MM/AAAA. */
export function formatarData(dataISO) {
  if (!dataISO) return "-";
  const [ano, mes, dia] = dataISO.split("-");
  return `${dia}/${mes}/${ano}`;
}
