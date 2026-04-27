# Especificação do Endpoint: GET /admin/dashboard

## Visão Geral

**URL:** `GET /admin/dashboard`
**Autenticação:** Bearer Token (somente role `admin`)
**Descrição:** Retorna todos os dados agregados necessários para o painel de gestão.

---

## Query Parameters (opcionais)

| Parâmetro     | Tipo   | Descrição                               | Exemplo      |
|---------------|--------|-----------------------------------------|--------------|
| `data_inicio` | string | Data inicial do período (YYYY-MM-DD)    | `2025-01-01` |
| `data_fim`    | string | Data final do período (YYYY-MM-DD)      | `2025-12-31` |

Se ambos forem omitidos, retorna todos os dados sem corte de período.

---

## Estrutura Completa do Retorno (JSON)

```json
{
  "visao_geral": { ... },
  "distribuicao_status": { ... },
  "evolucao_mensal": [ ... ],
  "desempenho_gerencias": [ ... ],
  "desempenho_supervisoes": [ ... ],
  "carga_fiscais": [ ... ],
  "ranking_criticidade": [ ... ],
  "comparativo_mensal": { ... }
}
```

---

## Detalhamento de cada campo

### `visao_geral`
KPIs globais exibidos nos cards do topo.

```json
{
  "total_os": 120,
  "os_abertas": 30,
  "os_em_andamento": 45,
  "os_concluidas": 40,
  "os_criticas": 15,
  "dias_parado_medio": 10,
  "tempo_medio_conclusao": 22,
  "os_sem_ciencia": 8,
  "total_fiscais": 35,
  "total_supervisores": 10
}
```

| Campo                   | Tipo | Descrição                                                          |
|-------------------------|------|--------------------------------------------------------------------|
| `total_os`              | int  | Total de OS no período                                             |
| `os_abertas`            | int  | OS com status = "aberta"                                           |
| `os_em_andamento`       | int  | OS com status = "em_andamento"                                     |
| `os_concluidas`         | int  | OS com status = "concluida"                                        |
| `os_criticas`           | int  | OS ativas com mais de 15 dias sem movimentação                     |
| `dias_parado_medio`     | int  | Média de dias sem movimentação entre OS ativas                     |
| `tempo_medio_conclusao` | int  | Média de dias entre abertura e conclusão das OS concluídas         |
| `os_sem_ciencia`        | int  | OS abertas sem data de ciência preenchida                          |
| `total_fiscais`         | int  | Quantidade de fiscais com ao menos 1 OS ativa                      |
| `total_supervisores`    | int  | Quantidade de supervisores com ao menos 1 OS                       |

---

### `distribuicao_status`
Usado no gráfico de rosca (pizza).

```json
{
  "aberta": 30,
  "em_andamento": 45,
  "concluida": 40,
  "cancelada": 5
}
```

---

### `evolucao_mensal`
Usado no gráfico de linha "Evolução Mensal". Lista ordenada por mês crescente.

```json
[
  { "mes": "2024-10", "abertas": 12, "concluidas": 8 },
  { "mes": "2024-11", "abertas": 15, "concluidas": 10 },
  { "mes": "2024-12", "abertas": 18, "concluidas": 14 }
]
```

| Campo        | Tipo   | Descrição                                              |
|--------------|--------|--------------------------------------------------------|
| `mes`        | string | Mês no formato `YYYY-MM`                               |
| `abertas`    | int    | Qtd de OS com data_abertura dentro do mês              |
| `concluidas` | int    | Qtd de OS concluídas dentro do mês                     |

---

### `desempenho_gerencias`
Usado nos gráficos e tabela da aba "Gerências". Um objeto por gerência.

```json
[
  {
    "id": 1,
    "nome": "Gerência de Fiscalização",
    "total_os": 40,
    "abertas": 10,
    "em_andamento": 15,
    "concluidas": 14,
    "taxa_conclusao": 35.0,
    "dias_parado_medio": 9,
    "os_criticas": 4,
    "tempo_medio_conclusao": 20
  }
]
```

| Campo                   | Tipo   | Descrição                                                    |
|-------------------------|--------|--------------------------------------------------------------|
| `id`                    | int    | ID da gerência (mesmo ID do cadastro)                        |
| `nome`                  | string | Nome da gerência                                             |
| `total_os`              | int    | Total de OS da gerência                                      |
| `abertas`               | int    | OS com status = "aberta"                                     |
| `em_andamento`          | int    | OS com status = "em_andamento"                               |
| `concluidas`            | int    | OS com status = "concluida"                                  |
| `taxa_conclusao`        | float  | `(concluidas / total_os) * 100`, arredondado 1 casa decimal  |
| `dias_parado_medio`     | int    | Média de dias parado entre OS ativas da gerência             |
| `os_criticas`           | int    | OS ativas com > 15 dias sem movimentação                     |
| `tempo_medio_conclusao` | int    | Média de dias do ciclo abertura → conclusão                  |

---

### `desempenho_supervisoes`
Usado na aba "Supervisões". Um objeto por supervisão.

```json
[
  {
    "id": 5,
    "nome": "Supervisão Alpha",
    "gerencia_id": 1,
    "gerencia_nome": "Gerência de Fiscalização",
    "total_os": 12,
    "abertas": 3,
    "em_andamento": 5,
    "concluidas": 4,
    "taxa_conclusao": 33.3,
    "dias_parado_medio": 7,
    "os_criticas": 2
  }
]
```

| Campo             | Tipo   | Descrição                                        |
|-------------------|--------|--------------------------------------------------|
| `id`              | int    | ID da supervisão                                 |
| `nome`            | string | Nome da supervisão                               |
| `gerencia_id`     | int    | ID da gerência pai (usado para filtro no front)  |
| `gerencia_nome`   | string | Nome da gerência pai                             |
| demais campos     | —      | Mesma lógica de `desempenho_gerencias`           |

---

### `carga_fiscais`
Usado na aba "Fiscais". Um objeto por fiscal com ao menos 1 OS ativa.
Ordenado por `os_ativas` decrescente (sobrecarregados primeiro).

```json
[
  {
    "nome": "João Silva",
    "supervisao_id": 5,
    "os_ativas": 4,
    "dias_parado_medio": 11,
    "os_criticas": 2
  }
]
```

| Campo               | Tipo   | Descrição                                                             |
|---------------------|--------|-----------------------------------------------------------------------|
| `nome`              | string | Nome/matrícula do fiscal (como aparece no campo `fiscais` das OS)     |
| `supervisao_id`     | int    | ID da supervisão do fiscal (usado para filtro no front)               |
| `os_ativas`         | int    | Qtd de OS ativas (aberta + em_andamento) onde o fiscal está vinculado |
| `dias_parado_medio` | int    | Média de dias parado nas OS ativas do fiscal                          |
| `os_criticas`       | int    | OS ativas do fiscal com > 15 dias sem movimentação                    |

---

### `ranking_criticidade`
Usado no "Termômetro da Fiscalização" (exibido na aba Visão Geral quando não há filtro de gerência).
Ordenado por `indice_saude` crescente (pior primeiro).

```json
[
  {
    "id": 2,
    "nome": "Gerência de Auditoria",
    "indice_saude": 42,
    "nivel": "critico",
    "total_os": 35,
    "os_criticas": 10,
    "pct_criticas": 28.6,
    "dias_parado_medio": 18,
    "taxa_conclusao": 20.0,
    "problemas": ["28% OS críticas", "18 dias parado (média)", "taxa conclusão baixa"]
  }
]
```

| Campo               | Tipo         | Descrição                                                                                      |
|---------------------|--------------|------------------------------------------------------------------------------------------------|
| `id`                | int          | ID da gerência                                                                                 |
| `nome`              | string       | Nome da gerência                                                                               |
| `indice_saude`      | int          | Score de 0 a 100. Quanto menor, pior. Ver regra abaixo                                         |
| `nivel`             | string       | `"saudavel"` (≥75) \| `"atencao"` (50–74) \| `"critico"` (25–49) \| `"emergencia"` (<25)     |
| `total_os`          | int          | Total de OS da gerência                                                                        |
| `os_criticas`       | int          | OS com > 15 dias sem movimentação                                                              |
| `pct_criticas`      | float        | `(os_criticas / total_os) * 100`                                                               |
| `dias_parado_medio` | int          | Média de dias parado entre OS ativas                                                           |
| `taxa_conclusao`    | float        | `(concluidas / total_os) * 100`                                                                |
| `problemas`         | list[string] | Lista de textos curtos com os principais problemas identificados (máx. ~3 itens)               |

**Sugestão de cálculo do `indice_saude`** (adaptar conforme regra de negócio):

| Condição                        | Penalidade |
|---------------------------------|------------|
| `pct_criticas > 20%`            | -30        |
| `pct_criticas > 10%`            | -15        |
| `dias_parado_medio > 15`        | -20        |
| `dias_parado_medio > 7`         | -10        |
| `taxa_conclusao < 20%`          | -20        |
| `taxa_conclusao < 40%`          | -10        |

Começa em 100, aplica as penalidades cabíveis, mínimo 0.

---

### `comparativo_mensal`
Deltas exibidos nos KPI cards (setas ▲▼). Compara o mês atual com o mês anterior.

```json
{
  "total_os":          { "atual": 40, "anterior": 35, "delta": 5  },
  "em_andamento":      { "atual": 15, "anterior": 18, "delta": -3 },
  "os_criticas":       { "atual": 8,  "anterior": 5,  "delta": 3  },
  "dias_parado_medio": { "atual": 10, "anterior": 12, "delta": -2 },
  "os_sem_ciencia":    { "atual": 6,  "anterior": 4,  "delta": 2  }
}
```

Cada chave é um KPI. O objeto tem sempre `atual`, `anterior` e `delta = atual - anterior`.
O front exibe a seta apenas quando `delta != 0`.

> **Atenção à interpretação de cor no front:**
> - `os_criticas`, `dias_parado_medio`, `os_sem_ciencia`: delta positivo = **ruim** (vermelho ▲)
> - `total_os`, `em_andamento`: delta positivo = **bom** (verde ▲)

---

## Exemplo de Request

```
GET /admin/dashboard?data_inicio=2025-01-01&data_fim=2025-03-31
Authorization: Bearer <token>
```

## Exemplo de Response (estrutura completa)

```json
{
  "visao_geral": {
    "total_os": 120,
    "os_abertas": 30,
    "os_em_andamento": 45,
    "os_concluidas": 40,
    "os_criticas": 15,
    "dias_parado_medio": 10,
    "tempo_medio_conclusao": 22,
    "os_sem_ciencia": 8,
    "total_fiscais": 35,
    "total_supervisores": 10
  },
  "distribuicao_status": {
    "aberta": 30,
    "em_andamento": 45,
    "concluida": 40,
    "cancelada": 5
  },
  "evolucao_mensal": [
    { "mes": "2025-01", "abertas": 12, "concluidas": 8  },
    { "mes": "2025-02", "abertas": 15, "concluidas": 10 },
    { "mes": "2025-03", "abertas": 18, "concluidas": 14 }
  ],
  "desempenho_gerencias": [
    {
      "id": 1,
      "nome": "Gerência de Fiscalização",
      "total_os": 40,
      "abertas": 10,
      "em_andamento": 15,
      "concluidas": 14,
      "taxa_conclusao": 35.0,
      "dias_parado_medio": 9,
      "os_criticas": 4,
      "tempo_medio_conclusao": 20
    }
  ],
  "desempenho_supervisoes": [
    {
      "id": 5,
      "nome": "Supervisão Alpha",
      "gerencia_id": 1,
      "gerencia_nome": "Gerência de Fiscalização",
      "total_os": 12,
      "abertas": 3,
      "em_andamento": 5,
      "concluidas": 4,
      "taxa_conclusao": 33.3,
      "dias_parado_medio": 7,
      "os_criticas": 2
    }
  ],
  "carga_fiscais": [
    {
      "nome": "João Silva",
      "supervisao_id": 5,
      "os_ativas": 4,
      "dias_parado_medio": 11,
      "os_criticas": 2
    }
  ],
  "ranking_criticidade": [
    {
      "id": 2,
      "nome": "Gerência de Auditoria",
      "indice_saude": 42,
      "nivel": "critico",
      "total_os": 35,
      "os_criticas": 10,
      "pct_criticas": 28.6,
      "dias_parado_medio": 18,
      "taxa_conclusao": 20.0,
      "problemas": ["28% OS críticas", "18 dias parado (média)", "taxa conclusão baixa"]
    }
  ],
  "comparativo_mensal": {
    "total_os":          { "atual": 40, "anterior": 35, "delta": 5  },
    "em_andamento":      { "atual": 15, "anterior": 18, "delta": -3 },
    "os_criticas":       { "atual": 8,  "anterior": 5,  "delta": 3  },
    "dias_parado_medio": { "atual": 10, "anterior": 12, "delta": -2 },
    "os_sem_ciencia":    { "atual": 6,  "anterior": 4,  "delta": 2  }
  }
}
```
