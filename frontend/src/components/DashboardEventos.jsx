/**
 * DashboardEventos.jsx – Aba "Eventos" do Dashboard.
 *
 * Bloco 2 da demanda de 31/08/2026, sobre o servico de eventos
 * (listarEventosOrdemServico), via GET /admin/dashboard/eventos.
 *
 * Fica separada da aba "Ordens de Servico" — e nao dentro dela — porque
 * conta outra coisa: ali a linha e uma OS, aqui e um EVENTO, e a mesma OS
 * aparece em varios. Somar os dois numeros na mesma tela sem dizer isso
 * seria convidar a leitura errada.
 *
 * A outra diferenca esta no filtro. A aba de OS tem um periodo so
 * (abertura); esta tem dois, e eles respondem perguntas distintas:
 * "eventos incluidos em janeiro" nao e o mesmo conjunto que "eventos de
 * OS abertas em janeiro". Por isso o periodo tem um seletor de qual data
 * esta sendo filtrada, em vez de duas barras competindo.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import apiClient from "../api.js";
import {
  COR_TOTAL, COR_VAZIO, PALETA_TIPO, TOPO_GRAFICO,
  intervaloDe, formatarDias, formatarNumero,
} from "../dashboardShared.js";
import DashboardFiltros, { opcoesDoCorte, opcoesDoMapa } from "./DashboardFiltros.jsx";
import { modeloLabels, motivoLabels } from "../constants.js";

/**
 * Periodos oferecidos. Nenhum passa de um ano porque o ATF recusa:
 * "Periodo informado ultrapassa um ano". Nao e limite de desempenho como
 * na aba de OS — este servico responde em menos de um segundo — e sim
 * regra do servico, entao "Personalizado" tambem esbarra nela.
 */
const PERIODO_OPTIONS = [
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "180", label: "6 meses" },
  { value: "ano", label: "Ano atual" },
  { value: "365", label: "12 meses" },
  { value: "custom", label: "Personalizado" },
];

/** Qual data o periodo filtra. Os dois campos existem no servico. */
const BASES = [
  {
    value: "inclusao",
    label: "Inclusao do evento",
    ajuda: "Quando o evento foi registrado no ATF. E o que mede trabalho feito no periodo: "
      + "um evento de marco numa OS aberta em janeiro e trabalho de marco.",
  },
  {
    value: "abertura",
    label: "Abertura da OS",
    ajuda: "Quando a OS foi aberta. Traz todos os eventos das OS abertas no periodo, "
      + "inclusive os registrados bem depois.",
  },
];

/** Barras horizontais de um corte, com a contagem de OS no hover. */
function GraficoCorte({ linhas, altura = 320 }) {
  return (
    <div style={{ position: "relative", width: "100%", height: altura }}>
      <Bar
        data={{
          labels: linhas.map((l) => l.rotulo),
          datasets: [{
            label: "Eventos",
            data: linhas.map((l) => l.total),
            backgroundColor: linhas.map((l) => (l.vazio ? COR_VAZIO : COR_TOTAL)),
            borderRadius: 4,
          }],
        }}
        options={{
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                afterBody: (ctx) => {
                  const l = linhas[ctx[0].dataIndex];
                  if (!l) return "";
                  return [
                    `OS distintas: ${formatarNumero(l.os)}`,
                    `Duracao media: ${formatarDias(l.duracao_media)}`,
                  ];
                },
              },
            },
          },
          scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
        }}
      />
    </div>
  );
}

/**
 * Tabela do corte. A coluna "OS" e o que separa uma equipe espalhada por
 * muitas OS de uma OS unica com muitos eventos — sem ela, "40 eventos"
 * nao diz qual dos dois casos e.
 */
function TabelaCorte({ linhas, cabecalho, altura }) {
  return (
    <div className="table-container" style={altura ? { maxHeight: altura, overflowY: "auto" } : undefined}>
      <table>
        <thead>
          <tr>
            <th>{cabecalho}</th>
            <th>Eventos</th>
            <th>OS</th>
            <th>Eventos por OS</th>
            <th>Duracao media</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={`${l.id}-${l.rotulo}`}>
              <td className={l.vazio ? "muted" : undefined}>
                {l.vazio ? l.rotulo : <strong>{l.rotulo}</strong>}
              </td>
              <td>{formatarNumero(l.total)}</td>
              <td>{formatarNumero(l.os)}</td>
              <td>{l.os ? (l.total / l.os).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : "—"}</td>
              <td>{formatarDias(l.duracao_media)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SEM_FILTRO = {
  modelo: "", motivoAbertura: "", equipeFiscal: "", gerencia: "", procedimento: "",
};

export default function DashboardEventos({ onError }) {
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(false);
  const [periodo, setPeriodo] = useState("ano");
  const [base, setBase] = useState("inclusao");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");

  // Dois estados para os filtros, de proposito: `filtros` e o que esta
  // nos <select> e `aplicados` e o que a consulta na tela usou. A
  // diferenca entre os dois e o que habilita o botao Aplicar — e o que
  // impede o painel de dizer "filtrado por X" antes de ter consultado X.
  const [filtros, setFiltros] = useState(SEM_FILTRO);
  const [aplicados, setAplicados] = useState(SEM_FILTRO);

  // Equipes fiscais do cadastro (planilha da SEFAZ). Falha silenciosa: o
  // filtro some, o resto da aba continua de pe.
  const [equipes, setEquipes] = useState([]);

  // Opcoes de gerencia e procedimento saem do PROPRIO resultado — nao ha
  // tabela de dominio delas deste lado. Guardadas da ultima consulta SEM
  // filtro de dimensao: tiradas da consulta filtrada, escolher uma opcao
  // apagaria as outras da lista e nao haveria como voltar.
  const [opcoesBase, setOpcoesBase] = useState({ gerencia: [], procedimento: [] });

  // Mesma trava da aba de OS: o StrictMode roda o efeito de montagem em
  // duplicata no dev e dispararia duas consultas iguais.
  const emVoo = useRef(null);

  const carregar = useCallback(async (inicio, fim, qualBase, dims) => {
    const chave = `${qualBase}|${inicio}|${fim}|${JSON.stringify(dims)}`;
    if (emVoo.current === chave) return;
    emVoo.current = chave;
    setLoading(true);
    try {
      const periodoArgs = qualBase === "abertura"
        ? { aberturaInicio: inicio, aberturaFim: fim }
        : { dataInicio: inicio, dataFim: fim };
      const resposta = await apiClient.getDashboardEventos({ ...periodoArgs, ...dims });
      setDados(resposta);
      setAplicados(dims);
      if (!Object.values(dims).some(Boolean)) {
        setOpcoesBase({
          gerencia: opcoesDoCorte(resposta.por_gerencia),
          procedimento: opcoesDoCorte(resposta.por_procedimento),
        });
      }
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
      emVoo.current = null;
    }
  }, [onError]);

  useEffect(() => {
    const { inicio, fim } = intervaloDe("ano");
    setDataInicio(inicio);
    setDataFim(fim);
    carregar(inicio, fim, "inclusao", SEM_FILTRO);
  }, [carregar]);

  useEffect(() => {
    apiClient.listEquipesFiscais().then(setEquipes).catch(() => setEquipes([]));
  }, []);

  function handlePeriodoChange(novo) {
    setPeriodo(novo);
    // "Personalizado" espera as datas do usuario antes de consultar.
    if (novo === "custom") return;
    const { inicio, fim } = intervaloDe(novo);
    setDataInicio(inicio);
    setDataFim(fim);
    carregar(inicio, fim, base, filtros);
  }

  function handleBaseChange(nova) {
    setBase(nova);
    // Trocar a data de referencia muda o conjunto inteiro, nao so o
    // rotulo — recarrega com o mesmo intervalo ja escolhido.
    if (dataInicio && dataFim) carregar(dataInicio, dataFim, nova, filtros);
  }

  function handleLimpar() {
    setFiltros(SEM_FILTRO);
    carregar(dataInicio, dataFim, base, SEM_FILTRO);
  }

  const visao = dados?.visao_geral;
  const baseAtual = BASES.find((b) => b.value === base);
  const equipesComNome = (dados?.por_equipe || []).filter((l) => !l.vazio);

  const campos = [
    { chave: "modelo", label: "Tipo", vazio: "Todos os tipos", opcoes: opcoesDoMapa(modeloLabels) },
    { chave: "motivoAbertura", label: "Motivo", vazio: "Todos os motivos", opcoes: opcoesDoMapa(motivoLabels) },
    {
      chave: "equipeFiscal", label: "Equipe", vazio: "Todas as equipes",
      opcoes: equipes.map((e) => ({ value: String(e.codigo), label: e.nome })),
    },
    { chave: "gerencia", label: "Gerencia", vazio: "Todas as gerencias", opcoes: opcoesBase.gerencia },
    { chave: "procedimento", label: "Procedimento", vazio: "Todos", opcoes: opcoesBase.procedimento },
  ];
  const pendente = JSON.stringify(filtros) !== JSON.stringify(aplicados);

  if (!dados && loading) {
    return <div className="card"><p className="muted">Consultando o ATF...</p></div>;
  }

  if (!dados) {
    return <div className="card"><p className="muted">Sem eventos do ATF para o periodo.</p></div>;
  }

  return (
    <>
      {/* ─── Aviso de ambiente ─── */}
      {dados.outro_ambiente && (
        <div className="alert error">
          <strong>Estes eventos vem de outro ambiente do ATF.</strong> A operacao
          listarEventosOrdemServico ainda nao esta publicada onde a listagem de OS roda, entao
          o sistema esta consultando o ambiente configurado em ATF_EVENTOS_BASE_URL.
          {" "}O ambiente de desenvolvimento e a <strong>mesma base de producao com o
          contribuinte mascarado</strong> — datas, modelo, motivo, orgao, procedimento e
          matriculas sao os reais, entao estas contagens valem. Mas ele e um{" "}
          <strong>snapshot congelado</strong>: em 02/09/2026 os dados iam ate o fim de julho.
          Um periodo que passe dessa data cai a zero aqui e parece queda de produtividade,
          quando e so o fim do snapshot. Nao usar para relatorio oficial.
        </div>
      )}

      {/* ─── Periodo ─── */}
      <div className="card dash-filter-bar">
        <div className="dash-periodo-row" style={{ borderTop: "none", paddingTop: 0 }}>
          <label className="dash-filter-label">Filtrar por:</label>
          <div className="dash-periodo-btns">
            {BASES.map((b) => (
              <button
                key={b.value}
                className={`dash-periodo-btn ${base === b.value ? "active" : ""}`}
                onClick={() => handleBaseChange(b.value)}
                disabled={loading}
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>

        <div className="dash-periodo-row">
          <label className="dash-filter-label">Periodo:</label>
          <div className="dash-periodo-btns">
            {PERIODO_OPTIONS.map((p) => (
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
          {periodo === "custom" && (
            <div className="dash-periodo-custom">
              <input
                type="date"
                value={dataInicio}
                onChange={(e) => setDataInicio(e.target.value)}
                className="dash-periodo-date"
              />
              <span className="dash-periodo-sep">ate</span>
              <input
                type="date"
                value={dataFim}
                onChange={(e) => setDataFim(e.target.value)}
                className="dash-periodo-date"
              />
              <button
                className="btn btn-primary dash-periodo-apply"
                onClick={() => carregar(dataInicio, dataFim, base)}
                disabled={loading || !dataInicio || !dataFim}
              >
                Aplicar
              </button>
            </div>
          )}
          {loading && <span className="dash-periodo-loading">Consultando o ATF...</span>}
        </div>

        <DashboardFiltros
          campos={campos}
          valores={filtros}
          onChange={(chave, valor) => setFiltros({ ...filtros, [chave]: valor })}
          onAplicar={() => carregar(dataInicio, dataFim, base, filtros)}
          onLimpar={handleLimpar}
          pendente={pendente}
          loading={loading}
        />

        <p className="muted" style={{ marginTop: 8, marginBottom: 4 }}>
          {baseAtual?.ajuda} O ATF nao aceita periodo maior que <strong>um ano</strong>.
          {" "}Filtrar por uma dimensao achata o corte dela — escolhida uma gerencia, o
          grafico de gerencias vira uma barra so, e sao os outros cortes que passam a
          contar a historia.
        </p>
      </div>

      {/* ─── KPIs ─── */}
      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_eventos)}</div>
          <div className="stat-label">Total de eventos</div>
        </div>
        <div className="stat-card concluida">
          <div className="stat-value">{formatarNumero(visao.total_os)}</div>
          <div className="stat-label">OS com evento</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">
            {visao.media_por_os === null ? "—" : visao.media_por_os.toLocaleString("pt-BR")}
          </div>
          <div className="stat-label">Eventos por OS</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarDias(visao.duracao_media)}</div>
          <div className="stat-label">Duracao media do evento</div>
        </div>
      </div>

      <div className="stats-row" style={{ marginTop: 16 }}>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_gerencias)}</div>
          <div className="stat-label">Gerencias</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_procedimentos)}</div>
          <div className="stat-label">Procedimentos</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{dados.por_motivo.length}</div>
          <div className="stat-label">Motivos de abertura</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{dados.por_tipo.length}</div>
          <div className="stat-label">Tipos de OS</div>
        </div>
      </div>

      {/* ─── Serie mensal ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>Eventos por mes de inclusao</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          Barras: quantos eventos foram registrados no mes. A linha cinza acompanha quantas OS
          distintas receberam esses eventos — quando as duas se afastam, poucas OS estao
          concentrando muito evento.
        </p>
        <div style={{ position: "relative", width: "100%", height: 300 }}>
          <Bar
            data={{
              labels: dados.por_mes.map((m) => m.rotulo),
              datasets: [
                {
                  type: "bar",
                  label: "Eventos",
                  data: dados.por_mes.map((m) => m.total),
                  backgroundColor: COR_TOTAL,
                  borderRadius: 4,
                  order: 2,
                },
                {
                  type: "line",
                  label: "OS distintas",
                  data: dados.por_mes.map((m) => m.os),
                  borderColor: COR_VAZIO,
                  backgroundColor: COR_VAZIO,
                  tension: 0.3,
                  pointRadius: 4,
                  pointHoverRadius: 7,
                  order: 1,
                },
              ],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { position: "bottom", labels: { usePointStyle: true } } },
              scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
            }}
          />
        </div>
      </div>

      {/* ─── Gerencia ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>Eventos por Gerencia</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          Aqui a gerencia vem <strong>do proprio ATF</strong> (cdGerencia/sgGerencia), e nao do
          cadastro local — por isso este corte se preenche mesmo com os fiscais sem lotacao
          amarrada, ao contrario do corte por gerencia da aba "Ordens de Servico".
          {visao.eventos_sem_gerencia > 0 && (
            <> {formatarNumero(visao.eventos_sem_gerencia)} eventos vieram sem gerencia informada.</>
          )}
        </p>
        <GraficoCorte linhas={dados.por_gerencia} altura={Math.max(200, dados.por_gerencia.length * 42)} />
        <div style={{ marginTop: 20 }}>
          <TabelaCorte linhas={dados.por_gerencia} cabecalho="Gerencia" />
        </div>
      </div>

      {/* ─── Procedimento ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>Eventos por Procedimento</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          {dados.por_procedimento.length > TOPO_GRAFICO
            ? `Os ${TOPO_GRAFICO} procedimentos com mais eventos. Os ${dados.por_procedimento.length - TOPO_GRAFICO} restantes estao na tabela abaixo.`
            : "Todos os procedimentos do periodo."}
        </p>
        <GraficoCorte linhas={dados.por_procedimento.slice(0, TOPO_GRAFICO)} altura={420} />
        <div style={{ marginTop: 20 }}>
          <TabelaCorte linhas={dados.por_procedimento} cabecalho="Procedimento" altura={360} />
        </div>
      </div>

      {/* ─── Tipo e motivo ─── */}
      <div className="dashboard-charts-row" style={{ marginTop: 20 }}>
        <div className="card dashboard-chart-card">
          <h2>Eventos por Tipo de OS</h2>
          <p className="muted" style={{ marginBottom: 12 }}>
            Modelo da OS a que o evento pertence (cdModeloOS).
          </p>
          <div className="chart-container-sm">
            <Doughnut
              data={{
                labels: dados.por_tipo.map((t) => t.rotulo),
                datasets: [{
                  data: dados.por_tipo.map((t) => t.total),
                  backgroundColor: dados.por_tipo.map(
                    (t, i) => (t.vazio ? COR_VAZIO : PALETA_TIPO[i % PALETA_TIPO.length]),
                  ),
                  borderWidth: 2,
                  borderColor: "#fff",
                }],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { position: "bottom", labels: { padding: 16, usePointStyle: true } },
                  tooltip: {
                    callbacks: {
                      label: (ctx) => {
                        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : 0;
                        return `${ctx.label}: ${formatarNumero(ctx.raw)} (${pct}%)`;
                      },
                      afterLabel: (ctx) => {
                        const t = dados.por_tipo[ctx.dataIndex];
                        return t ? `OS distintas: ${formatarNumero(t.os)}` : "";
                      },
                    },
                  },
                },
              }}
            />
          </div>
        </div>

        <div className="card dashboard-chart-card">
          <h2>Eventos por Motivo de Abertura</h2>
          <p className="muted" style={{ marginBottom: 12 }}>
            Motivo da OS a que o evento pertence.
          </p>
          <GraficoCorte linhas={dados.por_motivo.slice(0, TOPO_GRAFICO)} altura={280} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h2>Motivos em numeros</h2>
        <TabelaCorte linhas={dados.por_motivo} cabecalho="Motivo" altura={360} />
      </div>

      {/* ─── Equipe fiscal ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>Eventos por Equipe Fiscal</h2>
        {equipesComNome.length === 0 ? (
          <div className="alert info" style={{ marginTop: 12 }}>
            <strong>Nenhum evento deste periodo veio com equipe fiscal.</strong> O campo
            cdEquipeFisc voltou vazio nos {formatarNumero(visao.eventos_sem_equipe)} eventos.
            Isso costuma ser o <strong>periodo</strong>, e nao o campo: a equipe foi sendo
            adotada ao longo de 2026 — 0% dos eventos de janeiro, 83% dos de julho. Em
            janelas antigas o corte sai vazio mesmo. Diferente do corte por gerencia, isto
            nao depende de cadastro nosso.
          </div>
        ) : (
          <>
            <p className="muted" style={{ marginBottom: 16 }}>
              Equipe fiscal informada pelo ATF no evento.
              {visao.eventos_sem_equipe > 0 && (
                <> {formatarNumero(visao.eventos_sem_equipe)} eventos vieram sem equipe.</>
              )}
            </p>
            <GraficoCorte linhas={dados.por_equipe.slice(0, TOPO_GRAFICO)} altura={360} />
            <div style={{ marginTop: 20 }}>
              <TabelaCorte linhas={dados.por_equipe} cabecalho="Equipe fiscal" altura={360} />
            </div>
          </>
        )}
      </div>
    </>
  );
}
