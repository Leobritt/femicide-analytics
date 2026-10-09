"""Executa o pipeline completo: extract -> transform -> load.

Uso (na raiz do projeto):
    python -m etl.run_etl              # roda tudo e carrega no banco do .env
    python -m etl.run_etl --dry-run    # só gera data/processed/ e logs/, sem banco
"""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from etl.extract import extrair_territorios, extrair_vitimas
from etl.transform import transformar

RAIZ = Path(__file__).resolve().parent.parent
XLSX_VITIMAS = RAIZ / "data" / "raw" / "06_VIOLENCIA_CONTRA_MULHER_2025.xlsx"
PDF_TERRITORIOS = RAIZ / "data" / "raw" / "Anexo_II_-_Relacao_Territorios_de_Identidade.pdf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="não conecta ao banco")
    parser.add_argument("--vitimas", default=str(XLSX_VITIMAS), help="planilha XLSX da SSP-BA")
    parser.add_argument("--territorios", default=str(PDF_TERRITORIOS), help="PDF do Anexo II")
    args = parser.parse_args()

    vitimas_bruto, totais, ano = extrair_vitimas(args.vitimas)
    territorios_bruto = extrair_territorios(args.territorios)
    tabelas, correcoes = transformar(vitimas_bruto, totais, ano, territorios_bruto)

    processed = RAIZ / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (RAIZ / "logs").mkdir(exist_ok=True)
    tabelas["territorios"].to_csv(processed / "territorios_identidade.csv", index=False)
    tabelas["municipios"].to_csv(processed / "municipios.csv", index=False)
    tabelas["tipos_crime"].to_csv(processed / "tipos_crime.csv", index=False)
    tabelas["vitimas"].to_csv(processed / f"vitimas_municipio_crime_{ano}.csv", index=False)
    correcoes.to_csv(RAIZ / "logs" / "correcoes_territorios.csv", index=False)

    if args.dry_run:
        print("[run] --dry-run: carga no banco ignorada. Veja data/processed/ e logs/.")
        return

    load_dotenv(RAIZ / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida. Copie .env.example para .env e preencha.")

    from etl.load import carregar  # importado aqui para o --dry-run não exigir psycopg2
    carregar(tabelas, url)
    print("[run] Pipeline concluído.")


if __name__ == "__main__":
    main()
