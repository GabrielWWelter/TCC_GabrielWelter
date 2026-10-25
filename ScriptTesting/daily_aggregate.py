from argparse import ArgumentParser
from pathlib import Path

import duckdb


COLUNAS_NECESSARIAS = {"valid_time", "latitude", "longitude", "tp"}


def agregar_por_dia(
    variavel: str,
    csv_entrada: Path,
    csv_saida: Path,
    sobrescrever: bool = False,
) -> None:
    if not csv_entrada.is_file():
        raise SystemExit(f"CSV de entrada nao encontrado: {csv_entrada}")

    if csv_entrada.resolve() == csv_saida.resolve():
        raise SystemExit("Os arquivos de entrada e saida devem ser diferentes.")

    if csv_saida.exists() and not sobrescrever:
        raise SystemExit(
            f"Arquivo de saida ja existe: {csv_saida}. "
            "Use --sobrescrever para substitui-lo."
        )

    csv_saida.parent.mkdir(parents=True, exist_ok=True)
    csv_temporario = csv_saida.with_suffix(csv_saida.suffix + ".part")

    conexao = duckdb.connect()
    try:
        dados = conexao.read_csv(str(csv_entrada), header=True)
        colunas_ausentes = COLUNAS_NECESSARIAS.difference(dados.columns)
        if colunas_ausentes:
            nomes = ", ".join(sorted(colunas_ausentes))
            raise SystemExit(f"Colunas ausentes no CSV: {nomes}")

        if variavel == "precipitacao":
            # A acumulacao valida as 00 UTC representa a hora que termina
            # naquele instante e, portanto, pertence ao dia anterior.
            dados_com_data = dados.project(
                "CAST(CAST(valid_time AS TIMESTAMP) - INTERVAL 1 MICROSECOND "
                "AS DATE) AS data, latitude, longitude, tp"
            )
            resultado = dados_com_data.aggregate(
                "data, latitude, longitude, "
                "CAST(count(tp) AS INTEGER) AS sample_count, "
                "count(tp) = 24 AS complete, "
                "sum(tp) * 1000 AS precipitacao_mm",
                "data, latitude, longitude",
            )
        else:
            dados_com_data = dados.project(
                "CAST(valid_time AS DATE) AS data, latitude, longitude, tp"
            )
            resultado = dados_com_data.aggregate(
                "data, latitude, longitude, "
                "CAST(count(tp) AS INTEGER) AS sample_count, "
                "count(tp) = 24 AS complete, "
                "avg(tp) / 100 AS pressao_media_hpa",
                "data, latitude, longitude",
            )

        (
            resultado.order("data, latitude DESC, longitude")
            .write_csv(str(csv_temporario), header=True)
        )
        csv_temporario.replace(csv_saida)
    finally:
        conexao.close()

    print(f"Agregacao diaria concluida: {csv_saida}")


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Agrega por dia o CSV horario produzido por grib_to_csv. "
            "Precipitacao e somada em mm; pressao e calculada pela media em hPa."
        )
    )
    parser.add_argument(
        "variavel",
        choices=("precipitacao", "pressao"),
        help="Tipo da variavel contida no GRIB/CSV.",
    )
    parser.add_argument(
        "entrada",
        type=Path,
        help="CSV horario produzido pelo conversor grib_to_csv.",
    )
    parser.add_argument(
        "saida",
        nargs="?",
        type=Path,
        help=(
            "CSV diario de saida. Quando omitido, acrescenta '_diario' "
            "ao nome do arquivo de entrada."
        ),
    )
    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Substitui o CSV de saida caso ele ja exista.",
    )
    args = parser.parse_args()

    saida = args.saida or args.entrada.with_name(
        f"{args.entrada.stem}_diario.csv"
    )
    agregar_por_dia(
        args.variavel,
        args.entrada,
        saida,
        args.sobrescrever,
    )


if __name__ == "__main__":
    main()
