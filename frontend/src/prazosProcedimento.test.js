/**
 * Linhas da tabela de prazos por supervisao (prazosProcedimento.js). Roda
 * com `npm test`, no runner do proprio Node.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { linhasDaSupervisao } from "./prazosProcedimento.js";

const CATALOGO = { 10: "AUDITORIA NA ESCRITA FISCAL", 19: "OUTROS", 35: "AUDITORIA - CRÉDITOS" };
const lancado = (codigo, eventos, procedimento = "") => ({ procedimento_codigo: codigo, procedimento, eventos });
const codigos = (linhas) => linhas.map((l) => l.codigo);

test("mostra so o que a supervisao lancou, em ordem alfabetica, com os eventos", () => {
  const linhas = linhasDaSupervisao({ catalogo: CATALOGO, lancados: [lancado(19, 40), lancado(10, 3)] });
  assert.deepEqual(linhas, [
    { codigo: 10, nome: "AUDITORIA NA ESCRITA FISCAL", eventos: 3 },
    { codigo: 19, nome: "OUTROS", eventos: 40 },
  ]);
});

test("prazo salvo ou digitado nao some, mesmo sem evento no ano", () => {
  const linhas = linhasDaSupervisao({
    catalogo: CATALOGO, lancados: [lancado(19, 5)], gravado: { 35: 20 }, rascunho: { 10: "15", 35: "" },
  });
  assert.deepEqual(codigos(linhas), [35, 10, 19]);
});

test("rascunho apagado de procedimento nao lancado volta a sumir", () => {
  const linhas = linhasDaSupervisao({ catalogo: CATALOGO, lancados: [], rascunho: { 10: "  " } });
  assert.deepEqual(linhas, []);
});

test("mostrar todos traz o catalogo inteiro", () => {
  const linhas = linhasDaSupervisao({ catalogo: CATALOGO, lancados: [lancado(19, 5)], todos: true });
  assert.deepEqual(codigos(linhas), [35, 10, 19]);
});

test("sem a lista do ATF mostra todos", () => {
  assert.deepEqual(codigos(linhasDaSupervisao({ catalogo: CATALOGO, lancados: null })), [35, 10, 19]);
});

test("procedimento fora do catalogo entra com o nome do ATF", () => {
  const linhas = linhasDaSupervisao({ catalogo: CATALOGO, lancados: [lancado(50, 1, "AUDITORIA NOVA")] });
  assert.deepEqual(linhas, [{ codigo: 50, nome: "AUDITORIA NOVA", eventos: 1 }]);
});
