/**
 * AlertasConfig.jsx – Prazos dos alertas (admin).
 *
 * Os dias de cada regra de alerta e a janela de busca, gravados no banco
 * local (PUT /admin/alertas/config), e a tabela de prazo por procedimento
 * de cada supervisao (PUT /admin/alertas/prazos-procedimento/{equipe}). Valem da
 * proxima consulta de alertas em diante: ao salvar, o App descarta os
 * alertas ja carregados.
 */

import React, { useEffect, useState } from "react";
import apiClient from "../api.js";
import { procedimentoLabels } from "../constants.js";
import { linhasDaSupervisao } from "../prazosProcedimento.js";

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
    ajuda: "Dias sem evento na OS autorizada, contando do ultimo evento, ou da ciencia quando ainda nao teve nenhum. Vale para os dois alertas: \"nenhum evento\" e \"sem evento novo\".",
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

/** {codigo: dias} gravado -> {codigo: "texto"} do formulario. */
function paraTexto(prazos) {
  return Object.fromEntries(Object.entries(prazos || {}).map(([c, d]) => [c, String(d)]));
}

/** So o que foi preenchido; vazio volta ao prazo geral. */
function preenchidos(rascunho) {
  return Object.entries(rascunho || {}).filter(([, v]) => String(v).trim() !== "");
}

/** [{procedimento_codigo, dias}] da API -> {codigo: dias}. */
function porCodigo(prazos) {
  return Object.fromEntries(prazos.map((p) => [p.procedimento_codigo, p.dias]));
}

/**
 * Tabela supervisao x procedimento -> dias do alerta "sem evento".
 *
 * Uma supervisao (equipe fiscal do ATF) por vez, escolhida no select,
 * agrupado por gerencia. A tabela mostra os procedimentos que ela lancou
 * nos ultimos 12 meses — consulta ao ATF de alguns segundos, que chega
 * depois da lista de supervisoes —, os que ja tem prazo, e o resto em
 * "mostrar todos". O que se digita fica num rascunho por supervisao:
 * trocar de supervisao nao perde nada, e o select marca as que tem
 * alteracao por salvar. Salvar grava so a supervisao da tela, e troca a
 * tabela inteira dela — procedimento deixado em branco volta ao prazo
 * geral.
 */
function PrazosPorProcedimento({ prazoGeral, onSaved, onMessage, onError }) {
  const [supervisoes, setSupervisoes] = useState(null); // [{equipe_codigo, equipe_nome, gerencia_nome}]
  const [gravado, setGravado] = useState({}); // {equipe_codigo: {codigo: dias}}
  const [rascunhos, setRascunhos] = useState({}); // {equipe_codigo: {codigo: "texto"}}
  const [equipe, setEquipe] = useState("");
  const [lancados, setLancados] = useState(undefined); // undefined: carregando; null: falhou
  const [todos, setTodos] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    apiClient.listarPrazosProcedimento()
      .then((lista) => {
        const porEquipe = Object.fromEntries(lista.map((s) => [s.equipe_codigo, porCodigo(s.prazos)]));
        setSupervisoes(lista);
        setGravado(porEquipe);
        setRascunhos(Object.fromEntries(
          Object.entries(porEquipe).map(([codigo, prazos]) => [codigo, paraTexto(prazos)])
        ));
        if (lista.length) setEquipe(String(lista[0].equipe_codigo));
      })
      .catch((err) => onError(err.message));
    // Sem esta lista a tabela mostra todos os procedimentos, como antes.
    apiClient.listarProcedimentosLancados()
      .then((lista) => setLancados(Object.fromEntries(lista.map((s) => [s.equipe_codigo, s.procedimentos]))))
      .catch(() => setLancados(null));
  }, []);

  function alterado(codigo) {
    const salvo = paraTexto(gravado[codigo]);
    const atual = Object.fromEntries(preenchidos(rascunhos[codigo]).map(([c, v]) => [c, String(v).trim()]));
    return JSON.stringify(Object.entries(salvo).sort()) !== JSON.stringify(Object.entries(atual).sort());
  }

  function mudarDias(codigo, valor) {
    setRascunhos((r) => ({ ...r, [equipe]: { ...(r[equipe] || {}), [codigo]: valor } }));
  }

  async function salvar(e) {
    e.preventDefault();
    onError("");
    onMessage("");
    const prazos = [];
    for (const [codigo, valor] of preenchidos(rascunhos[equipe])) {
      const dias = Number(valor);
      if (!Number.isInteger(dias) || dias < 0 || dias > MAXIMO) {
        const nome = procedimentoLabels[codigo] || `Procedimento ${codigo}`;
        onError(`${nome}: informe um numero inteiro de 0 a ${MAXIMO}, ou deixe em branco.`);
        return;
      }
      prazos.push({ procedimento_codigo: Number(codigo), dias });
    }
    setSalvando(true);
    try {
      const salvo = await apiClient.salvarPrazosProcedimento(equipe, prazos);
      const novos = porCodigo(salvo.prazos);
      setGravado((g) => ({ ...g, [equipe]: novos }));
      setRascunhos((r) => ({ ...r, [equipe]: paraTexto(novos) }));
      onSaved();
      onMessage(`Prazos por procedimento de ${salvo.equipe_nome} salvos. Valem a partir da proxima consulta de alertas.`);
    } catch (err) {
      onError(err.message);
    } finally {
      setSalvando(false);
    }
  }

  // Gerencia -> supervisoes, na ordem em que a API manda (gerencia, nome).
  const grupos = [];
  for (const s of supervisoes || []) {
    const rotulo = s.gerencia_nome || "Sem gerencia cadastrada";
    if (grupos.at(-1)?.rotulo !== rotulo) grupos.push({ rotulo, itens: [] });
    grupos.at(-1).itens.push(s);
  }

  const rascunho = rascunhos[equipe] || {};
  const carregando = lancados === undefined && !todos;
  const linhas = carregando ? [] : linhasDaSupervisao({
    catalogo: procedimentoLabels,
    lancados: lancados ? lancados[equipe] || [] : null,
    gravado: gravado[equipe],
    rascunho,
    todos,
  });

  return (
    <div className="card">
      <h2>Prazo por procedimento</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Quantos dias a OS pode ficar sem evento novo, conforme o procedimento do ultimo evento.
        Vale para as OS da supervisao, que sai da equipe dos fiscais da OS. Eventos seguidos do mesmo
        procedimento contam como um so: a contagem parte do primeiro, porque a OS nao andou.
        Em branco, vale o prazo geral de "OS sem eventos"
        {prazoGeral !== undefined && prazoGeral !== "" ? ` (${prazoGeral} dias)` : ""}.
      </p>
      {!supervisoes ? (
        <p className="muted">Carregando...</p>
      ) : !supervisoes.length ? (
        <p className="muted">Nenhuma equipe fiscal importada.</p>
      ) : (
        <form onSubmit={salvar} className="form" style={{ maxWidth: 720 }}>
          <label style={{ maxWidth: 520 }}>
            Supervisao
            <select value={equipe} onChange={(e) => setEquipe(e.target.value)}>
              {grupos.map((g) => (
                <optgroup key={g.rotulo} label={g.rotulo}>
                  {g.itens.map((s) => {
                    const n = preenchidos(rascunhos[s.equipe_codigo]).length;
                    return (
                      <option key={s.equipe_codigo} value={s.equipe_codigo}>
                        {s.equipe_nome}
                        {n ? ` (${n} com prazo)` : ""}
                        {alterado(s.equipe_codigo) ? " - nao salvo" : ""}
                      </option>
                    );
                  })}
                </optgroup>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", userSelect: "none" }}>
            <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} />
            <span>Mostrar todos os procedimentos, e nao so os que a supervisao lancou nos ultimos 12 meses</span>
          </label>
          {lancados === null && !todos && (
            <p className="muted" style={{ margin: 0 }}>
              Nao foi possivel consultar os eventos no ATF: a tabela mostra todos os procedimentos.
            </p>
          )}
          {carregando ? (
            <p className="muted" style={{ margin: 0 }}>
              Consultando no ATF os procedimentos que a supervisao lancou...
            </p>
          ) : !linhas.length ? (
            <p className="muted" style={{ margin: 0 }}>
              A supervisao nao lancou evento com procedimento nos ultimos 12 meses. Marque "mostrar
              todos" para dar prazo a um procedimento.
            </p>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Procedimento</th>
                    <th style={{ width: 150 }}>Eventos em 12 meses</th>
                    <th style={{ width: 120 }}>Dias</th>
                  </tr>
                </thead>
                <tbody>
                  {linhas.map(({ codigo, nome, eventos }) => (
                    <tr key={codigo}>
                      <td>{nome}</td>
                      <td>{lancados ? eventos : "-"}</td>
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
          )}
          <div>
            <button type="submit" disabled={salvando || !alterado(equipe)}>
              {salvando ? "Salvando..." : "Salvar prazos da supervisao"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function AlertasConfig({ onSaved, onMessage, onError }) {
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
      prazoGeral={form?.dias_sem_eventos}
      onSaved={() => onSaved()}
      onMessage={onMessage}
      onError={onError}
    />
    </>
  );
}
