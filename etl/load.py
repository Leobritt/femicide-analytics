"""Carga: grava os dados tratados no PostgreSQL (Aiven) e recria as agregações.

A carga é idempotente: a tabela é esvaziada (TRUNCATE) e recarregada numa única
transação. Se algo falhar, nada é alterado no banco.
"""
import io
from pathlib import Path

import pandas as pd
import psycopg2

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def carregar(df: pd.DataFrame, database_url: str) -> None:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)

    colunas = ", ".join(df.columns)
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute((SQL_DIR / "01_schema.sql").read_text(encoding="utf-8"))
            cur.execute("TRUNCATE ocorrencias;")
            cur.copy_expert(
                f"COPY ocorrencias ({colunas}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buffer,
            )
            cur.execute((SQL_DIR / "02_agregacoes.sql").read_text(encoding="utf-8"))
            cur.execute("SELECT COUNT(*), pg_size_pretty(pg_database_size(current_database())) FROM ocorrencias;")
            total, tamanho = cur.fetchone()
    print(f"[load] {total} registros em 'ocorrencias' | tamanho do banco: {tamanho}")
