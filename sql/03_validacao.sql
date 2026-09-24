-- =====================================================================
-- 03_validacao.sql — checagens de qualidade (Veracidade)
-- Rodar após a carga:  psql "$DATABASE_URL" -f sql/03_validacao.sql
-- =====================================================================

-- 1. Total carregado (esperado: 804 registros no arquivo 2017-2024)
SELECT COUNT(*) AS total_registros FROM ocorrencias;

-- 2. Totais por ano — comparar com os números publicados pelo
--    Observatório da SESP-ES (observatorio.sesp.es.gov.br)
SELECT * FROM agg_ano ORDER BY ano;

-- 3. Completude: % de "NÃO INFORMADO"/NULL por coluna
SELECT 'idade_vitima'         AS coluna, ROUND(100.0 * COUNT(*) FILTER (WHERE idade_vitima IS NULL) / NULLIF(COUNT(*), 0), 1) AS pct_ausente FROM ocorrencias
UNION ALL
SELECT 'raca_cor',             ROUND(100.0 * COUNT(*) FILTER (WHERE raca_cor = 'NÃO INFORMADO') / NULLIF(COUNT(*), 0), 1) FROM ocorrencias
UNION ALL
SELECT 'relacao_vitima_autor', ROUND(100.0 * COUNT(*) FILTER (WHERE relacao_vitima_autor = 'NÃO INFORMADO') / NULLIF(COUNT(*), 0), 1) FROM ocorrencias
UNION ALL
SELECT 'tipo_local',           ROUND(100.0 * COUNT(*) FILTER (WHERE tipo_local = 'NÃO INFORMADO') / NULLIF(COUNT(*), 0), 1) FROM ocorrencias
UNION ALL
SELECT 'bairro',               ROUND(100.0 * COUNT(*) FILTER (WHERE bairro = 'NÃO INFORMADO') / NULLIF(COUNT(*), 0), 1) FROM ocorrencias
ORDER BY pct_ausente DESC;

-- 4. Registros com hora 00:00:00 (possível valor padrão, não horário real)
SELECT COUNT(*) AS hora_meia_noite FROM ocorrencias WHERE hora_fato = '00:00:00';

-- 5. Espaço ocupado (limite Aiven Free: 1 GB)
SELECT pg_size_pretty(pg_database_size(current_database())) AS tamanho_banco,
       pg_size_pretty(pg_total_relation_size('ocorrencias'))  AS tamanho_tabela;
