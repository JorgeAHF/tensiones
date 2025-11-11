"""
Script para convertir archivos Parquet a CSV.
Útil para abrir los datos en Excel, Google Sheets, o herramientas de gráficas.
"""
import pandas as pd
from pathlib import Path
import sys
from datetime import datetime


def convert_parquet_to_csv(parquet_path: Path, output_csv_path: Path = None) -> Path:
    """
    Convierte un archivo Parquet a CSV.

    Args:
        parquet_path: Ruta al archivo .parquet
        output_csv_path: Ruta de salida (opcional, por default usa el mismo nombre)

    Returns:
        Path al archivo CSV creado
    """
    # Si no se especifica output, usar el mismo nombre pero con .csv
    if output_csv_path is None:
        output_csv_path = parquet_path.with_suffix('.csv')

    print(f"Leyendo {parquet_path.name}...")
    df = pd.read_parquet(parquet_path)

    # Convertir timestamps a formato legible
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Convertir a string ISO format para CSV
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S.%f')

    print(f"Escribiendo {output_csv_path.name}...")
    df.to_csv(output_csv_path, index=False)

    file_size_mb = output_csv_path.stat().st_size / (1024 * 1024)
    print(f"✅ Archivo CSV creado: {output_csv_path}")
    print(f"   Tamaño: {file_size_mb:.2f} MB")
    print(f"   Filas: {len(df):,}")

    return output_csv_path


def convert_directory(directory: Path, recursive: bool = False):
    """
    Convierte todos los archivos Parquet en un directorio a CSV.

    Args:
        directory: Directorio a procesar
        recursive: Si True, busca en subdirectorios también
    """
    pattern = "**/*.parquet" if recursive else "*.parquet"
    parquet_files = list(directory.glob(pattern))

    if not parquet_files:
        print(f"❌ No se encontraron archivos .parquet en {directory}")
        return

    print(f"\n📁 Encontrados {len(parquet_files)} archivo(s) Parquet")
    print("="*80)

    total_size_mb = 0
    converted_count = 0

    for i, parquet_file in enumerate(parquet_files, 1):
        print(f"\n[{i}/{len(parquet_files)}] {parquet_file.relative_to(directory)}")

        try:
            csv_path = convert_parquet_to_csv(parquet_file)
            total_size_mb += csv_path.stat().st_size / (1024 * 1024)
            converted_count += 1
        except Exception as e:
            print(f"❌ Error al convertir: {e}")
            continue

    print("\n" + "="*80)
    print(f"✅ Conversión completada: {converted_count}/{len(parquet_files)} archivos")
    print(f"   Tamaño total CSV: {total_size_mb:.2f} MB")
    print("="*80)


def main():
    """Función principal - manejo de argumentos."""
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python convert_parquet_to_csv.py <archivo.parquet>")
        print("  python convert_parquet_to_csv.py <archivo.parquet> <salida.csv>")
        print("  python convert_parquet_to_csv.py <directorio/> [--recursive]")
        print("\nEjemplos:")
        print("  # Convertir un archivo (crea archivo.csv)")
        print("  python convert_parquet_to_csv.py data.parquet")
        print("\n  # Convertir con nombre específico")
        print("  python convert_parquet_to_csv.py data.parquet salida.csv")
        print("\n  # Convertir todos en un directorio")
        print("  python convert_parquet_to_csv.py data/acceleration/sensor_10603/")
        print("\n  # Convertir incluyendo subdirectorios")
        print("  python convert_parquet_to_csv.py data/acceleration/ --recursive")
        sys.exit(1)

    path_arg = sys.argv[1]
    path = Path(path_arg)

    if not path.exists():
        print(f"❌ Error: '{path_arg}' no existe")
        sys.exit(1)

    # Si es un archivo
    if path.is_file():
        if not path.suffix == '.parquet':
            print(f"❌ Error: '{path_arg}' no es un archivo .parquet")
            sys.exit(1)

        # Verificar si se especificó nombre de salida
        output_path = None
        if len(sys.argv) > 2 and not sys.argv[2].startswith('--'):
            output_path = Path(sys.argv[2])

        try:
            convert_parquet_to_csv(path, output_path)
        except Exception as e:
            print(f"❌ Error al convertir: {e}")
            sys.exit(1)

    # Si es un directorio
    elif path.is_dir():
        recursive = '--recursive' in sys.argv or '-r' in sys.argv
        try:
            convert_directory(path, recursive)
        except Exception as e:
            print(f"❌ Error al procesar directorio: {e}")
            sys.exit(1)

    else:
        print(f"❌ Error: '{path_arg}' no es un archivo ni directorio válido")
        sys.exit(1)


if __name__ == "__main__":
    main()
