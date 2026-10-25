from argparse import ArgumentParser
from pathlib import Path

import cdsapi


DATASET = "reanalysis-era5-single-levels"
ANOS_DISPONIVEIS = tuple(range(2020, 2026))
MESES = [f"{mes:02d}" for mes in range(1, 13)]
DIAS = [f"{dia:02d}" for dia in range(1, 32)]
HORAS = [f"{hora:02d}:00" for hora in range(24)]

# O CDS espera a area na ordem: norte, oeste, sul, leste.
# Os limites foram arredondados para a grade de 0,25 grau do ERA5 e cobrem
# toda a extensao territorial do Brasil.
AREA_BRASIL = [6, -74, -34, -34]

SSD_MOUNT = Path("/run/media/gabrielwwelter/FCA0-FCE6")
DESTINO_PADRAO = SSD_MOUNT / "Chuvas TCC" / "ERA5"

VARIAVEIS = {
    "precipitacao": {
        "nome_cds": "total_precipitation",
        "pasta": Path("raw/precipitacao_total/hourly"),
        "prefixo": "precipitacao_total_horaria",
    },
    "pressao": {
        "nome_cds": "mean_sea_level_pressure",
        "pasta": Path("raw/pressao_nivel_medio_mar/hourly"),
        "prefixo": "pressao_nivel_medio_mar_horaria",
    },
}


def criar_requisicao(
    ano: int, configuracao: dict[str, object]
) -> dict[str, object]:
    return {
        "product_type": ["reanalysis"],
        "variable": [configuracao["nome_cds"]],
        "year": [str(ano)],
        "month": MESES,
        "day": DIAS,
        "time": HORAS,
        "data_format": "grib",
        "download_format": "unarchived",
        "area": AREA_BRASIL,
    }


def baixar_variavel(
    client: cdsapi.Client,
    destino_base: Path,
    nome: str,
    ano: int,
    sobrescrever: bool,
) -> None:
    configuracao = VARIAVEIS[nome]
    pasta_ano = destino_base / configuracao["pasta"] / str(ano)
    arquivo = pasta_ano / f"{configuracao['prefixo']}_{ano}.grib"

    if arquivo.is_file() and arquivo.stat().st_size > 0 and not sobrescrever:
        print(f"Arquivo existente, ignorando: {arquivo}")
        return

    pasta_ano.mkdir(parents=True, exist_ok=True)
    arquivo_temporario = arquivo.with_suffix(".grib.part")
    requisicao = criar_requisicao(ano, configuracao)

    print(f"Baixando {nome} de {ano}...")
    client.retrieve(DATASET, requisicao).download(str(arquivo_temporario))
    arquivo_temporario.replace(arquivo)
    print(f"Download concluido: {arquivo}")


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Baixa precipitacao total e pressao ao nivel medio do mar, em "
            "resolucao horaria, do ERA5 para o Brasil."
        )
    )
    parser.add_argument(
        "--anos",
        nargs="+",
        type=int,
        choices=ANOS_DISPONIVEIS,
        default=list(ANOS_DISPONIVEIS),
        help="Anos que serao baixados (padrao: 2020 a 2025).",
    )
    parser.add_argument(
        "--variaveis",
        nargs="+",
        choices=tuple(VARIAVEIS),
        default=list(VARIAVEIS),
        help="Variaveis que serao baixadas (padrao: ambas).",
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=DESTINO_PADRAO,
        help=f"Pasta base dos dados (padrao: {DESTINO_PADRAO}).",
    )
    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Baixa novamente arquivos que ja existem.",
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Mostra os arquivos planejados sem consultar o CDS.",
    )
    args = parser.parse_args()

    tarefas = [
        (variavel, ano)
        for ano in sorted(set(args.anos))
        for variavel in args.variaveis
    ]

    if args.simular:
        print(f"Dataset: {DATASET}")
        print(f"Area: {AREA_BRASIL} [norte, oeste, sul, leste]")
        for variavel, ano in tarefas:
            configuracao = VARIAVEIS[variavel]
            arquivo = (
                args.destino
                / configuracao["pasta"]
                / str(ano)
                / f"{configuracao['prefixo']}_{ano}.grib"
            )
            print(f"{variavel}: {ano} | hourly | {arquivo}")
        return

    # Impede que o caminho padrao seja criado no disco interno quando o SSD
    # externo nao estiver montado.
    if args.destino == DESTINO_PADRAO and not SSD_MOUNT.is_dir():
        raise SystemExit(
            f"SSD externo nao encontrado em {SSD_MOUNT}. "
            "Monte o dispositivo antes de iniciar os downloads."
        )

    client = cdsapi.Client()
    for variavel, ano in tarefas:
        baixar_variavel(
            client,
            args.destino,
            variavel,
            ano,
            args.sobrescrever,
        )


if __name__ == "__main__":
    main()
