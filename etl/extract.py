"""Extração: lê os dois arquivos originais sem alterar nenhum valor.

- Planilha XLSX da SSP-BA: vítimas por município e tipo de crime.
- PDF do Anexo II: Territórios de Identidade e seus municípios.

Limpeza e conversão de tipos acontecem só no transform.
"""
import io
import re
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber


def _abrir_xlsx(caminho: Path):
    """A planilha da SSP-BA grava os caminhos internos do zip com '\\' em vez de '/',
    e o openpyxl não encontra as abas. O arquivo é reempacotado em memória; o original
    em data/raw/ não é modificado."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(caminho) as origem, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as destino:
        for item in origem.infolist():
            destino.writestr(item.filename.replace("\\", "/"), origem.read(item))
    buffer.seek(0)
    return openpyxl.load_workbook(buffer, data_only=True)


def extrair_vitimas(caminho: str | Path) -> tuple[pd.DataFrame, pd.Series, int]:
    """Retorna (linhas de municípios, linha Total, ano de referência).

    A planilha tem título nas primeiras linhas, o cabeçalho na linha que começa com
    'ID', um município por linha, a linha 'Total' e um rodapé com notas.
    """
    caminho = Path(caminho)
    linhas = list(_abrir_xlsx(caminho).worksheets[0].iter_rows(values_only=True))

    i_cab = next(i for i, l in enumerate(linhas) if str(l[0]).strip().upper() == "ID")
    i_total = next(i for i, l in enumerate(linhas) if str(l[0]).strip().upper() == "TOTAL")

    titulo = " ".join(str(l[0]) for l in linhas[:i_cab] if l[0])
    achado = re.search(r"\b(20\d{2})\b", titulo)
    if not achado:
        raise ValueError(f"Ano de referência não encontrado no título: {titulo!r}")
    ano = int(achado.group(1))

    colunas = [str(c).strip() for c in linhas[i_cab]]
    bruto = pd.DataFrame(linhas[i_cab + 1:i_total], columns=colunas)
    totais = pd.Series(linhas[i_total][2:], index=colunas[2:], name="Total")

    print(f"[extract] {caminho.name}: {len(bruto)} municípios x {len(colunas) - 2} tipos de crime | ano {ano}")
    return bruto, totais, ano


def extrair_territorios(caminho: str | Path) -> pd.DataFrame:
    """Retorna uma linha por território: numero, territorio, municipios (texto original)."""
    caminho = Path(caminho)
    registros = []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            for tabela in pagina.extract_tables():
                for linha in tabela:
                    celulas = [(c or "").strip() for c in linha]
                    # a tabela de interesse tem 3 colunas: nº, território, municípios
                    if len(celulas) >= 3 and celulas[0].isdigit() and celulas[2]:
                        registros.append(celulas[:3])

    territorios = pd.DataFrame(registros, columns=["numero", "territorio", "municipios"])
    print(f"[extract] {caminho.name}: {len(territorios)} territórios")
    return territorios
