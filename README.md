# Violência contra a mulher na Bahia por Território de Identidade

Projeto da disciplina Big Data e Analytics (UCSal). Pipeline de ETL que leva a planilha
de violência contra a mulher da SSP-BA (2025), a relação dos Territórios de Identidade e a
população e área de cada município (IBGE Cidades) até um PostgreSQL 16 hospedado na VPS da equipe (`db.filipe-oliveira.cloud`), atrás de
um proxy Traefik.

Equipe: Leonardo Britto, Gustavo Castelluccio, Filipe Miranda e Henrique Viana.

```
SSP-BA (XLSX) + Anexo II (PDF) + IBGE Cidades (CSV) → ETL em Python (extract → transform → load)
   → PostgreSQL na VPS (3 dimensões + 1 fato + visões) → Dashboard Streamlit
```

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

Os arquivos em `data/raw/` são os originais, sem nenhuma alteração. A versão tratada fica
em `data/processed/` e é gerada pelo ETL.

## 2. Estrutura do repositório

```
data/raw/              arquivos originais (XLSX da SSP-BA, PDF do Anexo II e CSV do IBGE)
data/processed/        CSVs tratados gerados pelo ETL (um por tabela do banco)
etl/extract.py         leitura da planilha, da tabela do PDF e do CSV do IBGE, sem alterar valores
etl/transform.py       tipagem, formato longo, vínculo município → território, validações
etl/load.py            carga no PostgreSQL e recriação das visões
etl/run_etl.py         executa o pipeline completo
sql/01_schema.sql      tabelas, chaves e restrições
sql/02_agregacoes.sql  visões de consumo (contagens e taxas por 100 mil hab., por território, município, crime e porte)
sql/03_validacao.sql   contagens, totais de controle, estrutura e tamanho do banco
sql/00_limpeza_base_antiga.sql  opcional: remove as tabelas da base anterior
logs/validacao_aiven.txt        saída de sql/03_validacao.sql no banco anterior (Aiven), 09/10/2026
logs/correcoes_territorios.csv  correções aplicadas aos nomes do anexo (gerado pelo ETL; fora do git)
dashboard/app.py       dashboard Streamlit (filtros, indicadores e abas por território, município e crime)
.streamlit/config.toml tema do dashboard (cores dos modos claro e escuro)
```

## 3. Processo de tratamento

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

    - O denominador é a `populacao_estimada_2026`, cuja referência é 1º/07/2024 e que é a
      mais próxima dos crimes de 2025.
    - É a população **total**, não a feminina. As taxas servem para comparar municípios e
      territórios entre si, mas não equivalem às taxas oficiais "por 100 mil mulheres".
    - Nos agregados, a taxa é `SUM(vítimas) / SUM(população)`, nunca a média das taxas
      municipais, que daria a um município de 5 mil habitantes o mesmo peso de Salvador.
    - `municipio_pequeno` marca os municípios com menos de 20 mil habitantes, onde uma
      única ocorrência já produz uma taxa alta. Em 2025, os cinco municípios com maior
      taxa de feminicídio são todos pequenos, com 1 ou 2 casos cada.

## 4. Quantidade de dados

| Tabela | Linhas |
|---|---|
| `dim_territorio` | 26 |
| `dim_municipio` | 417 |
| `dim_tipo_crime` | 11 |
| `fato_vitimas` | 4.587 |

Total de controle: 118.380 vítimas em 2025, das quais 102 feminicídios e 255 tentativas
de feminicídio. Totais do IBGE somando os 417 municípios: 14.141.626 habitantes no Censo
2022, 14.889.472 na estimativa de 2026 e 564.764 km² de área.

Medição no banco anterior, na Aiven, em 09/10/2026 (`logs/validacao_aiven.txt`): a tabela
fato ocupa 448 kB com índices e `dim_municipio`, 72 kB. As tabelas do projeto somam menos
de 1 MB, e o banco inteiro, com os catálogos do próprio PostgreSQL, cerca de 9 MB. Na VPS,
a carga de 21/10/2026 registrou 8,4 MB para o banco inteiro.

## 5. Passo a passo para rodar tudo

Do zero até o dashboard aberto. Os comandos são para Linux/Mac; onde o Windows difere,
a alternativa está indicada.

### 5.1 Pré-requisitos

- **Python 3.10 ou superior** e **Git**.
- O pacote de ambiente virtual do Python. No Ubuntu/Debian: `sudo apt install python3-venv`
  (sem ele, o `python -m venv` falha com `ensurepip is not available`).
- O usuário e a senha do banco da VPS, com quem administra o servidor.
- Opcional: o cliente **psql**, usado só no passo de validação.
  No Ubuntu/Debian: `sudo apt install postgresql-client`.

### 5.2 Baixar o projeto e instalar as dependências

```bash
git clone https://github.com/Leobritt/femicide-analytics.git
cd femicide-analytics
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

O ambiente virtual precisa estar ativo (`(.venv)` no início da linha do terminal) em
todos os passos seguintes.

### 5.3 Testar o tratamento sem banco

```bash
python -m etl.run_etl --dry-run
```

Saída esperada:

```
[extract] 06_VIOLENCIA_CONTRA_MULHER_2025.xlsx: 417 municípios x 11 tipos de crime | ano 2025
[extract] Anexo_II_-_Relacao_Territorios_de_Identidade.pdf: 26 territórios
[extract] IBGE_CIDADES_BAHIA_MUNICIPIOS.csv: 417 municípios (IBGE Cidades)
[transform] 26 territórios | 417 municípios | 11 tipos de crime | 4587 linhas no fato | 118380 vítimas | 10 correções no anexo | população estimada 2026: 14889472
```

Esse passo lê os originais em `data/raw/`, grava os CSVs tratados em `data/processed/`
e o registro de correções em `logs/correcoes_territorios.csv`. O aviso
`UserWarning: Workbook contains no default style` pode ser ignorado.

### 5.4 O banco na VPS

O PostgreSQL 16 roda em um container na VPS da equipe. O acesso externo passa pelo
Traefik, que recebe as conexões em `db.filipe-oliveira.cloud:5432` com certificado
Let's Encrypt e as repassa ao container. Por isso:

- a conexão **precisa** usar SSL (`sslmode=require`); sem SSL, quem responde é o roteador
  HTTP do Traefik, e o erro é `expected authentication request from server, but received H`;
- o `requirements.txt` fixa `psycopg2-binary==2.9.10`, que traz a libpq 16. A libpq 17
  (versões mais novas do pacote) anuncia o protocolo `postgresql` na negociação TLS (ALPN),
  o Traefik não reconhece e recusa a conexão com `tlsv1 alert no application protocol`.
  Clientes JDBC, como o DBeaver, não fazem isso e conectam com qualquer configuração.

### 5.4.1 Alternativa: banco local para testes (Docker)

Para testar o ETL sem mexer no banco da VPS, dá para subir um PostgreSQL 18 na própria
máquina. A porta 5433 evita conflito com outro PostgreSQL que use a 5432.

```bash
docker run -d --name femicide-pg \
  -e POSTGRES_USER=femicide -e POSTGRES_PASSWORD=femicide -e POSTGRES_DB=femicide \
  -p 127.0.0.1:5433:5432 \
  -v femicide-pg-data:/var/lib/postgresql \
  postgres:18
```

No `.env`, a URL local fica sem SSL:

```
DATABASE_URL=postgres://femicide:femicide@localhost:5433/femicide?sslmode=disable
```

O volume do PostgreSQL 18 é montado em `/var/lib/postgresql`, e não em
`/var/lib/postgresql/data` como nas versões anteriores. Comandos úteis:
`docker stop femicide-pg` / `docker start femicide-pg` para parar e voltar, e
`docker rm -f femicide-pg && docker volume rm femicide-pg-data` para apagar tudo.

### 5.5 Configurar a conexão

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Abrir o `.env` e preencher usuário e senha em `DATABASE_URL`:

```
DATABASE_URL=postgres://USUARIO:SENHA@db.filipe-oliveira.cloud:5432/defaultdb?sslmode=require
```

Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`, `%`, acentos), eles precisam
ser codificados na URL: `@` vira `%40`, `Ç` vira `%C3%87`. Para gerar a versão codificada:
`python -c "from urllib.parse import quote; print(quote('SENHA', safe=''))"`.

O `.env` está no `.gitignore`. **Nunca** fazer commit desse arquivo nem compartilhar a
URI em canal público.

### 5.6 Carregar os dados no banco

```bash
python -m etl.run_etl
```

Saída esperada, além das linhas do passo 5.3:

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

### 5.7 Validar a carga

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
pgAdmin, com host `db.filipe-oliveira.cloud`, porta 5432, banco `defaultdb` e SSL ativado.

### 5.8 Abrir o dashboard

```bash
streamlit run dashboard/app.py
```

O navegador abre em http://localhost:8501. No topo ficam os filtros (ano, Territórios de
Identidade, tipos de crime, só crimes letais) e a **Medida**, que alterna entre vítimas e
taxa por 100 mil habitantes em toda a página. Abaixo, quatro indicadores e cinco abas:

| Aba | Conteúdo |
|---|---|
| Visão geral | vítimas por tipo de crime, com os crimes letais num gráfico de escala própria, e os 10 territórios com mais vítimas (ou maior taxa) |
| Territórios | os 26 territórios; em taxa, com a linha da média da Bahia |
| Municípios | ranking dos 15 maiores (em taxa, sem os de menos de 20 mil hab. por padrão) e ficha de um município, com busca |
| Cruzamentos | taxa por porte e densidade do município e mapa de calor território × crime |
| Dados | tabela por município com download em CSV (abre direto no Excel) e tabela território × crime |

O tema segue o do sistema; para trocar, menu **⋮** no canto superior direito → **System /
Light / Dark**. As cores ficam em `.streamlit/config.toml`. Para encerrar,
`Ctrl+C` no terminal. Depois de rodar o ETL de novo, usar o botão **Atualizar dados**
no canto superior direito.
