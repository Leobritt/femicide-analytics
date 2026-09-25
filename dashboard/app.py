"""Dashboard — Feminicídio Interseccional no Espírito Santo (2017-2024).

Rodar na raiz do projeto:
    streamlit run dashboard/app.py

Faz uma única consulta à tabela ocorrencias (em cache) e agrega em pandas;
nunca exibe registros individuais.
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Paleta: série 1 = feminicídio (azul), série 2 = homicídio doloso (laranja). Ordem fixa.
COR_FEM, COR_HOM = "#2a78d6", "#eb6834"
ESCALA_SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
ORDEM_FAIXA = ["0-17", "18-29", "30-39", "40-59", "60+", "NÃO INFORMADO"]

st.set_page_config(page_title="Feminicídio Interseccional — ES", layout="wide")


COLUNAS = ["ano", "municipio", "feminicidio", "raca_cor", "raca_negra", "faixa_etaria",
           "tipo_local", "meio_empregado", "grupo_relacao"]


@st.cache_data(ttl=3600)
def carregar_base() -> pd.DataFrame:
    """Uma conexão e uma consulta; só as colunas usadas pelos gráficos."""
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(COLUNAS)} FROM ocorrencias")
            return pd.DataFrame(cur.fetchall(), columns=COLUNAS)


def contar(df: pd.DataFrame, por) -> pd.DataFrame:
    """Equivale a COUNT(*) FILTER (WHERE feminicidio) / (WHERE NOT feminicidio) ... GROUP BY por.
    feminicidio pode ser NULL: entra no grupo, mas não em nenhuma das duas contagens (como no SQL)."""
    return (df.assign(**{"Feminicídio": df["feminicidio"].eq(True),
                         "Homicídio doloso": df["feminicidio"].eq(False)})
              .groupby(por)[["Feminicídio", "Homicídio doloso"]].sum().reset_index())


def layout(fig, altura=360):
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=1.12, x=0, title=None),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


# ------------------------------------------------------------------ filtros
st.title("Homicídios de mulheres e feminicídios — Espírito Santo")
st.caption("Fonte: SESP-ES, Portal de Dados Abertos (dados.es.gov.br). Dados agregados; "
           "nenhum caso individual é exibido.")

if st.sidebar.button("Recarregar dados", help="Limpa o cache; use depois de rodar o ETL de novo."):
    st.cache_data.clear()

base = carregar_base()
anos = sorted(base["ano"].unique().tolist())
municipios = sorted(base["municipio"].unique().tolist())

c1, c2, c3 = st.columns([2, 2, 1])
faixa_anos = c1.select_slider("Período", options=anos, value=(anos[0], anos[-1]))
mun_sel = c2.multiselect("Municípios (vazio = todos)", municipios)
so_fem = c3.toggle("Só feminicídios", value=False)

filtro = base["ano"].between(faixa_anos[0], faixa_anos[1])
if mun_sel:
    filtro &= base["municipio"].isin(mun_sel)
if so_fem:
    filtro &= base["feminicidio"].eq(True)
dados = base[filtro]

# ------------------------------------------------------------------ KPIs
k = pd.Series({"fem": int(dados["feminicidio"].eq(True).sum()),
               "negras": int(dados["raca_negra"].eq(True).sum()),
               "com_raca": int(dados["raca_negra"].notna().sum())})
total = len(dados)
m1, m2, m3 = st.columns(3)
m1.metric("Vítimas no período", f"{total}")
m2.metric("Feminicídios", f"{int(k.fem)}", f"{100 * k.fem / total:.1f}% do total" if total else None,
          delta_color="off")
m3.metric("Vítimas negras (pretas + pardas)",
          f"{100 * k.negras / k.com_raca:.1f}%" if k.com_raca else "—",
          "entre vítimas com raça/cor informada", delta_color="off")

if total == 0:
    st.info("Nenhum registro para os filtros escolhidos.")
    st.stop()

# ------------------------------------------------------------------ série temporal
serie = contar(dados, "ano")
serie_long = serie.melt(id_vars="ano", var_name="Classificação", value_name="Vítimas")
fig = px.line(serie_long, x="ano", y="Vítimas", color="Classificação", markers=True,
              color_discrete_map={"Feminicídio": COR_FEM, "Homicídio doloso": COR_HOM},
              title="Vítimas por ano")
fig.update_traces(line_width=2, marker_size=8)
fig.update_xaxes(dtick=1, title=None)
st.plotly_chart(layout(fig), use_container_width=True)

# ------------------------------------------------------------------ perfis
def barras_por(coluna: str, titulo: str, ordem=None):
    df = contar(dados, coluna).rename(columns={coluna: "categoria"})
    df["total"] = df["Feminicídio"] + df["Homicídio doloso"]
    df = df.sort_values("total", ascending=True, kind="stable")
    longo = df.melt(id_vars=["categoria", "total"], var_name="Classificação", value_name="Vítimas")
    series = ["Feminicídio"] if so_fem else ["Feminicídio", "Homicídio doloso"]
    longo = longo[longo["Classificação"].isin(series)]
    f = px.bar(longo, y="categoria", x="Vítimas", color="Classificação", orientation="h",
               barmode="group", title=titulo,
               color_discrete_map={"Feminicídio": COR_FEM, "Homicídio doloso": COR_HOM},
               category_orders={"categoria": ordem} if ordem else None)
    f.update_yaxes(title=None)
    f.update_traces(marker_line_width=0)
    return layout(f, 340)


a, b = st.columns(2)
a.plotly_chart(barras_por("raca_cor", "Raça/cor da vítima"), use_container_width=True)
b.plotly_chart(barras_por("faixa_etaria", "Faixa etária", ORDEM_FAIXA[::-1]), use_container_width=True)
a, b = st.columns(2)
a.plotly_chart(barras_por("tipo_local", "Tipo de local"), use_container_width=True)
b.plotly_chart(barras_por("meio_empregado", "Meio empregado"), use_container_width=True)

# ------------------------------------------------------------------ interseccional
st.subheader("Cruzamento interseccional: faixa etária × raça/cor")
cruz = dados.groupby(["faixa_etaria", "raca_cor"]).size().reset_index(name="vitimas")
matriz = cruz.pivot(index="faixa_etaria", columns="raca_cor", values="vitimas").fillna(0).astype(int)
matriz = matriz.reindex([f for f in ORDEM_FAIXA if f in matriz.index])
hm = px.imshow(matriz, text_auto=True, aspect="auto", color_continuous_scale=ESCALA_SEQ,
               labels=dict(x="Raça/cor", y="Faixa etária", color="Vítimas"))
st.plotly_chart(layout(hm, 380), use_container_width=True)

# ------------------------------------------------------------------ relação e município
a, b = st.columns(2)
rel = (dados[dados["feminicidio"].eq(True)].groupby("grupo_relacao").size()
       .sort_values(kind="stable").rename_axis("Vínculo").reset_index(name="Vítimas"))
fr = px.bar(rel, y="Vínculo", x="Vítimas", orientation="h",
            title="Vínculo com o autor (somente feminicídios)", color_discrete_sequence=[COR_FEM])
a.plotly_chart(layout(fr, 340), use_container_width=True)
a.caption("A relação vítima-autor está registrada quase exclusivamente nos casos de feminicídio; "
          "nos homicídios dolosos o campo aparece como NÃO INFORMADO.")

mun = (dados.groupby("municipio").size().sort_values(ascending=False, kind="stable").head(15)
       .rename_axis("Município").reset_index(name="Vítimas"))
fm = px.bar(mun.iloc[::-1], y="Município", x="Vítimas", orientation="h",
            title="15 municípios com mais vítimas", color_discrete_sequence=[COR_FEM])
b.plotly_chart(layout(fm, 340), use_container_width=True)

# ------------------------------------------------------------------ tabela (acessibilidade)
with st.expander("Ver dados da série anual em tabela"):
    st.dataframe(serie, hide_index=True, use_container_width=True)
