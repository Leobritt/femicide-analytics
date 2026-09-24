# Monitoramento de Segurança Pública e Feminicídio Interseccional

Projeto da disciplina Big Data e Analytics (UCSal). Pipeline de ETL que leva a base de
homicídios de mulheres e feminicídios da SESP-ES até um PostgreSQL na Aiven e a um
dashboard em Streamlit.

```
Portal de Dados Abertos (CSV) → ETL em Python (extract → transform → load)
   → PostgreSQL Aiven (ocorrencias + agg_*) → Dashboard Streamlit
```

## Estrutura

```
data/raw/            CSV original baixado do portal (não vai para o banco)
data/processed/      CSV tratado gerado pelo ETL (ignorado pelo git)
etl/extract.py       leitura do CSV (detecta separador e encoding)
etl/transform.py     limpeza, tipagem, normalização e atributos derivados
etl/load.py          carga no PostgreSQL + recriação das agregações
etl/run_etl.py       executa o pipeline completo
sql/01_schema.sql    tabela ocorrencias + índices
sql/02_agregacoes.sql  materialized views agg_* para o dashboard
sql/03_validacao.sql   checagens de qualidade e tamanho do banco
dashboard/app.py     dashboard Streamlit
logs/rejeitados.csv  registros que falharam na validação (com o motivo)
```

## Passo a passo

### 1. Preparar o ambiente (cada integrante)
1. Instalar **Python 3.10+** e **Git**.
2. Clonar o repositório e entrar na pasta.
3. Criar o ambiente virtual e instalar as dependências:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate      Linux/Mac: source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Testar o ETL sem banco:
   ```bash
   python -m etl.run_etl --dry-run
   ```
   Esperado: `804 registros válidos | 0 rejeitados`.

### 2. Criar o banco na Aiven (uma pessoa)
1. Criar conta em https://console.aiven.io (não pede cartão).
2. **Create service → PostgreSQL → plano Free**, escolher uma região e criar.
3. Esperar o status ficar **Running** (cerca de 2 minutos).
4. Na aba **Overview**, copiar a **Service URI**.
5. Compartilhar a URI com o grupo por canal privado. **Nunca** colocar no GitHub.

> O serviço gratuito é desligado após um período sem uso (a Aiven avisa por e-mail).
> Se isso acontecer, é só religar pelo console antes de usar ou apresentar.

### 3. Configurar a conexão
```bash
cp .env.example .env      # no Windows: copy .env.example .env
```
Colar a Service URI em `DATABASE_URL` dentro do `.env`.

### 4. Rodar o pipeline
```bash
python -m etl.run_etl
```
Esse comando cria a tabela, carrega os dados e recria as agregações. Pode ser rodado
quantas vezes precisar, porque a carga apaga e recarrega tudo numa única transação.

### 5. Validar
Com `psql` instalado (ou por um cliente gráfico como DBeaver/pgAdmin), rodar `sql/03_validacao.sql`:
```bash
psql "$DATABASE_URL" -f sql/03_validacao.sql
```
Depois, comparar os totais por ano com os números publicados pelo Observatório da
SESP-ES (https://observatorio.sesp.es.gov.br).

### 6. Abrir o dashboard
```bash
streamlit run dashboard/app.py
```

## Decisões de tratamento (resumo)

| Coluna original | Coluna no banco | Tipo | Regra |
|---|---|---|---|
| `_id` | `id_origem` | INTEGER (PK) | id do portal, usado para rastreabilidade |
| DAT_OBT | `data_obito` | DATE | `2017-03-01T00:00:00` → `2017-03-01` |
| HOR_FAT | `hora_fato` | TIME | `HH:MM:SS` |
| SEX_VIT | — | — | constante `F`, só validada |
| IDD_VIT | `idade_vitima` | SMALLINT | vazio (54 casos) → NULL |
| MUN_OBT | `municipio` | VARCHAR(100) | maiúsculas, sem espaços extras |
| BAI_OBT | `bairro` | VARCHAR(150) | idem |
| COD_CIOD | `meio_empregado` | VARCHAR(30) | **é o meio do crime**: A01A arma de fogo, A01B arma branca, A01C outros |
| CUTIS | `raca_cor` | VARCHAR(30) | P/Parda→PARDA, B/Branca→BRANCA, N/Negra→PRETA, vazio/Indeterminada→NÃO INFORMADO |
| REL VIT AUT | `relacao_vitima_autor` | VARCHAR(60) | mantido; `grupo_relacao` agrupa (parceiro íntimo, ex-parceiro, familiar...) |
| FEMINICIDIO | `feminicidio` | BOOLEAN | FEMINICIDIO→true, HOMICÍDIO DOLOSO→false |
| TIPO LOCAL | `tipo_local` | VARCHAR(80) | 19 grafias → 8 categorias (ex.: Domicílio = RESIDÊNCIA) |

Derivadas: `ano`, `mes`, `dia_semana`, `periodo_dia`, `faixa_etaria`, `raca_negra`
(preta + parda, convenção IBGE) e `grupo_relacao`.

**Premissa a confirmar:** a base registra "N"/"Negra" separadamente de "Parda", por isso
foi tratada como PRETA (IBGE). Se a SESP-ES documentar outro significado, basta alterar o
dicionário `RACA_COR` em `etl/transform.py`.

## Limitações conhecidas dos dados
- `relacao_vitima_autor` está como NÃO INFORMADO em 64,6% dos registros e é preenchida
  quase só nos feminicídios. Por isso, não serve para comparar feminicídio com homicídio.
- 8 registros têm hora `00:00:00`, que pode ser valor padrão e não o horário real.
- O título do dataset no portal diz 2017–2023, mas o arquivo contém também 2024.
