"""Script para analizar valores cero anormales en archivos CSV de aceleración."""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

def analyze_csv_for_zeros(csv_path, show_context=True):
    """
    Analiza un archivo CSV buscando valores cero anormales.
    
    Args:
        csv_path: Ruta al archivo CSV
        show_context: Si True, muestra contexto alrededor de los ceros
    """
    try:
        # Leer CSV
        df = pd.read_csv(csv_path)
        
        print(f"\n{'='*80}")
        print(f"Analizando: {csv_path.name}")
        print(f"{'='*80}")
        print(f"Total de registros: {len(df)}")
        
        # Identificar columnas de aceleración
        accel_cols = [col for col in df.columns if col in ['ax_g', 'ay_g', 'az_g', 'accel_x', 'accel_y', 'accel_z']]
        
        if not accel_cols:
            print("❌ No se encontraron columnas de aceleración")
            return
        
        print(f"Columnas de aceleración: {accel_cols}")
        
        # Buscar filas donde TODOS los ejes sean exactamente 0.0
        # (excluyendo NaN que son ejes no configurados)
        zero_mask = pd.Series([True] * len(df))
        
        for col in accel_cols:
            # Si el valor no es NaN y es exactamente 0.0
            zero_mask &= (df[col].notna() & (df[col] == 0.0))
        
        zero_rows = df[zero_mask]
        
        print(f"\n📊 Resultados:")
        print(f"   Filas con TODOS los ejes configurados = 0.0: {len(zero_rows)}")
        
        if len(zero_rows) > 0:
            print(f"\n⚠️  ADVERTENCIA: Se encontraron {len(zero_rows)} filas con valores cero anormales")
            print(f"   Esto representa el {(len(zero_rows)/len(df)*100):.2f}% de los datos")
            
            if show_context and len(zero_rows) > 0:
                print(f"\n📍 Primeros 5 casos de valores cero:")
                for idx in zero_rows.index[:5]:
                    print(f"\n   Fila {idx}:")
                    # Mostrar contexto: 2 filas antes y 2 después
                    start_idx = max(0, idx - 2)
                    end_idx = min(len(df), idx + 3)
                    context = df.iloc[start_idx:end_idx][['timestamp_local'] + accel_cols]
                    print(context.to_string(index=True))
        else:
            print(f"   ✅ No se encontraron valores cero anormales")
        
        # Buscar valores cero en ejes individuales (no NaN)
        print(f"\n📈 Análisis por eje:")
        for col in accel_cols:
            valid_data = df[col].notna()
            zero_in_col = valid_data & (df[col] == 0.0)
            count_zeros = zero_in_col.sum()
            count_valid = valid_data.sum()
            
            if count_valid > 0:
                pct = (count_zeros / count_valid) * 100
                print(f"   {col}: {count_zeros}/{count_valid} ceros ({pct:.2f}%)")
        
        # Estadísticas generales
        print(f"\n📐 Estadísticas de valores (excluyendo NaN):")
        for col in accel_cols:
            valid_values = df[col].dropna()
            if len(valid_values) > 0:
                print(f"\n   {col}:")
                print(f"      Min: {valid_values.min():.2f}")
                print(f"      Max: {valid_values.max():.2f}")
                print(f"      Media: {valid_values.mean():.2f}")
                print(f"      Std: {valid_values.std():.2f}")
        
    except Exception as e:
        print(f"❌ Error al analizar {csv_path}: {e}")


def analyze_multiple_files(data_dir, num_files=5):
    """Analiza los últimos N archivos CSV."""
    data_path = Path(data_dir)
    csv_files = sorted(data_path.glob("acceleration_*.csv"), reverse=True)
    
    if not csv_files:
        print(f"❌ No se encontraron archivos CSV en {data_dir}")
        return
    
    print(f"\n{'#'*80}")
    print(f"ANÁLISIS DE VALORES CERO EN ARCHIVOS CSV DE ACELERACIÓN")
    print(f"{'#'*80}")
    
    files_to_analyze = csv_files[:num_files]
    print(f"\nAnalizando los {len(files_to_analyze)} archivos más recientes...")
    
    for csv_file in files_to_analyze:
        analyze_csv_for_zeros(csv_file, show_context=True)
    
    print(f"\n{'#'*80}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analizar valores cero en archivos CSV")
    parser.add_argument("--dir", default="data/acceleration", help="Directorio con archivos CSV")
    parser.add_argument("--num-files", type=int, default=3, help="Número de archivos recientes a analizar")
    parser.add_argument("--file", help="Analizar un archivo específico")
    
    args = parser.parse_args()
    
    if args.file:
        analyze_csv_for_zeros(Path(args.file), show_context=True)
    else:
        analyze_multiple_files(args.dir, args.num_files)
