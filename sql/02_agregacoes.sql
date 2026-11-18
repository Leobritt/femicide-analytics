-- =====================================================================
-- 02_agregacoes.sql — visões de consumo para o dashboard
-- Recriadas a cada carga pelo run_etl.py. São visões comuns (não
-- materializadas): com 4.587 linhas no fato, o cálculo é imediato e não
-- ocupa espaço adicional no banco.
-- =====================================================================

-- Território x tipo de crime
CREATE OR REPLACE VIEW vw_territorio_crime AS
SELECT f.ano, t.id_territorio, t.nome_territorio,
       c.id_tipo_crime, c.nome_tipo_crime, c.letal,
       SUM(f.qtd_vitimas)::INT AS qtd_vitimas
FROM fato_vitimas f
JOIN dim_municipio  m USING (cod_ibge)
JOIN dim_territorio t USING (id_territorio)
JOIN dim_tipo_crime c USING (id_tipo_crime)
GROUP BY f.ano, t.id_territorio, t.nome_territorio, c.id_tipo_crime, c.nome_tipo_crime, c.letal;

-- Resumo por território
CREATE OR REPLACE VIEW vw_territorio_resumo AS
SELECT f.ano, t.id_territorio, t.nome_territorio,
       COUNT(DISTINCT m.cod_ibge)::INT                                         AS municipios,
       SUM(f.qtd_vitimas)::INT                                                 AS total_vitimas,
       SUM(f.qtd_vitimas) FILTER (WHERE c.letal)::INT                          AS vitimas_crimes_letais,
       SUM(f.qtd_vitimas) FILTER (WHERE c.codigo = 'feminicidio')::INT         AS feminicidios,
       SUM(f.qtd_vitimas) FILTER (WHERE c.codigo = 'tentativa_de_feminicidio')::INT AS tentativas_feminicidio
FROM fato_vitimas f
JOIN dim_municipio  m USING (cod_ibge)
JOIN dim_territorio t USING (id_territorio)
JOIN dim_tipo_crime c USING (id_tipo_crime)
GROUP BY f.ano, t.id_territorio, t.nome_territorio;

-- Resumo por município
CREATE OR REPLACE VIEW vw_municipio_resumo AS
SELECT f.ano, m.cod_ibge, m.nome_municipio, t.nome_territorio,
       SUM(f.qtd_vitimas)::INT                                          AS total_vitimas,
       SUM(f.qtd_vitimas) FILTER (WHERE c.letal)::INT                   AS vitimas_crimes_letais,
       SUM(f.qtd_vitimas) FILTER (WHERE c.codigo = 'feminicidio')::INT  AS feminicidios
FROM fato_vitimas f
JOIN dim_municipio  m USING (cod_ibge)
JOIN dim_territorio t USING (id_territorio)
JOIN dim_tipo_crime c USING (id_tipo_crime)
GROUP BY f.ano, m.cod_ibge, m.nome_municipio, t.nome_territorio;

-- Total do estado por tipo de crime
CREATE OR REPLACE VIEW vw_crime_estado AS
SELECT f.ano, c.id_tipo_crime, c.nome_tipo_crime, c.letal,
       SUM(f.qtd_vitimas)::INT AS qtd_vitimas
FROM fato_vitimas f
JOIN dim_tipo_crime c USING (id_tipo_crime)
GROUP BY f.ano, c.id_tipo_crime, c.nome_tipo_crime, c.letal;

-- =====================================================================
-- Taxas por 100 mil habitantes (população e área do IBGE Cidades)
--
-- Denominador: populacao_estimada_2026 (estimativa do IBGE com referência em
-- 1º/07/2024, a mais próxima dos crimes de 2025). É a população TOTAL, não a
-- feminina: as taxas comparam municípios entre si, mas não equivalem às taxas
-- oficiais "por 100 mil mulheres".
-- Agregados (território, porte, densidade) usam SUM(vítimas) / SUM(população),
-- nunca a média das taxas municipais.
-- municipio_pequeno (< 20 mil hab.): poucas ocorrências já geram taxas altas;
-- serve para filtrar ou sinalizar em rankings.
-- =====================================================================

-- Município: contagens, taxas, densidade e porte
CREATE OR REPLACE VIEW vw_municipio_taxa AS
WITH v AS (
    SELECT f.ano, f.cod_ibge,
           SUM(f.qtd_vitimas)                                          AS total_vitimas,
           SUM(f.qtd_vitimas) FILTER (WHERE c.letal)                   AS vitimas_crimes_letais,
           SUM(f.qtd_vitimas) FILTER (WHERE c.codigo = 'feminicidio')  AS feminicidios
    FROM fato_vitimas f
    JOIN dim_tipo_crime c USING (id_tipo_crime)
    GROUP BY f.ano, f.cod_ibge
)
SELECT v.ano, m.cod_ibge, m.nome_municipio, t.id_territorio, t.nome_territorio,
       m.populacao_estimada_2026                                       AS populacao,
       m.area_km2,
       ROUND(m.populacao_estimada_2026 / m.area_km2, 2)                AS densidade_hab_km2,
       (m.populacao_estimada_2026 < 20000)                             AS municipio_pequeno,
       v.total_vitimas::INT, v.vitimas_crimes_letais::INT, v.feminicidios::INT,
       ROUND(100000.0 * v.total_vitimas         / m.populacao_estimada_2026, 2) AS taxa_vitimas_100k,
       ROUND(100000.0 * v.vitimas_crimes_letais / m.populacao_estimada_2026, 2) AS taxa_letais_100k,
       ROUND(100000.0 * v.feminicidios          / m.populacao_estimada_2026, 2) AS taxa_feminicidios_100k
FROM v
JOIN dim_municipio  m USING (cod_ibge)
JOIN dim_territorio t USING (id_territorio);

-- Território de Identidade: taxas pela soma de vítimas e de população
CREATE OR REPLACE VIEW vw_territorio_taxa AS
SELECT ano, id_territorio, nome_territorio,
       COUNT(*)::INT                                                AS municipios,
       SUM(populacao)::INT                                          AS populacao,
       SUM(area_km2)                                                AS area_km2,
       ROUND(SUM(populacao) / SUM(area_km2), 2)                     AS densidade_hab_km2,
       SUM(total_vitimas)::INT                                      AS total_vitimas,
       SUM(vitimas_crimes_letais)::INT                              AS vitimas_crimes_letais,
       SUM(feminicidios)::INT                                       AS feminicidios,
       ROUND(100000.0 * SUM(total_vitimas)         / SUM(populacao), 2) AS taxa_vitimas_100k,
       ROUND(100000.0 * SUM(vitimas_crimes_letais) / SUM(populacao), 2) AS taxa_letais_100k,
       ROUND(100000.0 * SUM(feminicidios)          / SUM(populacao), 2) AS taxa_feminicidios_100k
FROM vw_municipio_taxa
GROUP BY ano, id_territorio, nome_territorio;

-- Território x tipo de crime em taxa (versão proporcional da vw_territorio_crime)
CREATE OR REPLACE VIEW vw_crime_taxa_territorio AS
WITH pop AS (   -- população somada à parte, para não multiplicar pelo nº de crimes
    SELECT id_territorio, SUM(populacao_estimada_2026) AS populacao
    FROM dim_municipio GROUP BY id_territorio
)
SELECT tc.ano, tc.id_territorio, tc.nome_territorio,
       tc.id_tipo_crime, tc.nome_tipo_crime, tc.letal, tc.qtd_vitimas,
       pop.populacao::INT,
       ROUND(100000.0 * tc.qtd_vitimas / pop.populacao, 2)          AS taxa_100k
FROM vw_territorio_crime tc
JOIN pop USING (id_territorio);

-- Porte populacional (faixas do IBGE) e densidade demográfica, em formato longo:
-- dimensao = 'porte' ou 'densidade'; ordem_faixa ordena as faixas nos gráficos
CREATE OR REPLACE VIEW vw_porte_municipio AS
WITH faixas AS (
    SELECT mt.*, 'porte' AS dimensao,
           CASE WHEN populacao <  20000 THEN 1 WHEN populacao <  50000 THEN 2
                WHEN populacao < 100000 THEN 3 WHEN populacao < 500000 THEN 4 ELSE 5 END AS ordem_faixa,
           CASE WHEN populacao <  20000 THEN 'até 20 mil hab.'
                WHEN populacao <  50000 THEN '20 a 50 mil hab.'
                WHEN populacao < 100000 THEN '50 a 100 mil hab.'
                WHEN populacao < 500000 THEN '100 a 500 mil hab.'
                ELSE 'mais de 500 mil hab.' END                              AS faixa
    FROM vw_municipio_taxa mt
    UNION ALL
    SELECT mt.*, 'densidade',
           CASE WHEN densidade_hab_km2 < 10 THEN 1 WHEN densidade_hab_km2 < 25 THEN 2
                WHEN densidade_hab_km2 < 50 THEN 3 WHEN densidade_hab_km2 < 100 THEN 4 ELSE 5 END,
           CASE WHEN densidade_hab_km2 <  10 THEN 'até 10 hab./km²'
                WHEN densidade_hab_km2 <  25 THEN '10 a 25 hab./km²'
                WHEN densidade_hab_km2 <  50 THEN '25 a 50 hab./km²'
                WHEN densidade_hab_km2 < 100 THEN '50 a 100 hab./km²'
                ELSE 'mais de 100 hab./km²' END
    FROM vw_municipio_taxa mt
)
SELECT ano, dimensao, ordem_faixa, faixa,
       COUNT(*)::INT                                                AS municipios,
       SUM(populacao)::INT                                          AS populacao,
       SUM(total_vitimas)::INT                                      AS total_vitimas,
       SUM(vitimas_crimes_letais)::INT                              AS vitimas_crimes_letais,
       SUM(feminicidios)::INT                                       AS feminicidios,
       ROUND(100000.0 * SUM(total_vitimas)         / SUM(populacao), 2) AS taxa_vitimas_100k,
       ROUND(100000.0 * SUM(vitimas_crimes_letais) / SUM(populacao), 2) AS taxa_letais_100k,
       ROUND(100000.0 * SUM(feminicidios)          / SUM(populacao), 2) AS taxa_feminicidios_100k
FROM faixas
GROUP BY ano, dimensao, ordem_faixa, faixa;
