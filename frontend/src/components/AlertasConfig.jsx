/**
 * AlertasConfig.jsx – Prazos dos alertas (admin).
 *
 * Os dias de cada regra de alerta e a janela de busca, gravados no banco
 * local (PUT /admin/alertas/config). Valem da proxima consulta de alertas
 * em diante: ao salvar, o App descarta os alertas ja carregados.
 */

import React, { useEffect, useState } from "react";
import apiClient from "../api.js";

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
  );
}
