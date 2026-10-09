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
