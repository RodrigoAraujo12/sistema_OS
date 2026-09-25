/**
 * DashboardPanel.jsx – Painel principal do Dashboard (admin).
 *
 * Roteia as abas: OS, Eventos, Geral, Gerencias, Supervisoes, Fiscais.
 * Todas leem dados REAIS do ATF, por tres consultas diferentes:
 *
 * - "Ordens de Servico" (DashboardOS) e "Eventos" (DashboardEventos)
 *   tem cada uma o proprio endpoint e o proprio filtro de periodo — e
 *   contam unidades diferentes, OS numa e eventos na outra;
 * - as outras quatro dividem UMA consulta, GET /admin/dashboard, que
 *   mede situacao, ciencia e carga sobre a listagem do ATF. Por isso o
 *   periodo, os filtros de gerencia e equipe e os KPI cards daqui valem
 *   para as quatro juntas, e trocar entre elas nao consulta nada.
 *
 * Ate 25/09/2026 essas quatro liam uma lista fixa de OS de exemplo
 * (mock) e carregavam sozinhas no login. Agora seguem o contrato da aba
 * de OS: nada e consultado ate o clique em "Gerar dashboard", com
 * periodo de abertura obrigatorio de no maximo um ano.
 */

import React, { useCallback, useMemo, useRef, useState } from "react";
import apiClient from "../api.js";
import {
  PERIODOS_ABERTURA, intervaloDe, validarPeriodoAbertura, formatarNumero,
} from "../dashboardShared.js";
import DashboardOS from "./DashboardOS.jsx";
import DashboardEventos from "./DashboardEventos.jsx";
import DashboardGeral from "./DashboardGeral.jsx";
import DashboardGerencias from "./DashboardGerencias.jsx";
import DashboardSupervisoes from "./DashboardSupervisoes.jsx";
import DashboardFiscais from "./DashboardFiscais.jsx";

const ABAS = [
  { value: "os", label: "Ordens de Servico" },
  { value: "eventos", label: "Eventos" },
  { value: "geral", label: "Visao Geral" },
  { value: "gerencias", label: "Gerencias" },
  { value: "supervisoes", label: "Supervisoes" },
  { value: "fiscais", label: "Fiscais" },
];

export default function DashboardPanel({ onError }) {
  // Abre na aba de OS: e a que o dia a dia mais usa, e nenhuma aba
  // consulta nada sozinha — entao abrir o Dashboard nao custa uma ida ao
  // ATF, em nenhuma delas.
  const [view, setView] = useState("os");

  // ─── Consulta de desempenho (as quatro abas) ────────
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(false);
  const [periodo, setPeriodo] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [erro, setErro] = useState("");
  // O periodo da consulta que esta na tela (null = nenhuma ainda).
  const [consulta, setConsulta] = useState(null);
  const emVoo = useRef(null);

  // ─── Filtros (recortam o que ja veio, sem consultar) ─
  const [gerenciaFilter, setGerenciaFilter] = useState("");
  const [equipeFilter, setEquipeFilter] = useState("");

  const carregar = useCallback(async (inicio, fim) => {
    const problema = validarPeriodoAbertura(inicio, fim);
    if (problema) {
      setErro(problema);
      return;
    }
    setErro("");
    // Dois cliques seguidos sairiam antes de a primeira resposta popular
    // o cache do backend — seriam duas idas de verdade ao ATF.
    const chave = `${inicio}|${fim}`;
    if (emVoo.current === chave) return;
    emVoo.current = chave;
    setLoading(true);
    try {
      setDados(await apiClient.getDashboard({ dataInicio: inicio, dataFim: fim }));
      setConsulta({ inicio, fim });
      // Os filtros apontam para linhas da consulta anterior; uma gerencia
      // ou equipe sem OS no periodo novo continuaria filtrando o vazio.
      setGerenciaFilter("");
      setEquipeFilter("");
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
      emVoo.current = null;
    }
  }, [onError]);

  function handlePeriodoChange(novo) {
    setPeriodo(novo);
    const { inicio, fim } = intervaloDe(novo);
    setDataInicio(inicio);
    setDataFim(fim);
    setErro("");
  }

  function handleDataChange(qual, valor) {
    if (qual === "inicio") setDataInicio(valor);
    else setDataFim(valor);
    setPeriodo("");
    setErro("");
  }

  const pendente = !consulta || consulta.inicio !== dataInicio || consulta.fim !== dataFim;

  // ─── Dados filtrados (computados) ───────────────────
  const gerencias = dados?.desempenho_gerencias || [];
  const equipes = dados?.desempenho_equipes || [];
  const carga = dados?.carga_fiscais || [];

  const gerenciasFiltradas = useMemo(
    () => (gerenciaFilter ? gerencias.filter((g) => String(g.id) === gerenciaFilter) : gerencias),
    [gerencias, gerenciaFilter],
  );

  const equipesDaGerencia = useMemo(
    () => (gerenciaFilter ? equipes.filter((e) => String(e.gerencia_id) === gerenciaFilter) : equipes),
    [equipes, gerenciaFilter],
  );

  const equipesFiltradas = useMemo(
    () => (equipeFilter ? equipesDaGerencia.filter((e) => String(e.id) === equipeFilter) : equipesDaGerencia),
    [equipesDaGerencia, equipeFilter],
  );

  const fiscaisFiltrados = useMemo(() => {
    if (equipeFilter) return carga.filter((f) => f.equipes.map(String).includes(equipeFilter));
    if (gerenciaFilter) return carga.filter((f) => String(f.gerencia_id) === gerenciaFilter);
    return carga;
  }, [carga, gerenciaFilter, equipeFilter]);

  // ─── KPIs: os da linha filtrada, ou os gerais ───────
  // Nao se soma linha nenhuma: uma OS conta em cada gerencia e equipe
  // que seus fiscais alcancam, e somar contaria a mesma OS duas vezes.
  const kpis = useMemo(() => {
    if (!dados) return null;
    const linha = equipeFilter
      ? equipesFiltradas[0]
      : gerenciaFilter
        ? gerenciasFiltradas[0]
        : null;
    if (!linha) return dados.visao_geral;
    return {
      ...linha,
      total_fiscais: fiscaisFiltrados.length,
      total_equipes: equipesFiltradas.filter((e) => e.total_os > 0).length,
    };
  }, [dados, gerenciaFilter, equipeFilter, gerenciasFiltradas, equipesFiltradas, fiscaisFiltrados]);

  // ─── Comparativo mensal (deltas) ────────────────────
  // So sem filtro: o comparativo e do universo inteiro, e ao lado do
  // numero de uma gerencia pareceria ser dela.
  const comp = (!gerenciaFilter && !equipeFilter && dados?.comparativo_mensal) || {};
  const rotulosComp = comp._labels;

  function renderDelta(key, invertColor) {
    const item = comp[key];
    if (!item || item.delta === 0) return null;
    const isUp = item.delta > 0;
    const isGood = invertColor ? !isUp : isUp;
    const arrow = isUp ? "▲" : "▼";
    const sign = isUp ? "+" : "";
    return (
      <span
        className={`kpi-delta ${isGood ? "kpi-delta-good" : "kpi-delta-bad"}`}
        title={`Abertas em ${mesBr(rotulosComp.mes_atual)}: ${item.atual} · em ${mesBr(rotulosComp.mes_anterior)}: ${item.anterior}`}
      >
        {arrow} {sign}{item.delta}
      </span>
    );
  }

  // ─── Render ─────────────────────────────────────────
  const abas = (
    <div className="card dash-filter-bar">
      <div className="dash-view-tabs">
        {ABAS.map((a) => (
          <button
            key={a.value}
            className={`dash-view-tab ${view === a.value ? "active" : ""}`}
            onClick={() => setView(a.value)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );

  if (view === "os") return <>{abas}<DashboardOS onError={onError} /></>;
  if (view === "eventos") return <>{abas}<DashboardEventos onError={onError} /></>;

  const barraPeriodo = (
    <div className="card dash-filter-bar">
      <div className="dash-periodo-row" style={{ borderTop: "none", paddingTop: 0 }}>
        <label className="dash-filter-label">Abertura em:</label>
        <div className="dash-periodo-btns">
          {PERIODOS_ABERTURA.map((p) => (
            <button
              key={p.value}
              className={`dash-periodo-btn ${periodo === p.value ? "active" : ""}`}
              onClick={() => handlePeriodoChange(p.value)}
              disabled={loading}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="dash-periodo-custom">
          <input
            type="date"
            value={dataInicio}
            onChange={(e) => handleDataChange("inicio", e.target.value)}
            className="dash-periodo-date"
            disabled={loading}
            aria-label="Abertura de"
          />
          <span className="dash-periodo-sep">ate</span>
          <input
            type="date"
            value={dataFim}
            onChange={(e) => handleDataChange("fim", e.target.value)}
            className="dash-periodo-date"
            disabled={loading}
            aria-label="Abertura ate"
          />
          <button
            className="btn btn-primary dash-periodo-apply"
            onClick={() => carregar(dataInicio, dataFim)}
            disabled={loading || !pendente}
          >
            Gerar dashboard
          </button>
        </div>
        {loading && <span className="dash-periodo-loading">Consultando o ATF...</span>}
      </div>

      {erro && <div className="alert error" style={{ marginBottom: 12 }}>{erro}</div>}

      {dados && (
        <div className="dash-filter-row" style={{ marginTop: 12 }}>
          <div className="dash-filter-group">
            <label className="dash-filter-label">Gerencia:</label>
            <select
              value={gerenciaFilter}
              onChange={(e) => { setGerenciaFilter(e.target.value); setEquipeFilter(""); }}
              className="dash-filter-select"
            >
              <option value="">Todas as gerencias</option>
              {gerencias.map((g) => (
                <option key={g.id} value={g.id}>{g.nome}</option>
              ))}
            </select>
          </div>

          <div className="dash-filter-group">
            <label className="dash-filter-label">Equipe:</label>
            <select
              value={equipeFilter}
              onChange={(e) => setEquipeFilter(e.target.value)}
              className="dash-filter-select"
            >
              <option value="">Todas as equipes</option>
              {equipesDaGerencia.map((e) => (
                <option key={e.id} value={e.id}>{e.nome}</option>
              ))}
            </select>
          </div>

          {(gerenciaFilter || equipeFilter) && (
            <button
              className="btn btn-outline dash-filter-clear"
              onClick={() => { setGerenciaFilter(""); setEquipeFilter(""); }}
            >
              Limpar filtros
            </button>
          )}
        </div>
      )}

      <p className="muted" style={{ marginTop: 8, marginBottom: 4 }}>
        Dados da listagem do ATF. O periodo de abertura e <strong>obrigatorio</strong>, com no
        maximo um ano, e os botoes acima so preenchem as datas: a consulta sai no clique em
        {" "}<strong>Gerar dashboard</strong> e vale para as abas Visao Geral, Gerencias,
        Supervisoes e Fiscais. Gerencia e equipe recortam o que ja veio, sem consultar de novo.
      </p>
    </div>
  );

  if (!dados) {
    return (
      <>
        {abas}
        {barraPeriodo}
        <div className="card">
          {loading ? (
            <p className="muted">Consultando o ATF...</p>
          ) : (
            <>
              <h2>Escolha o periodo</h2>
              <p className="muted">
                Estas quatro abas nao consultam nada sozinhas. Informe o periodo de abertura
                (inicio e fim, no maximo um ano) e clique em <strong>Gerar dashboard</strong>.
                Cada consulta desce ate o ATF e leva de 5 a 16 segundos.
              </p>
            </>
          )}
        </div>
      </>
    );
  }

  const visao = dados.visao_geral;

  return (
    <>
      {abas}
      {barraPeriodo}

      {/* ===== KPI CARDS ===== */}
      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(kpis.total_os)} {renderDelta("total_os", false)}</div>
          <div className="stat-label">Total de OS</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{formatarNumero(kpis.em_andamento)} {renderDelta("em_andamento", true)}</div>
          <div className="stat-label">Em andamento</div>
        </div>
        <div className="stat-card concluida">
          <div className="stat-value">{kpis.taxa_encerramento}%</div>
          <div className="stat-label">Taxa de encerramento</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{formatarNumero(kpis.os_sem_ciencia)} {renderDelta("os_sem_ciencia", true)}</div>
          <div className="stat-label">OS sem ciencia</div>
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(kpis.encerradas)} {renderDelta("encerradas", false)}</div>
          <div className="stat-label">Encerradas</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(kpis.bloqueadas)} {renderDelta("bloqueadas", true)}</div>
          <div className="stat-label">Bloqueadas</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(kpis.total_fiscais)}</div>
          <div className="stat-label">Fiscais com OS ativa</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(kpis.total_equipes)}</div>
          <div className="stat-label">Equipes com OS</div>
        </div>
      </div>

      {!gerenciaFilter && !equipeFilter && (visao.os_sem_gerencia > 0 || visao.os_sem_equipe > 0) && (
        <p className="muted" style={{ marginTop: 0 }}>
          {formatarNumero(visao.os_sem_gerencia)} OS nao alcancam nenhuma gerencia do cadastro e
          {" "}{formatarNumero(visao.os_sem_equipe)} nenhuma equipe fiscal: entram no total, mas
          ficam fora dos cortes. Uma OS conta em cada gerencia e equipe que seus fiscais alcancam.
        </p>
      )}

      {/* ===== TAB CONTENT ===== */}
      {view === "geral" && (
        <DashboardGeral
          dados={dados}
          gerenciaFilter={gerenciaFilter}
          gerenciasFiltradas={gerenciasFiltradas}
          onGerenciaSelect={(id) => { setGerenciaFilter(String(id)); setEquipeFilter(""); setView("gerencias"); }}
        />
      )}

      {view === "gerencias" && (
        <DashboardGerencias
          gerenciasFiltradas={gerenciasFiltradas}
          gerenciaFilter={gerenciaFilter}
          onGerenciaToggle={(id) => {
            setGerenciaFilter(String(gerenciaFilter) === String(id) ? "" : String(id));
            setEquipeFilter("");
          }}
        />
      )}

      {view === "supervisoes" && (
        <DashboardSupervisoes
          equipesFiltradas={equipesFiltradas}
          gerenciaFilter={gerenciaFilter}
          equipeFilter={equipeFilter}
          onEquipeSelect={(id) => { setEquipeFilter(String(id)); setView("fiscais"); }}
        />
      )}

      {view === "fiscais" && (
        <DashboardFiscais
          fiscaisFiltrados={fiscaisFiltrados}
          gerenciaFilter={gerenciaFilter}
          equipeFilter={equipeFilter}
        />
      )}
    </>
  );
}

/** "2026-02" -> "02/2026". */
function mesBr(mes) {
  if (!mes) return "";
  const [ano, numero] = mes.split("-");
  return `${numero}/${ano}`;
}
