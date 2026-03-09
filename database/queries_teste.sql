-- Queries uteis para testar o banco sefaz_test

-- 1. Contar todas as OS
SELECT COUNT(*) as total FROM ordens_servico;

-- 2. OS por status
SELECT status, COUNT(*) as quantidade 
FROM ordens_servico 
GROUP BY status 
ORDER BY quantidade DESC;

-- 3. OS urgentes
SELECT numero, razao_social, matricula_supervisor 
FROM ordens_servico 
WHERE prioridade = 'urgente';

-- 4. OS sem ciencia
SELECT numero, razao_social, data_abertura 
FROM ordens_servico 
WHERE data_ciencia IS NULL;

-- 5. Listar todas com detalhes
SELECT numero, tipo, razao_social, status, prioridade, 
       data_abertura, data_ciencia 
FROM ordens_servico 
ORDER BY prioridade DESC, numero;
