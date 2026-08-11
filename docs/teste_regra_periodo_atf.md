# Teste: regra de período dos filtros do ATF (doc da listagem)

**Objetivo:** provar se o serviço `listarOrdensServicoWebService` segue a Regra b da
doc da listagem ou não, para reportar ao time do ATF.

**Regra b (doc):** os campos `cdModeloOS`, `cdMotivoAbertOS`, `statusOS`,
`cdEquipeFisc` e `cdOrgaoExec` devem ser informados combinados com **um** dos
períodos — data de Abertura **ou** data de Encerramento.

**Comportamento observado em 10/08/2026 (ambiente dev):** o serviço rejeitava a
busca quando apenas UM período era informado; só aceitava com os DOIS períodos
(abertura E encerramento) — divergindo da doc.

---

## Como rodar

Cada teste é um `curl` contra o ambiente de desenvolvimento. Rode no PowerShell
ou CMD, a partir da raiz do projeto. Se der erro de certificado TLS, adicione
`-k` após `curl.exe`.

> Os corpos XML estão em `docs/testes-atf/`. Importante: os parâmetros dentro do
> CDATA precisam ficar em **linha única** — o parser do ATF rejeita quebras de
> linha dentro do CDATA (respondendo "É necessário informar pelo menos um
> filtro"). Os arquivos já estão no formato correto, não reformate.

```powershell
curl.exe -s -X POST "https://<host-homologacao>/<caminho-do-servico>" -H "Content-Type: text/xml; charset=utf-8" --data-binary "@docs/testes-atf/teste_A_status_com_dois_periodos.xml"
curl.exe -s -X POST "https://<host-homologacao>/<caminho-do-servico>" -H "Content-Type: text/xml; charset=utf-8" --data-binary "@docs/testes-atf/teste_B_status_so_abertura.xml"
curl.exe -s -X POST "https://<host-homologacao>/<caminho-do-servico>" -H "Content-Type: text/xml; charset=utf-8" --data-binary "@docs/testes-atf/teste_C_status_so_encerramento.xml"
curl.exe -s -X POST "https://<host-homologacao>/<caminho-do-servico>" -H "Content-Type: text/xml; charset=utf-8" --data-binary "@docs/testes-atf/teste_D_status_sem_periodo.xml"
curl.exe -s -X POST "https://<host-homologacao>/<caminho-do-servico>" -H "Content-Type: text/xml; charset=utf-8" --data-binary "@docs/testes-atf/teste_E_modelo_so_abertura.xml"
```

## Matriz de testes e resultados esperados

| Teste | Parâmetros | Segundo a DOC | Se falhar, significa |
|-------|-----------|---------------|----------------------|
| A | `statusOS=1` + abertura (01/01–30/06/2026) + encerramento (01/01–30/06/2026) | ✅ deve listar | (controle — funcionava em 10/08) |
| B | `statusOS=1` + **só** abertura (01/01–30/06/2026) | ✅ deve listar | **serviço diverge da doc** ← teste-chave |
| C | `statusOS=1` + **só** encerramento (01/01–30/06/2026) | ✅ deve listar | **serviço diverge da doc** ← teste-chave |
| D | `statusOS=1` sem nenhum período | ❌ deve dar erro de negócio | (controle negativo — confirma que a regra existe) |
| E | `cdModeloOS=1` + **só** abertura | ✅ deve listar | mesma divergência, com outro campo da Regra b |

**Interpretação:**
- Se **B e C funcionarem**: o serviço está conforme a doc; o sistema (que agora
  valida exigindo apenas um período) está correto — nada a reportar.
- Se **B e/ou C falharem** (com `dsMensagemErro` pedindo os dois períodos, ou
  similar): o serviço diverge da Regra b da doc da listagem. Reportar ao ATF
  anexando o corpo enviado (arquivo XML) e a resposta recebida.
- **D deve sempre falhar** — se D funcionar, a regra b não está sendo aplicada
  de nenhuma forma (outra divergência, também vale reportar).

## Onde a resposta indica erro

Sucesso: a resposta traz `<listaOrdemServico>` com elementos `<ordemServico>`.
Erro de negócio: a resposta traz `<dsMensagemErro>` com a mensagem do ATF
(dentro do XML escapado em `<retorno>`).

## Estado do código (11/08/2026)

O frontend ([frontend/src/atfFilters.js](../frontend/src/atfFilters.js)) valida
conforme a **doc**: Modelo/Motivo/Situação/Equipe/Órgão exigem **um** período
(abertura ou encerramento). Se o ATF confirmar que o serviço exige os dois e
não for corrigi-lo, reverter a condição para
`aberturaCompleta && encerramentoCompleto`.
