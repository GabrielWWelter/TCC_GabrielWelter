from argparse import ArgumentParser
from pathlib import Path

import duckdb
import geobr
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SSD_BASE = Path("/run/media/gabrielwwelter/FCA0-FCE6/Chuvas TCC/ERA5")
PRECIPITACAO_2020 = (
    SSD_BASE
    / "processed/precipitacao_total/daily/2020"
    / "precipitacao_total_diaria_2020.csv"
)
RESULTADOS = Path(__file__).resolve().parent.parent / "Results" / "maps"


def carregar_precipitacao_anual(
    csv_file: Path, ano: int
) -> tuple[pd.DataFrame, str, str, int]:
    if not csv_file.is_file():
        raise SystemExit(f"CSV diario nao encontrado: {csv_file}")

    conexao = duckdb.connect()
    try:
        dados = conexao.read_csv(str(csv_file), header=True)
        periodo = (
            dados.filter(f"complete AND year(data) = {ano}")
            .aggregate(
                "min(data) AS inicio, max(data) AS fim, "
                "count(DISTINCT data) AS dias"
            )
            .fetchone()
        )
        resultado = (
            dados.filter(f"complete AND year(data) = {ano}")
            .aggregate(
                "latitude, longitude, "
                "sum(precipitacao_mm) AS precipitacao_mm",
                "latitude, longitude",
            )
            .df()
        )
    finally:
        conexao.close()

    if resultado.empty or periodo[0] is None:
        raise SystemExit(f"Nao ha dias completos para o ano {ano} em {csv_file}")

    return resultado, str(periodo[0]), str(periodo[1]), int(periodo[2])


def mascarar_fora_do_brasil(
    dados: pd.DataFrame, brasil: gpd.GeoDataFrame
) -> pd.DataFrame:
    pontos = gpd.GeoSeries(
        gpd.points_from_xy(dados["longitude"], dados["latitude"]),
        crs="EPSG:4326",
    )
    territorio = brasil.to_crs("EPSG:4326").geometry.union_all()
    dentro = pontos.within(territorio) | pontos.touches(territorio)

    resultado = dados.copy()
    resultado.loc[~dentro.to_numpy(), "precipitacao_mm"] = np.nan
    return resultado


def criar_grade(dados: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grade = dados.pivot(
        index="latitude",
        columns="longitude",
        values="precipitacao_mm",
    ).sort_index().sort_index(axis=1)

    return (
        grade.columns.to_numpy(),
        grade.index.to_numpy(),
        grade.to_numpy(),
    )


def plotar_precipitacao_anual(
    csv_file: Path,
    output_file: Path,
    ano: int,
    mostrar: bool = False,
) -> None:
    dados, inicio, fim, dias = carregar_precipitacao_anual(csv_file, ano)

    brasil = geobr.read_country(year=2020, show_progress=False).to_crs(
        "EPSG:4326"
    )
    estados = geobr.read_state(year=2020, show_progress=False).to_crs(
        "EPSG:4326"
    )

    dados = mascarar_fora_do_brasil(dados, brasil)
    longitudes, latitudes, precipitacao = criar_grade(dados)

    fig, ax = plt.subplots(figsize=(10, 10))
    mapa = ax.pcolormesh(
        longitudes,
        latitudes,
        precipitacao,
        shading="auto",
        cmap="YlGnBu",
    )

    estados.boundary.plot(
        ax=ax,
        color="#555555",
        linewidth=0.35,
        zorder=2,
    )
    brasil.boundary.plot(
        ax=ax,
        color="black",
        linewidth=0.9,
        zorder=3,
    )

    barra = fig.colorbar(mapa, ax=ax, shrink=0.78, pad=0.025)
    barra.set_label("Precipitacao acumulada (mm)")

    ax.set_title(
        f"Precipitacao acumulada no Brasil - {ano}\n"
        f"{inicio} a {fim} ({dias} dias completos)",
        fontsize=14,
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    ax.grid(
        visible=True,
        color="#999999",
        linestyle=":",
        linewidth=0.4,
        alpha=0.5,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, dpi=300, bbox_inches="tight")
    print(f"Mapa salvo em: {output_file}")

    if mostrar:
        plt.show()
    plt.close(fig)


def main() -> None:
    parser = ArgumentParser(
        description="Produz mapas a partir dos CSVs diarios do ERA5."
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=PRECIPITACAO_2020,
        help=f"CSV diario de precipitacao (padrao: {PRECIPITACAO_2020}).",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=RESULTADOS / "precipitacao_acumulada_brasil_2020.png",
        help="Arquivo PNG que sera produzido.",
    )
    parser.add_argument(
        "--ano",
        type=int,
        default=2020,
        help="Ano que sera agregado e representado (padrao: 2020).",
    )
    parser.add_argument(
        "--mostrar",
        action="store_true",
        help="Exibe a figura em uma janela alem de salva-la.",
    )
    args = parser.parse_args()

    plotar_precipitacao_anual(
        args.entrada,
        args.saida,
        args.ano,
        args.mostrar,
    )


if __name__ == "__main__":
    main()
