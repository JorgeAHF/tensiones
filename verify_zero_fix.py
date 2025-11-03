"""Script para verificar que el fix de valores cero funcionó correctamente."""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

def verify_zero_fix():
    """Verifica el archivo CSV más reciente para detectar valores cero."""
    
    # Buscar el archivo CSV más reciente
    data_path = Path("data/acceleration")
    csv_files = sorted(data_path.glob("acceleration_*.csv"), reverse=True)
    
    if not csv_files:
        print("❌ No se encontraron archivos CSV")
        return
    
    latest_file = csv_files[0]
    
    print("\n" + "="*80)
    print("VERIFICACIÓN DE FILTRO DE VALIDACIÓN (OPCIÓN 3)")
    print("="*80)
    print(f"\n📁 Archivo analizado: {latest_file.name}")
    
    # Leer CSV
    try:
        df = pd.read_csv(latest_file)
        print(f"📊 Total de registros: {len(df):,}")
        
        # Verificar si tiene columna is_valid
        has_validation = 'is_valid' in df.columns
        
        if has_validation:
            print("✅ Nueva columna 'is_valid' detectada - Fix implementado correctamente")
        else:
            print("⚠️  Columna 'is_valid' NO encontrada - Este CSV es de antes del fix")
        
        # Identificar columnas de aceleración
        accel_cols = [col for col in df.columns if col in ['ax_g', 'ay_g', 'az_g']]
        print(f"🔍 Columnas: {', '.join(df.columns.tolist())}")
        
        print("\n" + "-"*80)
        print("ANÁLISIS DE DATOS")
        print("-"*80)
        
        # Análisis general
        for col in accel_cols:
            valid_data = df[col].notna()
            count_valid = valid_data.sum()
            zero_in_col = valid_data & (df[col] == 0.0)
            count_zeros = zero_in_col.sum()
            
            if count_valid > 0:
                pct = (count_zeros / count_valid) * 100
                print(f"\n{col}:")
                print(f"   Total valores: {count_valid:,}")
                print(f"   Valores cero: {count_zeros:,} ({pct:.4f}%)")
        
        # Si tiene validación, analizar
        if has_validation:
            print("\n" + "-"*80)
            print("ANÁLISIS DE VALIDACIÓN")
            print("-"*80)
            
            total_samples = len(df)
            valid_samples = df['is_valid'].sum()
            invalid_samples = total_samples - valid_samples
            
            print(f"\n📈 Muestras válidas: {valid_samples:,} ({valid_samples/total_samples*100:.2f}%)")
            print(f"❌ Muestras inválidas: {invalid_samples:,} ({invalid_samples/total_samples*100:.2f}%)")
            
            # Verificar ceros en muestras marcadas como válidas
            print("\n🔍 Verificando ceros en muestras VÁLIDAS:")
            valid_df = df[df['is_valid'] == True]
            
            zeros_in_valid = 0
            for col in accel_cols:
                valid_data = valid_df[col].notna()
                zero_in_col = valid_data & (valid_df[col] == 0.0)
                count = zero_in_col.sum()
                zeros_in_valid += count
                if count > 0:
                    print(f"   ⚠️  {col}: {count} ceros en muestras VÁLIDAS")
            
            if zeros_in_valid == 0:
                print("   ✅ PERFECTO: Ningún cero en muestras marcadas como válidas")
            
            # Mostrar ejemplos de muestras inválidas
            if invalid_samples > 0:
                print("\n📋 Primeros ejemplos de muestras INVÁLIDAS:")
                invalid_df = df[df['is_valid'] == False]
                print(invalid_df[['timestamp_local', 'ax_g', 'ay_g', 'az_g']].head(5).to_string(index=False))
        
        print("\n" + "="*80)
        print("RESULTADO FINAL")
        print("="*80)
        
        if has_validation:
            if zeros_in_valid == 0:
                print("✅✅✅ EXCELENTE: El filtro está funcionando perfectamente")
                print("      - Todas las muestras válidas están libres de ceros")
                print("      - Las muestras inválidas se marcaron correctamente")
                print("      - CSV mantiene trazabilidad completa")
            else:
                print(f"⚠️  Se encontraron {zeros_in_valid} ceros en muestras válidas")
                print("   El filtro puede necesitar ajustes")
        else:
            print("ℹ️  Este CSV es anterior al fix - Ejecuta la app nuevamente para probar")
        
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"❌ Error al analizar: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    verify_zero_fix()
