-- =====================================================================
-- 00_limpeza_base_antiga.sql — OPCIONAL, rodar uma única vez
-- Remove a tabela e as visões da base anterior (SESP-ES, 2017-2024), que
-- deixou de ser usada no projeto. O ETL NÃO executa este arquivo.
--   psql "$DATABASE_URL" -f sql/00_limpeza_base_antiga.sql
-- =====================================================================
DROP MATERIALIZED VIEW IF EXISTS agg_ano, agg_ano_raca, agg_faixa_raca, agg_municipio,
                                 agg_relacao, agg_local_meio, agg_bairro;
DROP TABLE IF EXISTS ocorrencias;
