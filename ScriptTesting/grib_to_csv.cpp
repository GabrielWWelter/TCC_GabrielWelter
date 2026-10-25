#include <eccodes.h>

#include <charconv>
#include <cstdio>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

constexpr char GRIB_PATH[] =
    "/run/media/gabrielwwelter/FCA0-FCE6/Chuvas TCC/"
    "Testes Iniciais/2020/data.grib";
constexpr char CSV_PATH[] =
    "/run/media/gabrielwwelter/FCA0-FCE6/Chuvas TCC/"
    "Testes Iniciais/2020/data.csv";
constexpr std::size_t BUFFER_SIZE = 16 * 1024 * 1024;

namespace fs = std::filesystem;

struct FileDeleter {
    void operator()(FILE* file) const {
        if (file) std::fclose(file);
    }
};
using File = std::unique_ptr<FILE, FileDeleter>;

struct GribDeleter {
    void operator()(codes_handle* handle) const { codes_handle_delete(handle); }
};
using Grib = std::unique_ptr<codes_handle, GribDeleter>;

long read_long(codes_handle* grib, const char* key, long fallback = 0) {
    long value = fallback;
    return codes_get_long(grib, key, &value) == CODES_SUCCESS ? value : fallback;
}

std::string read_string(codes_handle* grib, const char* key) {
    char value[64];
    std::size_t size = sizeof(value);
    if (codes_get_string(grib, key, value, &size) != CODES_SUCCESS) {
        throw std::runtime_error(std::string("Erro lendo ") + key);
    }
    return value;
}

void append_integer(std::string& buffer, long value) {
    char text[32];
    const auto [end, error] = std::to_chars(text, text + sizeof(text), value);
    if (error != std::errc{}) throw std::runtime_error("Erro formatando inteiro");
    buffer.append(text, end);
}

void append_number(std::string& buffer, double value) {
    char text[64];
    const auto [end, error] = std::to_chars(
        text, text + sizeof(text), value, std::chars_format::general, 10
    );
    if (error != std::errc{}) throw std::runtime_error("Erro formatando número");
    buffer.append(text, end);
}

void append_date_time(std::string& buffer, long date, long time) {
    char text[32];
    const int size = std::snprintf(
        text,
        sizeof(text),
        "%04ld-%02ld-%02ld %02ld:%02ld:00",
        date / 10000,
        (date / 100) % 100,
        date % 100,
        time / 100,
        time % 100
    );
    buffer.append(text, static_cast<std::size_t>(size));
}

void append_step(std::string& buffer, long hours) {
    append_integer(buffer, hours / 24);
    buffer.append(" days ");
    char text[16];
    const int size = std::snprintf(text, sizeof(text), "%02ld:00:00", hours % 24);
    buffer.append(text, static_cast<std::size_t>(size));
}

void flush(FILE* output, std::string& buffer) {
    if (buffer.empty()) return;
    if (std::fwrite(buffer.data(), 1, buffer.size(), output) != buffer.size()) {
        throw std::runtime_error("Erro escrevendo o CSV");
    }
    buffer.clear();
}

void show_progress(long position, std::uintmax_t file_size) {
    const double percentage = position >= 0 && file_size > 0
        ? 100.0 * static_cast<double>(position) / static_cast<double>(file_size)
        : 0.0;
    static int last_tenth = -1;
    const int current_tenth = static_cast<int>(percentage * 10.0);
    if (current_tenth == last_tenth) return;
    last_tenth = current_tenth;
    std::cerr << '\r' << std::fixed << std::setprecision(1)
              << percentage << '%' << std::flush;
}

int main(int argc, char** argv) {
    try {
        if (argc > 3) {
            std::cerr << "Uso: " << argv[0] << " [entrada.grib] [saida.csv]\n";
            return 2;
        }

        const fs::path input_path = argc >= 2 ? argv[1] : GRIB_PATH;
        const fs::path output_path = argc >= 3 ? argv[2] : CSV_PATH;
        fs::path temporary_path = output_path;
        temporary_path += ".part";

        if (!fs::is_regular_file(input_path)) {
            throw std::runtime_error("GRIB não encontrado: " + input_path.string());
        }
        fs::create_directories(output_path.parent_path());

        File input(std::fopen(input_path.c_str(), "rb"));
        File output(std::fopen(temporary_path.c_str(), "wb"));
        if (!input || !output) throw std::runtime_error("Não foi possível abrir os arquivos");

        std::string buffer;
        buffer.reserve(BUFFER_SIZE);
        buffer.append("grupo_grib,time,step,latitude,longitude,number,surface,valid_time,tp\n");

        std::vector<double> latitudes;
        std::vector<double> longitudes;
        std::vector<double> values;
        std::vector<std::string> coordinates;
        std::string grid_signature;
        bool found_message = false;
        const auto file_size = fs::file_size(input_path);

        while (true) {
            int error = CODES_SUCCESS;
            Grib grib(codes_handle_new_from_file(nullptr, input.get(), PRODUCT_GRIB, &error));
            if (!grib) {
                if (error == CODES_SUCCESS || error == CODES_END_OF_FILE) break;
                throw std::runtime_error(codes_get_error_message(error));
            }

            std::size_t points = 0;
            if (codes_get_size(grib.get(), "values", &points) != CODES_SUCCESS) {
                throw std::runtime_error("Erro lendo o tamanho da grade");
            }
            values.resize(points);

            const std::string current_grid = read_string(grib.get(), "md5GridSection");
            if (current_grid != grid_signature) {
                latitudes.resize(points);
                longitudes.resize(points);
                error = codes_grib_get_data(
                    grib.get(), latitudes.data(), longitudes.data(), values.data()
                );
                if (error != CODES_SUCCESS) {
                    throw std::runtime_error(codes_get_error_message(error));
                }

                coordinates.resize(points);
                for (std::size_t index = 0; index < points; ++index) {
                    coordinates[index].clear();
                    append_number(coordinates[index], latitudes[index]);
                    coordinates[index].push_back(',');
                    append_number(coordinates[index], longitudes[index]);
                    coordinates[index].push_back(',');
                }
                grid_signature = current_grid;
            } else {
                std::size_t value_count = points;
                error = codes_get_double_array(
                    grib.get(), "values", values.data(), &value_count
                );
                if (error != CODES_SUCCESS || value_count != points) {
                    throw std::runtime_error("Erro lendo os valores da grade");
                }
            }

            const long data_date = read_long(grib.get(), "dataDate");
            const long data_time = read_long(grib.get(), "dataTime");
            const long valid_date = read_long(grib.get(), "validityDate", data_date);
            const long valid_time = read_long(grib.get(), "validityTime", data_time);
            const long step = read_long(grib.get(), "endStep");
            const long number = read_long(grib.get(), "number");
            const long surface = read_long(grib.get(), "level");

            std::string row_start = "0,";
            append_date_time(row_start, data_date, data_time);
            row_start.push_back(',');
            append_step(row_start, step);
            row_start.push_back(',');

            std::string row_end;
            append_integer(row_end, number);
            row_end.push_back(',');
            append_integer(row_end, surface);
            row_end.push_back(',');
            append_date_time(row_end, valid_date, valid_time);
            row_end.push_back(',');

            for (std::size_t index = 0; index < points; ++index) {
                buffer.append(row_start);
                buffer.append(coordinates[index]);
                buffer.append(row_end);
                append_number(buffer, values[index]);
                buffer.push_back('\n');
            }

            found_message = true;
            if (buffer.size() >= BUFFER_SIZE) flush(output.get(), buffer);
            show_progress(std::ftell(input.get()), file_size);
        }

        flush(output.get(), buffer);
        if (!found_message) throw std::runtime_error("Nenhuma mensagem GRIB encontrada");

        output.reset();
        input.reset();
        fs::rename(temporary_path, output_path);

        std::cout << "\nConversão concluída\nCSV: " << output_path << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "\nErro: " << error.what() << '\n';
        return 1;
    }
}
