# 📊 Monitoreo Sin Rotación + División Posterior

Nueva estrategia para capturar **100% de los datos** a altas frecuencias (256 Hz).

## 🎯 Estrategia

**Problema anterior:** La rotación cada 2 minutos bloqueaba la adquisición → pérdida de datos.

**Solución:**
1. Durante el monitoreo: UN SOLO ARCHIVO CSV (sin rotación)
2. Después del monitoreo: Dividir en chunks de 2 minutos con script

**Resultado:** ✅ 100% de datos + Archivos de 2 minutos como antes

---

## 🚀 Nuevo Flujo de Trabajo

### **Paso 1: Limpiar Datos Anteriores** (Solo primera vez)

```bash
# Crear respaldo de monitoreos viejos
mkdir -p data/backup_monitoreos_fallidos
mv data/acceleration/sensor_10603/*.csv data/backup_monitoreos_fallidos/
```

### **Paso 2: Reiniciar Aplicación** (IMPORTANTE)

La nueva configuración requiere reiniciar:

```bash
# Detener la aplicación actual (Ctrl+C)
# Reiniciar
python -m app.main
```

### **Paso 3: Monitorear Normalmente**

1. Configurar sensor en SensorConnect: **256 Hz, modo "Transmit"**
2. En interfaz web: **Start Monitoring**
3. Esperar (5-10 minutos)
4. Detener: **"Set nodes to Idle"**

Durante el monitoreo se creará **UN SOLO archivo CSV grande:**
```
data/acceleration/sensor_10603/
└── sensor_10603_acceleration_20251113_162100_XXXXX.csv  (UN archivo, creciendo)
```

### **Paso 4: Dividir en Chunks de 2 Minutos**

Después de detener el monitoreo:

```bash
# Dividir en chunks de 2 minutos
python scripts/dividir_csv.py sensor_10603

# O personalizar duración de chunks (ej: 5 minutos)
python scripts/dividir_csv.py sensor_10603 --duracion 5
```

**Output:**
```
📂 Procesando: sensor_10603_acceleration_20251113_162100_XXXXX.csv
============================================================
   Leyendo archivo...
   Total de muestras: 76,800
   Duración total: 5.00 minutos
   Dividiendo en chunks de 2.0 minutos...

✅ División completada:
   Total de chunks creados: 3
   Guardados en: data/acceleration/sensor_10603/chunks

   Detalle de chunks:
      sensor_10603_acceleration_162100_000-002min.csv: 30,720 muestras (0-2 min)
      sensor_10603_acceleration_162100_002-004min.csv: 30,720 muestras (2-4 min)
      sensor_10603_acceleration_162100_004-005min.csv: 15,360 muestras (4-5 min)

   Verificación de integridad:
      Muestras originales: 76,800
      Muestras en chunks:  76,800
      ✅ PERFECTO - No se perdieron datos
```

**Archivos generados:**
```
data/acceleration/sensor_10603/
├── sensor_10603_acceleration_20251113_162100_XXXXX.csv  (Archivo COMPLETO original)
└── chunks/
    ├── sensor_10603_acceleration_162100_000-002min.csv  (Chunk 0-2 min)
    ├── sensor_10603_acceleration_162100_002-004min.csv  (Chunk 2-4 min)
    └── sensor_10603_acceleration_162100_004-005min.csv  (Chunk 4-5 min)
```

### **Paso 5: Analizar**

Puedes analizar el archivo completo o los chunks:

```bash
# Analizar archivo completo
python scripts/analizar_csv.py sensor_10603 --graficar --excel

# O analizar chunks individuales
cd data/acceleration/sensor_10603/chunks
python ../../../scripts/analizar_csv.py . --graficar
```

---

## ✅ Ventajas de Este Enfoque

| Aspecto | Antes (rotación cada 2 min) | Ahora (sin rotación) |
|---------|----------------------------|----------------------|
| **Durante monitoreo** | Rotación bloquea adquisición | Sin interrupciones |
| **Pérdida de datos** | ❌ 40-60% perdido | ✅ 0% perdido |
| **Archivos de 2 min** | ✅ Automático | ✅ Generados después |
| **Complejidad** | Media | Baja |
| **Confiabilidad** | ⚠️ Baja | ✅ Alta |

---

## 📊 Ejemplo Completo (10 minutos @ 256 Hz)

### Durante el Monitoreo:
```
4:21 PM - 4:31 PM (10 minutos)
└── sensor_10603_acceleration_20251113_162100_XXXXX.csv
    └── 153,600 muestras (100% capturadas ✅)
```

### Después de Dividir:
```
chunks/
├── sensor_10603_acceleration_162100_000-002min.csv  (30,720 muestras)
├── sensor_10603_acceleration_162100_002-004min.csv  (30,720 muestras)
├── sensor_10603_acceleration_162100_004-006min.csv  (30,720 muestras)
├── sensor_10603_acceleration_162100_006-008min.csv  (30,720 muestras)
└── sensor_10603_acceleration_162100_008-010min.csv  (30,720 muestras)

Total: 153,600 muestras (100% ✅)
```

---

## 🔍 Verificar Integridad

El script de división verifica automáticamente que no se pierdan datos:

```
Verificación de integridad:
   Muestras originales: 153,600
   Muestras en chunks:  153,600
   ✅ PERFECTO - No se perdieron datos
```

Si hay diferencia, el script lo reportará:
```
   ⚠️  Diferencia: 128 muestras
```

---

## 🛠️ Opciones Avanzadas

### Dividir con Duración Personalizada

```bash
# Chunks de 5 minutos
python scripts/dividir_csv.py sensor_10603 --duracion 5

# Chunks de 1 minuto
python scripts/dividir_csv.py sensor_10603 --duracion 1

# Chunks de 30 segundos (0.5 minutos)
python scripts/dividir_csv.py sensor_10603 --duracion 0.5
```

### Dividir Archivo Específico

```bash
# Especificar archivo manualmente
python scripts/dividir_csv.py sensor_10603 --archivo "data/acceleration/sensor_10603/sensor_10603_acceleration_20251113_162100_XXXXX.csv"
```

---

## ❓ Troubleshooting

### Error: "No module named 'pandas'"

```bash
pip install pandas
```

### No se crearon chunks

Verifica que:
1. El archivo CSV existe
2. Tiene columna `timestamp_epoch`
3. Tiene datos

```bash
# Ver primeras líneas del CSV
head -5 data/acceleration/sensor_10603/*.csv
```

### Los chunks tienen menos muestras de las esperadas

Esto es normal si:
- El monitoreo fue más corto que la duración del chunk
- Hubo pausas en la adquisición

El script reportará el número real de muestras por chunk.

---

## 🔄 Volver a la Rotación Automática (Opcional)

Si en el futuro quieres volver a la rotación durante monitoreo:

```yaml
# app/config/app.yaml
rotation:
  minutes: 30  # Cambiar de null a número
  mode: time
```

**Nota:** Con rotación activada volverás a tener pérdida de datos a 256 Hz.

---

## 📚 Scripts Disponibles

1. **`scripts/dividir_csv.py`** - Divide archivos grandes en chunks
2. **`scripts/analizar_csv.py`** - Analiza y grafica datos
3. **`scripts/ejemplo_analisis.py`** - Ejemplos de análisis con Python

Ver `scripts/README.md` para más detalles.
