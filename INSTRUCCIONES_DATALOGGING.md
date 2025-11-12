# Instrucciones Rápidas: Modo Datalogging

## 📋 Resumen

Usa modo datalogging para capturar a frecuencias >64 Hz sin pérdida de datos.

## ⚙️ Setup Inicial (Una Sola Vez)

### 1. Configurar en SensorConnect

**Abrir SensorConnect:**
1. Iniciar aplicación SensorConnect
2. Conectar al BaseStation 177076

**Configurar Nodo en Modo Log:**
1. Click en "Base Station 177076" (panel izquierdo)
2. Click en "Wireless Network" (arriba)
3. En la tabla de nodos:
   - Buscar tu nodo (10603)
   - En columna "**Log/Transmit**", seleccionar dropdown
   - Elegir: **"Log"** (recomendado) o "Log and Transmit"

**Aplicar:**
1. Click en botón verde "**Apply and Start Network**" (abajo a la derecha)
2. Esperar mensaje de confirmación
3. **Cerrar SensorConnect**

✅ Esta configuración se mantiene - solo necesitas hacerlo una vez.

## 🚀 Uso Diario

### 2. Iniciar Aplicación en Modo Datalogging

```bash
python -m app.main --datalogging
```

En la terminal verás:
```
================================================================================
DATALOGGING MODE ENABLED
Data will be logged to sensor memory and downloaded when stopped
Real-time graphs will NOT be available during monitoring
================================================================================
```

### 3. Configurar y Monitorear

**En el navegador (http://localhost:8050):**

1. **Seleccionar sensor**: Nodo 10603
2. **Configurar frecuencia**: 1024 Hz (o la que necesites)
3. **Configurar ejes**: X, Y, Z
4. **Iniciar**: Click en "Start Monitoring"

**Durante el monitoreo:**
- ⚠️ **Gráficas estarán vacías** - esto es NORMAL
- ✅ **LED del sensor parpadeará** - confirma que está guardando datos
- ℹ️ Los datos se guardan en la memoria interna del sensor

### 4. Detener y Descargar

Cuando termines:
1. Click en "**Set nodes to Idle**"
2. Esperar la descarga (verás en terminal):

```
================================================================================
DATALOGGING MODE: Downloading data from sensor 10603...
================================================================================
Downloading datalog data... (this may take several minutes)
Downloaded 245760 data sweeps
Processing downloaded data...
Saved sensor_10603_acceleration_20251112_143025.csv (122880 samples)
Saved sensor_10603_acceleration_20251112_143145.csv (122880 samples)
Generated 2 CSV files in data/acceleration
```

### 5. Resultado

Archivos CSV en `data/acceleration/`:
- Formato: `sensor_10603_acceleration_YYYYMMDD_HHMMSS.csv`
- Cada archivo: 2 minutos de datos
- Estructura idéntica al modo normal

## ⏱️ Tiempos Estimados

| Frecuencia | Duración Test | Tiempo Descarga |
|------------|---------------|-----------------|
| 512 Hz     | 1 hora        | ~1 min          |
| 1024 Hz    | 1 hora        | ~2 min          |
| 2048 Hz    | 30 min        | ~1-2 min        |

## 🔄 Para Volver a Modo Normal

Si quieres volver a modo real-time (gráficas funcionando):

**En SensorConnect:**
1. Cambiar "Log/Transmit" a: **"Transmit"**
2. Apply and Start Network

**Iniciar app normalmente:**
```bash
python -m app.main
```

## ❓ Troubleshooting

### Problema: "No datalog sessions found"

**Solución:**
1. Verificar que el nodo esté configurado en modo "Log" en SensorConnect
2. Verificar que el LED del sensor parpadee durante el monitoreo
3. Si no funciona, reiniciar sensor (quitar/poner batería)

### Problema: Gráficas vacías durante monitoreo

✅ **Esto es normal** en modo datalogging - los datos están en el sensor, no se transmiten wireless.

### Problema: Descarga toma mucho tiempo

✅ **Esto es normal** - esperar pacientemente. No interrumpir la descarga.

## 📞 Resumen Rápido

1. **Setup (una vez)**: SensorConnect → Nodo en modo "Log"
2. **Uso diario**: `python -m app.main --datalogging`
3. **Monitorear**: Iniciar desde UI web (gráficas vacías = OK)
4. **Detener**: "Set nodes to Idle" → Descarga automática
5. **Resultado**: CSVs completos en `data/acceleration/`

---

**Última actualización**: Noviembre 12, 2025
