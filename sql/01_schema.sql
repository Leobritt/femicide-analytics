-- =====================================================================
-- 01_schema.sql — tabela principal (camada tratada)
-- Rodar uma vez no PostgreSQL da Aiven (o run_etl.py também executa).
-- =====================================================================

CREATE TABLE IF NOT EXISTS ocorrencias (
    id_origem             INTEGER      PRIMARY KEY,          -- _id do portal (rastreabilidade)
    data_obito            DATE         NOT NULL,             -- DAT_OBT
    hora_fato             TIME,                              -- HOR_FAT
    idade_vitima          SMALLINT     CHECK (idade_vitima BETWEEN 0 AND 110), -- IDD_VIT
    municipio             VARCHAR(100) NOT NULL,             -- MUN_OBT
    bairro                VARCHAR(150) NOT NULL,             -- BAI_OBT
    meio_empregado        VARCHAR(30)  NOT NULL,             -- COD_CIOD (A01A/A01B/A01C)
    raca_cor              VARCHAR(30)  NOT NULL,             -- CUTIS
    relacao_vitima_autor  VARCHAR(60)  NOT NULL,             -- REL VIT AUT
    feminicidio           BOOLEAN,                           -- FEMINICIDIO
    tipo_local            VARCHAR(80)  NOT NULL,             -- TIPO LOCAL
    -- atributos derivados no ETL
    ano                   SMALLINT     NOT NULL,
    mes                   SMALLINT     NOT NULL CHECK (mes BETWEEN 1 AND 12),
    dia_semana            SMALLINT     NOT NULL CHECK (dia_semana BETWEEN 1 AND 7), -- 1=segunda
    periodo_dia           VARCHAR(20)  NOT NULL,
    faixa_etaria          VARCHAR(20)  NOT NULL,
    raca_negra            BOOLEAN,                           -- preta + parda (convenção IBGE)
    grupo_relacao         VARCHAR(30)  NOT NULL
);
-- SEX_VIT não é carregada: é constante (todas as vítimas são mulheres) e só é validada no ETL.

CREATE INDEX IF NOT EXISTS idx_ocorrencias_ano        ON ocorrencias (ano);
CREATE INDEX IF NOT EXISTS idx_ocorrencias_municipio  ON ocorrencias (municipio);
CREATE INDEX IF NOT EXISTS idx_ocorrencias_raca_cor   ON ocorrencias (raca_cor);
CREATE INDEX IF NOT EXISTS idx_ocorrencias_feminicidio ON ocorrencias (feminicidio);

COMMENT ON TABLE ocorrencias IS
  'Homicídios de mulheres e feminicídios — SESP-ES, 2017-2024 (dados.es.gov.br). Camada tratada pelo ETL.';
