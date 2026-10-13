/**
 * AlertasConfig.jsx – Prazos dos alertas (admin).
 *
 * Os dias de cada regra de alerta e a janela de busca, gravados no banco
 * local (PUT /admin/alertas/config), e a tabela de prazo por procedimento
 * de cada gerencia (PUT /admin/alertas/prazos-procedimento/{id}). Valem da
 * proxima consulta de alertas em diante: ao salvar, o App descarta os
 * alertas ja carregados.
 */

import React, { useEffect, useState } from "react";
import apiClient from "../api.js";
import { procedimentoLabels } from "../constants.js";

const CAMPOS = [
  {
    chave: "dias_sem_designacao",
    rotulo: "OS sem designacao",
    ajuda: "Dias desde a abertura da OS sem fiscal designado. So o admin ve este alerta: sem fiscal, a OS nao se liga a ninguem.",
    min: 0,
  },
  {
    chave: "dias_sem_ciencia",
    rotulo: "OS sem ciencia",
    ajuda: "Dias desde a designacao sem o fiscal dar ciencia. O proprio ATF bloqueia a OS depois de 3 dias sem ciencia.",
    min: 0,
  },
  {
    chave: "dias_sem_eventos",
    rotulo: "OS sem eventos",
    ajuda: "Dias sem evento na OS autorizada, contando do ultimo evento, ou da ciencia quando ainda nao teve nenhum.",
    min: 0,
  },
  {
    chave: "janela_dias",
    rotulo: "Janela de busca",
    ajuda: "Os alertas olham as OS abertas nos ultimos N dias. No maximo 365, o limite do ATF.",
    min: 1,
  },
];

const MAXIMO = 365;

const PROCEDIMENTOS = Object.entries(procedimentoLabels)
  .map(([codigo, nome]) => ({ codigo: Number(codigo), nome }))
  .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));

/** {codigo: dias} gravado -> {codigo: "texto"} do formulario. */
function paraTexto(prazos) {
  return Object.fromEntries(Object.entries(prazos || {}).map(([c, d]) => [c, String(d)]));
}

/** So o que foi preenchido; vazio volta ao prazo geral. */
function preenchidos(rascunho) {
  return Object.entries(rascunho || {}).filter(([, v]) => String(v).trim() !== "");
}

/**
 * Tabela gerencia x procedimento -> dias do alerta "sem evento".
 *
 * Uma gerencia por vez, escolhida no select. O que se digita fica num
 * rascunho por gerencia: trocar de gerencia nao perde nada, e o select
 * marca as que tem alteracao por salvar. Salvar grava so a gerencia da
 * tela, e troca a tabela inteira dela — procedimento deixado em branco
 * volta ao prazo geral.
 */
function PrazosPorProcedimento({ gerencias, prazoGeral, onSaved, onMessage, onError }) {
  const [gravado, setGravado] = useState(null); // {gerencia_id: {codigo: dias}}
  const [rascunhos, setRascunhos] = useState({}); // {gerencia_id: {codigo: "texto"}}
  const [gerenciaId, setGerenciaId] = useState("");
  const [salvando, setSalvando] = useState(false);

  const ordenadas = [...(gerencias || [])].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));

  useEffect(() => {
    apiClient.listarPrazosProcedimento()
      .then((lista) => {
        const porGerencia = Object.fromEntries(lista.map((g) => [
          g.gerencia_id,
          Object.fromEntries(g.prazos.map((p) => [p.procedimento_codigo, p.dias])),
        ]));
        setGravado(porGerencia);
        setRascunhos(Object.fromEntries(
          Object.entries(porGerencia).map(([id, prazos]) => [id, paraTexto(prazos)])
        ));
      })
      .catch((err) => onError(err.message));
  }, []);

  // Primeira gerencia da lista assim que ela chegar.
  useEffect(() => {
    if (!gerenciaId && ordenadas.length) setGerenciaId(String(ordenadas[0].id));
  }, [gerencias]);

  function alterado(id) {
    const salvo = paraTexto(gravado?.[id]);
    const atual = Object.fromEntries(preenchidos(rascunhos[id]).map(([c, v]) => [c, String(v).trim()]));
    return JSON.stringify(Object.entries(salvo).sort()) !== JSON.stringify(Object.entries(atual).sort());
  }

  function mudarDias(codigo, valor) {
    setRascunhos((r) => ({ ...r, [gerenciaId]: { ...(r[gerenciaId] || {}), [codigo]: valor } }));
  }

  async function salvar(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    const prazos = [];
    for (const [codigo, valor] of preenchidos(rascunhos[gerenciaId])) {
      const dias = Number(valor);
      if (!Number.isInteger(dias) || dias < 0 || dias > MAXIMO) {
        onError(`${procedimentoLabels[codigo] || codigo}: informe um numero inteiro de 0 a ${MAXIMO}, ou deixe em branco.`);
        return;
      }
      prazos.push({ procedimento_codigo: Number(codigo), dias });
    }
    setSalvando(true);
    try {
      const salvo = await apiClient.salvarPrazosProcedimento(gerenciaId, prazos);
      const novos = Object.fromEntries(salvo.prazos.map((p) => [p.procedimento_codigo, p.dias]));
      setGravado((g) => ({ ...g, [gerenciaId]: novos }));
      setRascunhos((r) => ({ ...r, [gerenciaId]: paraTexto(novos) }));
      onSaved();
      const nome = ordenadas.find((g) => String(g.id) === gerenciaId)?.name;
      onMessage(`Prazos por procedimento de ${nome} salvos. Valem a partir da proxima consulta de alertas.`);
    } catch (err) {
      onError(err.message);
    } finally {
      setSalvando(false);
    }
  }

  const rascunho = rascunhos[gerenciaId] || {};

  return (
    <div className="card">
      <h2>Prazo por procedimento</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Quantos dias a OS pode ficar sem evento novo, conforme o procedimento do ultimo evento.
        Vale para as OS da gerencia, que sai dos fiscais da OS. Eventos seguidos do mesmo
        procedimento contam como um so: a contagem parte do primeiro, porque a OS nao andou.
        Em branco, vale o prazo geral de "OS sem eventos"
        {prazoGeral !== undefined && prazoGeral !== "" ? ` (${prazoGeral} dias)` : ""}.
      </p>
      {!gravado ? (
        <p className="muted">Carregando...</p>
      ) : !ordenadas.length ? (
        <p className="muted">Nenhuma gerencia cadastrada.</p>
      ) : (
        <form onSubmit={salvar} className="form" style={{ maxWidth: 720 }}>
          <label style={{ maxWidth: 520 }}>
            Gerencia
            <select value={gerenciaId} onChange={(e) => setGerenciaId(e.target.value)}>
              {ordenadas.map((g) => {
                const n = preenchidos(rascunhos[g.id]).length;
                return (
                  <option key={g.id} value={g.id}>
                    {g.name}
                    {n ? ` (${n} com prazo)` : ""}
                    {alterado(g.id) ? " - nao salvo" : ""}
                  </option>
                );
              })}
            </select>
          </label>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Procedimento</th>
                  <th style={{ width: 120 }}>Dias</th>
                </tr>
              </thead>
              <tbody>
                {PROCEDIMENTOS.map(({ codigo, nome }) => (
                  <tr key={codigo}>
                    <td>{nome}</td>
                    <td>
                      <input
                        type="number"
                        min={0}
                        max={MAXIMO}
                        step={1}
                        value={rascunho[codigo] ?? ""}
                        placeholder="geral"
                        aria-label={`Dias para ${nome}`}
                        onChange={(e) => mudarDias(codigo, e.target.value)}
                        style={{ width: 100, padding: "6px 8px" }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <button type="submit" disabled={salvando || !alterado(gerenciaId)}>
              {salvando ? "Salvando..." : "Salvar prazos da gerencia"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function AlertasConfig({ gerencias, onSaved, onMessage, onError }) {
  const [form, setForm] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    apiClient.getConfigAlertas()
      .then((config) => setForm(Object.fromEntries(
        Object.entries(config).map(([chave, valor]) => [chave, String(valor)])
      )))
      .catch((err) => onError(err.message));
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    // O backend recusa o que sair dos limites com um 422 que a tela nao
    // sabe mostrar; conferir aqui da uma mensagem que diz qual campo.
    const payload = {};
    for (const { chave, rotulo, min } of CAMPOS) {
      const valor = Number(form[chave]);
      if (!Number.isInteger(valor) || valor < min || valor > MAXIMO) {
        onError(`${rotulo}: informe um numero inteiro de ${min} a ${MAXIMO}.`);
        return;
      }
      payload[chave] = valor;
    }
    setSalvando(true);
    try {
      const salvo = await apiClient.salvarConfigAlertas(payload);
      onSaved(salvo);
      onMessage("Prazos dos alertas salvos. Valem a partir da proxima consulta de alertas.");
    } catch (err) {
      onError(err.message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
    <div className="card">
      <h2>Prazos dos alertas</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Quantos dias cada situacao pode durar antes de virar alerta. O alerta sai quando o prazo
        e ultrapassado.
      </p>
      {!form ? (
        <p className="muted">Carregando...</p>
      ) : (
        <form onSubmit={handleSubmit} className="form" style={{ maxWidth: 520 }}>
          {CAMPOS.map(({ chave, rotulo, ajuda, min }) => (
            <label key={chave}>
              {rotulo} (dias)
              <input
                type="number"
                min={min}
                max={MAXIMO}
                step={1}
                value={form[chave]}
                onChange={(e) => setForm({ ...form, [chave]: e.target.value })}
                required
              />
              <span className="muted" style={{ fontSize: 12, fontWeight: "normal" }}>{ajuda}</span>
            </label>
          ))}
          <button type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Salvar prazos"}
          </button>
        </form>
      )}
    </div>

    <PrazosPorProcedimento
      gerencias={gerencias}
      prazoGeral={form?.dias_sem_eventos}
      onSaved={() => onSaved()}
      onMessage={onMessage}
      onError={onError}
    />
    </>
  );
}
