# Diagnóstico: Gaps en Transmisión de Datos a 1024 Hz

## 📊 Síntomas Observados

Basado en el log de sesión `session_10603_20251111_125203.log`:

- **Duración total**: 4 minutos 17 segundos (257 segundos)
- **Samples esperados**: 1024 Hz × 257s = 263,168 samples
- **Samples recibidos**: 132,096 samples (50% de lo esperado)
- **Samples perdidos**: 0 (todos los datos recibidos se escribieron correctamente)
- **Frecuencia cuando llegan datos**: 1024 Hz ✓ (correcta)

**Patrón de gaps observado**:
```
12:52:06 → 12:52:07 → 12:52:08 (1 segundo entre writes)
12:52:08 → 12:52:14 (6 segundos de gap)
12:52:14 → 12:52:15 → 12:52:15 (normal)
12:53:21 → 12:53:23 → 12:53:25 (gaps de 2 segundos)
12:54:21 → 12:54:23 → 12:54:25 (gaps de 2 segundos)
12:55:15 → 12:55:19 → 12:55:23 (gaps de 4 segundos)
12:56:03 → 12:56:07 → 12:56:13 (gaps crecientes de 4-6 segundos)
```

**Los gaps aumentan progresivamente con el tiempo** 🚨

## 🔍 Análisis del Código

### Configuración Actual (real_mscl_client.py)

**✅ Correcto:**
- `samplingMode_sync` - Modo sincronizado habilitado
- `unlimitedDuration(True)` - Duración ilimitada configurada
- `lossless(True)` - Modo lossless habilitado en SyncSamplingNetwork
- `activeChannels` - Solo eje Z habilitado (1 canal)
- Throughput: 1024 samples/s << 4000 samples/s (límite LXRS)

**❓ Potencialmente problemático:**
- `base_station.getData(500)` - Timeout de 500ms puede ser insuficiente para grandes ráfagas
- No hay configuración explícita de `defaultMode` (transmit vs. datalogging)
- No se configura `retransmit` explícitamente

## 🎯 Causa Raíz Identificada

### Problema #1: **Modo de Transmisión del Sensor**

El sensor G-Link-200 puede operar en dos modos:
1. **Transmit Mode**: Transmite datos en tiempo real continuamente
2. **Datalogging Mode**: Almacena datos en memoria interna y transmite en ráfagas

**Hipótesis**: El sensor está configurado implícitamente en modo "Datalogging + Burst Transmit" en lugar de "Continuous Transmit", causando:
- Acumulación de datos en buffer interno del sensor
- Transmisión en ráfagas cuando el buffer alcanza cierto nivel
- Gaps cada vez más largos a medida que el buffer se llena más lento (por congestión RF)

### Problema #2: **Duty Cycle de Transmisión**

Según la documentación de LXRS:
- El protocolo usa TDMA (Time Division Multiple Access)
- Cada nodo tiene un "slot" de transmisión asignado
- A altas frecuencias, el duty cycle del radio puede ser limitante

**En sync sampling con 1 sensor a 1024 Hz**:
- Cada sweep contiene ~1-10 samples
- A 1024 Hz, necesita transmitir ~100-1000 sweeps/segundo
- El radio del sensor puede no tener duty cycle suficiente para transmitir continuamente

### Problema #3: **Buffer Overflow en BaseStation**

La línea `self.base_station.getData(500)` con timeout de 500ms puede estar causando pérdida si:
- El BaseStation recibe una ráfaga grande de datos
- El código Python no puede procesar datos tan rápido como llegan
- El buffer del BaseStation se llena y descarta datos antiguos

## 🛠️ Soluciones Propuestas

### Solución 1: **Configurar Modo de Transmisión Explícitamente** (ALTA PRIORIDAD)

Agregar configuración de `defaultMode` al nodo:

```python
# En configure_node(), después de node_config.activeChannels(channels)
try:
    # Configurar modo de transmisión (vs. datalogging)
    node_config.defaultMode(mscl.WirelessTypes.defaultMode_sync)
    LOGGER.info("Set default mode: SYNC (continuous transmit)")
except Exception as e:
    LOGGER.warning(f"Could not set defaultMode: {e}")
```

### Solución 2: **Aumentar Timeout de getData()** (MEDIA PRIORIDAD)

Cambiar el timeout para permitir ráfagas más grandes:

```python
# En _stream_worker(), línea 608
sweeps = self.base_station.getData(2000)  # Aumentar de 500ms a 2000ms
```

### Solución 3: **Configurar Retransmisión** (MEDIA PRIORIDAD)

Asegurar que el modo lossless esté funcionando correctamente:

```python
# En initialize_sync_network(), después de lossless(True)
try:
    # Configurar número de retransmisiones
    for sensor_id in sensor_ids:
        node = self.nodes[sensor_id]
        node_config = node.getConfig()
        node_config.retransmit(mscl.WirelessTypes.retransmission_on)
        node.applyConfig(node_config)
        LOGGER.info(f"Retransmission enabled for node {sensor_id}")
except Exception as e:
    LOGGER.warning(f"Could not configure retransmission: {e}")
```

### Solución 4: **Reducir Frecuencia de Muestreo Temporalmente** (BAJA PRIORIDAD - PRUEBA)

Para confirmar que es un problema de throughput, probar con:
- 512 Hz → ¿Se reduce el problema a la mitad?
- 256 Hz → ¿Desaparecen los gaps?

Si los gaps desaparecen a frecuencias menores, confirma que es un problema de throughput/duty cycle del hardware.

### Solución 5: **Verificar Firmware del Sensor** (INVESTIGACIÓN)

Ejecutar el script de diagnóstico para verificar:
```bash
python diagnose_sensor.py 10603
```

Verificar:
- Versión de firmware
- Modo de transmisión actual
- Estado del buffer interno
- Configuración de duty cycle

## 📋 Plan de Acción Recomendado

### Fase 1: Diagnóstico Adicional (15 minutos)
1. Ejecutar `diagnose_sensor.py 10603` y guardar output
2. Revisar logs del BaseStation para mensajes de buffer overflow
3. Verificar LED del sensor durante gaps (¿parpadea? ¿se apaga?)

### Fase 2: Implementar Soluciones (30 minutos)
1. Implementar Solución 1 (defaultMode)
2. Implementar Solución 2 (timeout getData)
3. Ejecutar prueba de 4 minutos
4. Revisar logs de sesión

### Fase 3: Validación (15 minutos)
1. Si persisten gaps, implementar Solución 3 (retransmit)
2. Si persisten gaps, probar Solución 4 (reducir frecuencia)
3. Si gaps desaparecen con menor frecuencia → problema confirmado de hardware/throughput

### Fase 4: Escalación (si es necesario)
- Contactar soporte técnico de MicroStrain/HBK
- Proporcionar:
  - Logs de sesión
  - Output de diagnose_sensor.py
  - Versión de firmware
  - Configuración exacta utilizada

## 🔗 Referencias

- MSCL API Documentation: https://github.com/LORD-MicroStrain/MSCL
- LXRS Protocol: 4,000 samples/s per channel maximum
- G-Link-200 Datasheet: https://www.microstrain.com/wireless-sensors/g-link-200
- MicroStrain Support: https://support.microstrain.com

## 📝 Notas Adicionales

**Por qué NO es un problema de software**:
- ✅ Todos los samples recibidos se escriben (0% pérdida)
- ✅ La frecuencia de datos escritos es exacta (1024 Hz)
- ✅ Los timestamps están ordenados correctamente
- ✅ El código de logging funciona perfectamente

**Por qué SÍ es un problema de hardware/configuración**:
- ❌ Los datos llegan en ráfagas con gaps
- ❌ Los gaps aumentan progresivamente
- ❌ Solo ~50% de datos esperados llegan
- ❌ El patrón sugiere buffer overflow o duty cycle limitado

---

**Generado**: 2025-11-11
**Autor**: Claude (Análisis de logs y código)
**Próxima acción**: Implementar Solución 1 + 2 y ejecutar nueva prueba
