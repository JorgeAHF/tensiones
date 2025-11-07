# G-Link-200 - Limitaciones de Hardware y Configuración

## 📊 Resumen de Cambios Implementados

### ✅ Problema Corregido: Configuración Duplicada

**Problema Original:**
- El método `_configure_and_start_node()` estaba **reconfigurando** el sensor después de que ya se había configurado desde la UI
- Esto causaba que la configuración del usuario fuera sobrescrita por valores por defecto

**Solución Aplicada:**
- Eliminada la reconfiguración duplicada en `_configure_and_start_node()`
- Ahora este método solo **verifica** la configuración y **inicia** el sampling
- La configuración se aplica una sola vez en `configure_node()`

### ✅ Validación de Frecuencias

**Problema Identificado:**
- El hardware G-Link-200 tiene limitaciones documentadas para frecuencias < 32 Hz en modo SYNC con 3 canales

**Solución Aplicada:**
- Agregada validación en `_hz_to_sample_rate_enum()` que advierte si se solicita frecuencia < 32 Hz
- Actualizada la UI para mostrar solo frecuencias válidas (32, 64, 128, 256, 512, 1024, 2048, 4096 Hz)
- Removidas opciones de 1, 2, 4, 8, 16 Hz que no están soportadas en modo SYNC

### ✅ Soporte para Sampling Modes

**Implementación:**
- Agregado parámetro `sampling_mode` en `configure_node()`:
  - `"continuous"`: Muestreo continuo ilimitado (ya funcionaba)
  - `"duration"`: Muestreo por duración específica (soporte básico implementado)
  - `"burst"`: Modo de ráfaga (pendiente implementación completa)
  - `"event"`: Muestreo por eventos (pendiente implementación completa)

---

## 🔍 Limitaciones de Hardware Identificadas

### 1. Formato de Datos en Modo SYNC

**IMPORTANTE:** El G-Link-200 **solo soporta datos calibrados (Float 32-bit)** en modo SYNC.

#### ✅ Formato Soportado
```
Float 32-bit (calibrated) - Datos calibrados en unidades de gravedad (g)
```

#### ❌ Formato NO Soportado
```
UInt16 (raw) - Datos sin calibrar en formato entero de 16 bits
```

**Razón:**
> El modo SYNC Sampling del G-Link-200 está diseñado para transmitir datos calibrados en tiempo real.
> El formato raw (uint16) solo está disponible en otros modos de operación (datalog, armed datalog).

**Comportamiento Observado:**
- Al intentar configurar formato `uint16`, el hardware rechaza la configuración con el error:
  ```
  Invalid Configuration: The Data Format is not supported by this Node
  ```
- La aplicación ahora fuerza automáticamente el formato Float si se solicita uint16

**Solución Implementada:**
- Removida la opción UInt16 de la interfaz web
- Agregada validación que fuerza Float si se solicita uint16
- Documentación clara sobre esta limitación en la UI

---

### 2. Frecuencias de Muestreo en Modo SYNC

Según la documentación de LORD MicroStrain y las pruebas realizadas:

#### ✅ **Frecuencias Completamente Soportadas** (>= 32 Hz)
```
32 Hz, 64 Hz, 128 Hz, 256 Hz, 512 Hz, 1024 Hz, 2048 Hz, 4096 Hz
```

#### ⚠️ **Frecuencias con Limitaciones** (< 32 Hz)
```
1 Hz, 2 Hz, 4 Hz, 8 Hz, 16 Hz
```

**Razón:**
> "Data transfer considerations become relevant when using 3 channels on G-Link-200
> with a sample rate **32Hz and less**"
>
> — LORD MicroStrain User Manual

**Comportamiento Observado:**
- El hardware **ignora** la configuración de frecuencias < 32 Hz
- Por defecto, usa **256 Hz** cuando se solicita una frecuencia no soportada
- Los logs muestran advertencias como: `WARNING: Unsupported sample rate 64Hz, using 256Hz`

---

## 🔧 Cómo Probar las Correcciones

### 1. Probar Frecuencia 32 Hz

```python
# En la interfaz web:
# 1. Ir a "Control de Red"
# 2. Click en "Sampling Network"
# 3. Seleccionar frecuencia: 32 Hz
# 4. Aplicar y ver logs
```

**Resultado Esperado:**
```log
[INFO] Set sample rate: 32.0 Hz (enum: sampleRate_32Hz)
[INFO] Node 10603 current configuration: 32.0Hz (requested: 32.0Hz)
[INFO] ✅ Configuration applied successfully
```

### 2. Probar Frecuencia 64 Hz

```python
# En la interfaz web:
# 1. Ir a "Control de Red"
# 2. Click en "Sampling Network"
# 3. Seleccionar frecuencia: 64 Hz
# 4. Aplicar y ver logs
```

**Resultado Esperado:**
```log
[INFO] Set sample rate: 64.0 Hz (enum: sampleRate_64Hz)
[INFO] Node 10603 current configuration: 64.0Hz (requested: 64.0Hz)
[INFO] ✅ Configuration applied successfully
```

### 3. Probar Frecuencia 128 Hz

```python
# En la interfaz web:
# 1. Ir a "Control de Red"
# 2. Click en "Sampling Network"
# 3. Seleccionar frecuencia: 128 Hz
# 4. Aplicar y ver logs
```

**Resultado Esperado:**
```log
[INFO] Set sample rate: 128.0 Hz (enum: sampleRate_128Hz)
[INFO] Node 10603 current configuration: 128.0Hz (requested: 128.0Hz)
[INFO] ✅ Configuration applied successfully
```

### 4. Verificar Frecuencia Real con FrequencyDetector

El código tiene un detector de frecuencia que mide la frecuencia real de los datos:

```log
[INFO] [FREQ CHECK] Sensor 10603 - Configured: 128.0 Hz, Measured: 127.85 Hz
```

**Interpretación:**
- ✅ Si `Measured` está dentro de ±10% de `Configured`: **Correcto**
- ⚠️ Si `Measured` difiere > 10%: **Problema de hardware o configuración**

---

## 📝 Verificación de Configuración Persistente

### Problema Original
El usuario reportó que SensorConnect era el único que podía configurar correctamente el sensor.

### Verificación Post-Corrección

1. **Configurar desde la App:**
   ```
   Frecuencia solicitada: 128 Hz
   ```

2. **Cerrar la App y Abrir SensorConnect:**
   - ¿SensorConnect muestra 128 Hz?
   - ✅ **SÍ** → La configuración persistió correctamente
   - ❌ **NO** → Aún hay un problema de persistencia

3. **Verificar con MSCL API:**
   ```python
   node = mscl.WirelessNode(10603, base_station)
   actual_rate_enum = node.getSampleRate()
   print(f"Configuración actual: {actual_rate_enum}")
   ```

---

## 🚀 Próximos Pasos (Opcionales)

### 1. Implementar Sampling Modes Completos

Para completar la paridad con SensorConnect, se necesita:

#### **Modo "For X Seconds"** (Duration)
```python
# Ejemplo de implementación en MSCL
node_config = mscl.WirelessNodeConfig()
node_config.unlimitedDuration(False)
node_config.dataCollectionMethod(mscl.WirelessTypes.collectionMethod_logAndTransmit)
# Configurar duración específica (requiere investigación adicional de API)
```

#### **Modo "Bursting Every X Seconds"** (Burst)
```python
# Requiere configuración de:
# - Tamaño de ráfaga (burst size)
# - Intervalo entre ráfagas (burst interval)
node_config.samplingMode(mscl.WirelessTypes.samplingMode_syncBurst)
```

#### **Modo "On Events"** (Event-Driven)
```python
# Requiere configuración de:
# - Trigger type (aceleración, vibración, etc.)
# - Threshold values
node_config.samplingMode(mscl.WirelessTypes.samplingMode_armedDatalog)
```

### 2. Agregar Selección de Protocolo (LXRS vs LXRS+)

```python
# LXRS: Máximo alcance, 4,000 samples/s por canal
# LXRS+: Mayor throughput, 16,000 samples/s por canal

# Esto se configura a nivel de BaseStation, no de nodo individual
base_station.protocol(mscl.WirelessTypes.commProtocol_lxrs)
# o
base_station.protocol(mscl.WirelessTypes.commProtocol_lxrsPlus)
```

---

## 📚 Referencias

### Documentación Oficial
- **LORD MicroStrain G-Link-200 User Manual**
  - Original: `https://www.microstrain.com/sites/default/files/g-link-200_user_manual_8500-0069_rev_k.pdf`
  - Mirror: [HBK MicroStrain Documentation](https://www.hbkworld.com/en/products/instruments/wireless-daq-systems/wireless-nodes/g-link-200)

### Especificaciones Técnicas
- **LXRS Protocol:** 4,000 samples/s por canal, -93.5 dBm Rx sensitivity
- **LXRS+ Protocol:** 16,000 samples/s por canal, -86.5 dBm Rx sensitivity
- **Sincronización:** ±50 µs entre nodos

### Archivos Modificados
1. `app/acquisition/real_mscl_client.py`:
   - Líneas 575-637: Eliminada reconfiguración duplicada
   - Líneas 731-783: Validación de frecuencias
   - Líneas 164-247: Soporte para sampling modes
   - Líneas 248-261: Validación de formato de datos (fuerza Float si se solicita uint16)

2. `app/acquisition/stream_manager.py`:
   - Líneas 411-461: Actualizado método `configure()`

3. `app/acquisition/mscl_client.py`:
   - Líneas 63-72: Actualizada firma de `configure_node()` en interfaz
   - Líneas 113-134: Actualizado `DemoMSCLClient.configure_node()`
   - Líneas 383-409: Actualizado `HttpMSCLClient.configure_node()`

4. `app/ui/dash_app.py`:
   - Líneas 1805-1818: Actualizado dropdown de frecuencias en UI
   - Líneas 610-636: Removida opción UInt16, agregada alerta informativa
   - Líneas 1832-1839: Formato de datos deshabilitado (solo Float soportado)

---

## 🐛 Si Aún Hay Problemas

### Logs a Revisar

Buscar en los logs:

```bash
# Problema de configuración duplicada
grep "IMPORTANTE: Este método NO debe reconfigurar" data/logs/mscl_tension.log

# Advertencias de hardware
grep "HARDWARE LIMITATION" data/logs/mscl_tension.log

# Verificación de frecuencia
grep "FREQ CHECK" data/logs/mscl_tension.log

# Discrepancias
grep "FREQ MISMATCH" data/logs/mscl_tension.log
```

### Diagnóstico con MSCL Script

Crear un script de prueba:

```python
import mscl

connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
base_station = mscl.BaseStation(connection)
node = mscl.WirelessNode(10603, base_station)

# Probar configuración directa
config = mscl.WirelessNodeConfig()
config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
config.sampleRate(mscl.WirelessTypes.sampleRate_128Hz)
config.unlimitedDuration(True)

node.applyConfig(config)

# Verificar
actual = node.getSampleRate()
print(f"Configuración aplicada: {actual}")
```

---

**Generado:** 2025-11-05
**Versión del Proyecto:** cesar-hardware branch
**Hardware:** LORD MicroStrain G-Link-200 (Node 10603)
