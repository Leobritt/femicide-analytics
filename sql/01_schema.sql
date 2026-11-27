-- =====================================================================
-- 01_schema.sql — modelo estrela (camada tratada)
-- Executado pelo run_etl.py antes de cada carga.
--
--   dim_territorio (26) 1---N dim_municipio (417) 1---N fato_vitimas (4.587)
--                                  dim_tipo_crime (11) 1---N fato_vitimas
-- =====================================================================

CREATE TABLE IF NOT EXISTS dim_territorio (
    id_territorio    SMALLINT     PRIMARY KEY,               -- nº do território no Anexo II
    nome_territorio  VARCHAR(50)  NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_municipio (
    cod_ibge         INTEGER      PRIMARY KEY                -- coluna ID da planilha (IBGE, 6 dígitos)
                     CHECK (cod_ibge BETWEEN 290000 AND 299999),
    nome_municipio   VARCHAR(60)  NOT NULL,
    id_territorio    SMALLINT     NOT NULL REFERENCES dim_territorio (id_territorio)
);

CREATE TABLE IF NOT EXISTS dim_tipo_crime (
    id_tipo_crime    SMALLINT     PRIMARY KEY,               -- ordem da coluna na planilha
    codigo           VARCHAR(40)  NOT NULL UNIQUE,           -- ex.: lesao_corporal_dolosa
    nome_tipo_crime  VARCHAR(40)  NOT NULL UNIQUE,           -- rótulo original da SSP-BA
    letal            BOOLEAN      NOT NULL                   -- crime com resultado morte
);

CREATE TABLE IF NOT EXISTS fato_vitimas (
    ano              SMALLINT     NOT NULL CHECK (ano BETWEEN 2000 AND 2100),
    cod_ibge         INTEGER      NOT NULL REFERENCES dim_municipio (cod_ibge),
    id_tipo_crime    SMALLINT     NOT NULL REFERENCES dim_tipo_crime (id_tipo_crime),
    qtd_vitimas      INTEGER      NOT NULL CHECK (qtd_vitimas >= 0),
    PRIMARY KEY (ano, cod_ibge, id_tipo_crime)               -- impede carga duplicada
);

-- Colunas do IBGE Cidades. ALTER em vez de CREATE para valer também em bancos já criados
-- (CREATE TABLE IF NOT EXISTS não acrescenta colunas). Entram sem NOT NULL porque a tabela
-- pode já ter linhas neste ponto; o load.py aplica o NOT NULL depois do TRUNCATE + COPY.
ALTER TABLE dim_municipio
    ADD COLUMN IF NOT EXISTS codigo_ibge7            INTEGER       UNIQUE
                             CHECK (codigo_ibge7 BETWEEN 2900000 AND 2999999 AND codigo_ibge7 / 10 = cod_ibge),
    ADD COLUMN IF NOT EXISTS area_km2                NUMERIC(10,3) CHECK (area_km2 > 0),
    ADD COLUMN IF NOT EXISTS populacao_censo_2022    INTEGER       CHECK (populacao_censo_2022 > 0),
    ADD COLUMN IF NOT EXISTS populacao_estimada_2026 INTEGER       CHECK (populacao_estimada_2026 > 0),
    -- Censo 2022, tabela 9606: mulheres residentes por cor ou raça
    ADD COLUMN IF NOT EXISTS mulheres_2022           INTEGER       CHECK (mulheres_2022 > 0),
    ADD COLUMN IF NOT EXISTS mulheres_brancas_2022   INTEGER       CHECK (mulheres_brancas_2022 >= 0),
    ADD COLUMN IF NOT EXISTS mulheres_pretas_2022    INTEGER       CHECK (mulheres_pretas_2022 >= 0),
    ADD COLUMN IF NOT EXISTS mulheres_pardas_2022    INTEGER       CHECK (mulheres_pardas_2022 >= 0),
    ADD COLUMN IF NOT EXISTS mulheres_amarelas_2022  INTEGER       CHECK (mulheres_amarelas_2022 >= 0),
    ADD COLUMN IF NOT EXISTS mulheres_indigenas_2022 INTEGER       CHECK (mulheres_indigenas_2022 >= 0);

CREATE INDEX IF NOT EXISTS idx_municipio_territorio ON dim_municipio (id_territorio);
CREATE INDEX IF NOT EXISTS idx_fato_tipo_crime      ON fato_vitimas (id_tipo_crime);

COMMENT ON TABLE dim_territorio IS 'Territórios de Identidade da Bahia (Anexo II, 2011).';
COMMENT ON TABLE dim_municipio  IS 'Municípios da Bahia (código IBGE de 6 dígitos), o território de cada um e população/área do IBGE.';
COMMENT ON COLUMN dim_municipio.codigo_ibge7            IS 'Código IBGE com dígito verificador (7 dígitos), padrão de IBGE/DATASUS/Siconfi.';
COMMENT ON COLUMN dim_municipio.area_km2                IS 'Área territorial em km² (IBGE Cidades, referência 2025).';
COMMENT ON COLUMN dim_municipio.populacao_censo_2022    IS 'População residente no Censo 2022 (IBGE).';
COMMENT ON COLUMN dim_municipio.populacao_estimada_2026 IS 'População estimada (IBGE Cidades, rótulo 2026).';
COMMENT ON COLUMN dim_municipio.mulheres_2022          IS 'Mulheres residentes no Censo 2022 (IBGE, tabela 9606), todas as cores ou raças e sem declaração.';
COMMENT ON COLUMN dim_municipio.mulheres_pretas_2022   IS 'Mulheres de cor ou raça preta no Censo 2022. Pretas + pardas = população negra (convenção do IBGE).';
COMMENT ON COLUMN dim_municipio.mulheres_pardas_2022   IS 'Mulheres de cor ou raça parda no Censo 2022.';
COMMENT ON TABLE dim_tipo_crime IS 'Tipos de crime publicados pela SSP-BA. Estupro inclui estupro de vulnerável.';
COMMENT ON TABLE fato_vitimas   IS 'Quantidade de vítimas mulheres por ano, município e tipo de crime (SSP-BA).';
