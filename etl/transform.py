"""Transformação: limpeza, tipagem, normalização de categorias e atributos derivados.

Regras documentadas na Seção 2 da entrega 1. Registros que não passam na validação
vão para logs/rejeitados.csv com o motivo.
"""
import re
import unicodedata

import pandas as pd

NI = "NÃO INFORMADO"
DATA_MIN, DATA_MAX = pd.Timestamp("2017-01-01"), pd.Timestamp("2024-12-31")

# ---------------------------------------------------------------- dicionários
# COD_CIOD traz o MEIO EMPREGADO (ex.: "A01A - ARMA DE FOGO"), não um código de ocorrência.
MEIO_POR_CODIGO = {"A01A": "ARMA DE FOGO", "A01B": "ARMA BRANCA", "A01C": "OUTROS MEIOS"}

# CUTIS mistura siglas (P, B, N) e nomes por extenso (Parda, Branca, Negra).
# Premissa: "N"/"Negra" corresponde à categoria PRETA do IBGE, pois a base registra
# "Parda" separadamente. Confirmar com a documentação da SESP-ES.
RACA_COR = {
    "P": "PARDA", "PARDA": "PARDA",
    "B": "BRANCA", "BRANCA": "BRANCA",
    "N": "PRETA", "NEGRA": "PRETA", "PRETA": "PRETA",
    "A": "AMARELA", "AMARELA": "AMARELA",
    "I": "INDÍGENA", "INDIGENA": "INDÍGENA",
    "INDETERMINADA": NI, "IGNORADA": NI, "": NI,
}

FEMINICIDIO = {"FEMINICIDIO": True, "HOMICIDIO DOLOSO": False}

TIPO_LOCAL = {
    "VIA PUBLICA": "VIA PÚBLICA",
    "RESIDENCIA": "RESIDÊNCIA",
    "DOMICILIO": "RESIDÊNCIA",
    "ESTABELECIMENTO COMERCIAL": "ESTABELECIMENTO COMERCIAL",
    "TERRENO BALDIO": "TERRENO BALDIO / MATA",
    "TERRENO BALDIO / CONSTRUCAO / MATA": "TERRENO BALDIO / MATA",
    "FLORESTA": "TERRENO BALDIO / MATA",
    "ZONA RURAL": "ZONA RURAL",
    "RIO/LAGO/LAGOA/REPRESSA": "CURSO D'ÁGUA / REPRESA",
    "LAGO / LAGOA / REPRESA": "CURSO D'ÁGUA / REPRESA",
    "CURSO D'AGUA": "CURSO D'ÁGUA / REPRESA",
    "ESCOLA": "OUTROS", "PRACA": "OUTROS", "VEICULO": "OUTROS",
    "TEMPLOS RELIGIOSOS": "OUTROS", "OUTROS LOCAIS": "OUTROS",
    "NAO INFORMADO": NI, "": NI,
}

GRUPO_RELACAO = {
    "MARIDO": "PARCEIRO ÍNTIMO", "COMPANHEIRO": "PARCEIRO ÍNTIMO", "NAMORADO": "PARCEIRO ÍNTIMO",
    "EX-MARIDO": "EX-PARCEIRO", "EX-COMPANHEIRO": "EX-PARCEIRO", "EX-NAMORADO": "EX-PARCEIRO",
    "PAI": "FAMILIAR", "PADRASTO": "FAMILIAR", "FILHO": "FAMILIAR", "FILHA": "FAMILIAR",
    "CUNHADO": "FAMILIAR", "PARENTE": "FAMILIAR",
    "CONHECIDO": "CONHECIDO",
    "NAO INFORMADO": NI, "": NI,
}

COLUNAS_SAIDA = [
    "id_origem", "data_obito", "hora_fato", "idade_vitima", "municipio", "bairro",
    "meio_empregado", "raca_cor", "relacao_vitima_autor", "feminicidio", "tipo_local",
    "ano", "mes", "dia_semana", "periodo_dia", "faixa_etaria", "raca_negra", "grupo_relacao",
]


# ---------------------------------------------------------------- utilitários
def _limpar(txt: str) -> str:
    """Remove espaços extras e coloca em maiúsculas (mantém acentos)."""
    return re.sub(r"\s+", " ", str(txt)).strip().upper()


def _chave(txt: str) -> str:
    """Versão sem acentos, usada só para procurar nos dicionários."""
    t = unicodedata.normalize("NFKD", _limpar(txt))
    return "".join(c for c in t if not unicodedata.combining(c))


def _mapear(serie: pd.Series, dicionario: dict, nome: str, padrao=None) -> pd.Series:
    chaves = serie.map(_chave)
    desconhecidos = sorted(set(chaves) - set(dicionario))
    if desconhecidos:
        print(f"[transform] AVISO {nome}: valores sem mapeamento {desconhecidos}")
    return chaves.map(lambda k: dicionario.get(k, padrao if padrao is not None else _limpar(k)))


def _faixa_etaria(idade) -> str:
    if pd.isna(idade):
        return NI
    if idade <= 17:
        return "0-17"
    if idade <= 29:
        return "18-29"
    if idade <= 39:
        return "30-39"
    if idade <= 59:
        return "40-59"
    return "60+"


def _periodo_dia(hora) -> str:
    if pd.isna(hora):
        return NI
    h = hora.hour
    if h < 6:
        return "MADRUGADA"
    if h < 12:
        return "MANHÃ"
    if h < 18:
        return "TARDE"
    return "NOITE"


# ---------------------------------------------------------------- pipeline
def transformar(bruto: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (dados_tratados, rejeitados)."""
    df = pd.DataFrame(index=bruto.index)

    df["id_origem"] = pd.to_numeric(bruto["_id"], errors="coerce").astype("Int64")
    df["data_obito"] = pd.to_datetime(bruto["DAT_OBT"], errors="coerce").dt.normalize()
    df["hora_fato"] = pd.to_datetime(bruto["HOR_FAT"], format="%H:%M:%S", errors="coerce").dt.time

    idade = pd.to_numeric(bruto["IDD_VIT"], errors="coerce")
    df["idade_vitima"] = idade.where(idade.between(0, 110)).astype("Int64")

    df["municipio"] = bruto["MUN_OBT"].map(_limpar)
    df["bairro"] = bruto["BAI_OBT"].map(_limpar).replace("", NI)

    codigo = bruto["COD_CIOD"].str.extract(r"^\s*(A\d{2}[A-Z])", expand=False)
    df["meio_empregado"] = codigo.map(MEIO_POR_CODIGO).fillna(NI)

    df["raca_cor"] = _mapear(bruto["CUTIS"], RACA_COR, "CUTIS", padrao=NI)
    df["relacao_vitima_autor"] = bruto["REL VIT AUT"].map(_limpar).replace("", NI)
    df["feminicidio"] = bruto["FEMINICIDIO"].map(_chave).map(FEMINICIDIO).astype("boolean")
    df["tipo_local"] = _mapear(bruto["TIPO LOCAL"], TIPO_LOCAL, "TIPO LOCAL")

    # atributos derivados
    df["ano"] = df["data_obito"].dt.year.astype("Int64")
    df["mes"] = df["data_obito"].dt.month.astype("Int64")
    df["dia_semana"] = (df["data_obito"].dt.dayofweek + 1).astype("Int64")  # 1=segunda ... 7=domingo
    df["periodo_dia"] = df["hora_fato"].map(_periodo_dia)
    df["faixa_etaria"] = df["idade_vitima"].map(_faixa_etaria)
    df["raca_negra"] = df["raca_cor"].map({"PRETA": True, "PARDA": True, "BRANCA": False,
                                           "AMARELA": False, "INDÍGENA": False}).astype("boolean")
    df["grupo_relacao"] = _mapear(df["relacao_vitima_autor"], GRUPO_RELACAO, "REL VIT AUT", padrao="OUTRO")

    # ------------------------------------------------------------ validação
    motivos = pd.Series("", index=df.index)
    motivos[df["data_obito"].isna()] += "data inválida; "
    motivos[~df["data_obito"].between(DATA_MIN, DATA_MAX) & df["data_obito"].notna()] += "fora do recorte 2017-2024; "
    motivos[bruto["SEX_VIT"].map(_limpar) != "F"] += "sexo diferente de F; "
    motivos[df["feminicidio"].isna()] += "classificação de feminicídio desconhecida; "
    motivos[df["id_origem"].isna()] += "_id inválido; "

    rejeitar = motivos != ""
    rejeitados = bruto[rejeitar].assign(motivo=motivos[rejeitar].str.rstrip("; "))
    tratados = df.loc[~rejeitar, COLUNAS_SAIDA].copy()
    tratados["data_obito"] = tratados["data_obito"].dt.date

    print(f"[transform] {len(tratados)} registros válidos | {len(rejeitados)} rejeitados")
    return tratados, rejeitados
