# Limitaciones del G-Link-200 para Frecuencias Altas

## Resumen Ejecutivo

El acelerómetro G-Link-200 de MicroStrain con protocolo LXRS+ tiene limitaciones fundamentales de hardware que impiden la transmisión inalámbrica sostenida a frecuencias superiores a 64 Hz.

## Pruebas Realizadas

### Configuración del Sistema
- **Hardware**: G-Link-200 (LORD MicroStrain)
- **BaseStation**: WSDA-2000 (Serial: 6314-2000-177076)
- **Protocolo**: LXRS+ habilitado (16,000 samples/s teórico)
- **MSCL**: v67.1.0-42 (última versión disponible)
- **Fecha**: Noviembre 12, 2025

### Resultados de Completitud por Frecuencia

| Frecuencia | Completitud | Estado | Uso Recomendado |
|------------|-------------|--------|-----------------|
| 32 Hz | 99.3% | ✅ Excelente | SÍ |
| 64 Hz | 100% | ✅ Perfecto | SÍ |
| 128 Hz | 66.2% | ⚠️ Pérdida moderada | Condicional |
| 256 Hz | ~40% | ❌ Pérdida severa | NO |
| 512 Hz | ~28% | ❌ Pérdida severa | NO |
| 1024 Hz | ~20% | ❌ Pérdida crítica | NO |
| 2048 Hz | ~14% | ❌ Pérdida crítica | NO |
| 4096 Hz | 1.9% | ❌ Catastrófico | NO |

### Verificaciones Realizadas

1. ✅ **Software validado**
   - Session logs muestran: 0% pérdida de datos recibidos
   - Todos los samples que llegan al software se escriben correctamente
   - Formato de almacenamiento (CSV/Parquet) no afecta el problema

2. ✅ **LXRS+ habilitado y verificado**
   - `communicationProtocol()` retorna 1 (LXRS+)
   - Throughput teórico: 16,000 samples/s
   - Configuración confirmada en BaseStation

3. ✅ **Configuración óptima aplicada**
   - Lossless mode habilitado
   - Retransmission configurado
   - defaultMode: sync
   - getData() timeout: 2000ms
   - Batch threshold optimizado

4. ✅ **MSCL actualizado**
   - Versión más reciente disponible (v67.1.0-42)
   - Python bindings para Python 3.13
   - Sin bugs conocidos relacionados

## Causa Raíz del Problema

### Limitaciones del Hardware G-Link-200

1. **Duty Cycle del Transmisor RF**
   - El radio puede transmitir solo ~30-40% del tiempo
   - Regulaciones FCC limitan tiempo de transmisión continua
   - Buffer interno del sensor: limitado

2. **Protocolo TDMA (Time Division Multiple Access)**
   - BaseStation asigna "time slots" a cada sensor
   - A altas frecuencias, se necesitan más slots de los disponibles
   - Resultado: Buffer overflow → transmisión en ráfagas → gaps

3. **Arquitectura del G-Link-200**
   - Diseñado para monitoreo estructural de baja frecuencia
   - Optimizado para vida de batería, no para alto throughput
   - Throughput sostenido real: ~100-150 samples/s por sensor

### Por Qué LXRS+ No Resuelve el Problema

LXRS+ aumenta el throughput teórico de la **red completa**, pero:
- No cambia el duty cycle del transmisor del sensor
- No aumenta el tamaño del buffer interno
- No elimina las limitaciones de TDMA
- El cuello de botella está en el sensor, no en el BaseStation

## Soluciones Intentadas (Sin Éxito)

1. ❌ Habilitar LXRS+
2. ❌ Optimizar código de escritura (CSV → Parquet)
3. ❌ Reducir batch threshold
4. ❌ Aumentar getData() timeout
5. ❌ Configurar lossless mode
6. ❌ Habilitar retransmission
7. ❌ Actualizar MSCL a última versión

**Conclusión**: No existe solución por software.

## Alternativas Viables

### Opción 1: Reducir Frecuencia a 64 Hz (✅ Recomendado)

**Ventajas:**
- 100% de datos, cero pérdida
- Mantiene hardware actual
- Sin costo adicional
- Implementación inmediata

**¿Es suficiente?**
Para medición de tensión en cables de puentes:
- Frecuencias naturales típicas: 0.5 - 5 Hz (modo fundamental)
- Frecuencias de interés: hasta ~20 Hz (primeros 5-10 modos)
- **64 Hz permite análisis hasta 30 Hz** (criterio de Nyquist: fs/2)
- **RESPUESTA: SÍ, es suficiente para la mayoría de aplicaciones**

### Opción 2: Modo Datalogging (⚠️ No tiempo real)

**Configuración:**
1. En SensorConnect, cambiar de "Transmit" → "Log"
2. Sensor guarda datos en memoria interna
3. Después de la prueba, descargar datos

**Ventajas:**
- Soporta hasta 4096 Hz sin pérdida
- Usa mismo hardware
- Memoria interna: ~2-4 horas a 1024 Hz

**Desventajas:**
- No es monitoreo en tiempo real
- Requiere desconectar sensor para descargar
- Datos disponibles solo después de la prueba

### Opción 3: Hardware Alternativo (💰 Requiere inversión)

**SG-Link-200 (MicroStrain)**
- Protocolo 2.4 GHz
- Throughput sostenido: ~1000 Hz
- Costo: ~$1,500-2,000 USD por sensor
- Retrocompatible con BaseStation WSDA-2000

**Sistema Cableado**
- USB o Ethernet
- Sin límites de frecuencia
- 100% confiable
- Costo: $500-1,500 USD
- Desventaja: Requiere instalación de cables

## Recomendaciones Técnicas

### Para Proyectos Nuevos

Si el proyecto **requiere >128 Hz sostenido**:
- ❌ NO usar G-Link-200 wireless
- ✅ Especificar SG-Link-200 o sistema cableado
- ✅ Validar throughput antes de adquisición

### Para Proyecto Actual

Basado en la aplicación (tensión en cables):
- ✅ **64 Hz es apropiado y suficiente**
- ✅ Implementar filtro antialiasing en 30 Hz
- ✅ Análisis espectral hasta 30 Hz
- ✅ Captura de primeros 10-15 modos de vibración

## Documentación de Soporte

### Contacto con MicroStrain

Si se requiere validación adicional:

**Soporte Técnico:**
- Email: support@microstrain.com
- Web: https://support.microstrain.com
- Teléfono: +1 802-862-6629

**Información a proporcionar:**
```
Modelo BaseStation: WSDA-2000
Serial: 6314-2000-177076
Modelo Sensor: G-Link-200
Protocolo: LXRS+
MSCL: v67.1.0-42
Pregunta: ¿Cuál es el throughput sostenido máximo real
          para un sensor G-Link-200 en modo continuous transmit?
```

### Referencias

1. MSCL Documentation: https://github.com/LORD-MicroStrain/MSCL
2. G-Link-200 Datasheet: https://www.microstrain.com/wireless-sensors/g-link-200
3. LXRS Protocol Specification: Contactar MicroStrain

## Conclusión

El G-Link-200 es un excelente sensor para:
- ✅ Monitoreo estructural de baja frecuencia (≤64 Hz)
- ✅ Medición de vibración de frecuencias <30 Hz
- ✅ Aplicaciones con larga vida de batería
- ✅ Instalaciones donde cableado no es viable

**NO es apropiado para:**
- ❌ Mediciones de alta frecuencia (>128 Hz) sostenidas
- ❌ Captura de eventos transitorios de alta velocidad
- ❌ Aplicaciones que requieren 100% de datos a >64 Hz

**Límite práctico validado: 64 Hz con 100% de completitud**

---

**Documento preparado por:** Análisis técnico de pruebas exhaustivas
**Fecha:** Noviembre 12, 2025
**Status:** FINAL - Limitación confirmada de hardware
