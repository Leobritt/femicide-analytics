-- =====================================================================
-- 02_agregacoes.sql — tabelas de agregação (materialized views)
-- Recriadas a cada carga pelo run_etl.py. Alimentam o dashboard.
-- =====================================================================

-- Série anual: feminicídio x homicídio doloso
DROP MATERIALIZED VIEW IF EXISTS agg_ano;
CREATE MATERIALIZED VIEW agg_ano AS
SELECT ano,
       COUNT(*)                                    AS total,
       COUNT(*) FILTER (WHERE feminicidio)         AS feminicidios,
       COUNT(*) FILTER (WHERE NOT feminicidio)     AS homicidios_dolosos,
       ROUND(100.0 * COUNT(*) FILTER (WHERE feminicidio) / NULLIF(COUNT(*), 0), 1) AS pct_feminicidio
FROM ocorrencias
GROUP BY ano;

-- Ano x raça/cor
DROP MATERIALIZED VIEW IF EXISTS agg_ano_raca;
CREATE MATERIALIZED VIEW agg_ano_raca AS
SELECT ano, raca_cor,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
FROM ocorrencias
GROUP BY ano, raca_cor;

-- Cruzamento interseccional: faixa etária x raça/cor
DROP MATERIALIZED VIEW IF EXISTS agg_faixa_raca;
CREATE MATERIALIZED VIEW agg_faixa_raca AS
SELECT faixa_etaria, raca_cor,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
FROM ocorrencias
GROUP BY faixa_etaria, raca_cor;

-- Município
DROP MATERIALIZED VIEW IF EXISTS agg_municipio;
CREATE MATERIALIZED VIEW agg_municipio AS
SELECT municipio,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
FROM ocorrencias
GROUP BY municipio;

-- Relação vítima-autor
DROP MATERIALIZED VIEW IF EXISTS agg_relacao;
CREATE MATERIALIZED VIEW agg_relacao AS
SELECT grupo_relacao, relacao_vitima_autor,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
FROM ocorrencias
GROUP BY grupo_relacao, relacao_vitima_autor;

-- Tipo de local x meio empregado
DROP MATERIALIZED VIEW IF EXISTS agg_local_meio;
CREATE MATERIALIZED VIEW agg_local_meio AS
SELECT tipo_local, meio_empregado,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
FROM ocorrencias
GROUP BY tipo_local, meio_empregado;

-- Bairro, com supressão de células pequenas (LGPD / risco de reidentificação):
-- bairros com menos de 3 casos são agrupados em "OUTROS BAIRROS".
DROP MATERIALIZED VIEW IF EXISTS agg_bairro;
CREATE MATERIALIZED VIEW agg_bairro AS
WITH base AS (
    SELECT municipio, bairro, COUNT(*) AS total,
           COUNT(*) FILTER (WHERE feminicidio) AS feminicidios
    FROM ocorrencias
    GROUP BY municipio, bairro
)
SELECT municipio,
       CASE WHEN total >= 3 THEN bairro ELSE 'OUTROS BAIRROS (<3 casos)' END AS bairro,
       SUM(total)::INT        AS total,
       SUM(feminicidios)::INT AS feminicidios
FROM base
GROUP BY 1, 2;
