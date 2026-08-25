# Diagrama ER - Sistema SEFAZ

## Visão Geral

O sistema utiliza **três fontes de dados**:
- **SQLite** (`backend/app.db`) — usuários, gerências, supervisões e equipes fiscais (persistência local)
- **API ATF** — ordens de serviço (fonte principal, via HTTPS + XML)
- **IBM Informix** (`sefaz_test`) — ordens de serviço (legado, via ODBC; substituído pela ATF)

## Diagrama Entidade-Relacionamento

```mermaid
erDiagram
    gerencias {
        INTEGER id PK
        TEXT name "UNIQUE NOT NULL"
    }

    supervisoes {
        INTEGER id PK
        INTEGER gerencia_id FK "NOT NULL"
        TEXT name "NOT NULL"
    }

    users {
        INTEGER id PK
        TEXT username "UNIQUE NOT NULL"
        TEXT password_hash "NOT NULL"
        TEXT salt "NOT NULL"
        TEXT role "NOT NULL (admin/gerente/supervisor/fiscal)"
        TEXT matricula "UNIQUE"
        INTEGER gerencia_id FK
        INTEGER supervisao_id FK
        INTEGER equipe_codigo FK "equipe do ATF que o supervisor chefia"
        INTEGER must_change_password
    }

    equipes_fiscais {
        INTEGER codigo PK "cdEquipeFisc do ATF"
        TEXT nome "NOT NULL"
    }

    equipe_membros {
        INTEGER codigo_equipe PK_FK
        TEXT matricula PK "auditor da equipe"
        TEXT nome "NOT NULL"
    }

    ordens_servico {
        VARCHAR numero PK "ex: OS-2026-001"
        VARCHAR tipo "Normal/Simplificada/Especial/Específica"
        VARCHAR ie "Inscricao Estadual"
        VARCHAR cnpj
        VARCHAR razao_social
        VARCHAR matricula_supervisor "vincula ao supervisor"
        VARCHAR fiscais "lista de fiscais (nomes/matriculas)"
        VARCHAR status "aberta/em_andamento/concluida/cancelada"
        VARCHAR prioridade "baixa/media/alta/urgente"
        DATE data_abertura
        DATE data_ciencia "pode ser NULL se fiscal ainda nao assinou"
    }

    gerencias ||--o{ supervisoes : "possui"
    gerencias ||--o{ users : "pertence a"
    supervisoes ||--o{ users : "pertence a"
    equipes_fiscais ||--o{ equipe_membros : "compoe"
    equipes_fiscais ||--o{ users : "supervisionada por"
    users ||--o{ ordens_servico : "supervisiona (matricula)"
    users }o--o{ ordens_servico : "fiscal (nome em fiscais)"
```

> **Nota:** `ordens_servico` não é uma tabela SQLite — representa os dados retornados pela API ATF
> (ou Informix em fallback). Os campos acima refletem o schema normalizado pelo backend após o parse do XML.

## Relações

| De | Para | Tipo | Descrição |
|---|---|---|---|
| `gerencias` | `supervisoes` | 1:N | Uma gerência possui várias supervisões |
| `gerencias` | `users` | 1:N | Gerentes pertencem a uma gerência |
| `supervisoes` | `users` | 1:N | Supervisores e fiscais pertencem a uma supervisão |
| `equipes_fiscais` | `equipe_membros` | 1:N | Uma equipe tem vários auditores (um auditor pode estar em mais de uma) |
| `equipes_fiscais` | `users` | 1:N | Um supervisor pode ser amarrado a uma equipe do ATF |
| `users` | `ordens_servico` | 1:N | Supervisor supervisiona OS (via `matricula` ↔ `matricula_supervisor`) |
| `users` | `ordens_servico` | N:N | Fiscal aparece em OS (via nome no campo `fiscais`) |

## Fontes de dados por endpoint

| Endpoint                    | Fonte de dados                      |
|-----------------------------|-------------------------------------|
| `GET /ordens`               | API ATF (primária) → MOCK           |
| `GET /ordens/{numero}/pdf`  | API ATF (primária) → MOCK           |
| `GET /admin/dashboard`      | Informix (legado) → MOCK            |
| `GET /relatorio/*`          | Informix (legado) → MOCK            |
| `GET /alertas`              | Informix (legado) → MOCK            |
| `GET/POST /admin/users`     | SQLite                              |
| `GET/POST /admin/gerencias` | SQLite                              |
| `GET/POST /admin/supervisoes` | SQLite                            |
| `GET /equipes-fiscais`      | SQLite                              |
