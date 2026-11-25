"""Dashboard — Violência contra a mulher na Bahia por Território de Identidade.

Rodar na raiz do projeto:
    streamlit run dashboard/app.py

Faz uma única consulta ao banco (em cache) e agrega em pandas, inclusive as taxas por
100 mil habitantes, para que elas respeitem os filtros. A base tem 4.587 linhas por
ano, então os filtros respondem sem novas idas ao banco.

Tema e cores: .streamlit/config.toml (modo claro e escuro, trocado no menu ⋮). Os
gráficos usam só cores que funcionam nos dois modos; textos e grades seguem o tema.
"""
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

st.set_page_config(page_title="Violência contra a mulher — Bahia", page_icon=":material/bar_chart:",
                   layout="wide")

SQL = """
    SELECT f.ano,
           t.nome_territorio AS territorio,
           m.cod_ibge,
           m.nome_municipio  AS municipio,
           m.populacao_estimada_2026 AS populacao,
           m.area_km2,
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

# ------------------------------------------------------------------ cores
# Valem para o modo claro e o escuro. O tema pode ser trocado no menu ⋮ sem rodar o script
# de novo, então os gráficos não fixam cor de texto, grade nem fundo: isso fica com o tema
# do Streamlit, aplicado no navegador. Aqui só entram cores legíveis nos dois fundos.
# A cor segue a categoria, não a posição: não letal = azul, letal = laranja.
COR = {"nao_letal": "#3380dd", "letal": "#e2602d",
       "neutro": "#8a8984",                         # linha da Bahia e rótulos secundários
       # no mapa de calor a escala é opaca: com transparência, o Plotly escolhe a cor do
       # número pela célula sem ver o fundo e escrevia preto sobre o modo escuro
       "seq_opaca": ["#e3eefb", "#b7d3f6", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]}

# Faixas iguais às da vw_porte_municipio (sql/02_agregacoes.sql): (limite superior, rótulo)
FAIXAS_PORTE = [(20_000, "até 20 mil hab."), (50_000, "20 a 50 mil hab."),
                (100_000, "50 a 100 mil hab."), (500_000, "100 a 500 mil hab."),
                (float("inf"), "mais de 500 mil hab.")]
FAIXAS_DENSIDADE = [(10, "até 10 hab./km²"), (25, "10 a 25 hab./km²"), (50, "25 a 50 hab./km²"),
                    (100, "50 a 100 hab./km²"), (float("inf"), "mais de 100 hab./km²")]
LIMITE_PEQUENO = 20_000   # municípios menores que isso geram taxas instáveis
MEDIDAS = ["Vítimas", "Taxa por 100 mil hab."]


# ------------------------------------------------------------------ formatação
CONECTORES = {"de", "da", "do", "das", "dos", "e"}


def nome_proprio(texto: str) -> str:
    """'AGRESTE DE ALAGOINHAS / LITORAL NORTE' -> 'Agreste de Alagoinhas / Litoral Norte';
    'Senhor Do Bonfim' -> 'Senhor do Bonfim'; 'Dias D'Ávila' -> "Dias d'Ávila"."""
    saida = []
    for i, palavra in enumerate(texto.lower().split()):
        if i > 0 and palavra in CONECTORES:
            saida.append(palavra)
        elif re.fullmatch(r"[ivx]+", palavra):            # algarismo romano: "II"
            saida.append(palavra.upper())
        elif palavra.startswith("d'"):
            saida.append("d'" + palavra[2:].capitalize())
        else:
            saida.append("-".join(p.capitalize() for p in palavra.split("-")))
    return " ".join(saida)


def num(valor, casas: int = 0) -> str:
    """12345.6 -> '12.345,6' (separadores brasileiros)."""
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def taxa_100k(vitimas, populacao):
    """Vítimas por 100 mil habitantes. Em agregados, recebe SOMAS (nunca média de taxas)."""
    return 100_000 * vitimas / populacao


def faixa(valor: float, faixas) -> str:
    return next(rotulo for limite, rotulo in faixas if valor < limite)


def variacao(valor: float, referencia: float) -> str | None:
    """'+26% vs. estado' — usado como delta dos indicadores."""
    if not referencia:
        return None
    pct = 100 * (valor / referencia - 1)
    return f"{'+' if pct >= 0 else '-'}{num(abs(pct))}% vs. estado"


# ------------------------------------------------------------------ dados
@st.cache_data(ttl=3600)
def carregar_base() -> pd.DataFrame:
    """Uma conexão e uma consulta; o resultado fica em cache por 1 hora."""
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
            colunas = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=colunas)
    # rótulos para exibição; os valores no banco ficam como na fonte
    df["crime"] = (df["crime"].str.capitalize()                # "LESÃO CORPORAL DOLOSA" -> "Lesão corporal dolosa"
                   .str.replace("homicidio", "homicídio"))     # a SSP-BA publica sem acento
    df["territorio"] = df["territorio"].map(nome_proprio)
    df["municipio"] = df["municipio"].map(nome_proprio)
    df["categoria"] = df["letal"].map({True: "Letal", False: "Não letal"})
    df["area_km2"] = df["area_km2"].astype(float)              # NUMERIC chega como Decimal
    return df


# ------------------------------------------------------------------ gráficos
ROTULOS = {"vitimas": "Vítimas", "taxa": "Taxa por 100 mil hab.", "populacao": "População",
           "territorio": "Território", "municipio": "Município", "crime": "Tipo de crime",
           "categoria": "Categoria", "faixa": "Faixa", "municipios": "Municípios"}


def layout(fig, altura: int):
    fig.update_layout(
        height=altura, margin=dict(l=8, r=56, t=8, b=8),
        separators=",.",                                   # decimal com vírgula, milhar com ponto
        font=dict(size=13),
        hoverlabel=dict(font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.28, barcornerradius=4)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)", zeroline=False, title=None,
                     tickformat=",.0f", tickfont=dict(size=12))
    fig.update_yaxes(showgrid=False, title=None, ticksuffix="  ", tickfont=dict(size=13))
    return fig


def barras(df: pd.DataFrame, categoria: str, valor: str, *, cor: str | None = None,
           ordenar: bool = True, referencia: float | None = None, altura: int | None = None):
    """Barras horizontais com o valor ao lado de cada barra.

    valor: 'vitimas' (contagem) ou 'taxa' (por 100 mil hab.).
    ordenar=False mantém a ordem recebida (ex.: faixas de porte), de cima para baixo.
    referencia: desenha a taxa do estado como linha tracejada.
    """
    if ordenar:
        df = df.sort_values(valor, ascending=False, kind="stable")
    ordem = df[categoria].tolist()
    formato = {"taxa": ":,.1f", "vitimas": ":,.0f", "populacao": ":,.0f"}
    fig = px.bar(df, y=categoria, x=valor, orientation="h", color=cor,
                 color_discrete_map={"Não letal": COR["nao_letal"], "Letal": COR["letal"]},
                 color_discrete_sequence=[COR["nao_letal"]],
                 category_orders={categoria: ordem, "categoria": ["Não letal", "Letal"]},
                 hover_data={c: formato.get(c, True) for c in df.columns if c not in (categoria, valor, cor)},
                 labels=ROTULOS)
    fig.update_traces(texttemplate="%{x:,.1f}" if valor == "taxa" else "%{x:,.0f}",
                      textposition="outside", cliponaxis=False, marker_line_width=0,
                      textfont=dict(size=12))
    if referencia is not None:
        # com a linha da Bahia, o valor vai para dentro da barra, para a linha não cruzar o texto
        fig.update_traces(textposition="inside", insidetextanchor="end",
                          textfont=dict(color="#ffffff", size=12))
        fig.add_vline(x=referencia, line_dash="dot", line_width=1.5, line_color=COR["neutro"],
                      layer="above",                       # na frente: atrás, sumia quando as barras passavam dela
                      annotation_text=f"Bahia: {num(referencia, 1)}", annotation_position="top",
                      annotation_font=dict(size=12, color=COR["neutro"]))
    fig = layout(fig, altura or max(220, 30 * len(df) + 40))
    if referencia is not None:
        fig.update_layout(margin=dict(t=28))
    if not cor:
        fig.update_layout(showlegend=False)
    return fig


def grafico(fig):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def titulo_secao(texto: str, legenda: str | None = None):
    st.markdown(f"**{texto}**")
    if legenda:
        st.caption(legenda)


# ------------------------------------------------------------------ cabeçalho
cab_titulo, cab_botao = st.columns([6, 1], vertical_alignment="bottom")
cab_titulo.title("Violência contra a mulher na Bahia")
cab_titulo.caption("Vítimas mulheres por Território de Identidade, município e tipo de crime · "
                   "Fontes: SSP-BA (vítimas) e IBGE (população) · Dados agregados; nenhum caso "
                   "individual é exibido.")
if cab_botao.button("Atualizar dados", icon=":material/refresh:", type="tertiary",
                    help="Limpa o cache. Use depois de rodar o ETL de novo."):
    st.cache_data.clear()

try:
    base = carregar_base()
except KeyError:
    st.error("DATABASE_URL não definida. Copie .env.example para .env e preencha.")
    st.stop()
except psycopg2.Error as erro:
    st.error(f"Não foi possível consultar o banco. Verifique se o banco está no ar "
             f"e se o ETL já foi executado.\n\n{erro}")
    st.stop()

anos = sorted(base["ano"].unique().tolist())
territorios = sorted(base["territorio"].unique().tolist())
crimes = (base[["id_tipo_crime", "crime"]].drop_duplicates()
          .sort_values("id_tipo_crime")["crime"].tolist())

# ------------------------------------------------------------------ filtros
with st.container(border=True):
    f1, f2, f3, f4 = st.columns([1.1, 3, 3, 2.4], vertical_alignment="bottom")
    ano = f1.selectbox("Ano", anos, index=len(anos) - 1)
    terr_sel = f2.multiselect("Territórios de Identidade", territorios, placeholder="Todos os territórios")
    crime_sel = f3.multiselect("Tipos de crime", crimes, placeholder="Todos os crimes")
    medida = f4.segmented_control(
        "Medida", MEDIDAS, default=MEDIDAS[0],
        help="A taxa divide as vítimas pela população estimada pelo IBGE (referência jul/2024), "
             "para comparar lugares de tamanhos diferentes. É sobre a população total, não a feminina.")
    so_letais = st.toggle("Só crimes letais",
                          help="Homicídio doloso, feminicídio e lesão corporal seguida de morte.")

em_taxa = (medida or MEDIDAS[0]) != MEDIDAS[0]
valor = "taxa" if em_taxa else "vitimas"
nome_valor = "Taxa por 100 mil hab." if em_taxa else "Vítimas"

base_ano = base[base["ano"] == ano]
filtro_crime = base_ano["crime"].isin(crime_sel or crimes)
if so_letais:
    filtro_crime &= base_ano["letal"]
dados = base_ano[filtro_crime & base_ano["territorio"].isin(terr_sel or territorios)]
dados_estado = base_ano[filtro_crime]          # referência "Bahia" com os mesmos crimes

# Uma linha por município: a população não pode ser somada a partir de `dados`, que tem
# uma linha por município x crime e multiplicaria a população pelo nº de crimes.
municipios = base_ano.drop_duplicates("cod_ibge")[["cod_ibge", "municipio", "territorio", "populacao", "area_km2"]]
mun_sel = municipios[municipios["territorio"].isin(terr_sel or territorios)]
pop_sel, pop_estado = int(mun_sel["populacao"].sum()), int(municipios["populacao"].sum())
taxa_estado = taxa_100k(dados_estado["vitimas"].sum(), pop_estado)

# ------------------------------------------------------------------ indicadores
# Seguem todos os filtros. Se o crime de um cartão ficou fora da seleção, o cartão mostra
# "—" em vez de um zero, que pareceria "nenhum caso".
INDICADORES = [("Vítimas", lambda d: d), ("Feminicídios", lambda d: d[d["codigo"] == "feminicidio"]),
               ("Tentativas de feminicídio", lambda d: d[d["codigo"] == "tentativa_de_feminicidio"]),
               ("Vítimas de crimes letais", lambda d: d[d["letal"]])]
for coluna, (nome, recorte) in zip(st.columns(4), INDICADORES):
    selecionado = recorte(dados)
    n = int(selecionado["vitimas"].sum())
    n_estado = int(recorte(dados_estado)["vitimas"].sum())
    t, t_estado = taxa_100k(n, pop_sel), taxa_100k(n_estado, pop_estado)
    with coluna.container(border=True):
        if selecionado.empty:
            st.metric(f"{nome} por 100 mil hab." if em_taxa else nome, "—")
            st.caption("fora do filtro de crimes")
        elif em_taxa:
            st.metric(f"{nome} por 100 mil hab.", num(t, 2),
                      delta=variacao(t, t_estado) if terr_sel else None, delta_color="inverse",
                      help="Comparação com a taxa da Bahia inteira." if terr_sel else None)
            st.caption(f"{num(n)} vítimas")
        else:
            st.metric(nome, num(n))
            st.caption(f"{num(100 * n / n_estado, 1)}% do estado" if terr_sel and n_estado
                       else f"{num(t, 2)} por 100 mil hab.")
st.caption(f"{ano} · {'territórios selecionados' if terr_sel else 'Bahia inteira'} · "
           f"{num(pop_sel)} habitantes · "
           + ("todos os tipos de crime" if not (crime_sel or so_letais)
              else "só os crimes selecionados") + ".")

if dados["vitimas"].sum() == 0:
    st.info("Nenhuma vítima registrada para os filtros escolhidos.", icon=":material/info:")
    st.stop()

# agregados usados em mais de uma aba
por_territorio = (dados.groupby("territorio", as_index=False)["vitimas"].sum()
                  .merge(mun_sel.groupby("territorio", as_index=False)["populacao"].sum(), on="territorio"))
por_territorio["taxa"] = taxa_100k(por_territorio["vitimas"], por_territorio["populacao"])

por_crime = dados.groupby(["crime", "categoria"], as_index=False)["vitimas"].sum()
por_crime["taxa"] = taxa_100k(por_crime["vitimas"], pop_sel)

por_municipio = (dados.groupby("cod_ibge", as_index=False)["vitimas"].sum()
                 .merge(mun_sel, on="cod_ibge", how="right").fillna({"vitimas": 0}))
por_municipio["taxa"] = taxa_100k(por_municipio["vitimas"], por_municipio["populacao"])
por_municipio["densidade"] = por_municipio["populacao"] / por_municipio["area_km2"]

referencia = taxa_estado if em_taxa else None
nota_taxa = ("Taxa por 100 mil habitantes, sobre a população total (não a feminina): compara lugares "
             "entre si, mas não equivale às taxas oficiais por 100 mil mulheres.")

aba_geral, aba_terr, aba_mun, aba_cruz, aba_dados = st.tabs(
    ["Visão geral", "Territórios", "Municípios", "Cruzamentos", "Dados"])

# ------------------------------------------------------------------ visão geral
with aba_geral:
    g1, g2 = st.columns(2, gap="large")
    with g1:
        # Dois gráficos com escalas próprias: num só, os crimes letais (dezenas ou centenas
        # de vítimas) viravam riscos ao lado de ameaça (dezenas de milhares).
        e_letal = por_crime["categoria"] == "Letal"
        nao_letais, letais = por_crime[~e_letal], por_crime[e_letal]
        titulo_secao(f"{nome_valor} por tipo de crime")
        if len(nao_letais):
            grafico(barras(nao_letais, "crime", valor, altura=30 * len(nao_letais) + 40))
        if len(letais):
            titulo_secao("Crimes com resultado morte", "Escala própria, bem menor que a do gráfico acima.")
            fig_letais = barras(letais, "crime", valor, cor="categoria", altura=30 * len(letais) + 40)
            grafico(fig_letais.update_layout(showlegend=False))
    with g2:
        top = por_territorio.sort_values(valor, ascending=False, kind="stable").head(10)
        titulo_secao(f"10 territórios com {'maior taxa' if em_taxa else 'mais vítimas'}",
                     "A lista completa está na aba Territórios.")
        grafico(barras(top, "territorio", valor, referencia=referencia, altura=420))
    if em_taxa:
        st.caption(nota_taxa)

# ------------------------------------------------------------------ territórios
with aba_terr:
    titulo_secao(f"{nome_valor} por Território de Identidade",
                 "Contagens absolutas: territórios mais populosos tendem a liderar. Use a medida "
                 "“Taxa por 100 mil hab.” para comparar territórios de tamanhos diferentes."
                 if not em_taxa else nota_taxa + " A linha pontilhada é a taxa da Bahia.")
    grafico(barras(por_territorio, "territorio", valor, referencia=referencia))

# ------------------------------------------------------------------ municípios
with aba_mun:
    m1, m2 = st.columns([1.15, 1], gap="large")
    with m1:
        ranking = por_municipio[["municipio", "territorio", "populacao", "vitimas", "taxa"]]
        titulo_secao(f"15 municípios com {'maior taxa' if em_taxa else 'mais vítimas'}",
                     "Passe o cursor sobre uma barra para ver vítimas e população.")
        if em_taxa:
            pequenos = st.toggle(f"Incluir municípios com menos de {num(LIMITE_PEQUENO)} habitantes",
                                 help="Nesses municípios, um ou dois casos já produzem taxas muito altas.")
            if not pequenos:
                ranking = ranking[ranking["populacao"] >= LIMITE_PEQUENO]
        ranking = ranking.sort_values(valor, ascending=False, kind="stable").head(15)
        grafico(barras(ranking, "municipio", valor, referencia=referencia))

    with m2:
        titulo_secao("Ficha do município")
        escolha = st.selectbox("Município", sorted(mun_sel["municipio"]), index=None,
                               placeholder="Digite para buscar um município", label_visibility="collapsed")
        if escolha is None:
            st.caption("Escolha um município para ver população, área, vítimas e taxas comparadas "
                       "com o território e a Bahia.")
        else:
            mun = por_municipio[por_municipio["municipio"] == escolha].iloc[0]
            terr = por_territorio[por_territorio["territorio"] == mun["territorio"]].iloc[0]
            # posição na Bahia inteira, com os mesmos filtros de crime
            todos = (dados_estado.groupby("cod_ibge")["vitimas"].sum()
                     .to_frame().join(municipios.set_index("cod_ibge")["populacao"]))
            todos["taxa"] = taxa_100k(todos["vitimas"], todos["populacao"])
            posicao = int((todos["taxa"] > mun["taxa"]).sum()) + 1
            with st.container(border=True):
                st.markdown(f"#### {escolha}")
                st.caption(f"Território {mun['territorio']} · {num(mun['populacao'])} habitantes · "
                           f"{num(mun['area_km2'], 1)} km² · {num(mun['densidade'], 1)} hab./km²")
                c1, c2 = st.columns(2)
                c1.metric("Vítimas", num(mun["vitimas"]))
                c2.metric("Taxa por 100 mil hab.", num(mun["taxa"], 1),
                          delta=variacao(mun["taxa"], taxa_estado), delta_color="inverse")
                st.caption(f"Taxa do território: {num(terr['taxa'], 1)} · Bahia: {num(taxa_estado, 1)} · "
                           f"{posicao}º maior taxa entre os {len(todos)} municípios"
                           + (" · município pequeno: taxa instável" if mun["populacao"] < LIMITE_PEQUENO else ""))
            crimes_mun = (dados[dados["cod_ibge"] == mun["cod_ibge"]]
                          .groupby(["crime", "categoria"], as_index=False)["vitimas"].sum())
            crimes_mun["taxa"] = taxa_100k(crimes_mun["vitimas"], mun["populacao"])
            crimes_mun = crimes_mun[crimes_mun["vitimas"] > 0]
            if len(crimes_mun):
                grafico(barras(crimes_mun, "crime", valor, cor="categoria"))

# ------------------------------------------------------------------ cruzamentos
with aba_cruz:
    titulo_secao("Taxa por porte e densidade do município",
                 "Vítimas por 100 mil habitantes, somando todos os municípios de cada faixa. Faixas "
                 "de porte do IBGE; a densidade (hab./km²) indica, de forma aproximada, quão urbano "
                 "é o município.")
    p1, p2 = st.columns(2, gap="large")
    for coluna, campo, faixas, titulo in [(p1, "populacao", FAIXAS_PORTE, "Por porte populacional"),
                                          (p2, "densidade", FAIXAS_DENSIDADE, "Por densidade demográfica")]:
        grupo = por_municipio.assign(faixa=por_municipio[campo].map(lambda v: faixa(v, faixas)))
        grupo = (grupo.groupby("faixa", as_index=False)
                 .agg(vitimas=("vitimas", "sum"), populacao=("populacao", "sum"),
                      municipios=("cod_ibge", "count")))
        ordem = [r for _, r in faixas if r in set(grupo["faixa"])]
        grupo = grupo.set_index("faixa").loc[ordem].reset_index()
        grupo["taxa"] = taxa_100k(grupo["vitimas"], grupo["populacao"])
        with coluna:
            st.caption(titulo)
            grafico(barras(grupo, "faixa", "taxa", ordenar=False, referencia=taxa_estado))

    st.divider()
    titulo_secao("Território × tipo de crime")
    MODOS = {"Taxa por 100 mil hab.": "taxa",
             "Composição do território": "pct_territorio",
             "Participação no crime": "pct_crime",
             "Vítimas": "vitimas"}
    h1, h2 = st.columns([3, 1.3], vertical_alignment="bottom")
    modo = MODOS[h1.segmented_control("Cor das células", list(MODOS), default="Taxa por 100 mil hab.")
                 or "Taxa por 100 mil hab."]
    por_coluna = h2.toggle("Escala própria por crime", value=True,
                           help="Cada coluna usa a própria escala, para mostrar a variação entre "
                                "territórios mesmo em crimes raros. O valor real aparece no cursor.")

    matriz = (dados.pivot_table(index="territorio", columns="crime", values="vitimas",
                                aggfunc="sum", fill_value=0)
              .reindex(columns=[c for c in crimes if c in dados["crime"].unique()]))
    pop_terr = mun_sel.groupby("territorio")["populacao"].sum().reindex(matriz.index)
    if modo == "taxa":
        valores = taxa_100k(matriz, pop_terr.values[:, None])
        sufixo, casas = " por 100 mil hab.", 1
    elif modo == "pct_territorio":
        valores = 100 * matriz.div(matriz.sum(axis=1).replace(0, float("nan")), axis=0)
        sufixo, casas = "% das vítimas do território", 1
    elif modo == "pct_crime":
        valores = 100 * matriz / matriz.sum(axis=0).replace(0, float("nan"))
        sufixo, casas = "% das vítimas desse crime na Bahia", 1
    else:
        valores, sufixo, casas = matriz, " vítimas", 0
    valores = valores.astype(float).fillna(0)
    ordem_linhas = valores.mean(axis=1).sort_values(ascending=False, kind="stable").index
    valores, matriz = valores.loc[ordem_linhas], matriz.loc[ordem_linhas]
    cor_celula = valores / valores.max(axis=0).replace(0, 1) if por_coluna else valores

    mapa = go.Figure(go.Heatmap(
        z=cor_celula.values, x=valores.columns, y=valores.index,
        customdata=np.dstack([valores.values, matriz.values]),   # [valor real, vítimas] por célula
        # valor escrito na célula, para ler sem o cursor (projetor, impressão)
        text=valores.apply(lambda coluna: coluna.map(lambda v: num(v, casas))).values, texttemplate="%{text}",
        textfont=dict(size=11),
        colorscale=COR["seq_opaca"], zmin=0, xgap=3, ygap=3, showscale=not por_coluna,
        colorbar=dict(thickness=10, outlinewidth=0),
        hovertemplate="<b>%{y}</b><br>%{x}<br>%{customdata[0]:,." + str(casas) + "f}" + sufixo
                      + "<br>%{customdata[1]:,.0f} vítimas<extra></extra>"))
    mapa.update_yaxes(autorange="reversed", ticksuffix="  ")
    mapa.update_xaxes(side="top", tickangle=-35, showgrid=False)
    mapa = layout(mapa, altura=26 * len(valores) + 170)
    mapa.update_xaxes(showgrid=False, tickfont=dict(size=12))
    mapa.update_layout(margin=dict(l=8, r=8, t=150, b=8))
    grafico(mapa)
    st.caption("Linhas ordenadas pelo valor médio do território. "
               + ("Com a escala própria, a cor compara territórios dentro de cada crime, não entre crimes. "
                  if por_coluna else "")
               + "Crimes com poucos casos na Bahia (como lesão corporal seguida de morte, com 9 vítimas "
                 "em 2025) geram valores instáveis.")

# ------------------------------------------------------------------ dados
with aba_dados:
    titulo_secao("Dados por município",
                 "Com os filtros acima. Clique no nome de uma coluna para ordenar.")
    tabela = (por_municipio.assign(letais=por_municipio["cod_ibge"].map(
                  dados[dados["letal"]].groupby("cod_ibge")["vitimas"].sum()).fillna(0),
                  feminicidios=por_municipio["cod_ibge"].map(
                  dados[dados["codigo"] == "feminicidio"].groupby("cod_ibge")["vitimas"].sum()).fillna(0))
              [["cod_ibge", "municipio", "territorio", "populacao", "area_km2", "densidade",
                "vitimas", "letais", "feminicidios", "taxa"]]
              .sort_values("vitimas", ascending=False, kind="stable"))
    st.dataframe(
        tabela, hide_index=True, width="stretch", height=420,
        column_config={
            "cod_ibge": st.column_config.NumberColumn("Código IBGE", format="%d"),
            "municipio": "Município", "territorio": "Território",
            "populacao": st.column_config.NumberColumn("População", format="localized"),
            "area_km2": st.column_config.NumberColumn("Área (km²)", format="%.1f"),
            "densidade": st.column_config.NumberColumn("Hab./km²", format="%.1f"),
            "vitimas": st.column_config.NumberColumn("Vítimas", format="localized"),
            "letais": st.column_config.NumberColumn("Crimes letais", format="%d"),
            "feminicidios": st.column_config.NumberColumn("Feminicídios", format="%d"),
            "taxa": st.column_config.NumberColumn("Taxa por 100 mil hab.", format="%.1f"),
        })
    st.download_button(
        "Baixar CSV", icon=":material/download:",
        data=tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),  # abre direto no Excel
        file_name=f"vitimas_municipios_{ano}.csv", mime="text/csv")

    st.divider()
    titulo_secao("Território × tipo de crime (vítimas)")
    tabela_terr = matriz.copy()
    tabela_terr.insert(0, "Total", tabela_terr.sum(axis=1))
    st.dataframe(tabela_terr.sort_values("Total", ascending=False).rename_axis("Território").reset_index(),
                 hide_index=True, width="stretch")
