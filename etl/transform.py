"""Transformação: tipagem, formato longo e vínculo município -> Território de Identidade.

Saída (modelo estrela):
    territorios   id_territorio, nome_territorio
    municipios    cod_ibge, nome_municipio, id_territorio, codigo_ibge7, area_km2,
                  populacao_censo_2022, populacao_estimada_2026,
                  mulheres_2022 e mulheres de cada cor ou raça (Censo 2022)
    tipos_crime   id_tipo_crime, codigo, nome_tipo_crime, letal
    vitimas       ano, cod_ibge, id_tipo_crime, qtd_vitimas

Qualquer inconsistência interrompe o pipeline com erro: a base é pequena e fechada
(417 municípios), então não há registro "rejeitável" sem comprometer os totais.
"""
import re
import unicodedata

import pandas as pd

# Crimes com resultado morte. Usado para separar violência letal e não letal no dashboard.
CRIMES_LETAIS = {"HOMICÍDIO DOLOSO", "FEMINICÍDIO", "LESÃO CORPORAL SEGUIDA DE MORTE"}

# O Anexo II (2011) diverge da planilha da SSP-BA em 10 pontos. A grafia adotada é a da
# planilha, que segue o IBGE. Chave: texto como está no PDF -> município(s) corretos.
CORRECOES_ANEXO = {
    # grafia diferente
    "Barra Choça": ["Barra do Choça"],
    "D. Macedo Costa": ["Dom Macêdo Costa"],
    "Lagedo do Tabocal": ["Lajedo do Tabocal"],
    "Rui Barbosa": ["Ruy Barbosa"],
    "Salinas das Margaridas": ["Salinas da Margarida"],
    "Santa Terezinha": ["Santa Teresinha"],
    "Tabocas d Brejo Velho": ["Tabocas do Brejo Velho"],
    # dois municípios sem vírgula entre eles no PDF
    "Barro Alto Cafarnaum": ["Barro Alto", "Cafarnaum"],
    "Bonito Ibicoara": ["Bonito", "Ibicoara"],
    "Lençóis Marcionílio Souza": ["Lençóis", "Marcionílio Souza"],
}

# Mesmo código IBGE com grafia diferente entre a planilha da SSP-BA e o IBGE Cidades.
# O join é pelo código; esta lista só libera a conferência de nomes. (nome SSP-BA, nome IBGE)
GRAFIAS_SSP_IBGE = {
    ("Santa Teresinha", "Santa Terezinha"),
}

# Categorias de cor ou raça do Censo 2022 (tabela 9606, só mulheres) -> colunas do banco.
# A diferença entre o total e a soma das cinco categorias são as pessoas sem declaração.
COLUNAS_COR_RACA = {
    "Total": "mulheres_2022",
    "Branca": "mulheres_brancas_2022",
    "Preta": "mulheres_pretas_2022",
    "Parda": "mulheres_pardas_2022",
    "Amarela": "mulheres_amarelas_2022",
    "Indígena": "mulheres_indigenas_2022",
}


# ---------------------------------------------------------------- utilitários
def _limpar(texto) -> str:
    """Une quebras de linha e remove espaços extras (mantém acentos e caixa)."""
    return re.sub(r"\s+", " ", str(texto)).strip()


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in t if not unicodedata.combining(c))


def _chave(nome: str) -> str:
    """Chave de comparação de nomes: sem acento, sem pontuação, sem espaço, maiúscula."""
    return re.sub(r"[^A-Z]", "", _sem_acento(_limpar(nome)).upper())


def _codigo(nome: str) -> str:
    """'LESÃO CORPORAL DOLOSA' -> 'lesao_corporal_dolosa'."""
    return re.sub(r"[^a-z]+", "_", _sem_acento(nome).lower()).strip("_")


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise ValueError(f"[transform] validação falhou: {mensagem}")


# ---------------------------------------------------------------- dimensões
def _territorios(bruto: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retorna (dim território, vínculo chave_município -> território, correções aplicadas)."""
    dim = pd.DataFrame({
        "id_territorio": pd.to_numeric(bruto["numero"]).astype(int),
        "nome_territorio": bruto["territorio"].map(_limpar),
    })
    _exigir(dim["id_territorio"].is_unique, "número de território repetido no anexo")

    vinculos, correcoes = [], []
    for id_territorio, lista in zip(dim["id_territorio"], bruto["municipios"]):
        for nome_pdf in (n.strip() for n in _limpar(lista).split(",")):
            if not nome_pdf:
                continue
            nomes = CORRECOES_ANEXO.get(nome_pdf, [nome_pdf])
            if nome_pdf in CORRECOES_ANEXO:
                correcoes.append({"id_territorio": id_territorio, "texto_no_anexo": nome_pdf,
                                  "corrigido_para": " | ".join(nomes)})
            vinculos += [{"chave": _chave(n), "nome_anexo": n, "id_territorio": id_territorio} for n in nomes]

    vinculo = pd.DataFrame(vinculos)
    repetidos = vinculo[vinculo["chave"].duplicated(keep=False)]["nome_anexo"].tolist()
    _exigir(not repetidos, f"município em mais de um território: {repetidos}")
    return dim, vinculo, pd.DataFrame(correcoes, columns=["id_territorio", "texto_no_anexo", "corrigido_para"])


def _municipios(bruto: pd.DataFrame, vinculo: pd.DataFrame) -> pd.DataFrame:
    dim = pd.DataFrame({
        "cod_ibge": pd.to_numeric(bruto["ID"], errors="coerce").astype("Int64"),  # texto '290010' -> inteiro
        "nome_municipio": bruto["MUNICÍPIO"].map(_limpar),
    })
    _exigir(dim["cod_ibge"].notna().all(), "código IBGE não numérico")
    _exigir(dim["cod_ibge"].between(290000, 299999).all(), "código IBGE fora da faixa da Bahia (29xxxx)")
    _exigir(dim["cod_ibge"].is_unique, "código IBGE repetido")

    dim["chave"] = dim["nome_municipio"].map(_chave)
    dim = dim.merge(vinculo[["chave", "id_territorio"]], on="chave", how="left")

    sem_territorio = dim[dim["id_territorio"].isna()]["nome_municipio"].tolist()
    _exigir(not sem_territorio, f"municípios da SSP-BA sem território no anexo: {sem_territorio}")
    sobrando = sorted(set(vinculo["chave"]) - set(dim["chave"]))
    _exigir(not sobrando, f"municípios do anexo que não existem na planilha: {sobrando}")

    dim["cod_ibge"] = dim["cod_ibge"].astype(int)
    dim["id_territorio"] = dim["id_territorio"].astype(int)
    return dim[["cod_ibge", "nome_municipio", "id_territorio"]]


def _com_ibge(dim: pd.DataFrame, bruto: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta população e área do IBGE Cidades à dimensão de municípios.

    A SSP-BA usa o código IBGE de 6 dígitos e o IBGE Cidades o de 7 (o último é o dígito
    verificador), então o join é feito por codigo_ibge7 // 10 = cod_ibge.
    """
    ibge = pd.DataFrame({
        "codigo_ibge7": pd.to_numeric(bruto["codigo_ibge7"], errors="coerce").astype("Int64"),
        "nome_ibge": bruto["nome_ibge"].map(_limpar),
        "area_km2": pd.to_numeric(bruto["area_km2"], errors="coerce"),
        "populacao_censo_2022": pd.to_numeric(bruto["populacao_censo_2022"], errors="coerce"),
        "populacao_estimada_2026": pd.to_numeric(bruto["populacao_estimada_2026"], errors="coerce"),
    })
    _exigir(ibge["codigo_ibge7"].between(2900000, 2999999).all(), "código IBGE (7 dígitos) fora da faixa da Bahia")
    _exigir(ibge["codigo_ibge7"].is_unique, "código IBGE repetido no CSV do IBGE")
    numericas = ["area_km2", "populacao_censo_2022", "populacao_estimada_2026"]
    _exigir(ibge[numericas].notna().all().all(), "área ou população vazia/não numérica no CSV do IBGE")
    _exigir((ibge[numericas] > 0).all().all(), "área ou população não positiva no CSV do IBGE")
    populacoes = ["populacao_censo_2022", "populacao_estimada_2026"]
    _exigir((ibge[populacoes] % 1 == 0).all().all(), "população não inteira no CSV do IBGE")

    ibge["cod_ibge"] = (ibge["codigo_ibge7"] // 10).astype(int)
    juntos = dim.merge(ibge, on="cod_ibge", how="outer", indicator=True)
    so_ssp = juntos[juntos["_merge"] == "left_only"]["nome_municipio"].tolist()
    so_ibge = juntos[juntos["_merge"] == "right_only"]["nome_ibge"].tolist()
    _exigir(not so_ssp, f"municípios da SSP-BA sem dados no IBGE: {so_ssp}")
    _exigir(not so_ibge, f"municípios do IBGE que não existem na planilha da SSP-BA: {so_ibge}")

    # conferência extra do join: o nome tem que bater (ignorando acento, caixa e pontuação),
    # salvo as grafias divergentes já conhecidas entre SSP-BA e IBGE Cidades
    diferente = juntos["nome_municipio"].map(_chave) != juntos["nome_ibge"].map(_chave)
    conhecido = [(a, b) in GRAFIAS_SSP_IBGE for a, b in zip(juntos["nome_municipio"], juntos["nome_ibge"])]
    nomes_diferentes = juntos[diferente & ~pd.Series(conhecido, index=juntos.index)]
    _exigir(nomes_diferentes.empty, "mesmo código com nomes diferentes: "
            f"{list(zip(nomes_diferentes['nome_municipio'], nomes_diferentes['nome_ibge']))}")

    juntos["codigo_ibge7"] = juntos["codigo_ibge7"].astype(int)
    for c in populacoes:
        juntos[c] = juntos[c].astype(int)
    return juntos[["cod_ibge", "nome_municipio", "id_territorio", "codigo_ibge7", *numericas]]


def _com_cor_raca(dim: pd.DataFrame, bruto: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a população feminina por cor ou raça (Censo 2022) à dimensão de municípios.

    O join é pelo código de 7 dígitos, que os dois arquivos do IBGE usam. Na tabela do
    IBGE, '-' significa zero absoluto (não é dado faltante), então vira 0; qualquer outro
    valor que não seja número interrompe o pipeline.
    """
    texto = bruto[list(COLUNAS_COR_RACA)].astype(str).apply(lambda c: c.str.strip())
    _exigir(texto.apply(lambda c: c.str.fullmatch(r"\d+|-")).all().all(),
            "valor fora do padrão (número ou '-') na tabela de cor ou raça")
    cor_raca = texto.replace("-", "0").astype(int).rename(columns=COLUNAS_COR_RACA)
    cor_raca.insert(0, "codigo_ibge7", pd.to_numeric(bruto["codigo_ibge7"], errors="coerce").astype("Int64"))
    _exigir(cor_raca["codigo_ibge7"].notna().all() and cor_raca["codigo_ibge7"].is_unique,
            "código IBGE vazio ou repetido na tabela de cor ou raça")
    _exigir((cor_raca["mulheres_2022"] > 0).all(), "município sem população feminina no Censo 2022")
    partes = [c for c in COLUNAS_COR_RACA.values() if c != "mulheres_2022"]
    _exigir((cor_raca[partes].sum(axis=1) <= cor_raca["mulheres_2022"]).all(),
            "soma das categorias de cor ou raça maior que o total de mulheres")

    juntos = dim.merge(cor_raca.astype({"codigo_ibge7": int}), on="codigo_ibge7", how="outer", indicator=True)
    sem_par = juntos[juntos["_merge"] != "both"]["codigo_ibge7"].tolist()
    _exigir(not sem_par, f"municípios sem par entre IBGE Cidades e Censo por cor ou raça: {sem_par}")
    _exigir((juntos["mulheres_2022"] <= juntos["populacao_censo_2022"]).all(),
            "mais mulheres do que habitantes no Censo 2022")
    return juntos.drop(columns="_merge")[[*dim.columns, *COLUNAS_COR_RACA.values()]]


def _tipos_crime(colunas: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "id_tipo_crime": range(1, len(colunas) + 1),   # ordem das colunas na planilha
        "codigo": [_codigo(c) for c in colunas],
        "nome_tipo_crime": colunas,
        "letal": [c in CRIMES_LETAIS for c in colunas],
    })


# ---------------------------------------------------------------- fato
def _vitimas(bruto: pd.DataFrame, tipos: pd.DataFrame, totais: pd.Series, ano: int) -> pd.DataFrame:
    colunas = tipos["nome_tipo_crime"].tolist()
    valores = bruto[colunas].apply(pd.to_numeric, errors="coerce")
    _exigir(valores.notna().all().all(), "contagem vazia ou não numérica")
    _exigir((valores % 1 == 0).all().all(), "contagem não inteira")
    _exigir((valores >= 0).all().all(), "contagem negativa")

    divergentes = [c for c in colunas if int(valores[c].sum()) != int(totais[c])]
    _exigir(not divergentes, f"soma diferente da linha Total da planilha em: {divergentes}")

    # largo -> longo: uma linha por município x tipo de crime
    largo = valores.astype(int).assign(cod_ibge=pd.to_numeric(bruto["ID"]).astype(int).values)
    longo = largo.melt(id_vars="cod_ibge", var_name="nome_tipo_crime", value_name="qtd_vitimas")
    longo = longo.merge(tipos[["id_tipo_crime", "nome_tipo_crime"]], on="nome_tipo_crime")
    longo["ano"] = ano
    return (longo[["ano", "cod_ibge", "id_tipo_crime", "qtd_vitimas"]]
            .sort_values(["cod_ibge", "id_tipo_crime"], kind="stable").reset_index(drop=True))


# ---------------------------------------------------------------- pipeline
def transformar(vitimas_bruto: pd.DataFrame, totais: pd.Series, ano: int,
                territorios_bruto: pd.DataFrame,
                ibge_bruto: pd.DataFrame,
                cor_raca_bruto: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Retorna ({nome_tabela: DataFrame}, correções aplicadas ao anexo)."""
    territorios, vinculo, correcoes = _territorios(territorios_bruto)
    municipios = _com_cor_raca(_com_ibge(_municipios(vitimas_bruto, vinculo), ibge_bruto), cor_raca_bruto)
    tipos = _tipos_crime([c for c in vitimas_bruto.columns if c not in ("ID", "MUNICÍPIO")])
    vitimas = _vitimas(vitimas_bruto, tipos, totais, ano)

    _exigir(len(vitimas) == len(municipios) * len(tipos), "fato incompleto (município x crime)")

    print(f"[transform] {len(territorios)} territórios | {len(municipios)} municípios | "
          f"{len(tipos)} tipos de crime | {len(vitimas)} linhas no fato | "
          f"{int(vitimas['qtd_vitimas'].sum())} vítimas | {len(correcoes)} correções no anexo | "
          f"população estimada 2026: {int(municipios['populacao_estimada_2026'].sum())} | "
          f"mulheres (Censo 2022): {int(municipios['mulheres_2022'].sum())}")
    tabelas = {"territorios": territorios, "municipios": municipios,
               "tipos_crime": tipos, "vitimas": vitimas}
    return tabelas, correcoes
