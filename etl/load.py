"""Carga: grava as quatro tabelas no PostgreSQL (Aiven) e recria as visões.

A carga é idempotente: as tabelas são esvaziadas e recarregadas numa única transação.
Se algo falhar, nada é alterado no banco.
"""
import io
from pathlib import Path

import pandas as pd
import psycopg2

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

# ordem de carga: dimensões antes do fato, por causa das chaves estrangeiras
DESTINO = [
    ("territorios", "dim_territorio"),
    ("municipios", "dim_municipio"),
    ("tipos_crime", "dim_tipo_crime"),
    ("vitimas", "fato_vitimas"),
]


def _copiar(cur, df: pd.DataFrame, tabela: str) -> None:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    cur.copy_expert(f"COPY {tabela} ({', '.join(df.columns)}) FROM STDIN WITH (FORMAT csv)", buffer)


def carregar(tabelas: dict[str, pd.DataFrame], database_url: str) -> None:
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute((SQL_DIR / "01_schema.sql").read_text(encoding="utf-8"))
            cur.execute("TRUNCATE fato_vitimas, dim_municipio, dim_tipo_crime, dim_territorio;")
            for nome, tabela in DESTINO:
                _copiar(cur, tabelas[nome], tabela)
            cur.execute((SQL_DIR / "02_agregacoes.sql").read_text(encoding="utf-8"))

            for _, tabela in DESTINO:
                cur.execute(f"SELECT COUNT(*) FROM {tabela};")
                print(f"[load] {tabela}: {cur.fetchone()[0]} linhas")
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()));")
            print(f"[load] tamanho do banco: {cur.fetchone()[0]}")
