"""Extração: lê os arquivos originais sem alterar nenhum valor.

- Planilha XLSX da SSP-BA: vítimas por município e tipo de crime.
- PDF do Anexo II: Territórios de Identidade e seus municípios.
- CSV do IBGE Cidades: população e área territorial de cada município.
- JSON da API de agregados do IBGE (Censo 2022): mulheres residentes por cor ou raça.

Limpeza e conversão de tipos acontecem só no transform.
"""
import csv
import html
import io
import json
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


# Colunas do IBGE Cidades usadas no projeto: prefixo do cabeçalho -> (nome da coluna, ano esperado).
# O ano vem entre colchetes no cabeçalho; se um export novo trouxer outro ano, a extração falha
# para que os nomes das colunas no banco não fiquem com o ano errado.
COLUNAS_IBGE = {
    "Código": ("codigo_ibge7", None),
    "Município": ("nome_ibge", None),
    "Área Territorial": ("area_km2", 2025),
    "População no último censo": ("populacao_censo_2022", 2022),
    "População estimada": ("populacao_estimada_2026", 2026),
}


def extrair_ibge(caminho: str | Path) -> pd.DataFrame:
    """Retorna uma linha por município com as colunas de COLUNAS_IBGE (texto original).

    O export do IBGE Cidades vem com entidades HTML no texto (ex.: 'Munic&iacute;pio'),
    uma linha de título antes do cabeçalho, vírgula sobrando no fim de cada linha e um
    rodapé com notas e fontes. Só as linhas com código numérico são municípios.
    """
    caminho = Path(caminho)
    texto = html.unescape(caminho.read_text(encoding="utf-8"))
    linhas = list(csv.reader(io.StringIO(texto)))

    i_cab = next(i for i, l in enumerate(linhas) if l and l[0].startswith("Município"))
    cabecalho = [c.strip() for c in linhas[i_cab]]

    indices, nomes = [], []
    for prefixo, (nome, ano) in COLUNAS_IBGE.items():
        achadas = [i for i, c in enumerate(cabecalho) if c.startswith(prefixo)]
        if len(achadas) != 1:
            raise ValueError(f"Coluna '{prefixo}' não encontrada (ou repetida) no CSV do IBGE")
        if ano is not None and f"[{ano}]" not in cabecalho[achadas[0]]:
            raise ValueError(f"Ano diferente do esperado ({ano}) na coluna: {cabecalho[achadas[0]]!r}")
        indices.append(achadas[0])
        nomes.append(nome)

    i_cod = indices[nomes.index("codigo_ibge7")]
    registros = [[l[i].strip() for i in indices] for l in linhas[i_cab + 1:]
                 if len(l) > i_cod and l[i_cod].strip().isdigit()]

    ibge = pd.DataFrame(registros, columns=nomes)
    print(f"[extract] {caminho.name}: {len(ibge)} municípios (IBGE Cidades)")
    return ibge


# Tabela 9606 do Censo 2022 (API de agregados do IBGE), já filtrada na consulta para
# sexo = Mulheres e idade = Total. Uma categoria de cor ou raça por resultado.
CATEGORIAS_COR_RACA = ["Total", "Branca", "Preta", "Parda", "Amarela", "Indígena"]


def extrair_cor_raca(caminho: str | Path) -> pd.DataFrame:
    """Retorna uma linha por município com a população feminina de cada cor ou raça (texto original).

    O JSON tem o formato da API de agregados: [variável] -> resultados (um por combinação de
    categorias) -> séries (uma por município). O IBGE usa '-' para zero; a conversão fica no
    transform. A consulta precisa ter sido feita só para mulheres e todas as idades.
    """
    caminho = Path(caminho)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if len(dados) != 1 or str(dados[0]["id"]) != "93":
        raise ValueError("JSON do IBGE: esperada só a variável 93 (população residente)")

    linhas: dict[str, dict[str, str]] = {}
    for resultado in dados[0]["resultados"]:
        classes = {c["id"]: next(iter(c["categoria"].values())) for c in resultado["classificacoes"]}
        if classes.get("2") != "Mulheres" or classes.get("287") != "Total":
            raise ValueError(f"JSON do IBGE: recorte inesperado (sexo/idade): {classes}")
        categoria = classes["86"]
        for serie in resultado["series"]:
            codigo = serie["localidade"]["id"]
            linhas.setdefault(codigo, {"codigo_ibge7": codigo})[categoria] = serie["serie"]["2022"]

    cor_raca = pd.DataFrame(list(linhas.values()))
    faltando = set(CATEGORIAS_COR_RACA) - set(cor_raca.columns)
    if faltando:
        raise ValueError(f"JSON do IBGE: categorias de cor ou raça ausentes: {sorted(faltando)}")
    print(f"[extract] {caminho.name}: {len(cor_raca)} municípios (Censo 2022, mulheres por cor ou raça)")
    return cor_raca[["codigo_ibge7", *CATEGORIAS_COR_RACA]]
