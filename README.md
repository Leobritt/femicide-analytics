# Violência contra a mulher na Bahia por Território de Identidade

Projeto da disciplina Big Data e Analytics (UCSal). Pipeline de ETL que leva a planilha
de violência contra a mulher da SSP-BA (2025), a relação dos Territórios de Identidade, a
população e área de cada município (IBGE Cidades) e a população feminina por cor ou raça
(Censo 2022) até um PostgreSQL 16 na VM da equipe (`db.filipe-oliveira.cloud`, atrás de um
proxy Traefik), provisionável com Terraform, e um dashboard Streamlit com filtros cruzados.

Alinhamento: **ODS 5** (igualdade de gênero), com vítimas mulheres e taxas por 100 mil
mulheres, e **ODS 18** (igualdade étnico-racial), com o recorte por percentual de mulheres
pretas e pardas em cada município.

**Dashboard online:** https://femicide-analytics-bahia.streamlit.app/

Equipe: Leonardo Britto, Gustavo Castelluccio, Filipe Miranda e Henrique Viana.

## Arquitetura

```mermaid
flowchart LR
    subgraph fontes["Fontes abertas"]
        A["SSP-BA<br/>XLSX"]
        B["Fundação Cultural<br/>PDF"]
        C["IBGE Cidades<br/>CSV"]
        D["IBGE Censo 2022<br/>JSON (API)"]
        E["IBGE malhas<br/>GeoJSON"]
    end
    subgraph etl["ETL em Python"]
        X["extract.py<br/>leitura sem alterar valores"] --> T["transform.py<br/>limpeza, tipagem, validação, formato longo"] --> L["load.py<br/>carga em uma transação"]
    end
    A & B & C & D --> X
    TF["Terraform<br/>provider Docker"] -. provisiona .-> PG
    GH["GitHub Actions<br/>lote mensal"] -. executa .-> X
    L --> PG[("PostgreSQL 16<br/>esquema estrela + visões")]
    PG --> S["Dashboard Streamlit<br/>filtros, mapa, cruzamentos"]
    E --> S
```

O ETL roda localmente ou no GitHub Actions. O banco é um container PostgreSQL criado pelo
Terraform (na máquina local ou na VM, via SSH), e o dashboard consulta as tabelas com uma
única consulta em cache.

## 1. Origem dos dados

| | Fonte principal | Territórios | População e área |
|---|---|---|---|
| Conteúdo | Violência contra Mulher – Bahia (quantidade de vítimas), jan–dez 2025 | Anexo II – Relação dos Territórios de Identidade | IBGE Cidades – Bahia, todos os municípios |
| Publicador | Secretaria da Segurança Pública da Bahia | Fundação Cultural do Estado da Bahia (edital de 2011) | Instituto Brasileiro de Geografia e Estatística (IBGE) |
| Formato | XLSX, uma aba, 426 linhas × 13 colunas | PDF com tabela de texto | CSV, 417 municípios × 14 indicadores, texto com entidades HTML |
| Versão usada | planilha gerada em 09/03/2026 | anexo de 2011, 26 territórios | export baixado em 18/11/2026 |
| Arquivo original | `data/raw/06_VIOLENCIA_CONTRA_MULHER_2025.xlsx` | `data/raw/Anexo_II_-_Relacao_Territorios_de_Identidade.pdf` | `data/raw/IBGE_CIDADES_BAHIA_MUNICIPIOS.csv` |
| Link | [ba.gov.br/ssp](https://www.ba.gov.br/ssp/sites/site-ssp/files/2026-03/06_VIOLENCIA_CONTRA_MULHER_2025.xlsx) | [ba.gov.br/fundacaocultural](https://www.ba.gov.br/fundacaocultural/sites/site-funceb/files/migracao_2024/arquivos/File/editais-antigos/2011/06/qqd2011/docs/Anexo_II_-_Relacao_Territorios_de_Identidade.pdf) | [cidades.ibge.gov.br](https://cidades.ibge.gov.br/brasil/ba) (Bahia → todos os municípios → exportar CSV) |

Do IBGE são usados só quatro indicadores: código do município com 7 dígitos, área
territorial (km², 2025), população do Censo 2022 e população estimada (rótulo 2026). As
fontes citadas no rodapé do próprio arquivo são a *Área territorial brasileira 2022*, o
*Censo 2022: População e Domicílios* e as *Estimativas da população residente* do IBGE.
Os demais indicadores do export (gentílico, prefeito, IDHM, PIB per capita, escolarização,
mortalidade infantil, receitas e despesas) ficam de fora.

A população feminina por cor ou raça vem da [API de agregados do IBGE](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3),
tabela 9606 do Censo 2022 (*População residente, por cor ou raça, segundo o sexo e a
idade*), consultada em 27/11/2026 só para mulheres de todas as idades, nos 417 municípios
da Bahia (`data/raw/IBGE_CENSO2022_MULHERES_COR_RACA_BAHIA.json`). A consulta usada foi:

```
https://servicodados.ibge.gov.br/api/v3/agregados/9606/periodos/2022/variaveis/93
    ?localidades=N6[N3[29]]&classificacao=86[all]|2[5]|287[100362]
```

A planilha da SSP-BA não informa a cor ou raça das vítimas. Por isso o cruzamento com
raça/cor é feito no nível do município (ver seção 6, RN07).

O dashboard usa ainda a malha municipal da Bahia, baixada da [API de malhas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3)
em 25/11/2026 (`data/raw/IBGE_MALHA_MUNICIPIOS_BAHIA.geojson`, qualidade intermediária,
417 municípios identificados pelo código IBGE de 7 dígitos). Ela não passa pelo ETL nem
vai para o banco: serve só para desenhar o mapa.

Os arquivos em `data/raw/` são os originais, sem nenhuma alteração. A versão tratada fica
em `data/processed/` e é gerada pelo ETL.

## 2. Estrutura do repositório

```
data/raw/              arquivos originais (XLSX da SSP-BA, PDF do Anexo II, CSV, JSON e malha do IBGE)
data/processed/        CSVs tratados gerados pelo ETL (um por tabela do banco)
etl/extract.py         leitura da planilha, da tabela do PDF, do CSV e do JSON do IBGE, sem alterar valores
etl/transform.py       tipagem, formato longo, vínculo município → território, validações
etl/load.py            carga no PostgreSQL e recriação das visões
etl/run_etl.py         executa o pipeline completo
sql/01_schema.sql      tabelas, chaves e restrições
sql/02_agregacoes.sql  visões de consumo (contagens e taxas por 100 mil hab. e por 100 mil mulheres; recorte por raça/cor)
sql/03_validacao.sql   contagens, totais de controle, estrutura e tamanho do banco
sql/00_limpeza_base_antiga.sql  opcional: remove as tabelas da base anterior
logs/validacao_aiven.txt        saída de sql/03_validacao.sql no banco anterior (Aiven), 09/10/2026
logs/correcoes_territorios.csv  correções aplicadas aos nomes do anexo (gerado pelo ETL; fora do git)
dashboard/app.py       dashboard Streamlit (filtros, indicadores, mapa e abas por território, município e crime)
.streamlit/config.toml tema do dashboard (cores dos modos claro e escuro)
terraform/             provisionamento do PostgreSQL em container (main.tf, variables.tf, outputs.tf)
.github/workflows/     ETL no GitHub Actions: valida a cada mudança e roda uma vez por mês
```

## 3. Os 5 V's aplicados ao projeto

| V | Como aparece neste projeto |
|---|---|
| **Volume** | 118.380 vítimas resumidas em 4.587 linhas no fato (417 municípios × 11 crimes); o banco inteiro ocupa cerca de 9 MB, muito abaixo do limite de 1 GB de um plano gratuito. Por isso não há amostragem: a base é usada inteira, e as visões são comuns (não materializadas). |
| **Variedade** | Cinco formatos de quatro publicadores: XLSX, CSV com entidades HTML, JSON de API, GeoJSON e uma tabela dentro de um PDF (seção 4). |
| **Velocidade** | A SSP-BA publica os dados uma vez por ano, então o processamento é em lote: um comando refaz extração, tratamento e carga em poucos segundos, numa única transação. O GitHub Actions valida o pipeline a cada mudança e roda de novo todo mês; o dashboard guarda a consulta em cache por 1 hora. |
| **Veracidade** | A linha `Total` da planilha é usada como controle; os 417 municípios precisam casar entre as quatro fontes; as 10 correções de nomes ficam registradas em log; o banco tem chaves, `CHECK`s e chave primária composta, que impede carga duplicada. Qualquer inconsistência interrompe o ETL. |
| **Valor** | Taxas por 100 mil habitantes e por 100 mil mulheres que permitem comparar os 26 Territórios de Identidade e os municípios, e o recorte por raça/cor: nos municípios com 90% ou mais de mulheres pretas e pardas, a taxa de vítimas de crimes letais é 2,25 vezes a dos municípios com menos de 70%. |

## 4. Tipos de dados

| Arquivo | Formato | Classificação | Como é lido |
|---|---|---|---|
| Vítimas por município e crime (SSP-BA) | XLSX | estruturado | `openpyxl`, depois de reempacotar o arquivo em memória |
| População e área (IBGE Cidades) | CSV | estruturado (texto com entidades HTML) | `csv` + `html.unescape` |
| Mulheres por cor ou raça (Censo 2022) | JSON da API de agregados | semiestruturado (hierarquia variável → categoria → município) | `json`, achatado para uma linha por município |
| Malha municipal (IBGE) | GeoJSON | semiestruturado (geometrias + propriedades) | lido direto pelo dashboard |
| Territórios de Identidade (Anexo II) | PDF | não estruturado (tabela impressa, lista de municípios em texto corrido) | `pdfplumber`, separação por vírgula e casamento de nomes |

Dentro do banco tudo vira dado estruturado: inteiros, `NUMERIC`, `BOOLEAN` e texto curto
(seção 7).

## 5. Processo de tratamento

### Extração (`etl/extract.py`)
- **Planilha.** O arquivo da SSP-BA grava os caminhos internos do pacote XLSX com `\`
  em vez de `/`, o que impede a leitura pelo `openpyxl`. O ETL reempacota o arquivo em
  memória; o original não é modificado.
- O cabeçalho é localizado pela linha que começa com `ID`, e os dados terminam na linha
  `Total`. Título, linha de total e rodapé não entram na base.
- O **ano de referência** é extraído do título ("JANEIRO A DEZEMBRO DE 2025").
- **PDF.** A tabela de territórios é extraída com `pdfplumber`; cada linha traz o número,
  o nome do território e a lista de municípios em texto.
- **CSV do IBGE.** O texto vem com entidades HTML (`Munic&iacute;pio`), que são decodificadas.
  A linha de título e o rodapé de notas e fontes são descartados, e só entram as linhas
  com código numérico. Cada coluna é localizada pelo início do nome, e o ano entre
  colchetes no cabeçalho precisa ser o esperado (ex.: `[2022]`). Um export com outro ano
  interrompe o ETL, para que as colunas do banco não fiquem com o ano errado no nome.

- **JSON do IBGE (Censo 2022).** A resposta da API tem um resultado por categoria de cor
  ou raça e, dentro dele, uma série por município. A extração confere se a consulta foi
  feita só para mulheres e todas as idades e monta uma linha por município.

### Transformação (`etl/transform.py`)

| Origem | Destino | Tipo | Regra |
|---|---|---|---|
| `ID` (texto `'290010'`) | `dim_municipio.cod_ibge` | `INTEGER` (PK) | texto → inteiro; faixa 290000–299999; sem repetição |
| `MUNICÍPIO` | `dim_municipio.nome_municipio` | `VARCHAR(60)` | espaços extras removidos; acentos mantidos |
| 11 colunas de crime | `fato_vitimas.qtd_vitimas` | `INTEGER`, `CHECK >= 0` | formato largo → longo: cada célula vira uma linha |
| nome da coluna de crime | `fato_vitimas.id_tipo_crime` | `SMALLINT` (FK) | identificador de 1 a 11, na ordem da planilha |
| nome da coluna de crime | `dim_tipo_crime.nome_tipo_crime` / `codigo` | `VARCHAR(40)` | rótulo original e versão sem acento (`lesao_corporal_dolosa`) |
| (derivada) | `dim_tipo_crime.letal` | `BOOLEAN` | verdadeiro para homicídio doloso, feminicídio e lesão corporal seguida de morte |
| título da planilha | `fato_vitimas.ano` | `SMALLINT` | ano extraído do título |
| nº do território (PDF) | `dim_territorio.id_territorio` | `SMALLINT` (PK) | texto → inteiro |
| nome do território (PDF) | `dim_territorio.nome_territorio` | `VARCHAR(50)` | quebras de linha do PDF unidas |
| lista de municípios (PDF) | `dim_municipio.id_territorio` | `SMALLINT` (FK) | lista separada por vírgula; cruzamento pelo nome sem acento e sem pontuação |
| `Código` (IBGE, `2900108`) | `dim_municipio.codigo_ibge7` | `INTEGER`, único | faixa 2900000–2999999; join por `codigo_ibge7 / 10 = cod_ibge` |
| `Área Territorial [2025]` | `dim_municipio.area_km2` | `NUMERIC(10,3)` | `CHECK > 0` |
| `População no último censo [2022]` | `dim_municipio.populacao_censo_2022` | `INTEGER` | `CHECK > 0` |
| `População estimada [2026]` | `dim_municipio.populacao_estimada_2026` | `INTEGER` | `CHECK > 0` |
| Censo 2022, mulheres por cor ou raça (JSON) | `dim_municipio.mulheres_2022`, `mulheres_brancas_2022`, `mulheres_pretas_2022`, `mulheres_pardas_2022`, `mulheres_amarelas_2022`, `mulheres_indigenas_2022` | `INTEGER` | `-` do IBGE (zero absoluto) vira 0; join pelo código de 7 dígitos; as cinco categorias somam no máximo o total (a diferença são as sem declaração) |

### Decisões e justificativas

1. **Formato longo em vez de largo.** A planilha tem uma coluna por crime. No banco, cada
   combinação município × crime é uma linha. Assim, um novo tipo de crime ou um novo ano
   entra como linhas novas, sem alterar a estrutura da tabela.
2. **Código IBGE como chave do município.** O nome tem variações de grafia entre fontes;
   o código é estável e permite cruzar com outras bases (IBGE, DATASUS).
3. **Nomes cruzados por chave normalizada.** O PDF não traz código IBGE. O vínculo é feito
   pelo nome em maiúsculas, sem acento, espaço ou pontuação.
4. **Dez correções explícitas no anexo**, declaradas no dicionário `CORRECOES_ANEXO` e
   registradas em `logs/correcoes_territorios.csv`:
   - 7 grafias diferentes da SSP-BA/IBGE (ex.: Rui Barbosa → Ruy Barbosa; Lagedo do
     Tabocal → Lajedo do Tabocal; D. Macedo Costa → Dom Macêdo Costa);
   - 3 pares de municípios sem vírgula entre eles no PDF (Barro Alto e Cafarnaum;
     Bonito e Ibicoara; Lençóis e Marcionílio Souza).
5. **Linha `Total` usada como controle, não como dado.** Ela não é carregada; a soma de
   cada coluna após o tratamento precisa ser igual a ela.
6. **Validação que interrompe o pipeline.** A base é fechada (417 municípios). Descartar
   um registro inválido mudaria os totais, então qualquer inconsistência gera erro:
   código IBGE repetido ou fora da faixa, contagem vazia/negativa/não inteira, soma
   diferente do `Total`, município sem território ou em dois territórios.
7. **Join com o IBGE pelo código, não pelo nome.** A SSP-BA usa o código IBGE de 6
   dígitos e o IBGE Cidades o de 7 (o último é o dígito verificador). O ETL exige que os
   417 municípios casem dos dois lados e confere também o nome. A única grafia diferente,
   Santa Teresinha (SSP-BA) × Santa Terezinha (IBGE), está liberada em `GRAFIAS_SSP_IBGE`.
   O código de 7 dígitos também é guardado, por ser o padrão de DATASUS e Siconfi.
8. **Colunas do IBGE adicionadas com `ALTER TABLE`.** O `CREATE TABLE IF NOT EXISTS` não
   acrescenta colunas a uma tabela que já existe. As colunas entram aceitando nulo e,
   depois de a tabela ser esvaziada e recarregada, o `load.py` as torna `NOT NULL`. Assim
   o mesmo ETL serve para um banco novo e para o da VPS, que já tem dados.
9. **Zeros mantidos.** 39,3% das células valem zero. Foram mantidos como zero, porque a
   fonte publica o valor explicitamente.
10. **Sem amostragem nem filtro.** A base inteira tem 4.587 linhas; não há ganho em reduzir.
11. **Taxas por 100 mil habitantes.** Com a população do IBGE, as visões de taxa permitem
    comparar municípios de tamanhos diferentes:

    | Visão | Uma linha por | Conteúdo |
    |---|---|---|
    | `vw_municipio_taxa` | município | população, área, densidade, `municipio_pequeno`, contagens e taxas |
    | `vw_territorio_taxa` | território | o mesmo, somado por Território de Identidade |
    | `vw_crime_taxa_territorio` | território × crime | taxa de cada tipo de crime por território |
    | `vw_porte_municipio` | faixa | taxas por porte (faixas do IBGE) e por densidade (hab./km²) |
    | `vw_faixa_mulheres_negras` | faixa | taxas por 100 mil mulheres por % de mulheres pretas e pardas (RN07) |

    - O denominador é a `populacao_estimada_2026`, cuja referência é 1º/07/2024 e que é a
      mais próxima dos crimes de 2025.
    - Essa é a população **total**. Para o recorte de gênero, as visões trazem também a
      taxa por 100 mil mulheres, com as mulheres do Censo 2022 como denominador (RN02).
    - Nos agregados, a taxa é `SUM(vítimas) / SUM(população)`, nunca a média das taxas
      municipais, que daria a um município de 5 mil habitantes o mesmo peso de Salvador.
    - `municipio_pequeno` marca os municípios com menos de 20 mil habitantes, onde uma
      única ocorrência já produz uma taxa alta. Em 2025, os cinco municípios com maior
      taxa de feminicídio são todos pequenos, com 1 ou 2 casos cada.

## 6. Regras de negócio

| Regra | Definição | Onde está |
|---|---|---|
| RN01 · Taxa por 100 mil habitantes | vítimas ÷ população estimada (IBGE, referência jul/2024) × 100.000 | `vw_municipio_taxa`, dashboard |
| RN02 · Taxa por 100 mil mulheres | vítimas ÷ mulheres no Censo 2022 × 100.000. É o denominador das taxas oficiais de violência contra a mulher | `vw_municipio_taxa`, dashboard (medida "por 100 mil mulheres") |
| RN03 · Agregação de taxas | em território, porte, densidade e faixa racial, taxa = soma das vítimas ÷ soma da população, nunca a média das taxas municipais | todas as visões `vw_*_taxa` e `vw_faixa_mulheres_negras` |
| RN04 · Crime letal | homicídio doloso, feminicídio e lesão corporal seguida de morte | `dim_tipo_crime.letal`, filtro "Só crimes letais" |
| RN05 · Município pequeno | menos de 20 mil habitantes: uma ocorrência já gera taxa alta. É sinalizado e, no ranking por taxa, fica de fora por padrão | `vw_municipio_taxa.municipio_pequeno`, aba Municípios |
| RN06 · Porte e densidade | faixas de porte do IBGE (até 20 mil, 20–50 mil, 50–100 mil, 100–500 mil, mais de 500 mil) e de densidade (hab./km²) | `vw_porte_municipio`, aba Cruzamentos |
| RN07 · Recorte racial | % de mulheres negras = (pretas + pardas) ÷ mulheres, pela convenção do IBGE. Faixas: menos de 70%, 70–80%, 80–85%, 85–90%, 90% ou mais. É uma comparação entre municípios (análise ecológica), não a cor ou raça das vítimas, que a SSP-BA não publica | `vw_faixa_mulheres_negras`, filtro e gráfico no dashboard |
| RN08 · Território de cada município | pelo Anexo II, com as 10 correções explícitas de `CORRECOES_ANEXO` | `transform.py`, `logs/correcoes_territorios.csv` |
| RN09 · Total de controle | a soma tratada de cada crime tem que ser igual à linha `Total` da planilha; qualquer inconsistência interrompe o pipeline | `transform.py` |
| RN10 · Zeros | zeros da SSP-BA e o `-` do IBGE são valores reais (nenhum caso / zero absoluto), não dados faltantes | `transform.py` |

Resultado do recorte racial em 2025, com só os crimes letais (homicídio doloso,
feminicídio e lesão corporal seguida de morte):

| % de mulheres pretas e pardas no município | Municípios | Vítimas de crimes letais por 100 mil mulheres |
|---|---|---|
| menos de 70% | 62 | 3,01 |
| 70% a 80% | 152 | 4,93 |
| 80% a 85% | 98 | 4,98 |
| 85% a 90% | 67 | 5,70 |
| 90% ou mais | 38 | 6,76 |

Com todos os crimes, a taxa faz o caminho contrário: cai de 1.676 para cerca de 1.500 por
100 mil mulheres. A violência letal cresce com a presença de mulheres negras, enquanto o
registro dos crimes não letais é menor nesses municípios, o que pode indicar
subnotificação. Os dados não permitem separar uma coisa da outra.

## 7. Dicionário de dados

**`dim_territorio`** — 26 linhas

| Coluna | Tipo | Descrição |
|---|---|---|
| `id_territorio` | `SMALLINT` PK | número do território no Anexo II |
| `nome_territorio` | `VARCHAR(50)` único | nome do Território de Identidade |

**`dim_municipio`** — 417 linhas

| Coluna | Tipo | Descrição |
|---|---|---|
| `cod_ibge` | `INTEGER` PK | código IBGE de 6 dígitos, como na planilha da SSP-BA |
| `nome_municipio` | `VARCHAR(60)` | nome como na SSP-BA |
| `id_territorio` | `SMALLINT` FK | território do município |
| `codigo_ibge7` | `INTEGER` único | código IBGE de 7 dígitos (com dígito verificador) |
| `area_km2` | `NUMERIC(10,3)` | área territorial (IBGE, 2025) |
| `populacao_censo_2022` | `INTEGER` | população residente no Censo 2022 |
| `populacao_estimada_2026` | `INTEGER` | população estimada pelo IBGE (rótulo 2026, referência jul/2024) |
| `mulheres_2022` | `INTEGER` | mulheres residentes no Censo 2022 |
| `mulheres_brancas_2022`, `mulheres_pretas_2022`, `mulheres_pardas_2022`, `mulheres_amarelas_2022`, `mulheres_indigenas_2022` | `INTEGER` | mulheres de cada cor ou raça no Censo 2022 |

**`dim_tipo_crime`** — 11 linhas

| Coluna | Tipo | Descrição |
|---|---|---|
| `id_tipo_crime` | `SMALLINT` PK | ordem da coluna na planilha |
| `codigo` | `VARCHAR(40)` único | nome sem acento (`lesao_corporal_dolosa`) |
| `nome_tipo_crime` | `VARCHAR(40)` único | rótulo original da SSP-BA |
| `letal` | `BOOLEAN` | crime com resultado morte (RN04) |

**`fato_vitimas`** — 4.587 linhas

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano` | `SMALLINT` | ano de referência (do título da planilha) |
| `cod_ibge` | `INTEGER` FK | município |
| `id_tipo_crime` | `SMALLINT` FK | tipo de crime |
| `qtd_vitimas` | `INTEGER` `>= 0` | vítimas mulheres; PK = (`ano`, `cod_ibge`, `id_tipo_crime`) |

**Visões** (recriadas a cada carga)

| Visão | Uma linha por | Colunas principais |
|---|---|---|
| `vw_municipio_taxa` | município | população, mulheres, `pct_mulheres_negras`, contagens e `taxa_*_100k` / `taxa_*_100k_mulheres` |
| `vw_territorio_taxa` | território | as mesmas, somadas por território (RN03) |
| `vw_crime_taxa_territorio` | território × crime | `qtd_vitimas`, `taxa_100k` |
| `vw_porte_municipio` | faixa de porte ou de densidade | contagens e taxas por faixa |
| `vw_faixa_mulheres_negras` | faixa de % de mulheres negras | mulheres, contagens e taxas por 100 mil mulheres (RN07) |
| `vw_territorio_crime`, `vw_territorio_resumo`, `vw_municipio_resumo`, `vw_crime_estado` | — | contagens sem taxa |

## 8. Escolha do banco de dados

**Relacional (PostgreSQL 16).** Os dados são tabelas com chaves naturais claras
(município, território, tipo de crime) e relações fixas entre elas. O modelo estrela, com
chaves estrangeiras, `CHECK`s e chave primária composta, garante no próprio banco a
veracidade que o ETL confere, e as agregações (taxas por território, faixa e crime) são
consultas SQL diretas. Com cerca de 9 MB, não há problema de escala que peça outra
tecnologia.

**Não relacional (opcional no guia).** O projeto não tem texto livre, logs ou documentos
para busca, que é onde um OpenSearch ajudaria. O único dado semiestruturado que chega ao
dashboard, a malha GeoJSON, é usado direto do arquivo, sem consulta.

**VM da equipe no lugar da Aiven.** O banco começou na Aiven (o registro da validação
está em `logs/validacao_aiven.txt`) e foi migrado para um container PostgreSQL na VM da
equipe. Por isso o Terraform usa o provider Docker em vez do provider Aiven: o mesmo
código cria o banco na máquina local ou na VM (seção 9).

## 9. Infraestrutura como código, segurança e LGPD

**Terraform** (`terraform/`): `versions.tf` declara o provider
[kreuzwerker/docker](https://registry.terraform.io/providers/kreuzwerker/docker/latest);
`main.tf` cria a imagem `postgres:16-alpine`, um volume persistente e o container com
*healthcheck*; `variables.tf` traz as variáveis; `outputs.tf` devolve o endereço e a URL
de conexão (marcada como sensível). A variável `docker_host` escolhe onde o banco nasce:
`unix:///var/run/docker.sock` (padrão, máquina local) ou `ssh://usuario@servidor` (VM).
O passo a passo está na seção 11.4.

**Credenciais.**

- Nenhuma senha, chave ou token fica no repositório.
- A conexão do ETL e do dashboard vem do `.env` local (fora do git) ou dos *Secrets* da
  plataforma: Streamlit Community Cloud no dashboard e GitHub Actions no ETL.
- A senha do banco no Terraform não tem valor padrão e vem de `TF_VAR_db_password` ou de
  `terraform.tfvars`. Esse arquivo e o estado do Terraform estão no `.gitignore`.
- A conexão com a VM usa SSL (seção 11.5).

**LGPD.**

- Todas as fontes são dados públicos e agregados por município: não há nenhum registro
  individual de vítima, nome, endereço ou data de ocorrência.
- O único dado pessoal dos arquivos brutos, o nome do prefeito no CSV do IBGE Cidades, é
  descartado na extração.
- A cor ou raça aparece só como contagem populacional do Censo, sem ligação com nenhuma
  pessoa. Por isso não há tratamento de dado pessoal sensível no sentido do art. 5º, II,
  da Lei 13.709/2018.
- O dashboard informa no cabeçalho que nenhum caso individual é exibido.

## 10. Quantidade de dados

| Tabela | Linhas |
|---|---|
| `dim_territorio` | 26 |
| `dim_municipio` | 417 |
| `dim_tipo_crime` | 11 |
| `fato_vitimas` | 4.587 |

Total de controle: 118.380 vítimas em 2025, das quais 102 feminicídios e 255 tentativas
de feminicídio. Totais do IBGE somando os 417 municípios: 14.141.626 habitantes no Censo
2022, 14.889.472 na estimativa de 2026, 564.764 km² de área e 7.305.940 mulheres no
Censo 2022, das quais 79,4% pretas ou pardas.

Medição no banco anterior, na Aiven, em 09/10/2026 (`logs/validacao_aiven.txt`): a tabela
fato ocupa 448 kB com índices e `dim_municipio`, 72 kB. As tabelas do projeto somam menos
de 1 MB, e o banco inteiro, com os catálogos do próprio PostgreSQL, cerca de 9 MB. Na VPS,
a carga de 21/10/2026 registrou 8,4 MB para o banco inteiro; com as colunas do Censo 2022
por cor ou raça, a carga de 27/11/2026 registrou 9,2 MB.

## 11. Passo a passo para rodar tudo

Do zero até o dashboard aberto. Os comandos são para Linux/Mac; onde o Windows difere,
a alternativa está indicada.

### 11.1 Pré-requisitos

- **Python 3.10 ou superior** e **Git**.
- O pacote de ambiente virtual do Python. No Ubuntu/Debian: `sudo apt install python3-venv`
  (sem ele, o `python -m venv` falha com `ensurepip is not available`).
- O usuário e a senha do banco da VPS, com quem administra o servidor.
- Opcional: o cliente **psql**, usado só no passo de validação.
  No Ubuntu/Debian: `sudo apt install postgresql-client`.
- Para criar o banco com Terraform (11.4.1): **Docker** e **Terraform 1.5 ou superior**.

### 11.2 Baixar o projeto e instalar as dependências

```bash
git clone https://github.com/Leobritt/femicide-analytics.git
cd femicide-analytics
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

O ambiente virtual precisa estar ativo (`(.venv)` no início da linha do terminal) em
todos os passos seguintes.

### 11.3 Testar o tratamento sem banco

```bash
python -m etl.run_etl --dry-run
```

Saída esperada:

```
[extract] 06_VIOLENCIA_CONTRA_MULHER_2025.xlsx: 417 municípios x 11 tipos de crime | ano 2025
[extract] Anexo_II_-_Relacao_Territorios_de_Identidade.pdf: 26 territórios
[extract] IBGE_CIDADES_BAHIA_MUNICIPIOS.csv: 417 municípios (IBGE Cidades)
[extract] IBGE_CENSO2022_MULHERES_COR_RACA_BAHIA.json: 417 municípios (Censo 2022, mulheres por cor ou raça)
[transform] 26 territórios | 417 municípios | 11 tipos de crime | 4587 linhas no fato | 118380 vítimas | 10 correções no anexo | população estimada 2026: 14889472 | mulheres (Censo 2022): 7305940
```

Esse passo lê os originais em `data/raw/`, grava os CSVs tratados em `data/processed/`
e o registro de correções em `logs/correcoes_territorios.csv`. O aviso
`UserWarning: Workbook contains no default style` pode ser ignorado.

### 11.4 O banco na VM da equipe

O PostgreSQL 16 roda em um container na VM da equipe. O acesso externo passa pelo
Traefik, que recebe as conexões em `db.filipe-oliveira.cloud:15432` (entrypoint TCP
`postgres`) com certificado Let's Encrypt e as repassa à porta 5432 do container. Por isso:

- a conexão **precisa** usar SSL (`sslmode=require`); sem SSL, quem responde é o roteador
  HTTP do Traefik, e o erro é `expected authentication request from server, but received H`;
- o `requirements.txt` fixa `psycopg2-binary==2.9.10`, que traz a libpq 16. A libpq 17
  (versões mais novas do pacote) anuncia o protocolo `postgresql` na negociação TLS (ALPN),
  o Traefik não reconhece e recusa a conexão com `tlsv1 alert no application protocol`.
  Clientes JDBC, como o DBeaver, não fazem isso e conectam com qualquer configuração. O
  mesmo vale para o `psql`: o da imagem oficial `postgres:16` vem com libpq mais nova e
  também é recusado.

### 11.4.1 Criar o banco com Terraform

O Terraform cria o PostgreSQL 16 num container Docker, com volume persistente. Sem
configuração extra, o banco nasce na própria máquina, em `127.0.0.1:5433`.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars    # trocar a senha; o arquivo fica fora do git
terraform init
terraform plan
terraform apply
terraform output -raw database_url              # URL para colocar no .env (passo 11.5)
cd ..
```

Para criar o banco na VM, e não na máquina local, basta descomentar no `terraform.tfvars`
as linhas de `docker_host = "ssh://usuario@servidor"`, `bind_address` e `host_port`. A VM
precisa ter Docker, e o usuário, acesso por chave SSH. Para apagar tudo,
`terraform destroy`.

Na URL que o Terraform devolve, a conexão é local e sem SSL
(`sslmode=disable`). Os passos seguintes são os mesmos para o banco local e para o da VM.

### 11.5 Configurar a conexão

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Abrir o `.env` e preencher usuário e senha em `DATABASE_URL`:

```
DATABASE_URL=postgres://USUARIO:SENHA@db.filipe-oliveira.cloud:15432/defaultdb?sslmode=require
```

Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`, `%`, acentos), eles precisam
ser codificados na URL: `@` vira `%40`, `Ç` vira `%C3%87`. Para gerar a versão codificada:
`python -c "from urllib.parse import quote; print(quote('SENHA', safe=''))"`.

O `.env` está no `.gitignore`. **Nunca** fazer commit desse arquivo nem compartilhar a
URI em canal público.

### 11.6 Carregar os dados no banco

```bash
python -m etl.run_etl
```

Saída esperada, além das linhas do passo 11.3:

```
[load] dim_territorio: 26 linhas
[load] dim_municipio: 417 linhas
[load] dim_tipo_crime: 11 linhas
[load] fato_vitimas: 4587 linhas
[load] tamanho do banco: ...
[run] Pipeline concluído.
```

O comando cria as tabelas, carrega os dados e recria as visões. Pode ser repetido à
vontade: a carga esvazia e recarrega tudo numa única transação, sem duplicar.

### 11.7 Validar a carga

```bash
URL="$(grep ^DATABASE_URL .env | cut -d= -f2-)"
psql "$URL" -f sql/03_validacao.sql
```

Confere a quantidade de linhas por tabela, os totais por tipo de crime (que precisam
ser iguais aos da linha `Total` da planilha), a estrutura das tabelas e o espaço
ocupado. Para guardar a saída como evidência:

```bash
psql "$URL" -f sql/03_validacao.sql > logs/validacao_vps.txt
```

Sem o `psql`, o mesmo arquivo pode ser executado em um cliente gráfico como DBeaver ou
pgAdmin, com host `db.filipe-oliveira.cloud`, porta 15432, banco `defaultdb` e SSL ativado.

### 11.8 Abrir o dashboard

```bash
streamlit run dashboard/app.py
```

O navegador abre em http://localhost:8501. No topo ficam os filtros cruzados (ano,
Territórios de Identidade, tipos de crime, faixa de % de mulheres pretas e pardas no
município, só crimes letais) e a **Medida**, que alterna em toda a página entre vítimas,
taxa por 100 mil habitantes e taxa por 100 mil mulheres. Abaixo, quatro indicadores e
seis abas:

| Aba | Conteúdo |
|---|---|
| Visão geral | vítimas por tipo de crime, com os crimes letais num gráfico de escala própria, e os 10 territórios com mais vítimas (ou maior taxa) |
| Mapa | mapa da Bahia colorido por território ou por município |
| Territórios | os 26 territórios; em taxa, com a linha da média da Bahia |
| Municípios | ranking dos 15 maiores (em taxa, sem os de menos de 20 mil hab. por padrão) e ficha de um município, com busca (*drill-down* do território para o município) |
| Cruzamentos | taxa por porte e densidade do município, taxa por 100 mil mulheres por % de mulheres pretas e pardas (RN07) e mapa de calor território × crime, com o valor em cada célula |
| Dados | tabela por município com download em CSV (abre direto no Excel) e tabela território × crime |

O tema segue o do sistema; para trocar, menu **⋮** no canto superior direito → **System /
Light / Dark**. As cores ficam em `.streamlit/config.toml`. Para encerrar,
`Ctrl+C` no terminal. Depois de rodar o ETL de novo, usar o botão **Atualizar dados**
no canto superior direito.

### 11.9 Publicar o dashboard online (Streamlit Community Cloud)

1. Entrar em [share.streamlit.io](https://share.streamlit.io) com a conta do GitHub
   que tem acesso ao repositório.
2. **Create app** → **Deploy a public app from GitHub**: repositório
   `Leobritt/femicide-analytics`, branch `main`, arquivo `dashboard/app.py`.
3. Em **Advanced settings**, escolher Python 3.12 (o `psycopg2-binary` 2.9.10 não tem
   versão para o 3.14, que vem selecionado por padrão) e colar em **Secrets**:

   ```toml
   DATABASE_URL = "postgres://USUARIO:SENHA@db.filipe-oliveira.cloud:15432/defaultdb?sslmode=require"
   ```

   O Streamlit expõe os *secrets* de primeiro nível como variáveis de ambiente, então o
   `app.py` lê a URL do mesmo jeito que lê o `.env` local.
4. **Deploy**. As dependências saem do `requirements.txt`, e o tema, do
   `.streamlit/config.toml`.

A versão publicada está em https://femicide-analytics-bahia.streamlit.app/.

O banco precisa aceitar conexões vindas da internet, como já acontece com o da VM. O banco
local criado pelo Terraform, em `127.0.0.1`, não serve para o dashboard online.

### 11.10 ETL agendado no GitHub Actions

O workflow `.github/workflows/etl.yml` roda sozinho a cada mudança no ETL, no SQL ou nos
dados, e todo dia 1º do mês. Sem configuração, ele só valida o tratamento (`--dry-run`) e
guarda os CSVs tratados como artefato. Para que ele também carregue o banco, cadastrar o
secret `DATABASE_URL` em **Settings → Secrets and variables → Actions** do repositório.
Também dá para rodar na hora, em **Actions → ETL → Run workflow**.
