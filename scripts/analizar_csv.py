"""
Script para analizar archivos CSV de aceleración del sensor.

Uso:
    python scripts/analizar_csv.py sensor_10603
    python scripts/analizar_csv.py sensor_10603 --graficar
    python scripts/analizar_csv.py sensor_10603 --excel
"""

import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime


def leer_archivos_csv(sensor_id: str, carpeta_base: str = "data/acceleration"):
    """Lee todos los archivos CSV de un sensor y los combina en un DataFrame."""

    carpeta_sensor = Path(carpeta_base) / sensor_id

    if not carpeta_sensor.exists():
        print(f"❌ Error: No existe la carpeta {carpeta_sensor}")
        return None

    archivos = sorted(carpeta_sensor.glob("*.csv"))

    if not archivos:
        print(f"❌ Error: No hay archivos CSV en {carpeta_sensor}")
        return None

    print(f"\n📁 Encontrados {len(archivos)} archivo(s) CSV:")
    for i, archivo in enumerate(archivos, 1):
        tamaño_mb = archivo.stat().st_size / (1024 * 1024)
        print(f"   {i}. {archivo.name} ({tamaño_mb:.2f} MB)")

    # Leer todos los archivos y combinarlos
    dfs = []
    for archivo in archivos:
        df = pd.read_csv(archivo)
        dfs.append(df)

    # Combinar todos los DataFrames
    df_completo = pd.concat(dfs, ignore_index=True)

    print(f"\n✅ Datos combinados:")
    print(f"   Total de muestras: {len(df_completo):,}")
    print(f"   Columnas: {list(df_completo.columns)}")
    print(f"   Primeras filas:")
    print(df_completo.head())

    return df_completo, archivos


def analizar_calidad(df: pd.DataFrame, frecuencia_hz: float = 256):
    """Analiza la calidad de los datos capturados."""

    print(f"\n📊 ANÁLISIS DE CALIDAD DE DATOS")
    print("=" * 60)

    # Calcular duración
    if 'timestamp_epoch' in df.columns:
        timestamps = df['timestamp_epoch'].values
        duracion_seg = timestamps[-1] - timestamps[0]
        duracion_min = duracion_seg / 60

        # Calcular muestras esperadas
        muestras_esperadas = int(duracion_seg * frecuencia_hz)
        muestras_reales = len(df)
        porcentaje_capturado = (muestras_reales / muestras_esperadas) * 100

        print(f"   Duración: {duracion_min:.2f} minutos ({duracion_seg:.1f} segundos)")
        print(f"   Frecuencia configurada: {frecuencia_hz} Hz")
        print(f"   Muestras esperadas: {muestras_esperadas:,}")
        print(f"   Muestras capturadas: {muestras_reales:,}")
        print(f"   Porcentaje capturado: {porcentaje_capturado:.2f}%")

        if porcentaje_capturado >= 99:
            print(f"   ✅ EXCELENTE: Datos casi completos!")
        elif porcentaje_capturado >= 90:
            print(f"   ⚠️  BUENO: Datos mayormente completos")
        else:
            print(f"   ❌ MALO: Pérdida significativa de datos")

        # Calcular frecuencia real
        freq_real = muestras_reales / duracion_seg
        print(f"   Frecuencia real promedio: {freq_real:.2f} Hz")

    else:
        print("   ⚠️  No se encontró columna 'timestamp_epoch'")

    # Estadísticas de aceleración
    if 'z_g' in df.columns:
        print(f"\n   Aceleración Z (g):")
        print(f"      Mínimo: {df['z_g'].min():.4f}")
        print(f"      Máximo: {df['z_g'].max():.4f}")
        print(f"      Media: {df['z_g'].mean():.4f}")
        print(f"      Desviación estándar: {df['z_g'].std():.4f}")


def graficar_datos(df: pd.DataFrame, sensor_id: str):
    """Crea gráficas de los datos."""

    print(f"\n📈 Generando gráficas...")

    # Crear figura con 2 subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # Gráfica 1: Serie temporal completa
    if 'timestamp_epoch' in df.columns:
        # Convertir timestamps a tiempo relativo (segundos desde inicio)
        tiempo = df['timestamp_epoch'] - df['timestamp_epoch'].iloc[0]

        ax1.plot(tiempo, df['z_g'], 'b-', linewidth=0.5, alpha=0.7)
        ax1.set_xlabel('Tiempo (segundos)', fontsize=12)
        ax1.set_ylabel('Aceleración Z (g)', fontsize=12)
        ax1.set_title(f'Serie Temporal Completa - {sensor_id}', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Gráfica 2: Zoom a los primeros 10 segundos
        mask_zoom = tiempo <= 10
        ax2.plot(tiempo[mask_zoom], df['z_g'][mask_zoom], 'r-', linewidth=1)
        ax2.set_xlabel('Tiempo (segundos)', fontsize=12)
        ax2.set_ylabel('Aceleración Z (g)', fontsize=12)
        ax2.set_title('Zoom: Primeros 10 segundos', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)
    else:
        # Si no hay timestamps, usar índice
        ax1.plot(df.index, df['z_g'], 'b-', linewidth=0.5, alpha=0.7)
        ax1.set_xlabel('Muestra #', fontsize=12)
        ax1.set_ylabel('Aceleración Z (g)', fontsize=12)
        ax1.set_title(f'Serie Temporal Completa - {sensor_id}', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        ax2.plot(df.index[:2560], df['z_g'][:2560], 'r-', linewidth=1)
        ax2.set_xlabel('Muestra #', fontsize=12)
        ax2.set_ylabel('Aceleración Z (g)', fontsize=12)
        ax2.set_title('Zoom: Primeras 2560 muestras (~10 seg @ 256 Hz)', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    # Guardar gráfica
    output_file = f"graficas_{sensor_id}.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"   ✅ Gráfica guardada: {output_file}")

    # Mostrar
    plt.show()


def exportar_excel(df: pd.DataFrame, archivos: list, sensor_id: str):
    """Exporta los datos a Excel con múltiples hojas."""

    print(f"\n📑 Exportando a Excel...")

    output_file = f"datos_{sensor_id}.xlsx"

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Hoja 1: Todos los datos combinados
        df.to_excel(writer, sheet_name='Datos Completos', index=False)

        # Hoja 2: Resumen
        resumen = {
            'Métrica': [
                'Total de archivos CSV',
                'Total de muestras',
                'Duración (minutos)',
                'Frecuencia promedio (Hz)',
                'Aceleración Z - Mínimo (g)',
                'Aceleración Z - Máximo (g)',
                'Aceleración Z - Media (g)',
            ],
            'Valor': [
                len(archivos),
                len(df),
                (df['timestamp_epoch'].iloc[-1] - df['timestamp_epoch'].iloc[0]) / 60 if 'timestamp_epoch' in df.columns else 'N/A',
                len(df) / (df['timestamp_epoch'].iloc[-1] - df['timestamp_epoch'].iloc[0]) if 'timestamp_epoch' in df.columns else 'N/A',
                df['z_g'].min(),
                df['z_g'].max(),
                df['z_g'].mean(),
            ]
        }
        df_resumen = pd.DataFrame(resumen)
        df_resumen.to_excel(writer, sheet_name='Resumen', index=False)

    print(f"   ✅ Archivo Excel guardado: {output_file}")
    print(f"   Hojas creadas: 'Datos Completos', 'Resumen'")


def main():
    parser = argparse.ArgumentParser(description='Analizar datos CSV de sensor de aceleración')
    parser.add_argument('sensor_id', help='ID del sensor (ej: sensor_10603)')
    parser.add_argument('--frecuencia', type=float, default=256, help='Frecuencia de muestreo en Hz (default: 256)')
    parser.add_argument('--graficar', action='store_true', help='Generar gráficas')
    parser.add_argument('--excel', action='store_true', help='Exportar a Excel')

    args = parser.parse_args()

    print(f"\n🔍 ANALIZANDO DATOS DEL SENSOR: {args.sensor_id}")
    print("=" * 60)

    # Leer archivos
    resultado = leer_archivos_csv(args.sensor_id)
    if resultado is None:
        return

    df, archivos = resultado

    # Analizar calidad
    analizar_calidad(df, args.frecuencia)

    # Graficar si se solicita
    if args.graficar:
        graficar_datos(df, args.sensor_id)

    # Exportar a Excel si se solicita
    if args.excel:
        exportar_excel(df, archivos, args.sensor_id)

    print(f"\n✅ Análisis completado!")


if __name__ == "__main__":
    main()
