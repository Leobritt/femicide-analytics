-- =====================================================================
-- 03_validacao.sql — checagens de qualidade e quantidade de dados
-- Rodar após a carga:  psql "$DATABASE_URL" -f sql/03_validacao.sql
-- =====================================================================

-- 1. Quantidade de linhas por tabela
--    Esperado: 26 territórios | 417 municípios | 11 tipos de crime | 4.587 linhas no fato
SELECT 'dim_territorio' AS tabela, COUNT(*) AS linhas FROM dim_territorio
UNION ALL SELECT 'dim_municipio',  COUNT(*) FROM dim_municipio
UNION ALL SELECT 'dim_tipo_crime', COUNT(*) FROM dim_tipo_crime
UNION ALL SELECT 'fato_vitimas',   COUNT(*) FROM fato_vitimas;

-- 2. Totais por tipo de crime — comparar com a linha "Total" da planilha da SSP-BA
--    Esperado em 2025: ameaça 56.601 | difamação 11.569 | importunação sexual 1.936 |
--    injúria 18.881 | lesão corporal dolosa 23.887 | tentativa de feminicídio 255 |
--    tentativa de homicídio 472 | estupro 4.422 | homicídio doloso 246 |
--    feminicídio 102 | lesão corporal seguida de morte 9  (soma: 118.380)
SELECT ano, nome_tipo_crime, qtd_vitimas FROM vw_crime_estado ORDER BY ano, id_tipo_crime;
SELECT ano, SUM(qtd_vitimas) AS total_vitimas FROM fato_vitimas GROUP BY ano ORDER BY ano;

-- 3. Integridade: todo município tem as 11 linhas de crime (esperado: 0 linhas)
SELECT m.cod_ibge, m.nome_municipio, COUNT(f.id_tipo_crime) AS tipos_carregados
FROM dim_municipio m
LEFT JOIN fato_vitimas f USING (cod_ibge)
GROUP BY m.cod_ibge, m.nome_municipio
HAVING COUNT(f.id_tipo_crime) <> (SELECT COUNT(*) FROM dim_tipo_crime);

-- 4. Municípios por território (esperado: 26 linhas somando 417)
SELECT t.id_territorio, t.nome_territorio, COUNT(*) AS municipios
FROM dim_territorio t JOIN dim_municipio m USING (id_territorio)
GROUP BY t.id_territorio, t.nome_territorio ORDER BY t.id_territorio;

-- 5. Proporção de células com zero (a fonte não distingue "nenhum caso" de "sem registro")
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE qtd_vitimas = 0) / COUNT(*), 1) AS pct_zeros FROM fato_vitimas;

-- 6. Estrutura: colunas e tipos das tabelas do projeto
SELECT table_name AS tabela, column_name AS coluna, data_type AS tipo,
       character_maximum_length AS tamanho, is_nullable AS aceita_nulo
FROM information_schema.columns
WHERE table_name IN ('dim_territorio', 'dim_municipio', 'dim_tipo_crime', 'fato_vitimas')
ORDER BY table_name, ordinal_position;

-- 7. Espaço ocupado (limite Aiven Free: 1 GB)
SELECT pg_size_pretty(pg_database_size(current_database()))      AS tamanho_banco,
       pg_size_pretty(pg_total_relation_size('fato_vitimas'))    AS tamanho_fato,
       pg_size_pretty(pg_total_relation_size('dim_municipio'))   AS tamanho_dim_municipio;
