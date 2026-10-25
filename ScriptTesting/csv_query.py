from argparse import ArgumentParser
from pathlib import Path

import duckdb

PASTA_DADOS = Path(
    "/run/media/gabrielwwelter/FCA0-FCE6/Chuvas TCC/"
    "Testes Iniciais/2020"
)
CSV_FONTE = PASTA_DADOS / "data.csv"
CSV_DESTINO_CHUVA = PASTA_DADOS / "data_resultado_consulta.csv"
CSV_DESTINO_MENSAL = PASTA_DADOS / "data_precipitacao_mensal.csv"


def executar_consulta(
    numero: int, csv_file: Path, resultado_file: Path
) -> None:
    if not csv_file.is_file():
        raise SystemExit(f"Arquivo CSV não encontrado: {csv_file}")

    dados = duckdb.read_csv(str(csv_file))
    if numero == 1:
        resultado = dados.filter("tp > 0")
    else:
        resultado = (
            dados.project(
                "latitude, longitude, "
                "strftime(valid_time, '%Y-%m') AS mes, tp"
            )
            .aggregate(
                "latitude, longitude, mes, sum(tp) AS tp_total",
                "latitude, longitude, mes",
            )
            .order("latitude, longitude, mes")
        )

    resultado.write_csv(str(resultado_file), header=True)
    print(f"Consulta salva em: {resultado_file}")


def main() -> None:
    parser = ArgumentParser(description="Executa consultas sobre o CSV meteorológico.")
    parser.add_argument(
        "consulta",
        type=int,
        choices=(1, 2),
        help="1: registros com tp > 0; 2: precipitação mensal por coordenada",
    )
    parser.add_argument(
        "entrada",
        nargs="?",
        type=Path,
        default=CSV_FONTE,
        help="CSV gerado a partir do GRIB",
    )
    parser.add_argument(
        "saida",
        nargs="?",
        type=Path,
        help="CSV de saída; se omitido, usa o caminho padrão da consulta",
    )
    args = parser.parse_args()

    saida_padrao = (
        CSV_DESTINO_CHUVA if args.consulta == 1 else CSV_DESTINO_MENSAL
    )
    resultado_file = args.saida or saida_padrao
    resultado_file.parent.mkdir(parents=True, exist_ok=True)
    executar_consulta(args.consulta, args.entrada, resultado_file)


if __name__ == "__main__":
    main()
