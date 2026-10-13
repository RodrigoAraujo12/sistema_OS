/**
 * DetalheOS.jsx – Modal com o detalhe completo de UMA OS do ATF.
 *
 * Aberto pela tela de OS (clique numa linha) e pela de alertas (clique
 * num alerta). Quem usa so diz qual OS abrir: buscar, o carregando, o
 * erro e o modal ficam aqui, para as duas telas mostrarem a mesma coisa.
 */

import React, { useEffect, useState } from "react";
import apiClient from "../api.js";
import { formatarData } from "../constants.js";

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
 * Busca a OS de `alvo` e mostra o detalhe dela; `alvo` null fecha.
 *
 * `alvo` e { numero, linha }. A linha e a OS como veio da listagem, quando
 * quem chama a tem em maos (a tela de OS): ela entra como base porque a
 * listagem tem campos que o detalhe nao devolve (ver mesclarDetalhe). O
 * alerta so tem o numero, entao a linha e buscada junto, em paralelo —
 * logo depois de carregar os alertas ela ainda esta no cache da listagem
 * e nao vai ao ATF. Se so ela falhar, o modal abre com o detalhe sozinho:
 * menos campos e melhor que modal nenhum.
 *
 * Cada `alvo` novo e uma consulta nova, mesmo que seja a mesma OS.
 */
export default function DetalheOS({ alvo, onClose }) {
  const [selectedOS, setSelectedOS] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    setSelectedOS(null);
    setDetailError("");
    setLoadingDetail(Boolean(alvo));
    if (!alvo) return undefined;
    // A resposta de uma OS que ja foi fechada ou trocada por outra nao
    // pode abrir o modal por cima.
    let ativo = true;
    const linha = alvo.linha
      ? Promise.resolve(alvo.linha)
      : apiClient.getOrdem(alvo.numero).catch(() => ({ numero_os: alvo.numero }));
    Promise.all([linha, apiClient.getOrdemDetalhe(alvo.numero)])
      .then(([base, detalhe]) => { if (ativo) setSelectedOS(mesclarDetalhe(base, detalhe)); })
      .catch((err) => { if (ativo) setDetailError(err.message || "Erro ao carregar detalhes da OS"); })
      .finally(() => { if (ativo) setLoadingDetail(false); });
    return () => { ativo = false; };
  }, [alvo]);

  function closeDetail() {
    onClose();
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

  return (
    <>
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
