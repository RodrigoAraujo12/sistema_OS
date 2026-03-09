-- ============================================================================
-- MIGRAÇÃO V2 - Sistema SEFAZ
-- ============================================================================
-- Esta migração:
-- 1. Remove a coluna "descricao" da tabela ordens_servico
-- 2. Adiciona a coluna "matricula_supervisor"
-- 3. Limpa dados antigos e adiciona novos dados com nomes reais
-- ============================================================================

-- Passo 1: Remover todos os dados antigos
DELETE FROM ordens_servico;

-- Passo 2: Remover coluna descricao (NOTA: Informix não suporta DROP COLUMN diretamente)
-- Solução: Recriar a tabela
DROP TABLE IF EXISTS ordens_servico;

-- Passo 3: Criar nova estrutura da tabela
CREATE TABLE ordens_servico (
    numero VARCHAR(20) PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,
    ie VARCHAR(20) NOT NULL,
    razao_social VARCHAR(200) NOT NULL,
    matricula_supervisor VARCHAR(20) NOT NULL,  -- NOVO CAMPO
    fiscais LVARCHAR(500),  -- Nomes separados por virgula
    status VARCHAR(20) NOT NULL DEFAULT 'aberta',
    prioridade VARCHAR(20) NOT NULL DEFAULT 'normal',
    data_abertura DATE NOT NULL,
    data_ciencia DATE,
    data_ultima_movimentacao DATE NOT NULL,
    
    -- Constraints
    CHECK (status IN ('aberta', 'em_andamento', 'concluida', 'cancelada')),
    CHECK (prioridade IN ('baixa', 'normal', 'alta', 'urgente')),
    CHECK (tipo IN ('Normal', 'Especifico', 'Simplificado'))
);

-- Passo 4: Recriar índices
CREATE INDEX idx_os_status ON ordens_servico(status);
CREATE INDEX idx_os_prioridade ON ordens_servico(prioridade);
CREATE INDEX idx_os_tipo ON ordens_servico(tipo);
CREATE INDEX idx_os_ie ON ordens_servico(ie);
CREATE INDEX idx_os_data_abertura ON ordens_servico(data_abertura);
CREATE INDEX idx_os_matricula_supervisor ON ordens_servico(matricula_supervisor);

-- ============================================================================
-- DADOS DE TESTE COM HIERARQUIA REALISTA (30 OS)
-- ============================================================================
-- Gerencia de Fiscalizacao:
--   Sup. Fiscal A     → Patricia Oliveira (23456) → Carlos Mendes (34567), Ana Ribeiro (34568), Pedro Nascimento (34569)
--   Sup. Fiscal B     → Joao Silva (23457)        → Jose Almeida (34570), Fernanda Costa (34571)
-- Gerencia de Arrecadacao:
--   Sup. Arrecadacao A → Maria Santos (23458)     → Marcos Silva (34572), Claudia Souza (34573), Rafael Lima (34574)
--   Sup. Arrecadacao B → Ricardo Pereira (23459)  → Juliana Martins (34575), Bruno Araujo (34576)
-- Gerencia de Tributacao:
--   Sup. Tributaria A  → Lucia Costa (23460)      → Tatiana Gomes (34577), Diego Cardoso (34578), Vanessa Rocha (34579)
--   Sup. Tributaria B  → Antonio Ferreira (23461) → Leandro Pinto (34580), Camila Teixeira (34581)
-- Gerentes: Roberto Santos (12345), Helena Rodrigues (12346), Sergio Barbosa (12347)
-- ============================================================================

-- ── GERENCIA DE FISCALIZACAO ─────────────────────────────────────

-- Supervisor Patricia Oliveira (23456) - 6 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-001', 'Normal', '12.345.678-9', 'Distribuidora ABC Ltda', '23456', 'Carlos Mendes, Ana Ribeiro', 'em_andamento', 'alta', MDY(1,10,2026), MDY(1,12,2026), MDY(1,25,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-003', 'Simplificado', '55.667.778-3', 'Transportes Rapido Ltda', '23456', 'Ana Ribeiro', 'em_andamento', 'normal', MDY(1,5,2026), MDY(1,8,2026), MDY(1,20,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-006', 'Especifico', '12.345.678-9', 'Distribuidora ABC Ltda', '23456', 'Carlos Mendes', 'aberta', 'alta', MDY(2,7,2026), MDY(2,9,2026), MDY(2,9,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-007', 'Normal', '98.765.432-1', 'Industria Delta S/A', '23456', 'Pedro Nascimento', 'em_andamento', 'normal', MDY(1,15,2026), MDY(1,18,2026), MDY(2,1,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-010', 'Normal', '77.889.900-5', 'Farmacia Popular Ltda', '23456', 'Ana Ribeiro, Pedro Nascimento', 'cancelada', 'alta', MDY(1,20,2026), MDY(1,22,2026), MDY(2,5,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-011', 'Especifico', '44.556.667-8', 'Auto Pecas Nordeste Ltda', '23456', 'Carlos Mendes, Ana Ribeiro', 'aberta', 'urgente', MDY(2,15,2026), NULL, MDY(2,15,2026));

-- Supervisor Joao Silva (23457) - 6 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-002', 'Especifico', '98.765.432-1', 'Industria Delta S/A', '23457', 'Jose Almeida, Fernanda Costa', 'aberta', 'urgente', MDY(2,1,2026), MDY(2,3,2026), MDY(2,3,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-004', 'Normal', '33.445.556-4', 'Supermercado Central Ltda', '23457', 'Jose Almeida', 'aberta', 'alta', MDY(2,5,2026), NULL, MDY(2,5,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-005', 'Simplificado', '77.889.900-5', 'Farmacia Popular Ltda', '23457', 'Fernanda Costa', 'concluida', 'normal', MDY(12,15,2025), MDY(12,18,2025), MDY(1,30,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-008', 'Simplificado', '33.445.556-4', 'Supermercado Central Ltda', '23457', 'Jose Almeida', 'aberta', 'baixa', MDY(12,1,2025), MDY(12,5,2025), MDY(12,10,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-009', 'Especifico', '55.667.778-3', 'Transportes Rapido Ltda', '23457', 'Fernanda Costa, Jose Almeida', 'aberta', 'urgente', MDY(2,8,2026), NULL, MDY(2,8,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-012', 'Normal', '88.990.001-2', 'Construtora Horizonte S/A', '23457', 'Fernanda Costa', 'concluida', 'normal', MDY(11,20,2025), MDY(11,22,2025), MDY(12,28,2025));

-- ── GERENCIA DE ARRECADACAO ──────────────────────────────────────

-- Supervisor Maria Santos (23458) - 5 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-013', 'Normal', '11.222.333-4', 'Comercio Atacadista Sol Ltda', '23458', 'Marcos Silva, Claudia Souza', 'em_andamento', 'alta', MDY(12,20,2025), MDY(12,23,2025), MDY(1,10,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-014', 'Especifico', '22.333.444-5', 'Metalurgica Forte S/A', '23458', 'Rafael Lima', 'aberta', 'urgente', MDY(1,28,2026), MDY(1,30,2026), MDY(1,30,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-015', 'Simplificado', '33.444.555-6', 'Padaria Estrela do Norte Ltda', '23458', 'Claudia Souza', 'concluida', 'normal', MDY(11,10,2025), MDY(11,12,2025), MDY(12,20,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-016', 'Normal', '44.555.666-7', 'Posto Combustivel Rota 101', '23458', 'Marcos Silva, Rafael Lima', 'em_andamento', 'normal', MDY(1,5,2026), MDY(1,8,2026), MDY(2,10,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-017', 'Especifico', '55.666.777-8', 'Textil Nordeste Industria Ltda', '23458', 'Claudia Souza, Marcos Silva', 'aberta', 'alta', MDY(2,12,2026), NULL, MDY(2,12,2026));

-- Supervisor Ricardo Pereira (23459) - 5 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-018', 'Normal', '66.777.888-9', 'Grafica Express Print Ltda', '23459', 'Juliana Martins', 'em_andamento', 'normal', MDY(12,10,2025), MDY(12,12,2025), MDY(1,5,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-019', 'Simplificado', '77.888.999-0', 'Loja Materiais Construcao JB', '23459', 'Bruno Araujo', 'concluida', 'baixa', MDY(10,15,2025), MDY(10,18,2025), MDY(11,30,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-020', 'Especifico', '88.999.000-1', 'Hotel Beira Mar Palace', '23459', 'Juliana Martins, Bruno Araujo', 'aberta', 'alta', MDY(2,1,2026), MDY(2,4,2026), MDY(2,4,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-021', 'Normal', '99.000.111-2', 'Restaurante Sabor e Arte Ltda', '23459', 'Bruno Araujo', 'aberta', 'normal', MDY(1,20,2026), MDY(1,23,2026), MDY(1,23,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-022', 'Simplificado', '11.222.333-4', 'Comercio Atacadista Sol Ltda', '23459', 'Juliana Martins', 'concluida', 'normal', MDY(11,5,2025), MDY(11,8,2025), MDY(12,15,2025));

-- ── GERENCIA DE TRIBUTACAO ───────────────────────────────────────

-- Supervisor Lucia Costa (23460) - 4 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-023', 'Normal', '10.203.040-5', 'Informatica Total Systems Ltda', '23460', 'Tatiana Gomes, Diego Cardoso', 'em_andamento', 'urgente', MDY(11,15,2025), MDY(11,18,2025), MDY(12,1,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-024', 'Especifico', '20.304.050-6', 'Agropecuaria Verde Campo S/A', '23460', 'Vanessa Rocha', 'aberta', 'alta', MDY(1,10,2026), NULL, MDY(1,10,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-025', 'Simplificado', '30.405.060-7', 'Clinica Saude Mais Ltda', '23460', 'Diego Cardoso', 'concluida', 'normal', MDY(10,20,2025), MDY(10,22,2025), MDY(11,28,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-026', 'Normal', '40.506.070-8', 'Escola Futuro Brilhante Ltda', '23460', 'Tatiana Gomes, Vanessa Rocha', 'aberta', 'normal', MDY(2,18,2026), MDY(2,20,2026), MDY(2,20,2026));

-- Supervisor Antonio Ferreira (23461) - 4 OS
INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-027', 'Especifico', '50.607.080-9', 'Imobiliaria Plano Alto Ltda', '23461', 'Leandro Pinto', 'em_andamento', 'alta', MDY(12,5,2025), MDY(12,8,2025), MDY(1,15,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-028', 'Simplificado', '60.708.090-0', 'Papelaria Central Office Ltda', '23461', 'Camila Teixeira', 'aberta', 'baixa', MDY(1,25,2026), MDY(1,28,2026), MDY(1,28,2026));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-029', 'Normal', '70.809.010-1', 'Academia Corpo em Forma Ltda', '23461', 'Leandro Pinto, Camila Teixeira', 'concluida', 'normal', MDY(9,10,2025), MDY(9,12,2025), MDY(10,30,2025));

INSERT INTO ordens_servico (numero, tipo, ie, razao_social, matricula_supervisor, fiscais, status, prioridade, data_abertura, data_ciencia, data_ultima_movimentacao)
VALUES ('OS-2026-030', 'Especifico', '80.900.120-2', 'Pet Shop Amigo Fiel Ltda', '23461', 'Camila Teixeira', 'aberta', 'urgente', MDY(2,20,2026), NULL, MDY(2,20,2026));

-- ============================================================================
-- QUERIES DE VERIFICACAO
-- ============================================================================

-- Total de OS (deve retornar 30)
SELECT COUNT(*) as total FROM ordens_servico;

-- Distribuicao por supervisor
SELECT matricula_supervisor, COUNT(*) as total 
FROM ordens_servico 
GROUP BY matricula_supervisor
ORDER BY matricula_supervisor;

-- Distribuicao por status
SELECT status, COUNT(*) as total 
FROM ordens_servico 
GROUP BY status
ORDER BY status;

-- Distribuicao por gerencia (via supervisor)
-- 23456,23457 = Fiscalizacao (12 OS)
-- 23458,23459 = Arrecadacao (10 OS)
-- 23460,23461 = Tributacao (8 OS)
SELECT 
  CASE 
    WHEN matricula_supervisor IN ('23456','23457') THEN 'Fiscalizacao'
    WHEN matricula_supervisor IN ('23458','23459') THEN 'Arrecadacao'
    WHEN matricula_supervisor IN ('23460','23461') THEN 'Tributacao'
  END as gerencia,
  COUNT(*) as total
FROM ordens_servico
GROUP BY 1
ORDER BY 1;
