"""Transformação: tipagem, formato longo e vínculo município -> Território de Identidade.

Saída (modelo estrela):
    territorios   id_territorio, nome_territorio
    municipios    cod_ibge, nome_municipio, id_territorio
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
                territorios_bruto: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Retorna ({nome_tabela: DataFrame}, correções aplicadas ao anexo)."""
    territorios, vinculo, correcoes = _territorios(territorios_bruto)
    municipios = _municipios(vitimas_bruto, vinculo)
    tipos = _tipos_crime([c for c in vitimas_bruto.columns if c not in ("ID", "MUNICÍPIO")])
    vitimas = _vitimas(vitimas_bruto, tipos, totais, ano)

    _exigir(len(vitimas) == len(municipios) * len(tipos), "fato incompleto (município x crime)")

    print(f"[transform] {len(territorios)} territórios | {len(municipios)} municípios | "
          f"{len(tipos)} tipos de crime | {len(vitimas)} linhas no fato | "
          f"{int(vitimas['qtd_vitimas'].sum())} vítimas | {len(correcoes)} correções no anexo")
    tabelas = {"territorios": territorios, "municipios": municipios,
               "tipos_crime": tipos, "vitimas": vitimas}
    return tabelas, correcoes
