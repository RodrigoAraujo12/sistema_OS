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
  "os_canceladas": 5,
  "os_sem_ciencia": 8,
  "taxa_conclusao": 33.3,
  "total_fiscais": 35,
  "total_supervisores": 10
}
```

| Campo                | Tipo  | Descrição                                                      |
|----------------------|-------|----------------------------------------------------------------|
| `total_os`           | int   | Total de OS no período                                         |
| `os_abertas`         | int   | OS com status = "aberta"                                       |
| `os_em_andamento`    | int   | OS com status = "em_andamento"                                 |
| `os_concluidas`      | int   | OS com status = "concluida"                                    |
| `os_canceladas`      | int   | OS com status = "cancelada"                                    |
| `os_sem_ciencia`     | int   | OS abertas sem data de ciência preenchida                      |
| `taxa_conclusao`     | float | `(os_concluidas / total_os) * 100`, arredondado 1 casa decimal |
| `total_fiscais`      | int   | Quantidade de fiscais com ao menos 1 OS ativa                  |
| `total_supervisores` | int   | Quantidade de supervisores com ao menos 1 OS                   |

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
Conta OS pela `data_abertura` (campo disponível na API ATF).

```json
[
  { "mes": "2024-10", "abertas": 12 },
  { "mes": "2024-11", "abertas": 15 },
  { "mes": "2024-12", "abertas": 18 }
]
```

| Campo     | Tipo   | Descrição                                   |
|-----------|--------|---------------------------------------------|
| `mes`     | string | Mês no formato `YYYY-MM`                    |
| `abertas` | int    | Qtd de OS com `data_abertura` dentro do mês |

---

### `desempenho_gerencias`
Usado nos gráficos e tabela da aba "Gerências". Um objeto por gerência.
Ordenado por `taxa_conclusao` crescente (pior primeiro).

```json
[
  {
    "id": 1,
    "nome": "Gerência de Fiscalização",
    "total_os": 40,
    "abertas": 10,
    "em_andamento": 15,
    "concluidas": 14,
    "canceladas": 1,
    "os_sem_ciencia": 6,
    "taxa_conclusao": 35.0
  }
]
```

| Campo            | Tipo   | Descrição                                                    |
|------------------|--------|--------------------------------------------------------------|
| `id`             | int    | ID da gerência (mesmo ID do cadastro SQLite)                 |
| `nome`           | string | Nome da gerência                                             |
| `total_os`       | int    | Total de OS da gerência                                      |
| `abertas`        | int    | OS com status = "aberta"                                     |
| `em_andamento`   | int    | OS com status = "em_andamento"                               |
| `concluidas`     | int    | OS com status = "concluida"                                  |
| `canceladas`     | int    | OS com status = "cancelada"                                  |
| `os_sem_ciencia` | int    | OS abertas sem data de ciência preenchida                    |
| `taxa_conclusao` | float  | `(concluidas / total_os) * 100`, arredondado 1 casa decimal  |

---

### `desempenho_supervisoes`
Usado na aba "Supervisões". Um objeto por supervisão.
Ordenado por `taxa_conclusao` crescente (pior primeiro).

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
    "os_sem_ciencia": 2,
    "taxa_conclusao": 33.3
  }
]
```

| Campo            | Tipo   | Descrição                                       |
|------------------|--------|-------------------------------------------------|
| `id`             | int    | ID da supervisão                                |
| `nome`           | string | Nome da supervisão                              |
| `gerencia_id`    | int    | ID da gerência pai (usado para filtro no front) |
| `gerencia_nome`  | string | Nome da gerência pai                            |
| demais campos    | —      | Mesma lógica de `desempenho_gerencias`          |

---

### `carga_fiscais`
Usado na aba "Fiscais". Um objeto por fiscal com ao menos 1 OS ativa.
Ordenado por `os_ativas` decrescente (sobrecarregados primeiro).

```json
[
  {
    "nome": "João Silva",
    "supervisao_id": 5,
    "os_ativas": 4
  }
]
```

| Campo           | Tipo   | Descrição                                                             |
|-----------------|--------|-----------------------------------------------------------------------|
| `nome`          | string | Nome/matrícula do fiscal (como aparece no campo `fiscais` das OS)     |
| `supervisao_id` | int    | ID da supervisão do fiscal (usado para filtro no front)               |
| `os_ativas`     | int    | Qtd de OS ativas (aberta + em_andamento) onde o fiscal está vinculado |

---

### `ranking_criticidade`
Usado no "Termômetro da Fiscalização" (exibido na aba Visão Geral quando não há filtro de gerência).
Ordenado por `indice_saude` crescente (pior primeiro).

```json
[
  {
    "id": 2,
    "nome": "Gerência de Auditoria",
    "indice_saude": 42.0,
    "nivel": "critico",
    "total_os": 35,
    "os_sem_ciencia": 10,
    "pct_sem_ciencia": 28.6,
    "taxa_conclusao": 20.0,
    "problemas": ["10 OS sem ciencia (28%)", "Taxa de conclusao 20%"]
  }
]
```

| Campo             | Tipo         | Descrição                                                                                  |
|-------------------|--------------|--------------------------------------------------------------------------------------------|
| `id`              | int          | ID da gerência                                                                             |
| `nome`            | string       | Nome da gerência                                                                           |
| `indice_saude`    | float        | Score de 0 a 100. Quanto menor, pior.                                                      |
| `nivel`           | string       | `"saudavel"` (≥75) \| `"atencao"` (50–74) \| `"critico"` (25–49) \| `"emergencia"` (<25) |
| `total_os`        | int          | Total de OS da gerência                                                                    |
| `os_sem_ciencia`  | int          | OS abertas sem data de ciência                                                             |
| `pct_sem_ciencia` | float        | `(os_sem_ciencia / total_os) * 100`                                                        |
| `taxa_conclusao`  | float        | `(concluidas / total_os) * 100`                                                            |
| `problemas`       | list[string] | Lista de textos curtos com os principais problemas identificados (máx. ~2 itens)           |

**Fórmula do `indice_saude`:**

Começa em 100 e aplica as penalidades abaixo (mínimo 0):

| Componente                                   | Penalidade máxima |
|----------------------------------------------|-------------------|
| `(100 - taxa_conclusao) * 0.50`              | até -50 pts       |
| `pct_sem_ciencia * 0.50`                     | até -50 pts       |

**Problemas detectados:**
- `pct_sem_ciencia > 10%` → lista quantidade e percentual
- `os_sem_ciencia > 0` → lista quantidade
- `taxa_conclusao < 30%` → alerta de taxa baixa

---

### `comparativo_mensal`
Deltas exibidos nos KPI cards (setas ▲▼). Compara o mês mais recente com o mês anterior (por `data_abertura`).

```json
{
  "total_os":       { "atual": 40, "anterior": 35, "delta": 5  },
  "abertas":        { "atual": 15, "anterior": 18, "delta": -3 },
  "em_andamento":   { "atual": 12, "anterior": 10, "delta": 2  },
  "concluidas":     { "atual": 10, "anterior": 8,  "delta": 2  },
  "os_sem_ciencia": { "atual": 6,  "anterior": 4,  "delta": 2  },
  "_labels":        { "mes_atual": "2026-04", "mes_anterior": "2026-03" }
}
```

Cada chave KPI tem sempre `atual`, `anterior` e `delta = atual - anterior`.
O campo `_labels` indica quais meses foram comparados.
O front exibe a seta apenas quando `delta != 0`.

> **Interpretação de cor no front:**
> - `os_sem_ciencia`: delta positivo = **ruim** (vermelho ▲)
> - `total_os`, `em_andamento`, `concluidas`, `abertas`: delta positivo = **neutro/bom**

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
    "os_canceladas": 5,
    "os_sem_ciencia": 8,
    "taxa_conclusao": 33.3,
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
    { "mes": "2025-01", "abertas": 12 },
    { "mes": "2025-02", "abertas": 15 },
    { "mes": "2025-03", "abertas": 18 }
  ],
  "desempenho_gerencias": [
    {
      "id": 1,
      "nome": "Gerência de Fiscalização",
      "total_os": 40,
      "abertas": 10,
      "em_andamento": 15,
      "concluidas": 14,
      "canceladas": 1,
      "os_sem_ciencia": 6,
      "taxa_conclusao": 35.0
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
      "os_sem_ciencia": 2,
      "taxa_conclusao": 33.3
    }
  ],
  "carga_fiscais": [
    {
      "nome": "João Silva",
      "supervisao_id": 5,
      "os_ativas": 4
    }
  ],
  "ranking_criticidade": [
    {
      "id": 2,
      "nome": "Gerência de Auditoria",
      "indice_saude": 42.0,
      "nivel": "critico",
      "total_os": 35,
      "os_sem_ciencia": 10,
      "pct_sem_ciencia": 28.6,
      "taxa_conclusao": 20.0,
      "problemas": ["10 OS sem ciencia (28%)", "Taxa de conclusao 20%"]
    }
  ],
  "comparativo_mensal": {
    "total_os":       { "atual": 40, "anterior": 35, "delta": 5  },
    "abertas":        { "atual": 15, "anterior": 18, "delta": -3 },
    "em_andamento":   { "atual": 12, "anterior": 10, "delta": 2  },
    "concluidas":     { "atual": 10, "anterior": 8,  "delta": 2  },
    "os_sem_ciencia": { "atual": 6,  "anterior": 4,  "delta": 2  },
    "_labels":        { "mes_atual": "2025-03", "mes_anterior": "2025-02" }
  }
}
```
