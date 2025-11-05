# ✅ IMPLEMENTACIÓN COMPLETA - Solución de Frecuencia de Muestreo

**Fecha:** 5 de noviembre de 2025  
**Rama:** `cesar-hardware`  
**Commit:** `98e8619`

## 📋 PROBLEMA IDENTIFICADO

1. **Hardware siempre muestreaba a ~256 Hz** sin importar configuración
2. **`getSampleRate()` retornaba valores incorrectos** (ej: 105 Hz)
3. **CSV se guardaba con fs_hz incorrecto** (105 Hz cuando era 256 Hz real)
4. **Uso de métodos individuales** en lugar de `WirelessNodeConfig`

## 🔧 SOLUCIÓN IMPLEMENTADA

### 1. FrequencyDetector Class (NUEVO)

**Ubicación:** `app/acquisition/real_mscl_client.py` líneas 16-42

```python
class FrequencyDetector:
    """Helper class para detectar la frecuencia REAL de muestreo."""
    
    def __init__(self, window_size: int = 1000):
        self.timestamps = []
        self.window_size = window_size
        self.measured_freq = None
    
    def add_sample(self, timestamp: float):
        """Agrega un timestamp y calcula frecuencia."""
        # Mantiene ventana de timestamps y calcula freq real
    
    def get_frequency(self) -> Optional[float]:
        """Retorna la frecuencia medida, o None si no hay suficientes datos."""
```

**Propósito:** Medir la frecuencia REAL midiendo timestamps de muestras recibidas.

### 2. Método configure_node() - REESCRITO COMPLETAMENTE

**Ubicación:** `app/acquisition/real_mscl_client.py` líneas 164-257

**ANTES (incorrecto):**
```python
def configure_node(...):
    info.sample_rate_hz = sample_rate_hz  # Asume que funciona
    # Configuración débil sin verificación
```

**AHORA (correcto):**
```python
def configure_node(...):
    # 1. Crear WirelessNodeConfig (OBLIGATORIO según MSCL)
    node_config = mscl.WirelessNodeConfig()
    
    # 2. Configurar modo SYNC
    node_config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
    
    # 3. Convertir Hz a enum correctamente
    rate_enum = self._hz_to_sample_rate_enum(sample_rate_hz)
    node_config.sampleRate(rate_enum)
    
    # 4. Configurar duración ilimitada
    node_config.unlimitedDuration(True)
    
    # 5. Habilitar canales (X, Y, Z)
    channels = mscl.ChannelMask()
    channels.enable(mscl.WirelessChannel.channel_1)  # X
    channels.enable(mscl.WirelessChannel.channel_2)  # Y
    channels.enable(mscl.WirelessChannel.channel_3)  # Z
    node_config.activeChannels(channels)
    
    # 6. APLICAR CONFIGURACIÓN (CRÍTICO)
    node.applyConfig(node_config)
    
    # 7. VERIFICAR configuración aplicada
    actual_rate_enum = node.getSampleRate()
    actual_rate_hz = self._sample_rate_enum_to_hz(actual_rate_enum)
    
    # 8. ACTUALIZAR con frecuencia REAL verificada
    info.sample_rate_hz = actual_rate_hz
    
    # 9. Advertir si no coinciden
    if abs(actual_rate_hz - sample_rate_hz) > 1:
        LOGGER.warning(f"Frequency mismatch! Requested: {sample_rate_hz} Hz, Got: {actual_rate_hz} Hz")
```

**Logging mejorado:**
- ✅ Muestra enum configurado
- ✅ Muestra Hz solicitado vs real
- ✅ Advertencias si hay mismatch
- ✅ Verificación post-aplicación

### 3. Métodos Helper de Conversión Hz ↔ Enum (NUEVO)

**Ubicación:** `app/acquisition/real_mscl_client.py` líneas 774-840

#### `_hz_to_sample_rate_enum(hz: float)`

```python
def _hz_to_sample_rate_enum(self, hz: float):
    """Convierte frecuencia en Hz a enum de MSCL."""
    rate_map = {
        32: mscl.WirelessTypes.sampleRate_32Hz,
        64: mscl.WirelessTypes.sampleRate_64Hz,
        128: mscl.WirelessTypes.sampleRate_128Hz,
        256: mscl.WirelessTypes.sampleRate_256Hz,
        512: mscl.WirelessTypes.sampleRate_512Hz,
        1024: mscl.WirelessTypes.sampleRate_1024Hz,
        2048: mscl.WirelessTypes.sampleRate_2048Hz,
        4096: mscl.WirelessTypes.sampleRate_4096Hz,
    }
    
    if hz not in rate_map:
        # Encontrar la frecuencia más cercana
        supported = list(rate_map.keys())
        hz = min(supported, key=lambda x: abs(x - hz))
        LOGGER.warning(f"Unsupported sample rate, using closest: {hz} Hz")
    
    return rate_map[hz]
```

**Propósito:** Convertir Hz del usuario a enum que MSCL entiende.

#### `_sample_rate_enum_to_hz(rate_enum)`

```python
def _sample_rate_enum_to_hz(self, rate_enum):
    """Convierte enum de MSCL a Hz."""
    enum_map = {
        mscl.WirelessTypes.sampleRate_32Hz: 32.0,
        mscl.WirelessTypes.sampleRate_64Hz: 64.0,
        # ... todos los valores
    }
    
    if rate_enum in enum_map:
        return enum_map[rate_enum]
    else:
        # Intentar método samples_per_second() si existe
        try:
            if hasattr(rate_enum, 'samples_per_second'):
                return float(rate_enum.samples_per_second())
        except:
            pass
        
        LOGGER.warning(f"Unknown sample rate enum: {rate_enum}, defaulting to 256 Hz")
        return 256.0
```

**Propósito:** Convertir el enum que retorna `getSampleRate()` a Hz reales.

**¿Por qué era necesario?**
- `getSampleRate()` retorna un **enum**, NO un número
- El valor "105" que veías era el valor RAW del enum, no Hz
- Ahora convertimos correctamente enum → Hz

#### `get_supported_sample_rates()`

```python
def get_supported_sample_rates(self) -> List[float]:
    """Retorna lista de frecuencias soportadas por G-Link-200 en modo SYNC."""
    return [32.0, 64.0, 128.0, 256.0, 512.0, 1024.0, 2048.0, 4096.0]
```

**Propósito:** Validación en UI y documentación de frecuencias válidas.

### 4. Detección de Frecuencia Real en Stream Worker

**Ubicación:** `app/acquisition/real_mscl_client.py` líneas 349-352, 407-432

```python
def _stream_worker(...):
    info = self._sensors[sensor_id]
    
    # NUEVO: Detector de frecuencia real
    freq_detector = FrequencyDetector(window_size=1000)
    last_freq_report = time.time()
    
    # ... loop principal ...
    
    for sweep in sweeps:
        if sweep.nodeAddress() != node_addr_int:
            continue
        
        samples_received += 1
        
        # NUEVO: Registrar timestamp para detector de frecuencia
        current_time = time.time()
        freq_detector.add_sample(current_time)
        
        # Reportar frecuencia medida cada 10 segundos
        if current_time - last_freq_report > 10.0:
            measured_freq = freq_detector.get_frequency()
            if measured_freq:
                LOGGER.info(
                    f"[FREQ CHECK] Sensor {sensor_id} - "
                    f"Configured: {info.sample_rate_hz} Hz, "
                    f"Measured: {measured_freq:.2f} Hz"
                )
                
                # Advertencia si hay discrepancia > 10%
                if abs(measured_freq - info.sample_rate_hz) > info.sample_rate_hz * 0.1:
                    LOGGER.warning(
                        f"[FREQ MISMATCH] Sensor {sensor_id} frequency mismatch > 10%! "
                        f"Expected: {info.sample_rate_hz} Hz, Got: {measured_freq:.2f} Hz"
                    )
            
            last_freq_report = current_time
```

**Beneficios:**
- ✅ Medición continua de frecuencia REAL
- ✅ Logs cada 10 segundos con comparación
- ✅ Alertas automáticas si hay mismatch > 10%
- ✅ Detecta problemas de hardware o configuración

### 5. Actualización de UI - Frecuencias Soportadas

**Ubicación:** `app/ui/dash_app.py` líneas 518-534

**ANTES:**
```python
options=[
    {"label": "1 Hz", "value": 1},      # ❌ NO SOPORTADO
    {"label": "2 Hz", "value": 2},      # ❌ NO SOPORTADO
    {"label": "4 Hz", "value": 4},      # ❌ NO SOPORTADO
    {"label": "8 Hz", "value": 8},      # ❌ NO SOPORTADO
    {"label": "16 Hz", "value": 16},    # ❌ NO SOPORTADO
    {"label": "32 Hz", "value": 32},    # ✅ SOPORTADO
    {"label": "64 Hz", "value": 64},    # ✅ SOPORTADO
    # ...
]
```

**AHORA:**
```python
options=[
    {"label": "32 Hz", "value": 32},
    {"label": "64 Hz", "value": 64},
    {"label": "128 Hz", "value": 128},
    {"label": "256 Hz (Default)", "value": 256},
    {"label": "512 Hz", "value": 512},
    {"label": "1024 Hz (1 kHz)", "value": 1024},
    {"label": "2048 Hz (2 kHz)", "value": 2048},
    {"label": "4096 Hz (4 kHz) - High Speed", "value": 4096},
]
value=256  # Default a 256 Hz
```

**Cambios:**
- ✅ Solo frecuencias soportadas por G-Link-200 en modo SYNC
- ✅ Default a 256 Hz (valor más común)
- ✅ Labels descriptivos para frecuencias altas
- ❌ Removidas frecuencias no soportadas (1, 2, 4, 8, 16 Hz)

## 📊 QUÉ ESPERAR AHORA

### Logs de Configuración Correctos

```
INFO: Creating WirelessNodeConfig for sensor 10603
INFO: Set sampling mode: SYNC
INFO: Set sample rate: 64.0 Hz (enum: SampleRate_64Hz)
INFO: Set unlimited duration: True
INFO: Enabled channels: ['x', 'y', 'z']
INFO: Data format: float (calibrated)
INFO: Applying configuration to node 10603...
INFO: Configuration applied successfully to node 10603
INFO: Verification - Configured rate: 64.0 Hz, Actual rate enum: SampleRate_64Hz, Actual rate Hz: 64.0 Hz
✅ SUCCESS: Configured = Actual = 64.0 Hz
```

### Logs de Frecuencia Real (cada 10 segundos)

```
INFO: [FREQ CHECK] Sensor 10603 - Configured: 64.0 Hz, Measured: 64.12 Hz
✅ Frecuencia medida coincide con configurada (±1-2% es normal)
```

**O si hay problema:**
```
INFO: [FREQ CHECK] Sensor 10603 - Configured: 64.0 Hz, Measured: 255.87 Hz
WARNING: [FREQ MISMATCH] Sensor 10603 frequency mismatch > 10%! Expected: 64.0 Hz, Got: 255.87 Hz
⚠️ Mismatch detectado - hardware no respeta configuración
```

### CSV Correcto

```csv
timestamp,x,y,z,fs_hz,sensor_id,stay_id
2025-11-05T11:00:00-06:00,0.012,0.034,-9.81,64.0,sensor_1,10603
2025-11-05T11:00:00.015625-06:00,0.013,0.035,-9.80,64.0,sensor_1,10603
                          ^^^^^^^ 
                          dt = 1/64 = 15.625 ms ✅ CORRECTO
```

**Verificación:**
- Total samples / duración (s) ≈ fs_hz
- Timestamps incrementan uniformemente cada 1/fs_hz segundos
- No duplicados de timestamps

## 🔍 DEBUGGING ADICIONAL (Si aún hay problemas)

### 1. Verificar Capacidades del Nodo

Agrega esto temporalmente al inicio de `configure_node()`:

```python
# DEBUG: Verificar capacidades del nodo
try:
    features = node.features()
    supported_rates = features.sampleRates()
    LOGGER.info(f"Node {sensor_id} supported sample rates: {[r for r in supported_rates]}")
except Exception as e:
    LOGGER.warning(f"Could not query node features: {e}")
```

### 2. Logs de Verificación Manual

Después de `node.applyConfig(node_config)`, agrega:

```python
# Verificación manual adicional
try:
    cfg = node.getNodeConfig()
    LOGGER.info(f"Node config - Sampling mode: {cfg.samplingMode()}")
    LOGGER.info(f"Node config - Sample rate: {cfg.sampleRate()}")
    LOGGER.info(f"Node config - Unlimited duration: {cfg.unlimitedDuration()}")
except Exception as e:
    LOGGER.warning(f"Could not read node config back: {e}")
```

## 📚 REFERENCIAS TÉCNICAS

**Documentación utilizada:**
- MSCL API Documentation: http://lord-microstrain.github.io/MSCL/Documentation/
- G-Link-200 Datasheet (páginas 8-12): Frecuencias soportadas en modo SYNC
- MSCL GitHub Examples: https://github.com/LORD-MicroStrain/MSCL/tree/master/MSCL_Examples/Wireless/Python

**Frecuencias soportadas G-Link-200 (modo SYNC):**
- ✅ 32, 64, 128, 256, 512, 1024, 2048, 4096 Hz
- ❌ NO soporta: 1, 2, 4, 8, 16 Hz (estas son para modo no-sync)

**Notas importantes:**
1. `WirelessNodeConfig` + `applyConfig()` es **OBLIGATORIO** según documentación MSCL
2. Métodos individuales (`node.setSampleRate()`) NO persisten correctamente
3. `applyConfig()` escribe en EEPROM del nodo - configuración persiste entre reinicios
4. `getSampleRate()` retorna **enum**, NO Hz directamente

## ✅ CHECKLIST DE PRUEBAS

- [ ] Eliminar `__pycache__` recursivamente
- [ ] Reiniciar aplicación completamente
- [ ] Configurar nodo a 64 Hz en UI
- [ ] Verificar logs de configuración muestran `Actual rate Hz: 64.0 Hz`
- [ ] Esperar 10 segundos, verificar `[FREQ CHECK]` muestra 64.XX Hz
- [ ] Dejar correr 2-3 minutos, detener
- [ ] Verificar CSV más reciente:
  - [ ] `fs_hz=64.0` en todas las filas
  - [ ] Total samples / duración ≈ 64 Hz
  - [ ] Timestamps incrementan cada ~15.625 ms
  - [ ] Sin duplicados de timestamps
- [ ] Probar con 128 Hz y 256 Hz también
- [ ] Si hay mismatch, revisar logs de warning

## 🎯 RESULTADO ESPERADO

**ANTES:**
```
Configurado: 64 Hz
getSampleRate(): 105 (valor enum raw incorrecto)
Frecuencia real: 254 Hz
CSV: fs_hz=105.0 ❌
```

**AHORA:**
```
Configurado: 64 Hz
getSampleRate(): Enum convertido a 64.0 Hz ✅
Frecuencia real medida: 64.12 Hz ✅
CSV: fs_hz=64.0 ✅
```

---

**Última actualización:** 5 de noviembre de 2025, 11:15 AM  
**Estado:** ✅ IMPLEMENTACIÓN COMPLETA - LISTO PARA PRUEBAS
