# PROMPT PARA CLAUDE - Problema con Configuración de Frecuencia de Muestreo en G-Link-200

## 📋 CONTEXTO DEL PROYECTO

Estoy trabajando en un sistema de adquisición de datos de aceleración usando sensores wireless **G-Link-200** de LORD MicroStrain con la librería **MSCL (MicroStrain Communication Library)** en Python.

**Repositorio:** https://github.com/JorgeAHF/tensiones/tree/cesar-hardware
**Rama actual:** `cesar-hardware`
**Commit más reciente:** `84e5c28`

## 🔴 PROBLEMA CRÍTICO IDENTIFICADO

He implementado un sistema de selección dinámica de frecuencia de muestreo (1-512 Hz) en la UI, pero el hardware **NO RESPETA** la configuración solicitada.

### Síntomas del Problema:

1. **La UI permite seleccionar frecuencias dinámicamente** (1, 2, 4, 8, 32, 64, 128, 256, 512 Hz)
2. **El hardware SIEMPRE muestrea a ~256 Hz** sin importar qué frecuencia se configure
3. **`node.getSampleRate()` retorna valores incorrectos** (ej: 105 Hz cuando realmente usa 256 Hz)
4. **Los CSV se guardan con `fs_hz` incorrecta** (dice 105 Hz pero tiene 254 samples/segundo)

### Evidencia Concreta:

```
CONFIGURACIÓN SOLICITADA: 64 Hz
RESPUESTA DEL HARDWARE (node.getSampleRate()): 105 Hz
DATOS REALES EN CSV:
  - Total muestras: 41,790
  - Duración: 164 segundos
  - Frecuencia REAL medida: 254.83 Hz ← ⚠️ SIEMPRE ~256 Hz
  - fs_hz guardado en CSV: 105.0 Hz ← ❌ INCORRECTO
```

Lo mismo ocurre si configuro 128 Hz: el sistema dice "105 Hz" pero sigue guardando 254 Hz.

## 🔍 CÓDIGO RELEVANTE

### Archivo: `app/acquisition/real_mscl_client.py` (Líneas 500-600)

**Configuración del nodo:**
```python
def _configure_and_start_node(self, node, sensor_id, info):
    # ... código previo ...
    
    # PASO 1: Configurar modo SYNC
    node.setSamplingMode(mscl.WirelessTypes.samplingMode_sync)
    
    # PASO 2: Configurar frecuencia de muestreo
    sample_rate_hz = float(info.sample_rate_hz)  # Ej: 64.0
    rate_enum = self._hz_to_sample_rate(sample_rate_hz)  # Convierte a enum
    
    if rate_enum is None:
        LOGGER.warning(f"Unsupported sample rate {sample_rate_hz}Hz, using 256Hz")
        rate_enum = mscl.WirelessTypes.sampleRate_256Hz
    
    node.setSampleRate(rate_enum)  # ← Configura con enum
    
    # PASO 3: Configurar duración ilimitada
    node.setUnlimitedDuration(True)
    
    # PASO 4: VERIFICAR configuración aplicada
    actual_rate = node.getSampleRate()  # ← Retorna int directo
    
    # Mapa para convertir de enum a Hz
    rate_to_hz = {
        mscl.WirelessTypes.sampleRate_64Hz: 64,
        mscl.WirelessTypes.sampleRate_105Hz: 105,  # ← Valor extraño
        mscl.WirelessTypes.sampleRate_128Hz: 128,
        mscl.WirelessTypes.sampleRate_256Hz: 256,
        # ... más valores
    }
    
    actual_rate_hz = rate_to_hz.get(actual_rate, sample_rate_hz)
    
    # AQUÍ es donde detectamos el mismatch
    if actual_rate_hz != sample_rate_hz:
        LOGGER.warning(f"Sample rate mismatch! Requested: {sample_rate_hz}Hz, Hardware using: {actual_rate_hz}Hz")
        # Actualizamos info.sample_rate_hz con el valor "reportado"
        info.sample_rate_hz = float(actual_rate_hz)  # ← Se actualiza a 105
```

**Función de conversión Hz → Enum:**
```python
def _hz_to_sample_rate(self, hz: float) -> Optional[mscl.WirelessTypes.WirelessSampleRate]:
    mapping = {
        1: mscl.WirelessTypes.sampleRate_1Hz,
        2: mscl.WirelessTypes.sampleRate_2Hz,
        4: mscl.WirelessTypes.sampleRate_4Hz,
        8: mscl.WirelessTypes.sampleRate_8Hz,
        16: mscl.WirelessTypes.sampleRate_16Hz,
        32: mscl.WirelessTypes.sampleRate_32Hz,
        64: mscl.WirelessTypes.sampleRate_64Hz,
        128: mscl.WirelessTypes.sampleRate_128Hz,
        256: mscl.WirelessTypes.sampleRate_256Hz,
        512: mscl.WirelessTypes.sampleRate_512Hz,
        1024: mscl.WirelessTypes.sampleRate_1024Hz,
        2048: mscl.WirelessTypes.sampleRate_2048Hz,
        4096: mscl.WirelessTypes.sampleRate_4096Hz,
    }
    return mapping.get(int(hz))
```

### Archivo: `app/acquisition/stream_manager.py` (Líneas 660-680)

**Escritura del CSV:**
```python
# Guardar a CSV
fs_hz = float(sample.fs_hz) if isinstance(sample.fs_hz, str) else sample.fs_hz
dt = 1.0 / fs_hz  # ← Aquí usa fs_hz=105, pero deberían ser 256

for timestamp, x, y, z in batch:
    row = [
        timestamp.isoformat(),
        x, y, z,
        fs_hz,  # ← Escribe 105.0 pero son 256 Hz reales
        sensor_id,
        stay_id
    ]
    writer.writerow(row)
```

## 📚 DOCUMENTACIÓN DISPONIBLE

**Librería MSCL:**
- GitHub: https://github.com/LORD-MicroStrain/MSCL
- Documentación: http://lord-microstrain.github.io/MSCL/Documentation/MSCL%20API%20Documentation/index.html
- Ejemplos Python: https://github.com/LORD-MicroStrain/MSCL/tree/master/MSCL_Examples/Wireless/Python

**Hardware G-Link-200:**
- Datasheet: https://www.microstrain.com/sites/default/files/g-link-200_datasheet_8400-0093_rev_h.pdf
- Manual de usuario: https://www.microstrain.com/support/documentation

## ❓ PREGUNTAS ESPECÍFICAS PARA CLAUDE

1. **¿Por qué `node.getSampleRate()` retorna valores que NO coinciden con el muestreo real?**
   - Configuramos 64 Hz → retorna 105 Hz → pero muestrea a 256 Hz

2. **¿El G-Link-200 tiene restricciones de hardware que no permiten ciertas frecuencias?**
   - ¿Existe documentación sobre frecuencias soportadas en modo SYNC?
   - ¿El valor "105 Hz" es válido? No aparece en el datasheet

3. **¿Hay algún método alternativo en MSCL para:**
   - Verificar la frecuencia REAL de muestreo (no la configurada)
   - Forzar una frecuencia específica
   - Leer las frecuencias soportadas por el nodo

4. **¿Necesito configurar algo adicional antes de `setSampleRate()`?**
   - ¿Hay parámetros de configuración previos?
   - ¿El modo SYNC tiene limitaciones?
   - ¿Necesito llamar a `applyConfiguration()` o similar?

5. **¿Cómo puedo medir la frecuencia REAL directamente desde el hardware?**
   - ¿Hay timestamps nativos del sensor?
   - ¿Los `DataSweep` tienen información de timing precisa?

6. **¿Existe algún callback o evento para detectar cuando el hardware ajusta automáticamente la frecuencia?**

## 🎯 OBJETIVO FINAL

Necesito que el sistema:
1. ✅ Configure el hardware a la frecuencia seleccionada por el usuario
2. ✅ Detecte la frecuencia REAL que usa el hardware (no la reportada incorrectamente)
3. ✅ Guarde los CSV con `fs_hz` correcto (coincidiendo con samples/segundo reales)
4. ✅ Muestre advertencias si la frecuencia solicitada no es soportada

## 📦 ARCHIVOS CLAVE DEL PROYECTO

```
app/acquisition/
  ├── real_mscl_client.py      ← Comunicación con hardware (CRÍTICO)
  ├── stream_manager.py         ← Procesamiento y guardado de datos
  └── streaming_coordinator.py  ← Coordinación de buffers

app/ui/
  └── dash_app.py               ← UI con selección de frecuencias

app/sinks/
  └── csv_writer.py             ← Escritura de CSV
```

## 🔧 AMBIENTE TÉCNICO

- **Python:** 3.13
- **MSCL:** Versión instalada via pip (`mscl`)
- **Hardware:** G-Link-200 (Wireless Accelerometer Node)
- **Modo de operación:** Sync Sampling (múltiples nodos sincronizados)
- **OS:** Windows (PowerShell)

## 💡 INTENTOS PREVIOS

Ya he intentado:
1. ✅ Leer `node.getSampleRate()` después de configurar → retorna valor incorrecto
2. ✅ Verificar con mapeo enum→Hz → el mapeo está correcto
3. ✅ Medir frecuencia real contando samples/tiempo → confirma ~256 Hz siempre
4. ✅ Probar diferentes frecuencias (64, 128) → todas resultan en 256 Hz

## 📝 SOLICITUD PARA CLAUDE

Por favor:

1. **Analiza el problema** basándote en la documentación de MSCL y G-Link-200
2. **Identifica la causa raíz** del mismatch entre configuración, reporte y realidad
3. **Proporciona código Python corregido** para:
   - Configurar correctamente la frecuencia
   - Leer la frecuencia REAL del hardware
   - Validar si una frecuencia es soportada antes de configurar
4. **Sugiere mejoras** al flujo de configuración
5. **Documenta cualquier limitación** del hardware o librería que deba conocer

Si necesitas ver código adicional del repositorio, está disponible en: https://github.com/JorgeAHF/tensiones/tree/cesar-hardware

---

**NOTA:** Este es un proyecto de investigación académica para monitoreo estructural. La precisión de la frecuencia de muestreo es CRÍTICA para análisis espectral y cálculo de tensión en cables.
