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

CREATE INDEX IF NOT EXISTS idx_municipio_territorio ON dim_municipio (id_territorio);
CREATE INDEX IF NOT EXISTS idx_fato_tipo_crime      ON fato_vitimas (id_tipo_crime);

COMMENT ON TABLE dim_territorio IS 'Territórios de Identidade da Bahia (Anexo II, 2011).';
COMMENT ON TABLE dim_municipio  IS 'Municípios da Bahia (código IBGE de 6 dígitos) e o território de cada um.';
COMMENT ON TABLE dim_tipo_crime IS 'Tipos de crime publicados pela SSP-BA. Estupro inclui estupro de vulnerável.';
COMMENT ON TABLE fato_vitimas   IS 'Quantidade de vítimas mulheres por ano, município e tipo de crime (SSP-BA).';
