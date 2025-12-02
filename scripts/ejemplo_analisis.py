"""
Ejemplo simple de cómo leer y analizar los datos del sensor.

Puedes copiar y pegar estos bloques en Jupyter Notebook o ejecutarlos directamente.
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# =============================================================================
# 1. LEER LOS DATOS
# =============================================================================

# Especifica tu sensor
SENSOR_ID = "sensor_10603"  # Cambia esto por tu sensor
CARPETA = f"data/acceleration/{SENSOR_ID}"

# Leer todos los CSV y combinarlos
archivos = sorted(Path(CARPETA).glob("*.csv"))
print(f"Encontrados {len(archivos)} archivos CSV")

# Leer y combinar
dfs = [pd.read_csv(archivo) for archivo in archivos]
df = pd.concat(dfs, ignore_index=True)

print(f"Total de muestras: {len(df):,}")
print(f"\nPrimeras 5 filas:")
print(df.head())

# =============================================================================
# 2. ANÁLISIS BÁSICO
# =============================================================================

# Calcular duración
duracion_seg = df['timestamp_epoch'].iloc[-1] - df['timestamp_epoch'].iloc[0]
duracion_min = duracion_seg / 60

print(f"\nDuración: {duracion_min:.2f} minutos")
print(f"Frecuencia promedio: {len(df) / duracion_seg:.2f} Hz")

# Estadísticas de aceleración
print(f"\nEstadísticas de aceleración Z:")
print(df['z_g'].describe())

# =============================================================================
# 3. VERIFICAR CALIDAD DE DATOS
# =============================================================================

# A 256 Hz, deberías tener 256 muestras por segundo
frecuencia_esperada = 256  # Cambia esto según tu configuración
muestras_esperadas = int(duracion_seg * frecuencia_esperada)
muestras_reales = len(df)
porcentaje_capturado = (muestras_reales / muestras_esperadas) * 100

print(f"\n📊 CALIDAD DE DATOS:")
print(f"   Esperadas: {muestras_esperadas:,} muestras")
print(f"   Capturadas: {muestras_reales:,} muestras")
print(f"   Porcentaje: {porcentaje_capturado:.2f}%")

if porcentaje_capturado >= 99:
    print("   ✅ EXCELENTE!")
elif porcentaje_capturado >= 90:
    print("   ⚠️  BUENO")
else:
    print("   ❌ MALO - Pérdida significativa de datos")

# =============================================================================
# 4. GRAFICAR
# =============================================================================

# Convertir timestamps a tiempo relativo
tiempo = df['timestamp_epoch'] - df['timestamp_epoch'].iloc[0]

# Crear gráfica
plt.figure(figsize=(14, 6))

# Plot completo
plt.subplot(2, 1, 1)
plt.plot(tiempo, df['z_g'], 'b-', linewidth=0.5, alpha=0.7)
plt.xlabel('Tiempo (segundos)')
plt.ylabel('Aceleración Z (g)')
plt.title(f'Datos de Aceleración - {SENSOR_ID}')
plt.grid(True, alpha=0.3)

# Zoom a primeros 10 segundos
plt.subplot(2, 1, 2)
mask = tiempo <= 10
plt.plot(tiempo[mask], df['z_g'][mask], 'r-', linewidth=1)
plt.xlabel('Tiempo (segundos)')
plt.ylabel('Aceleración Z (g)')
plt.title('Zoom: Primeros 10 segundos')
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(f'grafica_{SENSOR_ID}.png', dpi=150)
print(f"\n✅ Gráfica guardada: grafica_{SENSOR_ID}.png")
plt.show()

# =============================================================================
# 5. EXPORTAR A EXCEL
# =============================================================================

# Guardar en Excel (opcional - descomenta si necesitas)
# df.to_excel(f'datos_{SENSOR_ID}.xlsx', index=False)
# print(f"✅ Datos exportados a: datos_{SENSOR_ID}.xlsx")

# =============================================================================
# 6. ANÁLISIS AVANZADO (OPCIONAL)
# =============================================================================

# Detectar gaps en los datos
gaps = []
for i in range(1, len(df)):
    dt = df['timestamp_epoch'].iloc[i] - df['timestamp_epoch'].iloc[i-1]
    dt_esperado = 1.0 / frecuencia_esperada  # Tiempo esperado entre muestras
    if dt > dt_esperado * 2:  # Si el gap es más del doble de lo esperado
        gaps.append({
            'indice': i,
            'tiempo': tiempo.iloc[i],
            'gap_ms': (dt - dt_esperado) * 1000
        })

if gaps:
    print(f"\n⚠️  Detectados {len(gaps)} gaps en los datos:")
    for gap in gaps[:5]:  # Mostrar solo los primeros 5
        print(f"   - En t={gap['tiempo']:.2f}s: gap de {gap['gap_ms']:.1f}ms")
    if len(gaps) > 5:
        print(f"   ... y {len(gaps) - 5} gaps más")
else:
    print(f"\n✅ No se detectaron gaps significativos en los datos")

print("\n" + "="*60)
print("Análisis completado!")
print("="*60)
