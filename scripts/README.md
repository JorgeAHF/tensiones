# 📊 Scripts de Análisis de Datos de Sensores

Scripts para analizar, graficar y exportar datos de los sensores de aceleración.

## 🚀 Uso Rápido

### Opción 1: Script Automático (Recomendado)

```bash
# Análisis completo con gráficas y exportación a Excel
python scripts/analizar_csv.py sensor_10603 --graficar --excel

# Solo análisis sin gráficas
python scripts/analizar_csv.py sensor_10603

# Especificar frecuencia diferente
python scripts/analizar_csv.py sensor_10603 --frecuencia 128 --graficar
```

### Opción 2: Script Interactivo

```bash
# Ejecutar directamente
python scripts/ejemplo_analisis.py

# O abrir en Jupyter Notebook y ejecutar celda por celda
jupyter notebook scripts/ejemplo_analisis.py
```

### Opción 3: Desde Python/Jupyter

```python
import pandas as pd
from pathlib import Path

# Leer todos los CSV de un sensor
sensor_id = "sensor_10603"
archivos = sorted(Path(f"data/acceleration/{sensor_id}").glob("*.csv"))
dfs = [pd.read_csv(f) for f in archivos]
df = pd.concat(dfs, ignore_index=True)

print(f"Total de muestras: {len(df):,}")
print(df.head())

# Guardar a Excel
df.to_excel(f"datos_{sensor_id}.xlsx", index=False)
```

---

## 📁 Outputs Generados

### 1. **Análisis en Consola**
```
📊 ANÁLISIS DE CALIDAD DE DATOS
============================================================
   Duración: 5.00 minutos (300.0 segundos)
   Frecuencia configurada: 256 Hz
   Muestras esperadas: 76,800
   Muestras capturadas: 76,450
   Porcentaje capturado: 99.54%
   ✅ EXCELENTE: Datos casi completos!
```

### 2. **Gráfica PNG**
- Archivo: `graficas_sensor_XXXXX.png`
- Contiene:
  - Serie temporal completa
  - Zoom a los primeros 10 segundos

### 3. **Archivo Excel**
- Archivo: `datos_sensor_XXXXX.xlsx`
- Hojas:
  - **Datos Completos**: Todos los datos combinados
  - **Resumen**: Métricas y estadísticas

---

## 📊 Cómo Graficar en Excel

Una vez que tengas el archivo `.xlsx`:

1. **Abrir Excel** → Abrir `datos_sensor_XXXXX.xlsx`

2. **Crear Gráfica Rápida:**
   - Selecciona las columnas `timestamp_epoch` y `z_g`
   - Menu: **Insertar** → **Gráfico de Líneas**
   - Excel creará automáticamente la gráfica

3. **Gráfica Personalizada:**
   - Agregar nueva columna para tiempo relativo:
     ```excel
     # En columna D, fila 2:
     =(A2-$A$2)
     # Arrastrar hacia abajo
     ```
   - Seleccionar columna D (tiempo) y columna C (z_g)
   - Insertar gráfico de líneas

4. **Mejorar la Gráfica:**
   - Doble click en eje X → Formato → Cambiar a "Tiempo (segundos)"
   - Doble click en eje Y → Formato → "Aceleración (g)"
   - Agregar título: "Datos de Aceleración - Sensor XXXXX"

---

## 🔍 Verificar Calidad de Datos

### Verificación Manual

```python
# En Python/Jupyter:
import pandas as pd

df = pd.read_excel("datos_sensor_10603.xlsx", sheet_name="Datos Completos")

# Calcular porcentaje capturado
frecuencia = 256  # Hz
duracion = df['timestamp_epoch'].iloc[-1] - df['timestamp_epoch'].iloc[0]
esperadas = int(duracion * frecuencia)
reales = len(df)
porcentaje = (reales / esperadas) * 100

print(f"Esperadas: {esperadas:,}")
print(f"Capturadas: {reales:,}")
print(f"Porcentaje: {porcentaje:.2f}%")
```

### Criterios de Calidad

- **≥ 99%**: ✅ Excelente - Datos completos
- **90-99%**: ⚠️  Bueno - Pérdida menor aceptable
- **< 90%**: ❌ Malo - Pérdida significativa

---

## 🛠️ Troubleshooting

### Error: "No module named 'pandas'"

```bash
pip install pandas matplotlib openpyxl
```

### Error: "No such file or directory"

Verifica que estás en la carpeta raíz del proyecto:
```bash
cd tensiones
python scripts/analizar_csv.py sensor_10603
```

### Los archivos CSV están vacíos

Verifica que el monitoreo corrió correctamente:
```bash
ls -lh data/acceleration/sensor_XXXXX/
```

---

## 💡 Ejemplos Adicionales

### Combinar Datos de Múltiples Sensores

```python
import pandas as pd
from pathlib import Path

# Leer datos de varios sensores
sensores = ["sensor_10603", "sensor_14031"]
datos = {}

for sensor_id in sensores:
    archivos = sorted(Path(f"data/acceleration/{sensor_id}").glob("*.csv"))
    dfs = [pd.read_csv(f) for f in archivos]
    datos[sensor_id] = pd.concat(dfs, ignore_index=True)

# Comparar en una misma gráfica
import matplotlib.pyplot as plt

plt.figure(figsize=(14, 6))
for sensor_id, df in datos.items():
    tiempo = df['timestamp_epoch'] - df['timestamp_epoch'].iloc[0]
    plt.plot(tiempo[:2560], df['z_g'][:2560], label=sensor_id, alpha=0.7)

plt.xlabel('Tiempo (segundos)')
plt.ylabel('Aceleración Z (g)')
plt.title('Comparación de Sensores')
plt.legend()
plt.grid(True, alpha=0.3)
plt.show()
```

### Detectar Frecuencias Dominantes (FFT)

```python
import numpy as np
from scipy import signal

# Calcular FFT
fs = 256  # Frecuencia de muestreo (Hz)
f, Pxx = signal.welch(df['z_g'], fs, nperseg=1024)

# Graficar espectro de potencia
plt.figure(figsize=(10, 6))
plt.semilogy(f, Pxx)
plt.xlabel('Frecuencia (Hz)')
plt.ylabel('PSD (g²/Hz)')
plt.title('Espectro de Potencia')
plt.grid(True)
plt.show()

# Encontrar frecuencia dominante
idx_max = np.argmax(Pxx[1:]) + 1  # Ignorar DC component
freq_dominante = f[idx_max]
print(f"Frecuencia dominante: {freq_dominante:.2f} Hz")
```

---

## 📚 Referencias

- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Matplotlib Gallery](https://matplotlib.org/stable/gallery/index.html)
- [Excel con Python](https://openpyxl.readthedocs.io/)
