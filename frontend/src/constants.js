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

/** Motivos de abertura ATIVOS da OS no ATF (cdMotivoAbertOS => descricao).
 *  Fonte: doc da listagem; motivos marcados (INATIVO) foram omitidos. */
export const motivoLabels = {
  163: "ALTERACAO CADASTRAL",
  164: "ANALISE DE CREDITO",
  165: "ATENDIMENTO DEMANDA EXTERNA",
  166: "ATENDIMENTO DEMANDA SER-PB",
  167: "BENEFÍCIO FISCAL",
  168: "DENÚNCIA FISCAL",
  169: "DOCS ELETRÔNICOS X EFD / GIM",
  170: "DOCS ELETRÔNICOS OU PGDAS D",
  171: "ECF - CESSAÇÃO",
  172: "ECF - OUTROS",
  173: "ENTRADAS X SAÍDAS",
  174: "INADIMPLÊNCIA",
  176: "INSCRIÇÃO ESTADUAL",
  177: "LEVANTAMENTO DA CONTA MERCADORIAS",
  178: "LEVANTAMENTO DE ESTOQUE",
  179: "MONITORAMENTO",
  180: "OUTRAS INCONSISTÊNCIAS EFD / GIM",
  181: "OUTRAS INCONSISTÊNCIAS PGDASD",
  182: "OUTROS",
  183: "PROGRAMAÇÃO FISCAL",
  184: "PEDIDO DE RESSARCIMENTO",
  185: "REVISÃO / CANCELAMENTO DE DAR / FATURA",
  186: "REVISÃO / COMPLEMENTO / NOVO FEITO",
  187: "SUBSTITUIÇÃO TRIBUTÁRIA",
  188: "VALOR ADICIONADO - IPM",
  189: "VENDAS X CARTAO DE CREDITO",
  191: "INATIVAÇÃO CADASTRAL",
  192: "MONITORAMENTO SIMPLES NACIONAL",
  193: "MALHA DECADÊNCIA 2017 - 2018",
  194: "ACOMPANHAMENTO PERMANENTE",
  195: "MALHA FISCAL",
  196: "BD MALHA - MALHA FISCAL",
  197: "MONITORAMENTO SCANC",
  198: "PEDIDO DE RESTITUIÇÃO",
  200: "ATEND SER GT/COTEPE",
  202: "AUD ALTERACAO CADASTRAL",
  203: "AUD COMP _ PROGRAMAÇÃO_ INDICADORES",
  204: "AUD COMPLETA _ SOLICITAÇÃO",
  205: "AUD COMPLETA _ SUBST TRIBUTÁRIA",
  207: "ATEND EXT MINISTÉRIO PÚBLICO",
  208: "ATEND EXT TRIB JUSTICA",
  210: "ATEND EXT TRIBUNAL DE CONTAS",
  211: "ATEND EXT. OUTROS",
  212: "AI DILIGÊNCIA CRF",
  213: "AI DILIGÊNCIA GEJUP",
  214: "AI REVISÃO",
  215: "AI NOVO FEITO",
  216: "AI TERMO COMP. INFRACAO",
  217: "REGIME ESPECIAL",
  218: "AUDITORIA DE CONFORMIDADE",
  219: "PEDIDO RESSARCIMENTO",
  220: "PEDIDO RESTITUIÇÃO",
  221: "LIBERAÇÃO SELO FISCAL",
  223: "RETIFICAÇÃO ANEXO SCANC",
  225: "IMPORTACAO/EXPORTACAO",
  226: "ZONA FRANCA MANAUS/AREAS LIVRE COMÉRCIO",
  227: "MONIT SMTC",
  228: "MONIT PMPF",
  229: "MONIT MOINHOS/FARINHA DE TRIGO",
  230: "MONIT OMISSO/INADIMPLÊNCIA",
  231: "AUD INATIVAÇÃO CADASTRAL",
  232: "CONTAGEM DE ESTOQUE",
  233: "EC 87/2015 DIFAL NÃO CONTRIBUINTE",
  234: "ATEND EXT DENÚNCIA FISCAL",
  235: "ATEND EXT PGE",
  236: "VALOR ADICIONADO IPM",
  237: "ATENDIMENTO DEMANDA INTERNA DA SEFAZ PB",
  238: "ATENDIMENTO DEMANDA EXTERNA (OUTROS ÓRGÃOS)",
  239: "DIFAL NÃO CONTRIBUINTES",
  241: "MONITORAMENTO SMPC",
};

/** Orgaos executores de OS (codigo no ATF => sigla).
 *  Lista fechada, informada pela area fiscal em 17/08/2026. O ATF nao
 *  expoe endpoint para consultar esses codigos, entao ficam fixos aqui —
 *  se a area criar/extinguir um orgao, e aqui que se atualiza. */
export const orgaoExecutorLabels = {
  4: "GR2",
  5: "GR3",
  147: "P.F-N LOPES-CAJAZEIR",
  254: "GOFE-GEFTE",
  255: "SUPEA-GOFE",
  275: "GOFSE",
  337: "SGFE-GR4",
  339: "GOFMT",
  378: "SGFMT-GR3",
  379: "SGFE-GR5",
  380: "SGFE-GR2",
  383: "SGFMT-GR1",
  384: "SGFE-GR3",
  512: "GOFITCD/IPVA",
  513: "GOAC",
  535: "SF-SGFE-GR1",
  575: "GOP-GEFTE",
  629: "GECOF",
};

/** Opcoes do filtro de orgao executor, em ordem alfabetica pela sigla.
 *  Diferente de modelo/motivo, aqui a sigla vem antes do codigo: quem usa
 *  o filtro conhece a sigla e nao o numero, e num <select> nativo digitar
 *  as primeiras letras so salta para a opcao quando o texto comeca por elas. */
export const orgaoExecutorOptions = Object.entries(orgaoExecutorLabels)
  .map(([codigo, sigla]) => ({ codigo, sigla }))
  .sort((a, b) => a.sigla.localeCompare(b.sigla, "pt-BR"));

/** Procedimentos de evento do ATF (cdProcedimento => noProcedimento).
 *  Os 29 que aparecem nos eventos de OS abertas de 10/2025 a 10/2026,
 *  medido em producao em 13/10/2026 — o ATF nao expoe a tabela, e os
 *  codigos que faltam (4, 5, 8...) nao tiveram evento no periodo. E o
 *  "mostrar todos" da tabela de prazos por procedimento dos alertas; um
 *  procedimento novo que a supervisao lancar aparece la mesmo sem estar
 *  aqui, com o nome que o ATF mandar. Os nomes vao como o ATF escreve,
 *  com o travessao que ele manda quebrado ja corrigido. */
export const procedimentoLabels = {
  1: "AUDITORIA DA CONTA CAIXA",
  2: "AUDITORIA DA CONTA BANCOS",
  3: "AUDITORIA DO PASSIVO",
  6: "AUDITORIA NA ESCRITA CONTÁBIL",
  7: "CONFRONTO FISCAL/CONTÁBIL",
  9: "AUDITORIA NA ESCRITA FISCAL E CONTÁBIL",
  10: "AUDITORIA NA ESCRITA FISCAL",
  12: "ACERCA DE NÃO CONTENCIOSOS",
  13: "LEVANTAMENTO FINANCEIRO",
  14: "LEVANTAMENTO QUANTITATIVO DE MERCADORIAS",
  15: "AUDITORIA - SUBSTITUIÇÃO TRIBUTÁRIA",
  16: "CONTA MERCADORIAS",
  17: "AUDITORIA - PROC. ELETRÔNICO DE DADOS",
  19: "OUTROS",
  20: "AUDITORIA - ECF",
  21: "AUDITORIA - OBRIG. ACESSÓRIA",
  23: "AUDITORIA - SELO DE AUTENTICAÇÃO FISCAL",
  29: "AUDITORIA-SIMPLES NACIONAL",
  31: "AUDITORIA OBRIGAÇÃO PRINCIPAL",
  32: "AUDITORIA - VENDAS COM CARTÃO DE CRÉDITO/DÉBITO",
  33: "AUDITORIA – CONFORMIDADE (EFD X DOCUMENTOS FISCAIS",
  35: "AUDITORIA - CRÉDITOS",
  37: "AUDITORIA - TRIBUTAÇÃO DE ITEM/PRODUTO ESPECÍFICO",
  38: "AUDITORIA - MUDANÇA DE REGIME DE APURAÇÃO",
  39: "AUDITORIA - ICMS DIFERENCIAL DE ALÍQUOTA/FRONTEIRA",
  40: "AUDITORIA - CONFORMIDADE (EFD X TRANSPORTE SALDO)",
  42: "AUDITORIA – DÉBITOS",
  43: "AUDITORIA – CONFORMIDADE (APURAÇÃO EFD)",
  44: "DIFAL NÃO CONTRIBUINTES",
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
  // O ATF nem sempre manda data: alguns campos sao referencia de periodo
  // ("01/2024") e o backend os repassa crus. Sem esta guarda, o split por
  // "-" produziria "undefined/undefined/01/2024".
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(dataISO);
  if (!partes) return dataISO;
  const [, ano, mes, dia] = partes;
  return `${dia}/${mes}/${ano}`;
}
