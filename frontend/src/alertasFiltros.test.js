/**
 * Filtros da aba de alertas (alertasFiltros.js). Roda com `npm test`, no
 * runner do proprio Node: nao precisa de navegador nem de dependencia.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { SEM_GERENCIA, filtrarAlertas, opcoesTipo } from "./alertasFiltros.js";

const GOFE = { id: 1, nome: "GOFE" };
const GOAC = { id: 2, nome: "GOAC" };

const alerta = (referencia, tipo, gerencias = []) => ({ referencia, tipo, gerencias });

const LISTA = [
  alerta("A", "os_sem_designacao"),
  alerta("B", "os_sem_ciencia", [GOFE]),
  alerta("C", "os_sem_ciencia", [GOFE, GOAC]),
  alerta("D", "os_sem_eventos", [GOAC]),
  alerta("E", "os_sem_evento_novo", [GOFE]),
  alerta("F", "os_sem_evento_novo"),
];

const refs = (lista) => lista.map((a) => a.referencia);
const totais = (opcoes) => Object.fromEntries(opcoes.map((o) => [o.valor, o.total]));

test("sem filtro mostra tudo", () => {
  const r = filtrarAlertas(LISTA);
  assert.deepEqual(refs(r.filtrados), ["A", "B", "C", "D", "E", "F"]);
  assert.equal(r.totalTipos, 6);
  assert.equal(r.totalGerencias, 6);
});

test("cada tipo pega todos os alertas dele e so eles", () => {
  for (const { valor, total } of filtrarAlertas(LISTA).tipos) {
    const { filtrados } = filtrarAlertas(LISTA, { tipo: valor });
    assert.ok(filtrados.every((a) => a.tipo === valor), valor);
    assert.equal(filtrados.length, LISTA.filter((a) => a.tipo === valor).length, valor);
    assert.equal(filtrados.length, total, valor);
  }
});

test("os tipos somam o total: cada alerta tem um tipo so", () => {
  const r = filtrarAlertas(LISTA);
  assert.equal(r.tipos.reduce((s, o) => s + o.total, 0), r.totalTipos);
});

test("tipos na ordem em que a OS anda, com rotulo", () => {
  assert.deepEqual(
    opcoesTipo(LISTA).map((o) => o.nome),
    ["Sem designacao", "Sem ciencia", "Nenhum evento", "Sem evento novo"],
  );
});

test("tipo que a tela nao conhece aparece no fim, e nao some", () => {
  const opcoes = opcoesTipo([...LISTA, alerta("G", "os_tipo_futuro")]);
  assert.equal(opcoes.at(-1).valor, "os_tipo_futuro");
  assert.equal(opcoes.at(-1).nome, "Os tipo futuro");
});

test("so aparecem os tipos que tem alerta", () => {
  const opcoes = opcoesTipo([alerta("B", "os_sem_ciencia")]);
  assert.deepEqual(opcoes.map((o) => o.valor), ["os_sem_ciencia"]);
});

test("OS de duas gerencias aparece nas duas", () => {
  assert.deepEqual(refs(filtrarAlertas(LISTA, { gerencia: "1" }).filtrados), ["B", "C", "E"]);
  assert.deepEqual(refs(filtrarAlertas(LISTA, { gerencia: "2" }).filtrados), ["C", "D"]);
});

test("sem gerencia pega so quem nao tem gerencia, e fica por ultimo", () => {
  const r = filtrarAlertas(LISTA, { gerencia: SEM_GERENCIA });
  assert.deepEqual(refs(r.filtrados), ["A", "F"]);
  assert.deepEqual(r.gerencias.map((o) => o.nome), ["GOAC", "GOFE", "Sem gerencia cadastrada"]);
});

test("os dois filtros juntos", () => {
  const r = filtrarAlertas(LISTA, { tipo: "os_sem_ciencia", gerencia: "2" });
  assert.deepEqual(refs(r.filtrados), ["C"]);
});

test("a contagem de cada opcao respeita o outro filtro", () => {
  const r = filtrarAlertas(LISTA, { tipo: "os_sem_ciencia", gerencia: "1" });
  // Gerencias contadas so entre os alertas sem ciencia.
  assert.deepEqual(totais(r.gerencias), { 1: 2, 2: 1, [SEM_GERENCIA]: 0 });
  assert.equal(r.totalGerencias, 2);
  // Tipos contados so entre os alertas da GOFE.
  assert.deepEqual(totais(r.tipos), {
    os_sem_designacao: 0, os_sem_ciencia: 2, os_sem_eventos: 0, os_sem_evento_novo: 1,
  });
  assert.equal(r.totalTipos, 3);
});

test("combinacao sem alerta devolve lista vazia, sem tirar as opcoes", () => {
  const r = filtrarAlertas(LISTA, { tipo: "os_sem_designacao", gerencia: "1" });
  assert.deepEqual(r.filtrados, []);
  assert.equal(r.tipos.length, 4);
  assert.equal(r.gerencias.length, 3);
});

test("quem nao e admin nao tem opcoes de gerencia", () => {
  assert.deepEqual(filtrarAlertas(LISTA, {}, false).gerencias, []);
});

test("alerta sem o campo gerencias conta como sem gerencia", () => {
  const r = filtrarAlertas([{ referencia: "X", tipo: "os_sem_ciencia" }], { gerencia: SEM_GERENCIA });
  assert.deepEqual(refs(r.filtrados), ["X"]);
});
