# Modo Datalogging - Solución para Frecuencias Altas

## 🎯 Resumen

El **modo datalogging** es la solución para capturar datos a frecuencias altas (>64 Hz) con el G-Link-200, superando las limitaciones de transmisión wireless.

## 🔧 Cómo Funciona

### Modo Normal (Real-Time)
```
Sensor → [Wireless] → BaseStation → Software → CSV (cada 2 min)
                ↑
            Limitado a ~64 Hz
```

### Modo Datalogging
```
Sensor → [Memoria Interna] → Descarga al final → CSV (cada 2 min)
              ↑
          Hasta 4096 Hz sin pérdida
```

## ✅ Ventajas

1. **Sin pérdida de datos** a frecuencias altas (512, 1024, 2048, 4096 Hz)
2. **Sin modificar hardware** - usa mismo G-Link-200 y BaseStation
3. **Configuración programática** - no requiere SensorConnect
4. **CSVs automáticos** - genera archivos de 2 minutos al finalizar
5. **Formato idéntico** - misma estructura de datos que modo real-time

## ⚠️ Desventajas

1. **No hay visualización en tiempo real** - gráficas no funcionan durante monitoreo
2. **Descarga al final** - datos disponibles solo después de detener
3. **Tiempo de descarga** - puede tomar 2-5 minutos por cada hora de datos
4. **Memoria limitada** - ~2-4 horas a 1024 Hz, menos a frecuencias más altas

## 🚀 Uso

### Opción 1: Aplicación Principal

```bash
# Iniciar app en modo datalogging
python -m app.main --datalogging

# O también:
python -m app.main --datalogging --config app/config/app.yaml
```

### Opción 2: Script de Prueba

```bash
python test_datalogging_mode.py
```

## 📊 Workflow

### 1. Iniciar Monitoreo

```bash
python -m app.main --datalogging
```

La app mostrará:
```
================================================================================
DATALOGGING MODE ENABLED
Data will be logged to sensor memory and downloaded when stopped
Real-time graphs will NOT be available during monitoring
================================================================================
```

### 2. Configurar Sensor

En la UI web:
1. Seleccionar sensor
2. Configurar frecuencia (ej: 1024 Hz)
3. Iniciar monitoreo

El log mostrará:
```
Set sampling mode: ARMED DATALOGGING (data stored in sensor memory)
Starting DATALOGGING for node 10603...
Data is being stored in sensor memory (not transmitted)
SUCCESS: Datalogging started for node 10603
```

### 3. Monitorear

Durante el monitoreo:
- **Gráficas**: Estarán vacías/congeladas (es normal)
- **LED del sensor**: Parpadeará indicando que está guardando datos
- **Duración**: Hasta ~2-4 horas dependiendo de frecuencia

### 4. Detener y Descargar

Click en "Set nodes to Idle" o detener monitoreo.

El log mostrará:
```
================================================================================
DATALOGGING MODE: Downloading data from sensor 10603...
================================================================================
Stopping datalogging on node 10603...
Getting datalog session info...
Found 1 datalog session(s)
Downloading datalog data... (this may take several minutes)
Downloaded 245760 data sweeps
Processing downloaded data...
Parsed 245760 samples total
Total recording duration: 240.0 seconds (4.0 minutes)
Saved sensor_10603_acceleration_20251112_143025.csv (122880 samples)
Saved sensor_10603_acceleration_20251112_143145.csv (122880 samples)
Generated 2 CSV files in data/acceleration
================================================================================
DATALOG DOWNLOAD AND PROCESSING COMPLETED
================================================================================
```

### 5. Archivos Generados

Los CSVs se guardan en `data/acceleration/`:
```
data/acceleration/
├── sensor_10603_acceleration_20251112_143025.csv  (primeros 2 min)
├── sensor_10603_acceleration_20251112_143145.csv  (siguientes 2 min)
└── ...
```

Formato de cada CSV:
```csv
timestamp,x,y,z
1731434425.123,0.012,-0.008,1.002
1731434425.124,0.011,-0.007,1.001
...
```

## 📋 Frecuencias Soportadas

| Frecuencia | Memoria | Duración Máxima | Recomendado |
|------------|---------|-----------------|-------------|
| 512 Hz     | ~8 MB/h | ~4-6 horas      | ✅ SÍ       |
| 1024 Hz    | ~16 MB/h| ~2-4 horas      | ✅ SÍ       |
| 2048 Hz    | ~32 MB/h| ~1-2 horas      | ⚠️ Condicional |
| 4096 Hz    | ~64 MB/h| ~30-60 min      | ⚠️ Condicional |

## 🔍 Troubleshooting

### Problema: "No datalog sessions found"

**Causa**: El sensor no inició el datalogging correctamente.

**Solución**:
1. Verificar LED del sensor (debe parpadear durante logging)
2. Reiniciar sensor (quitar/poner batería)
3. Volver a configurar y iniciar

### Problema: Descarga toma mucho tiempo

**Causa**: Gran cantidad de datos acumulados.

**Solución**:
- Es normal, esperar pacientemente
- A 1024 Hz, 1 hora = ~2-3 minutos de descarga
- NO interrumpir la descarga

### Problema: "Memory full" en sensor

**Causa**: Memoria del sensor llena.

**Solución**:
1. Detener y descargar datos actuales
2. Borrar sesiones antiguas del sensor
3. Reducir duración de monitoreo
4. Considerar frecuencia más baja

## 🆚 Comparación de Modos

| Característica | Modo Real-Time | Modo Datalogging |
|----------------|----------------|------------------|
| **Frecuencia máxima** | 64 Hz (100% datos) | 4096 Hz (100% datos) |
| **Gráficas en vivo** | ✅ SÍ | ❌ NO |
| **Datos al final** | ✅ SÍ (durante) | ✅ SÍ (después) |
| **Duración** | Ilimitada | ~2-4 horas |
| **Descarga** | No necesaria | Automática |
| **Formato CSVs** | ✅ Idéntico | ✅ Idéntico |

## 📝 Recomendaciones

### Cuándo Usar Modo Datalogging

✅ **SÍ usar** cuando:
- Necesitas >64 Hz (128, 256, 512, 1024, 2048, 4096 Hz)
- No necesitas ver datos en tiempo real
- Duración del test es <4 horas
- Quieres 100% de datos sin pérdida

❌ **NO usar** cuando:
- 64 Hz o menos es suficiente (usa modo normal)
- Necesitas gráficas en tiempo real
- Monitoreo de larga duración (>4 horas)
- Necesitas reaccionar a eventos en tiempo real

### Mejores Prácticas

1. **Prueba primero**: Usar `test_datalogging_mode.py` para validar
2. **Duración controlada**: No exceder 2-4 horas por sesión
3. **Verificar memoria**: Revisar capacidad disponible antes de test largo
4. **Backup**: Descargar datos inmediatamente después de cada test
5. **Limpiar**: Borrar sesiones antiguas del sensor regularmente

## 🔗 Referencias

- [LIMITACIONES_HARDWARE_GLINK200.md](LIMITACIONES_HARDWARE_GLINK200.md) - Explicación técnica de limitaciones
- [test_datalogging_mode.py](test_datalogging_mode.py) - Script de prueba standalone
- [app/acquisition/real_mscl_client.py](app/acquisition/real_mscl_client.py) - Implementación

## 💡 Ejemplo Completo

### Caso de Uso: Captura a 1024 Hz por 30 minutos

```bash
# 1. Iniciar app en modo datalogging
python -m app.main --datalogging

# 2. En navegador: http://localhost:8050
#    - Seleccionar sensor 10603
#    - Configurar: 1024 Hz, ejes X,Y,Z
#    - Click "Start Monitoring"

# 3. Esperar 30 minutos
#    (LED del sensor parpadeando = OK)

# 4. Click "Set nodes to Idle"

# 5. Esperar descarga (~1-2 minutos)

# 6. Resultado: 15 archivos CSV de 2 min cada uno
#    data/acceleration/sensor_10603_acceleration_*.csv
#    Total: 1,843,200 muestras (30 min × 60 s/min × 1024 Hz)
```

## ✨ Conclusión

El modo datalogging resuelve completamente las limitaciones de transmisión wireless del G-Link-200, permitiendo capturar datos a frecuencias altas (hasta 4096 Hz) sin pérdida, a cambio de no tener visualización en tiempo real.

**Para tensión en cables** (frecuencias de interés <30 Hz):
- Si 64 Hz es suficiente → Usar modo normal (real-time)
- Si necesitas >64 Hz para análisis detallado → Usar modo datalogging

---

**Fecha**: Noviembre 12, 2025
**Versión**: 1.0
**Status**: Implementado y probado
