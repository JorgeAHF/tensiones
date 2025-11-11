"""
Script de ejemplo para leer y verificar archivos Parquet de sensores.
Demuestra cómo leer los archivos Parquet generados por el sistema
y verificar la completitud de los datos.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys


def read_parquet_file(file_path: str) -> pd.DataFrame:
    """
    Lee un archivo Parquet y retorna un DataFrame.

    Args:
        file_path: Ruta al archivo .parquet

    Returns:
        DataFrame con los datos del sensor
    """
    df = pd.read_parquet(file_path)
    return df


def verify_data_completeness(df: pd.DataFrame, expected_fs_hz: int = None) -> dict:
    """
    Verifica la completitud de los datos en el DataFrame.

    Args:
        df: DataFrame con datos del sensor
        expected_fs_hz: Frecuencia de muestreo esperada en Hz (opcional)

    Returns:
        Diccionario con estadísticas de completitud
    """
    stats = {}

    # Total de muestras
    stats['total_samples'] = len(df)

    # Rango de tiempo
    if 'timestamp_utc' in df.columns:
        # Convertir a datetime si es necesario
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp_utc']):
            df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'], unit='ms')

        time_start = df['timestamp_utc'].min()
        time_end = df['timestamp_utc'].max()
        duration_seconds = (time_end - time_start).total_seconds()

        stats['time_start'] = time_start
        stats['time_end'] = time_end
        stats['duration_seconds'] = duration_seconds

        # Calcular frecuencia medida
        if duration_seconds > 0:
            measured_fs_hz = stats['total_samples'] / duration_seconds
            stats['measured_fs_hz'] = measured_fs_hz

            # Si se proporcionó frecuencia esperada, calcular completitud
            if expected_fs_hz is not None:
                expected_samples = int(expected_fs_hz * duration_seconds)
                stats['expected_samples'] = expected_samples
                stats['completeness_pct'] = (stats['total_samples'] / expected_samples) * 100
                stats['missing_samples'] = expected_samples - stats['total_samples']

    # Verificar timestamps ordenados
    if 'timestamp_utc' in df.columns:
        is_sorted = df['timestamp_utc'].is_monotonic_increasing
        stats['timestamps_sorted'] = is_sorted

        if not is_sorted:
            # Contar timestamps desordenados
            diffs = df['timestamp_utc'].diff()
            negative_diffs = (diffs < pd.Timedelta(0)).sum()
            stats['out_of_order_count'] = negative_diffs

    # Verificar valores válidos (columna is_valid si existe)
    if 'is_valid' in df.columns:
        valid_count = df['is_valid'].sum()
        stats['valid_samples'] = valid_count
        stats['invalid_samples'] = stats['total_samples'] - valid_count
        stats['valid_pct'] = (valid_count / stats['total_samples']) * 100

    return stats


def print_stats(stats: dict):
    """Imprime las estadísticas de forma legible."""
    print("\n" + "="*80)
    print("ESTADÍSTICAS DEL ARCHIVO PARQUET")
    print("="*80)

    print(f"\n📊 Datos generales:")
    print(f"   Total de muestras:     {stats['total_samples']:,}")

    if 'time_start' in stats:
        print(f"\n⏱️  Rango temporal:")
        print(f"   Inicio:                {stats['time_start']}")
        print(f"   Fin:                   {stats['time_end']}")
        print(f"   Duración:              {stats['duration_seconds']:.2f} segundos")

    if 'measured_fs_hz' in stats:
        print(f"\n📈 Frecuencia de muestreo:")
        print(f"   Frecuencia medida:     {stats['measured_fs_hz']:.2f} Hz")

    if 'expected_samples' in stats:
        print(f"\n✅ Completitud:")
        print(f"   Muestras esperadas:    {stats['expected_samples']:,}")
        print(f"   Muestras recibidas:    {stats['total_samples']:,}")
        print(f"   Completitud:           {stats['completeness_pct']:.2f}%")

        if stats['missing_samples'] > 0:
            print(f"   ⚠️  Muestras faltantes:  {stats['missing_samples']:,}")
        else:
            print(f"   ✅ Sin muestras faltantes")

    if 'timestamps_sorted' in stats:
        print(f"\n🔢 Orden de timestamps:")
        if stats['timestamps_sorted']:
            print(f"   ✅ Timestamps ordenados correctamente")
        else:
            print(f"   ❌ Timestamps DESORDENADOS")
            if 'out_of_order_count' in stats:
                print(f"   Timestamps fuera de orden: {stats['out_of_order_count']}")

    if 'valid_samples' in stats:
        print(f"\n✔️  Validez de datos:")
        print(f"   Muestras válidas:      {stats['valid_samples']:,} ({stats['valid_pct']:.2f}%)")
        if stats['invalid_samples'] > 0:
            print(f"   ⚠️  Muestras inválidas:  {stats['invalid_samples']:,}")

    print("="*80 + "\n")


def analyze_sensor_directory(sensor_dir: Path, expected_fs_hz: int = None):
    """
    Analiza todos los archivos Parquet en un directorio de sensor.

    Args:
        sensor_dir: Ruta al directorio del sensor (ej: data/acceleration/sensor_10603/)
        expected_fs_hz: Frecuencia de muestreo esperada en Hz
    """
    parquet_files = list(sensor_dir.glob("*.parquet"))

    if not parquet_files:
        print(f"❌ No se encontraron archivos .parquet en {sensor_dir}")
        return

    print(f"\n📁 Encontrados {len(parquet_files)} archivo(s) Parquet en {sensor_dir}")

    # Ordenar por nombre (que incluye timestamp)
    parquet_files.sort()

    total_samples = 0
    total_duration = 0

    for i, file_path in enumerate(parquet_files, 1):
        print(f"\n{'='*80}")
        print(f"Archivo {i}/{len(parquet_files)}: {file_path.name}")
        print(f"{'='*80}")

        # Leer archivo
        df = read_parquet_file(str(file_path))

        # Verificar completitud
        stats = verify_data_completeness(df, expected_fs_hz)

        # Imprimir estadísticas
        print_stats(stats)

        # Acumular totales
        total_samples += stats['total_samples']
        if 'duration_seconds' in stats:
            total_duration += stats['duration_seconds']

    # Resumen final
    print("\n" + "="*80)
    print("RESUMEN TOTAL DE LA SESIÓN")
    print("="*80)
    print(f"Total de archivos:       {len(parquet_files)}")
    print(f"Total de muestras:       {total_samples:,}")
    print(f"Duración total:          {total_duration:.2f} segundos")

    if expected_fs_hz and total_duration > 0:
        expected_total = int(expected_fs_hz * total_duration)
        completeness = (total_samples / expected_total) * 100
        print(f"Muestras esperadas:      {expected_total:,}")
        print(f"Completitud total:       {completeness:.2f}%")

        if completeness < 95:
            print(f"⚠️  Completitud < 95% - Revisar problemas de transmisión")
        elif completeness < 99:
            print(f"⚠️  Completitud < 99% - Pérdida menor de datos")
        else:
            print(f"✅ Completitud excelente (>99%)")

    print("="*80 + "\n")


def main():
    """Función principal - ejemplo de uso."""
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python read_parquet_example.py <archivo.parquet> [frecuencia_hz]")
        print("  python read_parquet_example.py <directorio_sensor/> [frecuencia_hz]")
        print("\nEjemplos:")
        print("  # Analizar un archivo específico")
        print("  python read_parquet_example.py data/acceleration/sensor_10603/sensor_10603_acceleration_20251111_131444.parquet 1024")
        print("\n  # Analizar todos los archivos de un sensor")
        print("  python read_parquet_example.py data/acceleration/sensor_10603/ 1024")
        sys.exit(1)

    path_arg = sys.argv[1]
    expected_fs_hz = int(sys.argv[2]) if len(sys.argv) > 2 else None

    path = Path(path_arg)

    if not path.exists():
        print(f"❌ Error: La ruta '{path_arg}' no existe")
        sys.exit(1)

    # Determinar si es archivo o directorio
    if path.is_file():
        # Analizar archivo individual
        print(f"📄 Analizando archivo: {path.name}")
        df = read_parquet_file(str(path))

        # Verificar y mostrar estadísticas
        stats = verify_data_completeness(df, expected_fs_hz)
        print_stats(stats)

        # Mostrar primeras filas
        print("\n📋 Primeras 5 filas:")
        print(df.head())

        print("\n📋 Últimas 5 filas:")
        print(df.tail())

        print(f"\n📊 Columnas: {list(df.columns)}")
        print(f"📊 Tipos de datos:")
        print(df.dtypes)

    elif path.is_dir():
        # Analizar directorio completo
        analyze_sensor_directory(path, expected_fs_hz)

    else:
        print(f"❌ Error: '{path_arg}' no es un archivo ni un directorio válido")
        sys.exit(1)


if __name__ == "__main__":
    main()
