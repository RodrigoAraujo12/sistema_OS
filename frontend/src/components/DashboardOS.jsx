/**
 * DashboardOS.jsx – Aba "Ordens de Servico" do Dashboard.
 *
 * A unica aba que roda sobre os dados REAIS do ATF (GET
 * /admin/dashboard/os). Mostra os cortes de quantidade de OS pedidos
 * pela area fiscal em 31/08/2026: por gerencia, orgao executor, fiscal,
 * motivo, tipo e mes de abertura — cada um com o tempo medio de
 * execucao.
 *
 * NAO consulta nada ao abrir. O periodo de abertura e obrigatorio
 * (inicio e fim, no maximo um ano) e o painel so e montado no clique —
 * mesmo contrato da tela de Ordens de Servico. Ate 03/09/2026 ela puxava
 * o ano corrente sozinha a cada visita: dezenas de segundos de varredura
 * no ATF por um recorte que quase nunca era o procurado.
 *
 * As demais abas (Visao Geral, Gerencias, Supervisoes, Fiscais) ainda
 * consomem o formato interno legado, que e mock.
 *
 * A contagem de EVENTOS que a mesma demanda pede nao esta aqui: a
 * listagem do ATF nao traz evento nenhum, so o detalhe traz — uma
 * chamada por OS. Vira outro servico.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import apiClient from "../api.js";
import {
  COR_TOTAL, COR_TEMPO, COR_VAZIO, PALETA_TIPO, TOPO_GRAFICO,
  intervaloDe, formatarDias, formatarNumero,
} from "../dashboardShared.js";
import DashboardFiltros, { opcoesDoMapa } from "./DashboardFiltros.jsx";
import { modeloLabels, motivoLabels, orgaoExecutorOptions } from "../constants.js";

/**
 * Atalhos de periodo. Sao so isso: preenchem as duas datas e NAO
 * consultam nada — a consulta sai no botao, como na tela de Ordens de
 * Servico. Nenhum passa de um ano, que e o teto do periodo aqui.
 *
 * Nao ha "Todos" nem "Personalizado": os campos de data estao sempre na
 * tela, entao qualquer intervalo (dentro do teto) e digitavel, e a base
 * inteira nao cabe — a consulta desce ate o ATF e um ano ja sao milhares
 * de OS e dezenas de segundos de espera.
 */
const PERIODO_OPTIONS = [
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "180", label: "6 meses" },
  { value: "ano", label: "Ano atual" },
  { value: "365", label: "12 meses" },
];

/** Teto do periodo: um ano. 366 dias para o ano bissexto caber inteiro —
 *  mesmo numero da busca so por periodo em atfFilters.js. */
const LIMITE_DIAS = 366;

/**
 * Valida o periodo ANTES de gastar uma varredura no ATF.
 * Retorna a mensagem de erro, ou null se estiver tudo certo.
 *
 * As datas vem de <input type="date">, sempre em YYYY-MM-DD: comparar
 * como texto ja da a ordem certa, sem passar por Date.
 */
function validarPeriodo(inicio, fim) {
  if (!inicio || !fim) return "Informe o periodo de abertura: inicio e fim.";
  if (inicio > fim) return "Periodo de abertura: o inicio nao pode ser depois do fim.";
  const dias = (new Date(fim) - new Date(inicio)) / 86400000;
  if (dias > LIMITE_DIAS) return "Periodo de abertura: no maximo um ano entre inicio e fim.";
  return null;
}

/**
 * Barras horizontais de um corte. Horizontal porque os rotulos sao
 * nomes longos (motivos, orgaos, fiscais) e no eixo X ficariam de lado.
 */
function GraficoCorte({ linhas, altura = 320 }) {
  return (
    <div style={{ position: "relative", width: "100%", height: altura }}>
      <Bar
        data={{
          labels: linhas.map((l) => l.rotulo),
          datasets: [{
            label: "OS",
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
                    `Encerradas: ${formatarNumero(l.encerradas)}`,
                    `Em execucao: ${formatarNumero(l.em_execucao)}`,
                    `Tempo medio: ${formatarDias(l.tempo_medio)}`,
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

/** Tabela do corte, com o tempo medio que o grafico so mostra no hover. */
function TabelaCorte({ linhas, cabecalho, altura }) {
  return (
    <div className="table-container" style={altura ? { maxHeight: altura, overflowY: "auto" } : undefined}>
      <table>
        <thead>
          <tr>
            <th>{cabecalho}</th>
            <th>OS</th>
            <th>Encerradas</th>
            <th>Em execucao</th>
            <th>Tempo medio</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={`${l.id}-${l.rotulo}`}>
              <td className={l.vazio ? "muted" : undefined}>
                {l.vazio ? l.rotulo : <strong>{l.rotulo}</strong>}
              </td>
              <td>{formatarNumero(l.total)}</td>
              <td>{formatarNumero(l.encerradas)}</td>
              <td>{formatarNumero(l.em_execucao)}</td>
              <td>{formatarDias(l.tempo_medio)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Dimensoes filtraveis. Sao as quatro que o ATF aceita em <parametros> e
 * que correspondem a cortes desta aba. Situacao ficou de fora de
 * proposito: o painel ja separa encerradas de em execucao, e o tempo
 * medio e definido sobre as encerradas — filtrar por situacao mudaria o
 * significado do KPI sem dizer isso na tela.
 */
const SEM_FILTRO = {
  modelo: "", motivoAbertura: "", orgaoExecutor: "", equipeFiscal: "",
};

export default function DashboardOS({ onError }) {
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(false);
  // Nada preenchido na entrada: a aba abre vazia e nao consulta o ATF
  // ate alguem definir o periodo — mesmo contrato da tela de Ordens de
  // Servico, que so pesquisa depois que o filtro esta posto. Antes daqui
  // ela puxava um ano inteiro sozinha a cada visita, uma varredura de
  // dezenas de segundos que quase sempre nao era o recorte procurado.
  const [periodo, setPeriodo] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [erro, setErro] = useState("");

  // `filtros` e o que esta nos campos; `consulta`, o que a consulta na
  // tela usou (null = nenhuma ainda). Aqui a distincao pesa mais que na
  // aba de Eventos: cada consulta custa de 5 a 16 segundos, entao o
  // botao existe para que montar um recorte de periodo mais tres
  // dimensoes nao dispare quatro varreduras.
  const [filtros, setFiltros] = useState(SEM_FILTRO);
  const [consulta, setConsulta] = useState(null);
  const [equipes, setEquipes] = useState([]);

  // Consulta em voo, para nao disparar a mesma duas vezes — dois cliques
  // no botao sairiam antes de a primeira popular o cache do backend,
  // entao seriam duas idas de verdade ao ATF.
  const emVoo = useRef(null);

  const carregar = useCallback(async (inicio, fim, dims) => {
    // O periodo e barrado aqui, e nao so no botao: e o unico caminho ate
    // o ATF, entao vale para o Aplicar, para o Limpar e para o que vier.
    const problema = validarPeriodo(inicio, fim);
    if (problema) {
      setErro(problema);
      return;
    }
    setErro("");
    const chave = `${inicio}|${fim}|${JSON.stringify(dims)}`;
    if (emVoo.current === chave) return;
    emVoo.current = chave;
    setLoading(true);
    try {
      setDados(await apiClient.getDashboardOS({
        dataInicio: inicio, dataFim: fim, ...dims,
      }));
      setConsulta({ inicio, fim, dims });
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
      emVoo.current = null;
    }
  }, [onError]);

  useEffect(() => {
    apiClient.listEquipesFiscais().then(setEquipes).catch(() => setEquipes([]));
  }, []);

  /** Atalho de periodo: preenche as duas datas e para por ai. */
  function handlePeriodoChange(novo) {
    setPeriodo(novo);
    const { inicio, fim } = intervaloDe(novo);
    setDataInicio(inicio);
    setDataFim(fim);
    setErro("");
  }

  /** Data digitada na mao desmarca o atalho — ele nao descreve mais o
   *  intervalo que esta na tela. */
  function handleDataChange(qual, valor) {
    if (qual === "inicio") setDataInicio(valor);
    else setDataFim(valor);
    setPeriodo("");
    setErro("");
  }

  function handleLimpar() {
    setFiltros(SEM_FILTRO);
    // So refaz a consulta se ja houver uma na tela: sem isso, Limpar em
    // uma aba ainda vazia viraria um segundo jeito de consultar.
    if (consulta) carregar(dataInicio, dataFim, SEM_FILTRO);
  }

  const campos = [
    { chave: "modelo", label: "Tipo", vazio: "Todos os tipos", opcoes: opcoesDoMapa(modeloLabels) },
    { chave: "motivoAbertura", label: "Motivo", vazio: "Todos os motivos", opcoes: opcoesDoMapa(motivoLabels) },
    {
      chave: "orgaoExecutor", label: "Orgao executor", vazio: "Todos os orgaos",
      opcoes: orgaoExecutorOptions.map((o) => ({ value: o.codigo, label: o.sigla })),
    },
    {
      chave: "equipeFiscal", label: "Equipe", vazio: "Todas as equipes",
      opcoes: equipes.map((e) => ({ value: String(e.codigo), label: e.nome })),
    },
  ];
  // Ha o que aplicar quando a tela difere da consulta que esta nela — e
  // sempre, enquanto nao houver consulta nenhuma. Diferente da aba de
  // Eventos, o periodo entra na conta: aqui ele tambem so vai ao ATF no
  // clique, entao mudar so as datas ja precisa habilitar o botao.
  const pendente = !consulta
    || consulta.inicio !== dataInicio
    || consulta.fim !== dataFim
    || JSON.stringify(consulta.dims) !== JSON.stringify(filtros);

  const visao = dados?.visao_geral;

  // `vazio` marca o grupo "Sem <dimensao>", que o backend rotula. Nao da
  // para olhar o id: no ATF um orgao pode vir com nome e sem codigo.
  const gerenciasComCadastro = useMemo(
    () => (dados?.por_gerencia || []).filter((l) => !l.vazio),
    [dados],
  );

  // A barra fica em pe nos tres estados (vazio, consultando e com
  // dados): e ela que o usuario veio usar, e esconde-la enquanto o ATF
  // responde tiraria da tela o recorte que ele acabou de montar.
  const barraFiltros = (
    <div className="card dash-filter-bar">
      <div className="dash-periodo-row" style={{ borderTop: "none", paddingTop: 0 }}>
        <label className="dash-filter-label">Abertura em:</label>
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
        </div>
        {loading && <span className="dash-periodo-loading">Consultando o ATF...</span>}
      </div>

      <DashboardFiltros
        campos={campos}
        valores={filtros}
        onChange={(chave, valor) => setFiltros({ ...filtros, [chave]: valor })}
        onAplicar={() => carregar(dataInicio, dataFim, filtros)}
        onLimpar={handleLimpar}
        pendente={pendente}
        loading={loading}
        rotuloAplicar="Gerar dashboard"
      />

      {erro && <div className="alert error" style={{ marginBottom: 12 }}>{erro}</div>}

      <p className="muted" style={{ marginTop: 8, marginBottom: 4 }}>
        O periodo de abertura e <strong>obrigatorio</strong> — inicio e fim, com no maximo
        um ano entre os dois. Os botoes acima so preenchem as datas: o dashboard e montado
        no clique em <strong>Gerar dashboard</strong>.
      </p>
      <p className="muted" style={{ marginTop: 0, marginBottom: 4 }}>
        Dados vindos direto da listagem do ATF. O tempo medio e a media de dias das OS
        <strong> ja encerradas</strong> — as que ainda correm nao entram, porque o contador
        delas cresce todo dia.
      </p>
      <p className="muted" style={{ marginTop: 0, marginBottom: 4 }}>
        Os filtros descem ate o ATF e encurtam a consulta, mas so em parte: a chamada tem
        um piso de <strong>~5s</strong> mais cerca de 2ms por OS. Restringir a metade das
        OS corta perto de um quarto do tempo, nao a metade. E filtrar por uma dimensao
        achata o corte dela — escolhido um orgao, o grafico de orgaos vira uma barra so.
      </p>
    </div>
  );

  // Sem consulta feita, a aba mostra so o filtro e o que fazer com ele.
  if (!dados) {
    return (
      <>
        {barraFiltros}
        <div className="card">
          {loading ? (
            <p className="muted">Consultando o ATF...</p>
          ) : (
            <>
              <h2>Escolha o periodo</h2>
              <p className="muted" style={{ marginBottom: 4 }}>
                Esta aba nao consulta nada sozinha. Informe o periodo de abertura (inicio e
                fim, no maximo um ano), escolha os filtros que quiser e clique em
                {" "}<strong>Gerar dashboard</strong>.
              </p>
              <p className="muted" style={{ marginTop: 0 }}>
                E o mesmo caminho da tela de Ordens de Servico, pelo mesmo motivo: cada
                consulta desce ate o ATF e custa de 5 a 16 segundos — nao vale gastar isso
                num recorte que ninguem pediu.
              </p>
            </>
          )}
        </div>
      </>
    );
  }

  return (
    <>
      {/* ─── Periodo e filtros ─── */}
      {barraFiltros}

      {/* ─── KPIs ─── */}
      <div className="stats-row">
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_os)}</div>
          <div className="stat-label">Total de OS</div>
        </div>
        <div className="stat-card concluida">
          <div className="stat-value">{formatarNumero(visao.encerradas)}</div>
          <div className="stat-label">Encerradas</div>
        </div>
        <div className="stat-card alta">
          <div className="stat-value">{formatarNumero(visao.em_execucao)}</div>
          <div className="stat-label">Em execucao</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarDias(visao.tempo_medio)}</div>
          <div className="stat-label">Tempo medio de execucao</div>
        </div>
      </div>

      <div className="stats-row" style={{ marginTop: 16 }}>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_fiscais)}</div>
          <div className="stat-label">Fiscais com OS</div>
        </div>
        <div className="stat-card normal">
          <div className="stat-value">{formatarNumero(visao.total_orgaos)}</div>
          <div className="stat-label">Orgaos executores</div>
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

      {/* ─── OS por mes de abertura + tempo medio ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>OS por mes de abertura</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          Barras: quantas OS foram abertas no mes. Linha: tempo medio de execucao das que ja
          encerraram, entre as abertas naquele mes.
        </p>
        <div style={{ position: "relative", width: "100%", height: 300 }}>
          <Bar
            data={{
              labels: dados.por_mes.map((m) => m.rotulo),
              datasets: [
                {
                  type: "bar",
                  label: "OS abertas",
                  data: dados.por_mes.map((m) => m.total),
                  backgroundColor: COR_TOTAL,
                  borderRadius: 4,
                  yAxisID: "y",
                  order: 2,
                },
                {
                  type: "line",
                  label: "Tempo medio (dias)",
                  data: dados.por_mes.map((m) => m.tempo_medio),
                  borderColor: COR_TEMPO,
                  backgroundColor: COR_TEMPO,
                  tension: 0.3,
                  pointRadius: 4,
                  pointHoverRadius: 7,
                  // Mes sem nenhuma OS encerrada vem com tempo_medio null:
                  // a linha corta ali em vez de fingir uma queda a zero.
                  spanGaps: false,
                  yAxisID: "y1",
                  order: 1,
                },
              ],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: "index", intersect: false },
              plugins: {
                legend: { position: "bottom", labels: { padding: 16, usePointStyle: true } },
                tooltip: {
                  callbacks: {
                    afterBody: (ctx) => {
                      const m = dados.por_mes[ctx[0].dataIndex];
                      if (!m) return "";
                      return `Encerradas: ${formatarNumero(m.encerradas)} | Em execucao: ${formatarNumero(m.em_execucao)}`;
                    },
                  },
                },
              },
              scales: {
                y: {
                  beginAtZero: true,
                  position: "left",
                  ticks: { precision: 0 },
                  title: { display: true, text: "Qtd de OS" },
                },
                y1: {
                  beginAtZero: true,
                  position: "right",
                  grid: { drawOnChartArea: false },
                  title: { display: true, text: "Dias" },
                },
              },
            }}
          />
        </div>
      </div>

      {/* ─── Tipo (modelo) e orgao executor ─── */}
      <div className="dashboard-charts-row" style={{ marginTop: 20 }}>
        <div className="card dashboard-chart-card">
          <h2>OS por Tipo</h2>
          <p className="muted" style={{ marginBottom: 12 }}>
            Modelo da OS no ATF (cdModeloOS).
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
                        return t ? `Tempo medio: ${formatarDias(t.tempo_medio)}` : "";
                      },
                    },
                  },
                },
              }}
            />
          </div>
        </div>

        <div className="card dashboard-chart-card">
          <h2>OS por Orgao Executor</h2>
          <p className="muted" style={{ marginBottom: 12 }}>
            Sigla do orgao que executa a OS (sgOrgaoExec).
          </p>
          <GraficoCorte linhas={dados.por_orgao_executor.slice(0, TOPO_GRAFICO)} altura={280} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h2>Orgaos executores em numeros</h2>
        <TabelaCorte linhas={dados.por_orgao_executor} cabecalho="Orgao executor" altura={360} />
      </div>

      {/* ─── Motivo ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>OS por Motivo de Abertura</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          {dados.por_motivo.length > TOPO_GRAFICO
            ? `Os ${TOPO_GRAFICO} motivos com mais OS. Os ${dados.por_motivo.length - TOPO_GRAFICO} restantes estao na tabela abaixo.`
            : "Todos os motivos do periodo."}
        </p>
        <GraficoCorte linhas={dados.por_motivo.slice(0, TOPO_GRAFICO)} altura={420} />
        <div style={{ marginTop: 20 }}>
          <TabelaCorte linhas={dados.por_motivo} cabecalho="Motivo" altura={360} />
        </div>
      </div>

      {/* ─── Gerencia ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>OS por Gerencia</h2>
        {gerenciasComCadastro.length === 0 ? (
          <div className="alert info" style={{ marginTop: 12 }}>
            <strong>Nenhuma OS tem gerencia.</strong> A gerencia nao vem do ATF — e cadastro
            daqui, e a unica ligacao ate a OS sao as matriculas dos fiscais. As
            {" "}{formatarNumero(visao.os_sem_gerencia)} OS do periodo ficam sem gerencia enquanto
            os fiscais nao tiverem lotacao (tela de Usuarios) ou os supervisores nao tiverem
            equipe fiscal amarrada. Assim que isso for feito, este corte se preenche sozinho.
          </div>
        ) : (
          <>
            <p className="muted" style={{ marginBottom: 16 }}>
              Uma OS com fiscais de gerencias diferentes conta em cada uma, entao a soma pode
              passar do total.
              {visao.os_sem_gerencia > 0 && (
                <> {formatarNumero(visao.os_sem_gerencia)} OS ainda estao sem gerencia cadastrada.</>
              )}
            </p>
            <GraficoCorte linhas={dados.por_gerencia} altura={Math.max(200, dados.por_gerencia.length * 42)} />
            <div style={{ marginTop: 20 }}>
              <TabelaCorte linhas={dados.por_gerencia} cabecalho="Gerencia" />
            </div>
          </>
        )}
      </div>

      {/* ─── Fiscal ─── */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2>OS por Fiscal</h2>
        <p className="muted" style={{ marginBottom: 16 }}>
          Uma OS designada a mais de um fiscal conta para cada um: a soma das linhas passa do
          total de OS, de proposito.
          {visao.os_sem_fiscal > 0 && (
            <> {formatarNumero(visao.os_sem_fiscal)} OS estao sem fiscal designado.</>
          )}
          {dados.por_fiscal.length > TOPO_GRAFICO && (
            <> O grafico mostra os {TOPO_GRAFICO} com mais OS; a tabela traz os {dados.por_fiscal.length}.</>
          )}
        </p>
        <GraficoCorte linhas={dados.por_fiscal.slice(0, TOPO_GRAFICO)} altura={420} />
        <div style={{ marginTop: 20 }}>
          <TabelaCorte linhas={dados.por_fiscal} cabecalho="Fiscal" altura={420} />
        </div>
      </div>
    </>
  );
}
