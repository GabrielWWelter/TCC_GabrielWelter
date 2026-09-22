from argparse import ArgumentParser
from pathlib import Path

import duckdb as duck
import pandas as pd
import xarray as xr


def converter_grib(grib_file: Path, csv_file: Path) -> None:
    if not grib_file.is_file():
        raise SystemExit(f"Arquivo GRIB não encontrado: {grib_file}")

    datasets = []
    try:
        datasets = [
            xr.open_dataset(
                grib_file, engine="cfgrib", backend_kwargs={"indexpath": ""}
            )
        ]
    except Exception as error:
        # Um GRIB pode conter níveis/coordenadas incompatíveis. Nesse caso,
        # preserve todos os dados separando-os em datasets homogêneos.
        from cfgrib import open_datasets

        print(f"GRIB com grupos distintos ({error}). Separando os grupos...")
        datasets = open_datasets(str(grib_file), backend_kwargs={"indexpath": ""})

    if not datasets:
        raise SystemExit(f"Nenhum dado foi encontrado em {grib_file}")

    frames = []
    try:
        for numero, dataset in enumerate(datasets):
            frame = dataset.to_dataframe().reset_index()
            frame.insert(0, "grupo_grib", numero)
            frames.append(frame)

        pd.concat(frames, ignore_index=True, sort=False).to_csv(csv_file, index=False)
    finally:
        for dataset in datasets:
            dataset.close()

    print(f"Conversão concluída: {grib_file} -> {csv_file}")


def main() -> None:
    pasta_repositorio = Path(__file__).resolve().parent.parent
    parser = ArgumentParser(description="Converte arquivos GRIB em CSV.")
    parser.add_argument(
        "entrada",
        nargs="?",
        type=Path,
        default=Path("/run/media/gabrielwwelter/FCA0-FCE6/RainVolume"),
        help="Arquivo GRIB ou pasta que contém arquivos GRIB",
    )
    parser.add_argument(
        "saida",
        nargs="?",
        type=Path,
        default=pasta_repositorio / "Results",
        help="Pasta onde os CSVs serão salvos",
    )
    args = parser.parse_args()

    if args.entrada.is_file():
        arquivos = [args.entrada]
    elif args.entrada.is_dir():
        arquivos = sorted(
            arquivo
            for arquivo in args.entrada.iterdir()
            if arquivo.is_file()
            and arquivo.suffix.lower() in {".grib", ".grb", ".grib2"}
        )
    else:
        raise SystemExit(f"Entrada não encontrada: {args.entrada}")

    if not arquivos:
        raise SystemExit(f"Nenhum arquivo GRIB encontrado em: {args.entrada}")

    args.saida.mkdir(parents=True, exist_ok=True)
    for grib_file in arquivos:
        csv_file = args.saida / f"{grib_file.stem}.csv"
        consulta_file = args.saida / f"{grib_file.stem}_resultado_consulta.csv"
        converter_grib(grib_file, csv_file)
        duck.read_csv(str(csv_file)).filter("tp > 0").df().to_csv(
            consulta_file, index=False
        )
        print(f"Consulta salva em: {consulta_file}")


if __name__ == "__main__":
    main()
