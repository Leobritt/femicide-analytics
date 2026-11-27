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

-- 4b. Dados do IBGE: todo município com código de 7 dígitos coerente, área e população
--     (esperado: 0 linhas; população estimada 2026 da Bahia somando ~14,9 milhões)
SELECT cod_ibge, nome_municipio, codigo_ibge7, area_km2, populacao_censo_2022, populacao_estimada_2026
FROM dim_municipio
WHERE codigo_ibge7 IS NULL OR codigo_ibge7 / 10 <> cod_ibge
   OR area_km2 IS NULL OR populacao_censo_2022 IS NULL OR populacao_estimada_2026 IS NULL;
SELECT SUM(populacao_censo_2022) AS pop_censo_2022, SUM(populacao_estimada_2026) AS pop_estimada_2026,
       SUM(area_km2) AS area_km2 FROM dim_municipio;

-- 4c. Visões de taxa: todas precisam somar o mesmo total do fato (esperado: 118.380
--     em cada coluna) e cobrir os 417 municípios e a população inteira
SELECT (SELECT SUM(qtd_vitimas)   FROM fato_vitimas)                                  AS fato,
       (SELECT SUM(total_vitimas) FROM vw_municipio_taxa)                             AS vw_municipio_taxa,
       (SELECT SUM(total_vitimas) FROM vw_territorio_taxa)                            AS vw_territorio_taxa,
       (SELECT SUM(qtd_vitimas)   FROM vw_crime_taxa_territorio)                      AS vw_crime_taxa_territorio,
       (SELECT SUM(total_vitimas) FROM vw_porte_municipio WHERE dimensao = 'porte')     AS vw_porte_porte,
       (SELECT SUM(total_vitimas) FROM vw_porte_municipio WHERE dimensao = 'densidade') AS vw_porte_densidade,
       (SELECT COUNT(*)           FROM vw_municipio_taxa)                             AS municipios,
       (SELECT SUM(populacao)     FROM vw_territorio_taxa)                            AS populacao;

-- 4d. Recorte de gênero e raça: mulheres do Censo 2022 (esperado: 7.305.940, 79,4% pretas
--     e pardas) e a visão por faixa somando as 118.380 vítimas e os 417 municípios
SELECT SUM(mulheres_2022) AS mulheres_2022,
       ROUND(100.0 * SUM(mulheres_pretas_2022 + mulheres_pardas_2022) / SUM(mulheres_2022), 1) AS pct_negras
FROM dim_municipio;
SELECT ordem_faixa, faixa, municipios, mulheres, total_vitimas, vitimas_crimes_letais,
       taxa_vitimas_100k_mulheres, taxa_letais_100k_mulheres
FROM vw_faixa_mulheres_negras ORDER BY ano, ordem_faixa;

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
