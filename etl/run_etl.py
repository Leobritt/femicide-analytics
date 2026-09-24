"""Executa o pipeline completo: extract -> transform -> load.

Uso (na raiz do projeto):
    python -m etl.run_etl              # roda tudo e carrega no banco do .env
    python -m etl.run_etl --dry-run    # só gera data/processed/ e logs/, sem banco
"""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from etl.extract import extrair
from etl.transform import transformar

RAIZ = Path(__file__).resolve().parent.parent
CSV_BRUTO = RAIZ / "data" / "raw" / "homicidios_feminicidios_mulheres_2017_2024.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="não conecta ao banco")
    parser.add_argument("--arquivo", default=str(CSV_BRUTO), help="caminho do CSV bruto")
    args = parser.parse_args()

    bruto = extrair(args.arquivo)
    tratados, rejeitados = transformar(bruto)

    (RAIZ / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (RAIZ / "logs").mkdir(exist_ok=True)
    tratados.to_csv(RAIZ / "data" / "processed" / "ocorrencias_tratadas.csv", index=False)
    rejeitados.to_csv(RAIZ / "logs" / "rejeitados.csv", index=False)

    if args.dry_run:
        print("[run] --dry-run: carga no banco ignorada. Veja data/processed/ e logs/.")
        return

    load_dotenv(RAIZ / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida. Copie .env.example para .env e preencha.")

    from etl.load import carregar  # importado aqui para o --dry-run não exigir psycopg2
    carregar(tratados, url)
    print("[run] Pipeline concluído.")


if __name__ == "__main__":
    main()
