/**
 * constants.js – Constantes e utilitarios compartilhados entre componentes.
 */

/** Opcoes de cargo para criacao/edicao de usuarios. */
export const roleOptions = [
  { value: "gerente", label: "Gerente" },
  { value: "supervisor", label: "Supervisor" },
  { value: "fiscal", label: "Fiscal" },
];

/** Mapeamento de status da OS para exibicao. */
export const statusLabels = {
  aberta: "Aberta",
  em_andamento: "Em Andamento",
  concluida: "Concluida",
  cancelada: "Cancelada",
};

/** Mapeamento de tipo da OS para exibicao. */
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
