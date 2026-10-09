# Violência contra a mulher na Bahia por Território de Identidade

Projeto da disciplina Big Data e Analytics (UCSal). Pipeline de ETL que leva a planilha
de violência contra a mulher da SSP-BA (2025) e a relação dos Territórios de Identidade
até um PostgreSQL na Aiven.

Equipe: Leonardo Britto, Gustavo Castelluccio, Filipe Miranda e Henrique Viana.

```
SSP-BA (XLSX) + Anexo II (PDF) → ETL em Python (extract → transform → load)
   → PostgreSQL Aiven (3 dimensões + 1 fato + visões) → Dashboard
```

## 1. Origem dos dados

| | Fonte principal | Fonte complementar |
|---|---|---|
| Conteúdo | Violência contra Mulher – Bahia (quantidade de vítimas), jan–dez 2025 | Anexo II – Relação dos Territórios de Identidade |
| Publicador | Secretaria da Segurança Pública da Bahia | Fundação Cultural do Estado da Bahia (edital de 2011) |
| Formato | XLSX, uma aba, 426 linhas × 13 colunas | PDF com tabela de texto |
| Versão usada | planilha gerada em 09/03/2026 | anexo de 2011, 26 territórios |
| Arquivo original | `data/raw/06_VIOLENCIA_CONTRA_MULHER_2025.xlsx` | `data/raw/Anexo_II_-_Relacao_Territorios_de_Identidade.pdf` |
| Link | [ba.gov.br/ssp](https://www.ba.gov.br/ssp/sites/site-ssp/files/2026-03/06_VIOLENCIA_CONTRA_MULHER_2025.xlsx) | [ba.gov.br/fundacaocultural](https://www.ba.gov.br/fundacaocultural/sites/site-funceb/files/migracao_2024/arquivos/File/editais-antigos/2011/06/qqd2011/docs/Anexo_II_-_Relacao_Territorios_de_Identidade.pdf) |

Os arquivos em `data/raw/` são os originais, sem nenhuma alteração. A versão tratada fica
em `data/processed/` e é gerada pelo ETL.

## 2. Estrutura do repositório

```
data/raw/              arquivos originais (XLSX da SSP-BA e PDF do Anexo II)
data/processed/        CSVs tratados gerados pelo ETL (um por tabela do banco)
etl/extract.py         leitura da planilha e da tabela do PDF, sem alterar valores
etl/transform.py       tipagem, formato longo, vínculo município → território, validações
etl/load.py            carga no PostgreSQL e recriação das visões
etl/run_etl.py         executa o pipeline completo
sql/01_schema.sql      tabelas, chaves e restrições
sql/02_agregacoes.sql  visões de consumo (por território, município e crime)
sql/03_validacao.sql   contagens, totais de controle, estrutura e tamanho do banco
sql/00_limpeza_base_antiga.sql  opcional: remove as tabelas da base anterior
logs/correcoes_territorios.csv  correções aplicadas aos nomes do anexo (gerado pelo ETL)
dashboard/app.py       dashboard Streamlit
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
7. **Zeros mantidos.** 39,3% das células valem zero. Foram mantidos como zero, porque a
   fonte publica o valor explicitamente.
8. **Sem amostragem nem filtro.** A base inteira tem 4.587 linhas; não há ganho em reduzir.

## 4. Modelo do banco

Modelo estrela: uma tabela fato com as contagens e três dimensões descritivas. A escolha
se justifica porque a base é numérica e agregada, e as perguntas do projeto são somas por
território, município e tipo de crime. Os textos ficam nas dimensões, sem repetição.

```
dim_territorio (26) 1 ── N dim_municipio (417) 1 ── N fato_vitimas (4.587) N ── 1 dim_tipo_crime (11)
```

| Tabela | Campo | Tipo | Restrição |
|---|---|---|---|
| `dim_territorio` | `id_territorio` | `SMALLINT` | chave primária |
| | `nome_territorio` | `VARCHAR(50)` | obrigatório, único |
| `dim_municipio` | `cod_ibge` | `INTEGER` | chave primária, entre 290000 e 299999 |
| | `nome_municipio` | `VARCHAR(60)` | obrigatório |
| | `id_territorio` | `SMALLINT` | chave estrangeira → `dim_territorio` |
| `dim_tipo_crime` | `id_tipo_crime` | `SMALLINT` | chave primária |
| | `codigo` | `VARCHAR(40)` | obrigatório, único |
| | `nome_tipo_crime` | `VARCHAR(40)` | obrigatório, único |
| | `letal` | `BOOLEAN` | obrigatório |
| `fato_vitimas` | `ano` | `SMALLINT` | parte da chave primária |
| | `cod_ibge` | `INTEGER` | parte da chave primária; chave estrangeira → `dim_municipio` |
| | `id_tipo_crime` | `SMALLINT` | parte da chave primária; chave estrangeira → `dim_tipo_crime` |
| | `qtd_vitimas` | `INTEGER` | obrigatório, `>= 0` |

Visões de consumo (`sql/02_agregacoes.sql`): `vw_territorio_crime`, `vw_territorio_resumo`,
`vw_municipio_resumo` e `vw_crime_estado`. São visões comuns, calculadas na consulta.

### Quantidade de dados

| Tabela | Linhas |
|---|---|
| `dim_territorio` | 26 |
| `dim_municipio` | 417 |
| `dim_tipo_crime` | 11 |
| `fato_vitimas` | 4.587 |

Total de controle: 118.380 vítimas em 2025, das quais 102 feminicídios e 255 tentativas
de feminicídio. As tabelas do projeto ocupam menos de 1 MB (a tabela fato, com índices,
cerca de 600 kB), frente ao limite de 1 GB do plano gratuito da Aiven. O valor medido no
banco da equipe é exibido pelo ETL e por `sql/03_validacao.sql`.

## 5. Como executar

1. Instalar **Python 3.10+**, clonar o repositório e instalar as dependências:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate      Linux/Mac: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Testar o ETL sem banco:
   ```bash
   python -m etl.run_etl --dry-run
   ```
   Esperado: `26 territórios | 417 municípios | 11 tipos de crime | 4587 linhas no fato | 118380 vítimas | 10 correções no anexo`.
3. Configurar a conexão: copiar `.env.example` para `.env` e colar a **Service URI** do
   PostgreSQL da Aiven em `DATABASE_URL`. **Nunca** fazer commit do `.env`.
4. Rodar o pipeline completo:
   ```bash
   python -m etl.run_etl
   ```
   Cria as tabelas, carrega os dados e recria as visões. Pode ser repetido: a carga
   esvazia e recarrega tudo numa única transação.
5. Validar:
   ```bash
   psql "$DATABASE_URL" -f sql/03_validacao.sql
   ```
6. (Opcional, uma vez) Remover as tabelas da base anterior:
   ```bash
   psql "$DATABASE_URL" -f sql/00_limpeza_base_antiga.sql
   ```

> O serviço gratuito da Aiven é desligado após um período sem uso (há aviso por e-mail).
> Se isso acontecer, basta religar pelo console antes de usar ou apresentar.

## 6. Limitações conhecidas

- **Sem perfil da vítima.** A planilha não traz raça/cor, idade nem relação com o autor.
- **Um único ano.** Não há série temporal enquanto outros anos não forem carregados; o
  modelo já tem a coluna `ano` para recebê-los.
- **Zeros ambíguos.** A fonte não distingue "nenhum caso" de "sem registro".
- **Estupro agregado.** A coluna soma estupro e estupro de vulnerável (nota da SSP-BA).
- **Territórios de 2011.** O anexo lista 26 territórios; a divisão atual do estado tem 27.
  Para atualizar, basta trocar o PDF e ajustar `CORRECOES_ANEXO`; a tabela fato não muda.
- **Contagem absoluta.** Não há taxa por habitante; municípios populosos lideram em
  números absolutos.
