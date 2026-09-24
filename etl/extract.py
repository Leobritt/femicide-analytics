"""Extração: lê o CSV bruto da SESP-ES sem alterar nenhum valor.

Tudo é lido como texto (dtype=str). A conversão de tipos acontece só no transform.
"""
import csv
from pathlib import Path

import pandas as pd

COLUNAS_ESPERADAS = [
    "_id", "DAT_OBT", "HOR_FAT", "SEX_VIT", "IDD_VIT", "MUN_OBT", "BAI_OBT",
    "COD_CIOD", "CUTIS", "REL VIT AUT", "FEMINICIDIO", "TIPO LOCAL",
]


def _detectar_encoding(caminho: Path) -> str:
    """UTF-8 (com ou sem BOM) e, se falhar, Latin-1."""
    try:
        caminho.read_text(encoding="utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "latin-1"


def _detectar_separador(caminho: Path, encoding: str) -> str:
    amostra = caminho.read_text(encoding=encoding)[:5000]
    return csv.Sniffer().sniff(amostra, delimiters=",;").delimiter


def extrair(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    encoding = _detectar_encoding(caminho)
    sep = _detectar_separador(caminho, encoding)

    df = pd.read_csv(caminho, sep=sep, encoding=encoding, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]

    faltando = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes no CSV: {faltando}")

    print(f"[extract] {caminho.name}: {len(df)} linhas | separador='{sep}' | encoding={encoding}")
    return df
