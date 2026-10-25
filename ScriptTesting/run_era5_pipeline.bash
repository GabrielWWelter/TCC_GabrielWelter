#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

SSD_MOUNT="${SSD_MOUNT:-/run/media/gabrielwwelter/FCA0-FCE6}"
ERA5_DATA_DIR="${ERA5_DATA_DIR:-$SSD_MOUNT/Chuvas TCC/ERA5}"

API_REQUEST="$SCRIPT_DIR/APIRequest.py"
AGGREGATOR="$SCRIPT_DIR/daily_aggregate.py"
CONVERTER_SOURCE="$SCRIPT_DIR/grib_to_csv.cpp"
CONVERTER="$SCRIPT_DIR/grib_to_csv"

DEFAULT_YEARS=(2021 2022 2023 2024 2025)


log() {
    printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}


fail() {
    printf 'Erro: %s\n' "$*" >&2
    exit 1
}


show_help() {
    cat <<EOF
Uso:
  bash ScriptTesting/run_era5_pipeline.bash [ANO ...]

Sem argumentos, processa 2021, 2022, 2023, 2024 e 2025.

Exemplos:
  bash ScriptTesting/run_era5_pipeline.bash
  bash ScriptTesting/run_era5_pipeline.bash 2021
  bash ScriptTesting/run_era5_pipeline.bash 2022 2023

Variaveis de ambiente opcionais:
  SSD_MOUNT       Ponto de montagem do SSD.
  ERA5_DATA_DIR   Pasta base dos dados ERA5.
EOF
}


validate_year() {
    local year="$1"
    [[ "$year" =~ ^202[1-5]$ ]] || fail "ano invalido: $year (use 2021 a 2025)"
}


check_environment() {
    command -v python3 >/dev/null || fail "python3 nao encontrado"
    command -v g++ >/dev/null || fail "g++ nao encontrado"
    command -v pkg-config >/dev/null || fail "pkg-config nao encontrado"
    command -v findmnt >/dev/null || fail "findmnt nao encontrado"

    [[ -f "$API_REQUEST" ]] || fail "arquivo nao encontrado: $API_REQUEST"
    [[ -f "$AGGREGATOR" ]] || fail "arquivo nao encontrado: $AGGREGATOR"
    [[ -f "$CONVERTER_SOURCE" ]] || fail "arquivo nao encontrado: $CONVERTER_SOURCE"
    [[ -d "$SSD_MOUNT" ]] || fail "SSD nao montado em: $SSD_MOUNT"

    local mount_options
    mount_options="$(findmnt -no OPTIONS -T "$SSD_MOUNT")"
    if [[ ",$mount_options," != *,rw,* ]]; then
        fail "SSD montado sem permissao de escrita: $mount_options"
    fi

    mkdir -p "$ERA5_DATA_DIR"
}


compile_converter() {
    if [[ ! -x "$CONVERTER" || "$CONVERTER_SOURCE" -nt "$CONVERTER" ]]; then
        log "Compilando grib_to_csv"
        # A expansao da saida de pkg-config deve formar argumentos separados.
        # shellcheck disable=SC2046
        g++ -O3 -std=c++17 "$CONVERTER_SOURCE" \
            $(pkg-config --cflags --libs eccodes) \
            -o "$CONVERTER"
    else
        log "Conversor ja compilado e atualizado"
    fi
}


convert_grib() {
    local input_file="$1"
    local output_file="$2"

    [[ -s "$input_file" ]] || fail "GRIB ausente ou vazio: $input_file"

    if [[ -s "$output_file" ]]; then
        log "CSV horario existente, ignorando: $output_file"
        return
    fi

    log "Convertendo GRIB para CSV horario: $input_file"
    "$CONVERTER" "$input_file" "$output_file"
}


aggregate_daily() {
    local variable="$1"
    local input_file="$2"
    local output_file="$3"

    [[ -s "$input_file" ]] || fail "CSV horario ausente ou vazio: $input_file"

    if [[ -s "$output_file" ]]; then
        log "CSV diario existente, ignorando: $output_file"
        return
    fi

    local overwrite_args=()
    if [[ -e "$output_file" ]]; then
        overwrite_args=(--sobrescrever)
    fi

    log "Gerando CSV diario de $variable"
    python3 "$AGGREGATOR" \
        "$variable" \
        "$input_file" \
        "$output_file" \
        "${overwrite_args[@]}"
}


process_year() {
    local year="$1"

    local precipitation_grib
    local pressure_grib
    local precipitation_hourly
    local pressure_hourly
    local precipitation_daily
    local pressure_daily

    precipitation_grib="$ERA5_DATA_DIR/raw/precipitacao_total/hourly/$year/precipitacao_total_horaria_$year.grib"
    pressure_grib="$ERA5_DATA_DIR/raw/pressao_nivel_medio_mar/hourly/$year/pressao_nivel_medio_mar_horaria_$year.grib"

    precipitation_hourly="$ERA5_DATA_DIR/processed/precipitacao_total/hourly/$year/precipitacao_total_horaria_$year.csv"
    pressure_hourly="$ERA5_DATA_DIR/processed/pressao_nivel_medio_mar/hourly/$year/pressao_nivel_medio_mar_horaria_$year.csv"

    precipitation_daily="$ERA5_DATA_DIR/processed/precipitacao_total/daily/$year/precipitacao_total_diaria_$year.csv"
    pressure_daily="$ERA5_DATA_DIR/processed/pressao_nivel_medio_mar/daily/$year/pressao_media_diaria_$year.csv"

    log "Iniciando o ano $year"
    python3 "$API_REQUEST" \
        --anos "$year" \
        --variaveis precipitacao pressao

    convert_grib "$precipitation_grib" "$precipitation_hourly"
    aggregate_daily precipitacao "$precipitation_hourly" "$precipitation_daily"

    convert_grib "$pressure_grib" "$pressure_hourly"
    aggregate_daily pressao "$pressure_hourly" "$pressure_daily"

    log "Ano $year concluido"
    du -h \
        "$precipitation_grib" \
        "$pressure_grib" \
        "$precipitation_hourly" \
        "$pressure_hourly" \
        "$precipitation_daily" \
        "$pressure_daily"
}


main() {
    if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
        show_help
        exit 0
    fi

    local years=("${DEFAULT_YEARS[@]}")
    if (( $# > 0 )); then
        years=("$@")
    fi

    local year
    for year in "${years[@]}"; do
        validate_year "$year"
    done

    check_environment
    compile_converter

    log "Pasta ERA5: $ERA5_DATA_DIR"
    df -h "$SSD_MOUNT"

    for year in "${years[@]}"; do
        process_year "$year"
    done

    log "Pipeline concluido para: ${years[*]}"
}


trap 'printf "\nFalha na linha %s. Execute novamente o mesmo comando para retomar.\n" "$LINENO" >&2' ERR

main "$@"
