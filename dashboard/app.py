"""Dashboard — Violência contra a mulher na Bahia por Território de Identidade.

Rodar na raiz do projeto:
    streamlit run dashboard/app.py

Faz uma única consulta ao banco (em cache) e agrega em pandas. A base tem 4.587
linhas por ano, então os filtros respondem sem novas idas ao banco.
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Cores fixas por categoria: não letal = azul, letal = laranja (a cor segue a categoria,
# não a posição). Escala sequencial de um único matiz para o mapa de calor.
COR_NAO_LETAL, COR_LETAL = "#2a78d6", "#eb6834"
ESCALA_SEQ = ["#eef5fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]

SQL = """
    SELECT f.ano,
           t.nome_territorio AS territorio,
           m.nome_municipio  AS municipio,
           c.id_tipo_crime,
           c.codigo,
           c.nome_tipo_crime AS crime,
           c.letal,
           f.qtd_vitimas     AS vitimas
    FROM fato_vitimas f
    JOIN dim_municipio  m USING (cod_ibge)
    JOIN dim_territorio t USING (id_territorio)
    JOIN dim_tipo_crime c USING (id_tipo_crime)
"""

st.set_page_config(page_title="Violência contra a mulher — Bahia", layout="wide")


@st.cache_data(ttl=3600)
def carregar_base() -> pd.DataFrame:
    """Uma conexão e uma consulta; o resultado fica em cache por 1 hora."""
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
            colunas = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=colunas)
    df["crime"] = df["crime"].str.capitalize()          # "LESÃO CORPORAL DOLOSA" -> "Lesão corporal dolosa"
    df["categoria"] = df["letal"].map({True: "Letal", False: "Não letal"})
    return df


def milhar(n) -> str:
    """12345 -> '12.345' (separador brasileiro)."""
    return f"{int(n):,}".replace(",", ".")


def layout(fig, altura=360):
    fig.update_layout(height=altura, margin=dict(l=10, r=40, t=40, b=10),
                      separators=",.",   # decimal com vírgula, milhar com ponto
                      legend=dict(orientation="h", y=1.08, x=0, title=None),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)", zeroline=False)
    fig.update_yaxes(showgrid=False, title=None)
    return fig


def barras(df: pd.DataFrame, categoria: str, titulo: str, altura: int, cor: str | None = None):
    """Barras horizontais ordenadas, com o valor escrito ao lado de cada barra."""
    df = df.sort_values("vitimas", ascending=True, kind="stable")
    fig = px.bar(df, y=categoria, x="vitimas", orientation="h", title=titulo,
                 color=cor,
                 color_discrete_map={"Não letal": COR_NAO_LETAL, "Letal": COR_LETAL},
                 color_discrete_sequence=[COR_NAO_LETAL],
                 category_orders={categoria: df[categoria].tolist()[::-1],
                                  "categoria": ["Não letal", "Letal"]},
                 hover_data={c: True for c in df.columns if c not in (categoria, "vitimas", cor)},
                 labels={"vitimas": "Vítimas", "territorio": "Território", "municipio": "Município",
                         "crime": "Tipo de crime", "categoria": "Categoria"})
    fig.update_traces(texttemplate="%{x:,.0f}", textposition="outside", cliponaxis=False,
                      marker_line_width=0)
    fig.update_xaxes(title=None)
    return layout(fig, altura)


# ------------------------------------------------------------------ cabeçalho e filtros
st.title("Violência contra a mulher na Bahia")
st.caption("Quantidade de vítimas por Território de Identidade, município e tipo de crime. "
           "Fonte: SSP-BA. Dados agregados; nenhum caso individual é exibido.")

if st.sidebar.button("Recarregar dados", help="Limpa o cache; use depois de rodar o ETL de novo."):
    st.cache_data.clear()

try:
    base = carregar_base()
except KeyError:
    st.error("DATABASE_URL não definida. Copie .env.example para .env e preencha.")
    st.stop()
except psycopg2.Error as erro:
    st.error(f"Não foi possível consultar o banco. Verifique se o serviço da Aiven está ligado "
             f"e se o ETL já foi executado.\n\n{erro}")
    st.stop()

anos = sorted(base["ano"].unique().tolist())
territorios = sorted(base["territorio"].unique().tolist())
crimes = (base[["id_tipo_crime", "crime"]].drop_duplicates()
          .sort_values("id_tipo_crime")["crime"].tolist())

c1, c2, c3, c4 = st.columns([1, 3, 3, 1.4])
ano = c1.selectbox("Ano", anos, index=len(anos) - 1, disabled=len(anos) == 1)
terr_sel = c2.multiselect("Territórios de Identidade", territorios, placeholder="Todos")
crime_sel = c3.multiselect("Tipos de crime", crimes, placeholder="Todos")
so_letais = c4.toggle("Só crimes letais", value=False,
                      help="Homicídio doloso, feminicídio e lesão corporal seguida de morte.")

no_territorio = base[(base["ano"] == ano) & (base["territorio"].isin(terr_sel or territorios))]
dados = no_territorio[no_territorio["crime"].isin(crime_sel or crimes)]
if so_letais:
    dados = dados[dados["letal"]]

# ------------------------------------------------------------------ indicadores
# Seguem só o filtro de território, para não zerar quando um tipo de crime é escolhido.
def soma(filtro) -> int:
    return int(no_territorio.loc[filtro, "vitimas"].sum())

total = soma(slice(None))
letais = soma(no_territorio["letal"])
k1, k2, k3, k4 = st.columns(4)
k1.metric("Vítimas (todos os crimes)", milhar(total))
k2.metric("Feminicídios", milhar(soma(no_territorio["codigo"] == "feminicidio")))
k3.metric("Tentativas de feminicídio", milhar(soma(no_territorio["codigo"] == "tentativa_de_feminicidio")))
k4.metric("Vítimas de crimes letais", milhar(letais))
pct_letais = f"{100 * letais / total:.2f}".replace(".", ",") if total else "0"
st.caption(f"Indicadores de {ano} para "
           f"{'os territórios selecionados' if terr_sel else 'todo o estado'}, considerando todos os tipos de crime. "
           f"Crimes letais são {pct_letais}% das vítimas.")

if dados["vitimas"].sum() == 0:
    st.info("Nenhuma vítima registrada para os filtros escolhidos.")
    st.stop()

# ------------------------------------------------------------------ território e tipo de crime
a, b = st.columns(2)
por_territorio = dados.groupby("territorio", as_index=False)["vitimas"].sum()
a.plotly_chart(barras(por_territorio, "territorio", "Vítimas por Território de Identidade",
                      altura=max(300, 26 * len(por_territorio) + 80)),
               width="stretch")

por_crime = dados.groupby(["crime", "categoria"], as_index=False)["vitimas"].sum()
b.plotly_chart(barras(por_crime, "crime", "Vítimas por tipo de crime",
                      altura=max(300, 34 * len(por_crime) + 110), cor="categoria"),
               width="stretch")

por_municipio = (dados.groupby(["municipio", "territorio"], as_index=False)["vitimas"].sum()
                 .sort_values("vitimas", ascending=False, kind="stable").head(15))
b.plotly_chart(barras(por_municipio, "municipio", "15 municípios com mais vítimas", altura=470),
               width="stretch")
b.caption("Contagens absolutas, sem ajuste por população: municípios mais populosos tendem a liderar.")

# ------------------------------------------------------------------ cruzamento território x crime
st.subheader("Território × tipo de crime")
MODOS = {
    "Participação do território no total do crime": "pct_crime",
    "Composição dentro do território": "pct_territorio",
    "Vítimas (valor absoluto)": "vitimas",
}
modo = MODOS[st.radio("Cor do mapa de calor", list(MODOS), horizontal=True)]

matriz = (dados.pivot_table(index="territorio", columns="crime", values="vitimas",
                            aggfunc="sum", fill_value=0)
          .reindex(columns=[c for c in crimes if c in dados["crime"].unique()]))
matriz = matriz.loc[matriz.sum(axis=1).sort_values(ascending=False, kind="stable").index]

if modo == "pct_crime":
    cor = 100 * matriz / matriz.sum(axis=0).replace(0, float("nan"))
    legenda, sufixo = "% do crime", "% das vítimas desse crime estão neste território"
elif modo == "pct_territorio":
    cor = 100 * matriz.div(matriz.sum(axis=1).replace(0, float("nan")), axis=0)
    legenda, sufixo = "% no território", "% das vítimas deste território são desse crime"
else:
    cor, legenda, sufixo = matriz, "Vítimas", ""
cor = cor.astype(float).fillna(0)

dica = "<b>%{y}</b><br>%{x}<br>%{customdata:,.0f} vítimas"
if sufixo:
    dica += "<br>%{z:.1f}" + sufixo
mapa = go.Figure(go.Heatmap(
    z=cor.values, x=cor.columns, y=cor.index, customdata=matriz.values,
    colorscale=ESCALA_SEQ, zmin=0, xgap=2, ygap=2,
    colorbar=dict(title=legenda, thickness=12, outlinewidth=0),
    hovertemplate=dica + "<extra></extra>"))
mapa.update_yaxes(autorange="reversed")
mapa.update_xaxes(side="top", tickangle=-30)
mapa = layout(mapa, altura=max(320, 24 * len(matriz) + 190))
mapa.update_layout(margin=dict(l=10, r=110, t=130, b=10))
mapa.update_xaxes(showgrid=False)
st.plotly_chart(mapa, width="stretch")
st.caption("Passe o cursor sobre uma célula para ver a quantidade de vítimas. "
           "Linhas ordenadas pelo total de vítimas do território. Crimes com poucos casos no estado "
           "(como lesão corporal seguida de morte, com 9 vítimas em 2025) geram percentuais instáveis.")

# ------------------------------------------------------------------ tabela (acessibilidade)
with st.expander("Ver os dados em tabela (território × tipo de crime)"):
    tabela = matriz.copy()
    tabela.insert(0, "Total", tabela.sum(axis=1))
    st.dataframe(tabela.rename_axis("Território").reset_index(), hide_index=True,
                 width="stretch")
