/**
 * atfFilters.js – Filtros de busca de OS e as regras do ATF (doc da listagem).
 *
 * Compartilhado entre o painel de Ordens de Servico e o gerador de
 * relatorios, que fazem a mesma consulta com saidas diferentes.
 */

/** Estado inicial dos filtros de busca de OS. */
export const EMPTY_OS_FILTERS = {
  numero: "",
  modelo: "",
  motivo_abertura: "",
  ie: "",
  cnpj: "",
  razao_social: "",
  matriculas: "",
  equipe_fiscal: "",
  orgao_executor: "",
  situacoes: [],
  data_abertura_inicio: "",
  data_abertura_fim: "",
  data_encerramento_inicio: "",
  data_encerramento_fim: "",
  data_ciencia_inicio: "",
  data_ciencia_fim: "",
};

/** Tamanho minimo aceito no filtro de razao social. */
export const RAZAO_SOCIAL_MIN = 6;

/**
 * Valida os filtros contra as regras do ATF.
 * Retorna a mensagem de erro, ou null se estiver tudo certo.
 */
export function validarFiltrosOS(f) {
  const aberturaCompleta = Boolean(f.data_abertura_inicio && f.data_abertura_fim);
  const encerramentoCompleto = Boolean(f.data_encerramento_inicio && f.data_encerramento_fim);
  const temPeriodo = aberturaCompleta || encerramentoCompleto;
  const razaoValida = Boolean(f.razao_social && f.razao_social.length >= RAZAO_SOCIAL_MIN);

  const hasFilter =
    f.numero ||
    f.modelo ||
    f.motivo_abertura ||
    f.ie ||
    f.cnpj ||
    razaoValida ||
    f.matriculas ||
    f.equipe_fiscal ||
    f.orgao_executor ||
    f.situacoes.length > 0 ||
    f.data_abertura_inicio ||
    f.data_abertura_fim ||
    f.data_encerramento_inicio ||
    f.data_encerramento_fim ||
    f.data_ciencia_inicio ||
    f.data_ciencia_fim;

  if (!hasFilter) return "Informe ao menos um filtro para pesquisar.";
  if (f.razao_social && f.razao_social.length < RAZAO_SOCIAL_MIN)
    return `Razão Social: mínimo de ${RAZAO_SOCIAL_MIN} caracteres.`;

  // Periodos devem ser informados conjuntamente (inicio e fim)
  if ((f.data_abertura_inicio || f.data_abertura_fim) && !aberturaCompleta)
    return "Período de abertura: informe início e fim.";
  if ((f.data_encerramento_inicio || f.data_encerramento_fim) && !encerramentoCompleto)
    return "Período de encerramento: informe início e fim.";

  // Modelo, motivo, situacao, equipe e orgao exigem periodo.
  // Regra b da doc da listagem: combinados com UM dos periodos — abertura OU
  // encerramento. (Em 10/08/2026 o ambiente de dev do ATF rejeitou busca
  // com apenas um periodo, divergindo da doc; divergencia em apuracao
  // junto ao ATF — ver docs/teste_regra_periodo_atf.md.)
  const exigePeriodo =
    f.modelo || f.motivo_abertura || f.situacoes.length > 0 ||
    f.equipe_fiscal || f.orgao_executor;
  if (exigePeriodo && !temPeriodo)
    return "Modelo, Motivo, Situação, Equipe e Órgão exigem um período preenchido: abertura (início e fim) ou encerramento (início e fim).";

  // Busca exclusivamente por periodo: no maximo um ano
  const apenasPeriodo =
    temPeriodo &&
    !f.numero && !f.modelo && !f.motivo_abertura && !f.ie && !f.cnpj &&
    !razaoValida && !f.matriculas && !f.equipe_fiscal && !f.orgao_executor &&
    f.situacoes.length === 0;
  if (apenasPeriodo) {
    const umAnoMs = 366 * 24 * 60 * 60 * 1000;
    const ini = aberturaCompleta ? f.data_abertura_inicio : f.data_encerramento_inicio;
    const fim = aberturaCompleta ? f.data_abertura_fim : f.data_encerramento_fim;
    if (new Date(fim) - new Date(ini) > umAnoMs)
      return "Busca apenas por período: intervalo máximo de um ano.";
  }

  return null;
}

/** Converte os filtros do formulario no payload aceito pelo apiClient. */
export function filtrosParaPayload(f) {
  return {
    numero: f.numero || null,
    modelo: f.modelo || null,
    motivo_abertura: f.motivo_abertura || null,
    ie: f.ie || null,
    cnpj: f.cnpj || null,
    razao_social: f.razao_social || null,
    matriculas: f.matriculas || null,
    equipe_fiscal: f.equipe_fiscal || null,
    orgao_executor: f.orgao_executor || null,
    situacoes: f.situacoes.length > 0 ? f.situacoes : null,
    data_abertura_inicio: f.data_abertura_inicio || null,
    data_abertura_fim: f.data_abertura_fim || null,
    data_encerramento_inicio: f.data_encerramento_inicio || null,
    data_encerramento_fim: f.data_encerramento_fim || null,
    data_ciencia_inicio: f.data_ciencia_inicio || null,
    data_ciencia_fim: f.data_ciencia_fim || null,
  };
}
