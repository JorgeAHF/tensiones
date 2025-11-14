"""
Script para dividir archivos CSV grandes en chunks de 2 minutos.

Uso:
    python scripts/dividir_csv.py sensor_10603
    python scripts/dividir_csv.py sensor_10603 --duracion 5  # Chunks de 5 minutos
"""

import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime


def dividir_csv_por_tiempo(
    archivo_csv: Path,
    duracion_minutos: float = 2.0,
    carpeta_salida: Path = None
):
    """
    Divide un CSV grande en chunks basados en tiempo.

    Args:
        archivo_csv: Ruta al archivo CSV grande
        duracion_minutos: Duración de cada chunk en minutos
        carpeta_salida: Carpeta donde guardar los chunks (default: misma carpeta)
    """

    print(f"\nProcesando: {archivo_csv.name}")
    print("=" * 60)

    # Leer CSV completo
    print(f"   Leyendo archivo...")
    import pandas as pd
    df = pd.read_csv(archivo_csv)

    total_muestras = len(df)
    print(f"   Total de muestras: {total_muestras:,}")

    # Detectar columna de timestamp y crear columna temporal para cálculos
    if 'timestamp_epoch' in df.columns:
        timestamp_col = 'timestamp_epoch'
        timestamps = df['timestamp_epoch'].values
        columna_temporal_creada = False
    elif 'timestamp_utc' in df.columns:
        timestamp_col = 'timestamp_utc'
        # Convertir timestamp_utc (ISO format) a epoch SOLO para cálculos internos
        df['_temp_timestamp_epoch'] = pd.to_datetime(df['timestamp_utc']).astype('int64') / 1e9
        timestamps = df['_temp_timestamp_epoch'].values
        columna_temporal_creada = True
    else:
        print(f"   ERROR: No se encontró columna 'timestamp_epoch' ni 'timestamp_utc'")
        return

    # Calcular duración
    duracion_total_seg = timestamps[-1] - timestamps[0]
    duracion_total_min = duracion_total_seg / 60

    print(f"   Duración total: {duracion_total_min:.2f} minutos")
    print(f"   Dividiendo en chunks de {duracion_minutos} minutos...")

    # Carpeta de salida
    if carpeta_salida is None:
        carpeta_salida = archivo_csv.parent / "chunks"
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    # Dividir en chunks
    timestamp_inicio = timestamps[0]
    duracion_chunk_seg = duracion_minutos * 60

    chunk_num = 0
    archivos_creados = []

    tiempo_actual = timestamp_inicio
    while tiempo_actual < timestamps[-1]:
        # Definir rango de este chunk
        tiempo_fin = tiempo_actual + duracion_chunk_seg

        # Filtrar datos del chunk
        mask = (timestamps >= tiempo_actual) & (timestamps < tiempo_fin)
        df_chunk = df[mask]

        if len(df_chunk) == 0:
            # Saltar chunks vacíos
            tiempo_actual = tiempo_fin
            continue

        # Calcular minutos de inicio/fin para el nombre
        min_inicio = int((tiempo_actual - timestamp_inicio) / 60)
        min_fin = int((tiempo_fin - timestamp_inicio) / 60)

        # Crear nombre de archivo
        sensor_id = archivo_csv.stem.split('_')[0] + '_' + archivo_csv.stem.split('_')[1]

        # Obtener timestamp del archivo original
        partes = archivo_csv.stem.split('_')
        if len(partes) >= 4:
            fecha_hora = f"{partes[3]}_{partes[4]}"
        else:
            fecha_hora = datetime.now().strftime("%Y%m%d_%H%M%S")

        nombre_chunk = f"{sensor_id}_acceleration_{fecha_hora}_{min_inicio:03d}-{min_fin:03d}min.csv"
        ruta_chunk = carpeta_salida / nombre_chunk

        # Eliminar columna temporal si fue creada
        if columna_temporal_creada and '_temp_timestamp_epoch' in df_chunk.columns:
            df_chunk_clean = df_chunk.drop(columns=['_temp_timestamp_epoch'])
        else:
            df_chunk_clean = df_chunk

        # Guardar chunk
        df_chunk_clean.to_csv(ruta_chunk, index=False)
        archivos_creados.append({
            'archivo': nombre_chunk,
            'muestras': len(df_chunk),
            'min_inicio': min_inicio,
            'min_fin': min_fin
        })

        chunk_num += 1
        tiempo_actual = tiempo_fin

    # Reporte
    print(f"\nDivision completada:")
    print(f"   Total de chunks creados: {len(archivos_creados)}")
    print(f"   Guardados en: {carpeta_salida}")
    print(f"\n   Detalle de chunks:")

    total_muestras_chunks = 0
    for info in archivos_creados:
        total_muestras_chunks += info['muestras']
        print(f"      {info['archivo']}: {info['muestras']:,} muestras ({info['min_inicio']}-{info['min_fin']} min)")

    # Verificar integridad
    print(f"\n   Verificación de integridad:")
    print(f"      Muestras originales: {total_muestras:,}")
    print(f"      Muestras en chunks:  {total_muestras_chunks:,}")

    if total_muestras == total_muestras_chunks:
        print(f"      PERFECTO - No se perdieron datos")
    else:
        diferencia = total_muestras - total_muestras_chunks
        print(f"      Diferencia: {diferencia:,} muestras")

    return archivos_creados


def main():
    parser = argparse.ArgumentParser(description='Dividir CSV grande en chunks por tiempo')
    parser.add_argument('sensor_id', help='ID del sensor (ej: sensor_10603)')
    parser.add_argument('--duracion', type=float, default=2.0, help='Duración de cada chunk en minutos (default: 2)')
    parser.add_argument('--archivo', help='Archivo específico a dividir (opcional)')

    args = parser.parse_args()

    print(f"\nDIVIDIR CSV EN CHUNKS DE {args.duracion} MINUTOS")
    print("=" * 60)

    # Buscar archivo(s) a procesar
    if args.archivo:
        # Archivo específico
        archivo_csv = Path(args.archivo)
        if not archivo_csv.exists():
            print(f"ERROR: Archivo no encontrado: {archivo_csv}")
            return
        archivos = [archivo_csv]
    else:
        # Buscar todos los CSV del sensor
        carpeta_sensor = Path(f"data/acceleration/{args.sensor_id}")
        if not carpeta_sensor.exists():
            print(f"ERROR: No existe la carpeta {carpeta_sensor}")
            return

        archivos = sorted(carpeta_sensor.glob("*.csv"))

        # Excluir chunks previamente creados
        archivos = [f for f in archivos if 'min.csv' not in f.name]

        if not archivos:
            print(f"ERROR: No hay archivos CSV en {carpeta_sensor}")
            return

        print(f"\nEncontrados {len(archivos)} archivo(s) para procesar:")
        for i, archivo in enumerate(archivos, 1):
            tamaño_mb = archivo.stat().st_size / (1024 * 1024)
            print(f"   {i}. {archivo.name} ({tamaño_mb:.2f} MB)")

    # Procesar cada archivo
    for archivo in archivos:
        dividir_csv_por_tiempo(archivo, args.duracion)

    print(f"\nProceso completado!")


if __name__ == "__main__":
    main()
