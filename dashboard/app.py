"""Dashboard — Feminicídio Interseccional no Espírito Santo (2017-2024).

Rodar na raiz do projeto:
    streamlit run dashboard/app.py

Lê somente as tabelas de agregação (agg_*) e a tabela ocorrencias com filtros,
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


@st.cache_data(ttl=600)
def consulta(sql: str, params: tuple = ()) -> pd.DataFrame:
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)


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

anos = consulta("SELECT DISTINCT ano FROM ocorrencias ORDER BY ano")["ano"].tolist()
municipios = consulta("SELECT DISTINCT municipio FROM ocorrencias ORDER BY municipio")["municipio"].tolist()

c1, c2, c3 = st.columns([2, 2, 1])
faixa_anos = c1.select_slider("Período", options=anos, value=(anos[0], anos[-1]))
mun_sel = c2.multiselect("Municípios (vazio = todos)", municipios)
so_fem = c3.toggle("Só feminicídios", value=False)

where = ["ano BETWEEN %s AND %s"]
params = [faixa_anos[0], faixa_anos[1]]
if mun_sel:
    where.append("municipio = ANY(%s)")
    params.append(mun_sel)
if so_fem:
    where.append("feminicidio")
W = " AND ".join(where)
P = tuple(params)

# ------------------------------------------------------------------ KPIs
k = consulta(f"""SELECT COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE feminicidio) AS fem,
                        COUNT(*) FILTER (WHERE raca_negra) AS negras,
                        COUNT(*) FILTER (WHERE raca_negra IS NOT NULL) AS com_raca
                 FROM ocorrencias WHERE {W}""", P).iloc[0]
total = int(k.total)
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
serie = consulta(f"""SELECT ano,
                            COUNT(*) FILTER (WHERE feminicidio) AS "Feminicídio",
                            COUNT(*) FILTER (WHERE NOT feminicidio) AS "Homicídio doloso"
                     FROM ocorrencias WHERE {W} GROUP BY ano ORDER BY ano""", P)
serie_long = serie.melt(id_vars="ano", var_name="Classificação", value_name="Vítimas")
fig = px.line(serie_long, x="ano", y="Vítimas", color="Classificação", markers=True,
              color_discrete_map={"Feminicídio": COR_FEM, "Homicídio doloso": COR_HOM},
              title="Vítimas por ano")
fig.update_traces(line_width=2, marker_size=8)
fig.update_xaxes(dtick=1, title=None)
st.plotly_chart(layout(fig), use_container_width=True)

# ------------------------------------------------------------------ perfis
def barras_por(coluna: str, titulo: str, ordem=None):
    df = consulta(f"""SELECT {coluna} AS categoria,
                             COUNT(*) FILTER (WHERE feminicidio) AS "Feminicídio",
                             COUNT(*) FILTER (WHERE NOT feminicidio) AS "Homicídio doloso"
                      FROM ocorrencias WHERE {W} GROUP BY 1""", P)
    df["total"] = df["Feminicídio"] + df["Homicídio doloso"]
    df = df.sort_values("total", ascending=True)
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
cruz = consulta(f"""SELECT faixa_etaria, raca_cor, COUNT(*) AS vitimas
                    FROM ocorrencias WHERE {W} GROUP BY 1, 2""", P)
matriz = cruz.pivot(index="faixa_etaria", columns="raca_cor", values="vitimas").fillna(0).astype(int)
matriz = matriz.reindex([f for f in ORDEM_FAIXA if f in matriz.index])
hm = px.imshow(matriz, text_auto=True, aspect="auto", color_continuous_scale=ESCALA_SEQ,
               labels=dict(x="Raça/cor", y="Faixa etária", color="Vítimas"))
st.plotly_chart(layout(hm, 380), use_container_width=True)

# ------------------------------------------------------------------ relação e município
a, b = st.columns(2)
rel = consulta(f"""SELECT grupo_relacao AS "Vínculo", COUNT(*) AS "Vítimas"
                   FROM ocorrencias WHERE {W} AND feminicidio GROUP BY 1 ORDER BY 2""", P)
fr = px.bar(rel, y="Vínculo", x="Vítimas", orientation="h",
            title="Vínculo com o autor (somente feminicídios)", color_discrete_sequence=[COR_FEM])
a.plotly_chart(layout(fr, 340), use_container_width=True)
a.caption("A relação vítima-autor está registrada quase exclusivamente nos casos de feminicídio; "
          "nos homicídios dolosos o campo aparece como NÃO INFORMADO.")

mun = consulta(f"""SELECT municipio AS "Município", COUNT(*) AS "Vítimas"
                   FROM ocorrencias WHERE {W} GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", P)
fm = px.bar(mun.iloc[::-1], y="Município", x="Vítimas", orientation="h",
            title="15 municípios com mais vítimas", color_discrete_sequence=[COR_FEM])
b.plotly_chart(layout(fm, 340), use_container_width=True)

# ------------------------------------------------------------------ tabela (acessibilidade)
with st.expander("Ver dados da série anual em tabela"):
    st.dataframe(serie, hide_index=True, use_container_width=True)
