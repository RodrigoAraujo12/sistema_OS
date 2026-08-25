import React, { useEffect, useState } from "react";
import apiClient from "../api.js";
import { situacaoLabels, modeloLabels, motivoLabels, orgaoExecutorOptions, formatarData } from "../constants.js";
import { EMPTY_OS_FILTERS, validarFiltrosOS, filtrosParaPayload } from "../atfFilters.js";

const LIMITE_POR_PAGINA = 20;
const SITUACOES = Object.entries(situacaoLabels); // [[0, "AGUARDANDO..."], ...]
const MOTIVOS = Object.entries(motivoLabels);

const EMPTY_FILTERS = EMPTY_OS_FILTERS;

// Colunas da listagem. A chave e o nome que o backend aceita em
// ordenar_por (_ORDENACAO_ATF); o tipo define o alinhamento e a direcao
// inicial do clique — texto comeca em A-Z, data e numero comecam do maior
// para o menor, que e o que interessa ver primeiro (mais recente, mais
// dias parado).
const COLUNAS = [
  { key: "numero_os", label: "Número", tipo: "texto" },
  { key: "razao_social", label: "Razão Social", tipo: "texto" },
  { key: "modelo", label: "Modelo", tipo: "texto" },
  { key: "motivo_abertura", label: "Motivo", tipo: "texto" },
  { key: "procedimento", label: "Procedimento", tipo: "texto" },
  { key: "situacao", label: "Situação", tipo: "texto" },
  { key: "data_abertura", label: "Abertura", tipo: "data" },
  { key: "dias_execucao", label: "Dias Exec.", tipo: "numero" },
  { key: "data_ultimo_evento", label: "Último Evento", tipo: "data" },
  { key: "dias_sem_evento", label: "Dias s/ Evento", tipo: "numero" },
];

const IconeCopiar = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

const IconeCheck = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

/**
 * Copia sobre `base` apenas os campos preenchidos de `novo`.
 *
 * O detalhe (doc do detalhe) e a listagem (doc da listagem) sao servicos
 * diferentes e nenhum e superconjunto do outro: a listagem tem equipe
 * fiscal, dias de execucao e as medias por Modelo/Motivo, que o detalhe
 * nao devolve. Uma copia crua ({...linha, ...detalhe}) apagaria esses
 * campos com "" ou null — por isso o vazio nao sobrescreve.
 */
function sobrepor(base, novo) {
  const resultado = { ...base };
  for (const [chave, valor] of Object.entries(novo || {})) {
    const vazio = valor === null || valor === undefined || valor === ""
      || (Array.isArray(valor) && valor.length === 0);
    if (!vazio) resultado[chave] = valor;
  }
  return resultado;
}

/** Junta a linha do grid com o detalhe recem-buscado da mesma OS. */
function mesclarDetalhe(linha, detalhe) {
  const os = sobrepor(linha, detalhe);
  // Fiscais: o detalhe manda, mas a data de cancelamento so existe na
  // listagem — casa por matricula para nao perde-la.
  if (detalhe.fiscais?.length) {
    const daLinha = linha.fiscais || [];
    os.fiscais = detalhe.fiscais.map(f =>
      sobrepor(daLinha.find(x => x.matricula === f.matricula) || {}, f));
  }
  return os;
}

/** "01/2024 a 12/2024". `formatar` converte cada ponta (padrao: crua). */
function periodoTexto(periodo, formatar = (v) => v) {
  if (!periodo) return "";
  const inicio = periodo.inicio ? formatar(periodo.inicio) : "";
  const fim = periodo.fim ? formatar(periodo.fim) : "";
  if (inicio && fim) return `${inicio} a ${fim}`;
  return inicio || fim || "";
}

/** Endereco em uma linha: "AV EPITACIO PESSOA, 1420 - SALA 302". */
function enderecoLinha(endereco) {
  if (!endereco) return "";
  // Quando o cadastro nao conseguiu separar o endereco em campos, o texto
  // solto e a unica informacao que existe.
  if (endereco.nao_decodificado) return endereco.nao_decodificado;
  const rua = [endereco.logradouro, endereco.numero].filter(Boolean).join(", ");
  return [rua, endereco.complemento].filter(Boolean).join(" - ");
}

/** "JOAO PESSOA / PB - 58039-000" */
function municipioLinha(endereco) {
  if (!endereco) return "";
  const cidade = [endereco.municipio, endereco.uf].filter(Boolean).join(" / ");
  return [cidade, endereco.cep].filter(Boolean).join(" - ");
}

function formatarValor(valor) {
  if (valor === null || valor === undefined) return "";
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Rotulo + valor do detalhe. Valor vazio vira "-", para a grade nao
 *  ficar com buracos onde o ATF nao mandou nada. */
function Campo({ label, valor }) {
  const vazio = valor === null || valor === undefined || valor === "";
  return (
    <div className="os-detail-field">
      <span className="os-detail-label">{label}</span>
      <span className="os-detail-value">{vazio ? "-" : valor}</span>
    </div>
  );
}

/** Bloco titulado do modal de detalhes. */
function Secao({ titulo, children }) {
  return (
    <div className="os-detail-section">
      <h3 className="os-detail-section-title">{titulo}</h3>
      {children}
    </div>
  );
}

export default function OrdensPanel() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [ordens, setOrdens] = useState(null); // null = ainda nao pesquisou
  const [paginacao, setPaginacao] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [ordenacao, setOrdenacao] = useState({ campo: null, dir: "asc" });
  const [copiedOS, setCopiedOS] = useState(null);

  // Equipes fiscais do ATF, para o select do filtro. Lista vazia = a
  // planilha da SEFAZ ainda nao foi importada; o filtro entao volta a
  // ser o campo de codigo, que e como funcionava antes de existir a
  // tabela. Ver backend/importar_equipes.py.
  const [equipes, setEquipes] = useState([]);

  const [selectedOS, setSelectedOS] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  // Carrega as equipes uma vez. Falha silenciosa de proposito: sem a
  // lista o filtro degrada para o campo de codigo, e um erro aqui nao
  // deve atrapalhar quem so quer pesquisar OS.
  useEffect(() => {
    let ativo = true;
    apiClient.listEquipesFiscais()
      .then(lista => { if (ativo) setEquipes(lista || []); })
      .catch(() => { /* sem lista: cai no campo de codigo */ });
    return () => { ativo = false; };
  }, []);

  function handleFilterChange(e) {
    const { name, value } = e.target;
    setFilters(prev => ({ ...prev, [name]: value }));
  }

  function handleSituacaoToggle(codigo) {
    const cod = Number(codigo);
    setFilters(prev => {
      const already = prev.situacoes.includes(cod);
      return {
        ...prev,
        situacoes: already
          ? prev.situacoes.filter(s => s !== cod)
          : [...prev.situacoes, cod],
      };
    });
  }

  // A ordenacao vai por parametro (e nao lida do state) porque handleSort
  // precisa buscar ja com o criterio novo — o setState so vale no proximo
  // render.
  async function fetchOrdens(page, ord = ordenacao) {
    const error = validarFiltrosOS(filters);
    if (error) {
      setSearchError(error);
      return;
    }

    setLoading(true);
    setSearchError("");
    try {
      const data = await apiClient.listOrdens({
        ...filtrosParaPayload(filters),
        pagina: page,
        limite: LIMITE_POR_PAGINA,
        ordenar_por: ord.campo,
        ordem: ord.dir,
      });
      setOrdens(data.ordens ?? data);
      setPaginacao(data.paginacao ?? null);
      setCurrentPage(page);
    } catch (err) {
      setSearchError(err.message || "Erro ao buscar ordens");
      setOrdens([]);
      setPaginacao(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(e) {
    e.preventDefault();
    fetchOrdens(1);
  }

  function handlePageChange(newPage) {
    fetchOrdens(newPage);
  }

  /**
   * Clique no cabecalho: primeira vez ordena pela direcao natural do tipo,
   * cliques seguintes invertem. Volta sempre para a pagina 1 — manter a
   * pagina atual mostraria um recorte do meio de uma lista que acabou de
   * mudar de ordem.
   */
  function handleSort(coluna) {
    const nova = ordenacao.campo === coluna.key
      ? { campo: coluna.key, dir: ordenacao.dir === "asc" ? "desc" : "asc" }
      : { campo: coluna.key, dir: coluna.tipo === "texto" ? "asc" : "desc" };
    setOrdenacao(nova);
    fetchOrdens(1, nova);
  }

  function handleClear() {
    setFilters(EMPTY_FILTERS);
    setOrdens(null);
    setPaginacao(null);
    setCurrentPage(1);
    setSearchError("");
  }

  /**
   * Abre o detalhe de UMA OS. Cada clique chama o servico de detalhe do
   * ATF (doc do detalhe) para a ordem clicada — fechar e clicar em outra
   * chama de novo, com o numero da nova.
   *
   * A linha do grid entra como base porque a listagem tem campos que o
   * detalhe nao devolve (equipe fiscal, dias de execucao e as medias por
   * Modelo/Motivo); ver mesclarDetalhe.
   */
  async function handleOSClick(ordem) {
    setLoadingDetail(true);
    setDetailError("");
    try {
      const detalhe = await apiClient.getOrdemDetalhe(ordem.numero_os || ordem.numero);
      setSelectedOS(mesclarDetalhe(ordem, detalhe));
    } catch (err) {
      setDetailError(err.message || "Erro ao carregar detalhes da OS");
    } finally {
      setLoadingDetail(false);
    }
  }

  /**
   * Copia o numero da OS. O stopPropagation e essencial: a linha inteira e
   * clicavel e abre o modal de detalhes — copiar nao pode disparar isso.
   * navigator.clipboard so existe em contexto seguro (https ou localhost);
   * em intranet http o fallback do textarea + execCommand ainda funciona.
   */
  async function handleCopyNumero(e, numero) {
    e.stopPropagation();
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(numero);
      } else {
        const ta = document.createElement("textarea");
        ta.value = numero;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setCopiedOS(numero);
      setTimeout(() => setCopiedOS(atual => (atual === numero ? null : atual)), 1500);
    } catch {
      // Sem clipboard disponivel: o numero continua selecionavel na tela.
    }
  }

  function closeDetail() {
    setSelectedOS(null);
    setDetailError("");
  }

  async function handleDownloadPdf(numero) {
    try {
      const blob = await apiClient.downloadOrdemPdf(numero);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${numero.replace(/\//g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDetailError(err.message || "Erro ao baixar PDF");
    }
  }

  function renderSituacao(os) {
    if (os.situacao) {
      return <span className="badge normal">{os.situacao.descricao}</span>;
    }
    return <span className="badge normal">{os.status || "-"}</span>;
  }

  /**
   * Mostra o NOME da coisa, nunca o codigo do ATF junto.
   *
   * Codigo (cdModeloOS, cdMotivoAberturaOS, cdElementoOrg...) e chave de
   * integracao: continua indo e voltando nas consultas, mas nao e o que
   * o fiscal precisa ler na tela. So aparece quando o ATF manda o codigo
   * sem a descricao — ai e melhor do que um campo vazio.
   */
  function nomeOuCodigo(codigo, texto) {
    if (texto) return texto;
    const temCodigo = codigo !== null && codigo !== undefined && codigo !== "";
    return temCodigo ? String(codigo) : "-";
  }

  /**
   * Dias corridos entre a data (YYYY-MM-DD) e hoje.
   * Retorna null quando nao ha data: o ATF so manda dataUltimoEventoOS
   * quando existe ao menos um evento lancado na OS — a maioria das OS em
   * aberto nao tem nenhum, e ai nao ha o que contar.
   */
  function diasDesde(dataISO) {
    if (!dataISO) return null;
    const d = new Date(`${dataISO}T00:00:00`);
    if (Number.isNaN(d.getTime())) return null;
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    return Math.floor((hoje - d) / 86400000);
  }

  const totalPages = paginacao?.total_paginas ?? (ordens ? 1 : 1);
  const totalRegistros = paginacao?.total_registros ?? (ordens?.length ?? 0);

  return (
    <>
      {/* Filtros */}
      <div className="card filters-card">
        <div className="filters-header">
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Filtros de Pesquisa</h3>
          <button className="small secondary" type="button" onClick={handleClear}>Limpar</button>
        </div>

        <form onSubmit={handleSearch}>
          {/* Linha 1: numero, modelo, ie, cnpj */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">N&uacute;mero OS</label>
              <input
                type="text"
                name="numero"
                value={filters.numero}
                onChange={handleFilterChange}
                placeholder="Ex: 93300008.12.00000001/2026-99"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">
                Modelo
                {filters.modelo &&
                  !((filters.data_abertura_inicio && filters.data_abertura_fim) ||
                    (filters.data_encerramento_inicio && filters.data_encerramento_fim)) && (
                  <span style={{ color: "#e53e3e", marginLeft: 6, fontSize: 11 }}>*requer per&iacute;odo de abertura ou encerramento</span>
                )}
              </label>
              {/* O value das opcoes continua sendo o codigo — e o que o ATF
                  aceita nos filtros. Para o usuario aparece so o nome. */}
              <select name="modelo" value={filters.modelo} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {Object.entries(modeloLabels).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">IE</label>
              <input
                type="text"
                name="ie"
                value={filters.ie}
                onChange={handleFilterChange}
                placeholder="Inscri&ccedil;&atilde;o Estadual"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">CNPJ</label>
              <input
                type="text"
                name="cnpj"
                value={filters.cnpj}
                onChange={handleFilterChange}
                placeholder="CNPJ do contribuinte"
                className="filter-select"
              />
            </div>
          </div>

          {/* Linha 2: motivo abertura, equipe fiscal, orgao executor */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group" style={{ gridColumn: "span 2" }}>
              <label className="filter-label">Motivo de Abertura</label>
              <select name="motivo_abertura" value={filters.motivo_abertura} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {MOTIVOS.map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">
                Equipe Fiscal{equipes.length === 0 && " (código)"}
              </label>
              {equipes.length > 0 ? (
                <select name="equipe_fiscal" value={filters.equipe_fiscal} onChange={handleFilterChange} className="filter-select">
                  <option value="">Todas</option>
                  {equipes.map(({ codigo, nome }) => (
                    <option key={codigo} value={codigo}>{nome}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  name="equipe_fiscal"
                  value={filters.equipe_fiscal}
                  onChange={handleFilterChange}
                  placeholder="Ex: 427"
                  className="filter-select"
                />
              )}
            </div>
            <div className="filter-group">
              <label className="filter-label">&Oacute;rg&atilde;o Executor</label>
              <select name="orgao_executor" value={filters.orgao_executor} onChange={handleFilterChange} className="filter-select">
                <option value="">Todos</option>
                {orgaoExecutorOptions.map(({ codigo, sigla }) => (
                  <option key={codigo} value={codigo}>{sigla}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Linha 3: razao_social, matriculas */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">
                Raz&atilde;o Social
                {filters.razao_social.length > 0 && filters.razao_social.length < 6 && (
                  <span style={{ color: "#e53e3e", marginLeft: 8, fontSize: 11 }}>
                    m&iacute;n. 6 caracteres ({filters.razao_social.length}/6)
                  </span>
                )}
              </label>
              <input
                type="text"
                name="razao_social"
                value={filters.razao_social}
                onChange={handleFilterChange}
                placeholder="Parte do nome (m&iacute;n. 6 chars)"
                className="filter-select"
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">Matr&iacute;culas dos Fiscais</label>
              <input
                type="text"
                name="matriculas"
                value={filters.matriculas}
                onChange={handleFilterChange}
                placeholder="Ex: 1468901, 1447041"
                className="filter-select"
              />
            </div>
          </div>

          {/* Linha 4: periodos de abertura e encerramento */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">Abertura — In&iacute;cio</label>
              <input type="date" name="data_abertura_inicio" value={filters.data_abertura_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Abertura — Fim</label>
              <input type="date" name="data_abertura_fim" value={filters.data_abertura_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Encerramento — In&iacute;cio</label>
              <input type="date" name="data_encerramento_inicio" value={filters.data_encerramento_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Encerramento — Fim</label>
              <input type="date" name="data_encerramento_fim" value={filters.data_encerramento_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
          </div>

          {/* Linha 5: periodo de ciencia */}
          <div className="filters-grid" style={{ marginBottom: 10 }}>
            <div className="filter-group">
              <label className="filter-label">Ci&ecirc;ncia — In&iacute;cio</label>
              <input type="date" name="data_ciencia_inicio" value={filters.data_ciencia_inicio} onChange={handleFilterChange} className="filter-select" />
            </div>
            <div className="filter-group">
              <label className="filter-label">Ci&ecirc;ncia — Fim</label>
              <input type="date" name="data_ciencia_fim" value={filters.data_ciencia_fim} onChange={handleFilterChange} className="filter-select" />
            </div>
          </div>

          {/* Situacoes: checkboxes */}
          <div style={{ marginBottom: 14 }}>
            <label className="filter-label" style={{ display: "block", marginBottom: 6 }}>Situa&ccedil;&atilde;o</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
              {SITUACOES.map(([cod, desc]) => (
                <label
                  key={cod}
                  style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, cursor: "pointer", userSelect: "none" }}
                >
                  <input
                    type="checkbox"
                    checked={filters.situacoes.includes(Number(cod))}
                    onChange={() => handleSituacaoToggle(cod)}
                  />
                  <span>{desc}</span>
                </label>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              disabled={loading}
              style={{ background: "#1a3a6c", color: "#fff", border: "none", padding: "8px 24px", borderRadius: 6, fontWeight: 600, fontSize: 13, cursor: loading ? "not-allowed" : "pointer" }}
            >
              {loading ? "Pesquisando..." : "Pesquisar"}
            </button>
          </div>
        </form>

        {searchError && (
          <div className="alert error" style={{ marginTop: 10 }}>{searchError}</div>
        )}
      </div>

      {/* Resultado */}
      <div className="card">
        {ordens === null ? (
          <div className="empty-state">
            <p className="muted">Preencha os filtros acima e clique em <strong>Pesquisar</strong> para carregar as ordens.</p>
          </div>
        ) : (
          <>
            <h2>
              Ordens de Servi&ccedil;o ({totalRegistros} registros) &mdash; p&aacute;g. {currentPage}/{totalPages}
            </h2>
            <p className="muted" style={{ marginBottom: 12 }}>
              Dados do ATF. Somente consulta.
            </p>
            {ordens.length === 0 ? (
              <div className="empty-state">
                <p className="muted">Nenhuma ordem de servi&ccedil;o encontrada para os filtros informados.</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="tabela-ordens">
                  <thead>
                    <tr>
                      {COLUNAS.map((c) => {
                        const ativa = ordenacao.campo === c.key;
                        return (
                          <th
                            key={c.key}
                            className={`th-sortable${ativa ? " th-sorted" : ""}`}
                            style={c.tipo === "numero" ? { textAlign: "center" } : undefined}
                            title={`Ordenar por ${c.label}`}
                            onClick={() => handleSort(c)}
                          >
                            {c.label}
                            <span className="sort-arrow">
                              {ativa ? (ordenacao.dir === "asc" ? "▲" : "▼") : "↕"}
                            </span>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {ordens.map((os) => {
                      const numeroOS = os.numero_os || os.numero;
                      const diasSemEvento = diasDesde(os.data_ultimo_evento);
                      return (
                        <tr
                          key={numeroOS}
                          className="os-row-clickable"
                          onClick={() => handleOSClick(os)}
                          title="Clique para ver detalhes"
                        >
                          <td>
                            <span className="os-numero-cell">
                              <strong>{numeroOS}</strong>
                              <button
                                type="button"
                                className="btn-copiar-os"
                                title={copiedOS === numeroOS ? "Copiado!" : "Copiar número da OS"}
                                aria-label={`Copiar número da OS ${numeroOS}`}
                                onClick={(e) => handleCopyNumero(e, numeroOS)}
                              >
                                {copiedOS === numeroOS ? <IconeCheck /> : <IconeCopiar />}
                              </button>
                            </span>
                          </td>
                          <td>{os.razao_social || "-"}</td>
                          <td>{os.modelo || "-"}</td>
                          <td>{os.motivo_abertura || "-"}</td>
                          <td>{os.procedimento || "-"}</td>
                          <td>{renderSituacao(os)}</td>
                          <td>{formatarData(os.data_abertura)}</td>
                          <td style={{ textAlign: "center" }}>{os.dias_execucao ?? "-"}</td>
                          <td>{formatarData(os.data_ultimo_evento)}</td>
                          <td style={{ textAlign: "center" }}>{diasSemEvento ?? "-"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
                <button className="small secondary" onClick={() => handlePageChange(1)} disabled={currentPage === 1 || loading}>«</button>
                <button className="small secondary" onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1 || loading}>‹ Anterior</button>
                <span style={{ fontSize: 13, color: "#6b7280" }}>
                  P&aacute;gina {currentPage} de {totalPages} &mdash; {totalRegistros} registros
                </span>
                <button className="small secondary" onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages || loading}>Pr&oacute;xima ›</button>
                <button className="small secondary" onClick={() => handlePageChange(totalPages)} disabled={currentPage === totalPages || loading}>»</button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Loading overlay detalhes */}
      {loadingDetail && (
        <div className="confirm-overlay">
          <div className="confirm-modal">
            <p>Carregando detalhes da OS...</p>
          </div>
        </div>
      )}

      {/* Error toast */}
      {detailError && !loadingDetail && (
        <div className="confirm-overlay" onClick={() => setDetailError("")}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-icon" data-variant="danger">!</div>
            <h3 className="confirm-title">Erro</h3>
            <p className="confirm-message">{detailError}</p>
            <div className="confirm-actions">
              <button className="small secondary" onClick={() => setDetailError("")}>Fechar</button>
            </div>
          </div>
        </div>
      )}

      {/* OS Detail Modal */}
      {selectedOS && (
        <div className="confirm-overlay" onClick={closeDetail}>
          <div className="os-detail-modal" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="os-detail-header">
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>{selectedOS.numero_os || selectedOS.numero}</h2>
                <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: 13 }}>
                  {selectedOS.razao_social}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {selectedOS.situacao
                  ? <span className="badge normal">{selectedOS.situacao.descricao}</span>
                  : <span className="badge normal">{selectedOS.status || "-"}</span>
                }
                <button className="small secondary" onClick={closeDetail} style={{ fontSize: 18, lineHeight: 1, padding: "4px 10px" }}>&times;</button>
              </div>
            </div>

            {/* Body */}
            <div className="os-detail-body">
              {selectedOS.detalhe_de_outro_ambiente && (
                <div className="os-detail-aviso">
                  Detalhe obtido em um ambiente diferente do da listagem: os
                  bancos nao sao os mesmos, entao contribuinte, situacao e
                  fiscais podem nao corresponder a linha da tabela.
                </div>
              )}

              <Secao titulo="Informações da Ordem">
                <div className="os-detail-grid">
                  <Campo label="Modelo" valor={nomeOuCodigo(selectedOS.modelo_codigo, selectedOS.modelo)} />
                  <Campo label="Motivo de Abertura" valor={nomeOuCodigo(selectedOS.motivo_abertura_codigo, selectedOS.motivo_abertura)} />
                  <Campo label="Procedimento" valor={selectedOS.procedimento} />
                  <Campo label="Período a Fiscalizar" valor={periodoTexto(selectedOS.periodo_fiscalizar)} />
                  {/* Codigo + sigla + nome: o nome sozinho passa de 150
                      chars, a sigla da o reconhecimento imediato. */}
                  <Campo
                    label="Órgão Executor"
                    valor={nomeOuCodigo(
                      selectedOS.orgao_executor_codigo,
                      [selectedOS.orgao_executor_sigla, selectedOS.orgao_executor]
                        .filter(Boolean).join(" — "),
                    )}
                  />
                  <Campo label="Órgão de Origem" valor={nomeOuCodigo(selectedOS.orgao_origem_codigo, selectedOS.orgao_origem)} />
                  <Campo label="Equipe Fiscal" valor={nomeOuCodigo(selectedOS.equipe_fiscal_codigo, selectedOS.equipe_fiscal)} />
                  <Campo label="Tipo de Funcionário" valor={selectedOS.tipo_funcionario} />
                  <Campo label="BD Fiscal" valor={nomeOuCodigo(selectedOS.bd_fiscal_codigo, selectedOS.bd_fiscal)} />
                  {/* idOsGerouBanco vem como flag S/N */}
                  <Campo
                    label="Gerou BD Fiscal"
                    valor={{ S: "Sim", N: "Não" }[selectedOS.id_os_gerou_banco] ?? selectedOS.id_os_gerou_banco}
                  />
                  {/* idTermoOS vem como flag ("N"); quem tem texto util e
                      dsIdTermoOS — o codigo so entra se a descricao faltar. */}
                  <Campo label="Termo da OS" valor={selectedOS.termo_os_descricao || selectedOS.termo_os} />
                </div>
              </Secao>

              {/* Alguns campos do ATF chegam so como codigo, sem descricao
                  que os traduza (tpNatureza "I", tpDocumento "1",
                  stPrazoOS "0", cdMunicipio). Eles continuam na resposta
                  da API — para relatorio, cruzamento e depuracao — mas
                  ficam fora da tela: um numero solto nao informa ninguem.
                  Quando o ATF publicar as tabelas desses codigos, e so
                  voltar com os Campo correspondentes. */}
              <Secao titulo="Contribuinte">
                <div className="os-detail-grid">
                  <Campo label="Razão Social" valor={selectedOS.razao_social} />
                  <Campo label="IE" valor={selectedOS.ie} />
                  <Campo label="CNPJ / CPF" valor={selectedOS.cnpj} />
                  {selectedOS.contribuinte?.endereco && (
                    <>
                      <Campo label="Endereço" valor={enderecoLinha(selectedOS.contribuinte.endereco)} />
                      <Campo label="Bairro" valor={selectedOS.contribuinte.endereco.bairro} />
                      <Campo label="Município / UF" valor={municipioLinha(selectedOS.contribuinte.endereco)} />
                      <Campo label="Repartição" valor={selectedOS.contribuinte.endereco.reparticao} />
                      <Campo
                        label="Coordenadas"
                        valor={[selectedOS.contribuinte.endereco.latitude,
                                selectedOS.contribuinte.endereco.longitude]
                          .filter(Boolean).join(", ")}
                      />
                      <Campo label="Endereço Atualizado em" valor={formatarData(selectedOS.contribuinte.endereco.atualizado_em)} />
                    </>
                  )}
                </div>
              </Secao>

              <Secao titulo="Datas e Execução">
                <div className="os-detail-grid">
                  <Campo label="Abertura" valor={formatarData(selectedOS.data_abertura)} />
                  <Campo label="Emissão" valor={formatarData(selectedOS.data_emissao)} />
                  <Campo label="Início da Fiscalização" valor={formatarData(selectedOS.data_inicio_fiscalizacao)} />
                  <Campo label="Prazo Final" valor={formatarData(selectedOS.data_prazo_final)} />
                  <Campo label="Encerramento" valor={formatarData(selectedOS.data_encerramento)} />
                  <Campo label="Último Evento" valor={formatarData(selectedOS.data_ultimo_evento)} />
                  <Campo label="Dias de Execução" valor={selectedOS.dias_execucao} />
                  <Campo
                    label="Tempo Médio (Modelo/Motivo)"
                    valor={selectedOS.tempo_medio_execucao_modelo_motivo != null
                      ? `${selectedOS.tempo_medio_execucao_modelo_motivo} dias`
                      : ""}
                  />
                  <Campo label="Média de Eventos (Modelo/Motivo)" valor={selectedOS.qtd_media_eventos_modelo_motivo} />
                  <Campo
                    label="Exercício"
                    valor={periodoTexto(
                      { inicio: selectedOS.data_inicio_exercicio, fim: selectedOS.data_final_exercicio },
                      formatarData,
                    )}
                  />
                  <Campo label="Total Recolhido" valor={formatarValor(selectedOS.valor_total_recolhido)} />
                </div>
              </Secao>

              {(selectedOS.periodo_nf || selectedOS.periodo_efd || selectedOS.autorizacao) && (
                <Secao titulo="Cargas e Autorização">
                  <div className="os-detail-grid">
                    <Campo label="Período de NF (emissão)" valor={periodoTexto(selectedOS.periodo_nf, formatarData)} />
                    <Campo label="Período de EFD (referência)" valor={periodoTexto(selectedOS.periodo_efd, formatarData)} />
                    <Campo label="Autorizada em" valor={formatarData(selectedOS.autorizacao?.data)} />
                    <Campo
                      label="Autorizada por"
                      valor={[selectedOS.autorizacao?.usuario, selectedOS.autorizacao?.matricula]
                        .filter(Boolean).join(" — ")}
                    />
                  </div>
                </Secao>
              )}

              <Secao titulo={`Fiscais (${selectedOS.fiscais?.length ?? 0})`}>
                {selectedOS.fiscais?.length > 0 ? (
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Matr&iacute;cula</th>
                          <th>Nome</th>
                          <th>Respons&aacute;vel</th>
                          <th>Status</th>
                          <th>Designa&ccedil;&atilde;o</th>
                          <th>Ci&ecirc;ncia</th>
                          <th>Cancelamento</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.fiscais.map((f, i) => (
                          <tr key={i}>
                            <td>{f.matricula}</td>
                            <td>{f.nome}</td>
                            <td>{f.responsavel || "-"}</td>
                            <td>{nomeOuCodigo(f.status_codigo, f.status)}</td>
                            <td>{formatarData(f.data_designacao)}</td>
                            <td>{formatarData(f.data_ciencia)}</td>
                            <td>{formatarData(f.data_cancelamento)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                    Nenhum fiscal designado.
                  </p>
                )}
              </Secao>

              {selectedOS.eventos?.length > 0 && (
                <Secao titulo={`Eventos de Acompanhamento (${selectedOS.eventos.length})`}>
                  <div className="os-movimentacoes-timeline">
                    {selectedOS.eventos.map((ev, i) => (
                      <div className="os-mov-item" key={i}>
                        <span className="os-mov-dot" />
                        <div className="os-mov-content">
                          <div className="os-mov-header">
                            <strong style={{ fontSize: 13 }}>{nomeOuCodigo(ev.tipo_codigo, ev.tipo)}</strong>
                            <span className="os-mov-date">
                              {periodoTexto(
                                { inicio: ev.data_inicial, fim: ev.data_final }, formatarData,
                              ) || "-"}
                            </span>
                          </div>
                          {ev.procedimento && <p className="os-mov-desc">{ev.procedimento}</p>}
                          {ev.observacao && <p className="os-mov-desc">{ev.observacao}</p>}
                          {ev.arquivo && <p className="os-mov-desc">&#128206; {ev.arquivo}</p>}
                          <span className="os-mov-resp">
                            {[
                              periodoTexto({ inicio: ev.referencia_inicial, fim: ev.referencia_final }),
                              ev.valor_levantado != null ? `Levantado: ${formatarValor(ev.valor_levantado)}` : "",
                            ].filter(Boolean).join("  ·  ")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </Secao>
              )}

              {selectedOS.prorrogacoes?.length > 0 && (
                <Secao titulo={`Prorrogações (${selectedOS.prorrogacoes.length})`}>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Dias</th>
                          <th>Prazo Anterior</th>
                          <th>Prazo Atual</th>
                          <th>Situa&ccedil;&atilde;o</th>
                          <th>Status</th>
                          <th>Solicitante</th>
                          <th>Homologa&ccedil;&atilde;o</th>
                          <th>Justificativa</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.prorrogacoes.map((p, i) => (
                          <tr key={i}>
                            <td>{p.dias ?? "-"}</td>
                            <td>{formatarData(p.prazo_anterior)}</td>
                            <td>{formatarData(p.prazo_atual)}</td>
                            <td>{p.situacao_prazo || "-"}</td>
                            <td>{p.status || "-"}</td>
                            <td>{p.usuario || "-"}</td>
                            <td>
                              {p.data_homologacao
                                ? `${formatarData(p.data_homologacao)}${p.usuario_homologacao ? ` — ${p.usuario_homologacao}` : ""}`
                                : "-"}
                            </td>
                            <td>{p.justificativa || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Secao>
              )}

              {(selectedOS.notificacoes?.length > 0 || selectedOS.notificacoes_scamf?.length > 0) && (
                <Secao titulo="Notificações">
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Origem</th>
                          <th>C&oacute;digo</th>
                          <th>Notifica&ccedil;&atilde;o</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ...(selectedOS.notificacoes || []).map(n => ({ ...n, origem: "ATF" })),
                          ...(selectedOS.notificacoes_scamf || []).map(n => ({ ...n, origem: "SCAMF" })),
                        ].map((n, i) => (
                          <tr key={i}>
                            <td>{n.origem}</td>
                            <td>{n.codigo || "-"}</td>
                            <td>{n.nome || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Secao>
              )}

              {selectedOS.processos?.length > 0 && (
                <Secao titulo={`Processos (${selectedOS.processos.length})`}>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>N&uacute;mero</th>
                          <th>Tipo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.processos.map((p, i) => (
                          <tr key={i}>
                            <td>{p.numero || "-"}</td>
                            <td>{p.tipo || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Secao>
              )}

              {selectedOS.recolhimentos?.length > 0 && (
                <Secao titulo={`Recolhimentos (${selectedOS.recolhimentos.length})`}>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Inclus&atilde;o</th>
                          <th>Refer&ecirc;ncia</th>
                          <th>Receita</th>
                          <th>Descri&ccedil;&atilde;o</th>
                          <th>Nosso N&uacute;mero</th>
                          <th>D&eacute;bito</th>
                          <th>ARR</th>
                          <th style={{ textAlign: "right" }}>Principal</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.recolhimentos.map((rec, i) => (
                          <tr key={i}>
                            <td>{formatarData(rec.data_inclusao)}</td>
                            <td>{rec.referencia || "-"}</td>
                            <td>{nomeOuCodigo(rec.receita_codigo, rec.receita_nome)}</td>
                            <td>{rec.descricao || "-"}</td>
                            <td>{rec.nosso_numero || "-"}</td>
                            <td>{rec.situacao_debito || "-"}</td>
                            <td>{rec.situacao_arr || "-"}</td>
                            <td style={{ textAlign: "right" }}>{formatarValor(rec.valor_principal) || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Secao>
              )}

              {selectedOS.denuncias?.length > 0 && (
                <Secao titulo={`Den&uacute;ncias (${selectedOS.denuncias.length})`}>
                  <div className="os-movimentacoes-timeline">
                    {selectedOS.denuncias.map((den, i) => (
                      <div className="os-mov-item" key={i}>
                        <span className="os-mov-dot" />
                        <div className="os-mov-content">
                          <div className="os-mov-header">
                            <strong style={{ fontSize: 13 }}>Den&uacute;ncia</strong>
                            <span className="os-mov-date">{formatarData(den.data)}</span>
                          </div>
                          <p className="os-mov-desc" style={{ whiteSpace: "pre-wrap" }}>{den.descricao}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Secao>
              )}

              {selectedOS.justificativas?.length > 0 && (
                <Secao titulo={`Justificativas de Atraso (${selectedOS.justificativas.length})`}>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Data</th>
                          <th>Tipo</th>
                          <th>Justificativa</th>
                          <th>Respons&aacute;vel</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedOS.justificativas.map((j, i) => (
                          <tr key={i}>
                            <td>{formatarData(j.data_inclusao)}</td>
                            <td>{j.tipo || "-"}</td>
                            <td>{j.descricao || "-"}</td>
                            <td>{j.usuario || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Secao>
              )}

              {selectedOS.descricoes_complementares?.length > 0 && (
                <Secao titulo="Descrições Complementares">
                  <div className="os-movimentacoes-timeline">
                    {selectedOS.descricoes_complementares.map((d, i) => (
                      <div className="os-mov-item" key={i}>
                        <span className="os-mov-dot" />
                        <div className="os-mov-content">
                          <div className="os-mov-header">
                            <strong style={{ fontSize: 13 }}>{d.usuario || "-"}</strong>
                            <span className="os-mov-date">{formatarData(d.data_inclusao)}</span>
                          </div>
                          <p className="os-mov-desc" style={{ whiteSpace: "pre-wrap" }}>{d.descricao}</p>
                          {/* dsTxtComplOSFormatado costuma repetir o texto acima;
                              so aparece quando traz algo diferente. Vai como
                              texto puro de proposito: e conteudo do ATF, e
                              injeta-lo como HTML abriria porta para XSS. */}
                          {d.descricao_formatada && d.descricao_formatada !== d.descricao && (
                            <p className="os-mov-desc" style={{ whiteSpace: "pre-wrap" }}>
                              {d.descricao_formatada}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </Secao>
              )}
            </div>

            {/* Footer */}
            <div className="os-detail-footer">
              <button className="small secondary" onClick={closeDetail}>Fechar</button>
              <button
                className="small"
                style={{ background: "#1a3a6c", color: "#fff", border: "none" }}
                onClick={() => handleDownloadPdf(selectedOS.numero_os || selectedOS.numero)}
              >
                &#128196; Baixar PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
