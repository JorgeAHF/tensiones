# Conclusiones: Modo Datalogging G-Link-200

## 📋 Resumen Ejecutivo

**El modo datalogging NO es viable para G-Link-200 via Python/MSCL API.**

## 🔬 Investigación Realizada

### 1. Documentación Oficial LORD MicroStrain
- ✅ Revisado repositorio oficial MSCL en GitHub
- ✅ Consultados ejemplos oficiales de Python
- ❌ **NO existe ejemplo de datalogging para wireless nodes**
- ❌ Solo ejemplos de: SynchronizedSampling, ParseData, ConfigureNode

### 2. API de MSCL
**Métodos explorados:**
```python
node.getDatalogSessionInfos()  # Retorna vacío o no soportado
node.getDatalogData(session)   # No funciona con G-Link-200
```

**Resultado:** Estos métodos existen en MSCL pero NO están soportados para G-Link-200.

### 3. Pruebas Realizadas
**Configuración probada:**
- SensorConnect: Modo "Log" configurado ✅
- App Python: Iniciada con `--datalogging` ✅
- Monitoreo: Ejecutado durante 2+ minutos ✅
- Detener: Presionar "Set nodes to Idle" ✅

**Resultado:**
- ❌ No se descargaron datos
- ❌ No se generaron CSVs
- ❌ `getDatalogSessionInfos()` retorna vacío o error

### 4. Modo "Log" en SensorConnect
**Conclusión:**
- El modo "Log" SÍ existe en SensorConnect
- PERO es solo para uso con **SensorConnect GUI**
- Los datos deben descargarse **manualmente** desde SensorConnect
- NO hay API programática para descarga

## ⚙️ Limitaciones del G-Link-200

### Hardware
| Característica | Soportado | Vía API | Vía SensorConnect |
|----------------|-----------|---------|-------------------|
| Transmisión wireless (Sync) | ✅ SÍ | ✅ SÍ | ✅ SÍ |
| Datalogging en memoria | ✅ SÍ | ❌ NO | ✅ SÍ |
| Descarga programática | ❌ NO | ❌ NO | ✅ SÍ (manual) |

### Comparación con Otros Modelos

**G-Link-200** (actual):
- ❌ Sin descarga programática de logs
- ✅ Transmisión wireless hasta 64 Hz (100% datos)
- ⚠️ Pérdida de datos >64 Hz

**SG-Link-200** (~$1,500-2,000 USD):
- ✅ Descarga programática de logs via API
- ✅ Soporta hasta ~1000 Hz sin pérdida
- ✅ Mayor memoria interna

## 📊 Resultados de Pruebas Exhaustivas

### Modo Transmisión (Actual)
| Frecuencia | Completitud | Viable |
|------------|-------------|--------|
| 32 Hz      | 99.3%       | ✅ SÍ  |
| 64 Hz      | 100%        | ✅ SÍ  |
| 128 Hz     | 66.2%       | ⚠️ Parcial |
| 256 Hz     | ~40%        | ❌ NO  |
| 512+ Hz    | <30%        | ❌ NO  |

### Modo Datalogging (Intentado)
| Acción | Resultado | Notas |
|--------|-----------|-------|
| Configurar en SensorConnect | ✅ OK | Modo "Log" configurado |
| Iniciar app con --datalogging | ✅ OK | Mensaje de activación visible |
| Monitorear | ✅ OK | Sensor guarda en memoria |
| Presionar "Set to Idle" | ⚠️ Tarda | ~1.5 minutos en responder |
| Descargar datos automáticamente | ❌ FALLA | `getDatalogSessionInfos()` vacío |
| Generar CSVs | ❌ FALLA | No hay datos descargados |

## 💡 Solución Adoptada

### Configuración Recomendada

**Hardware:**
- Sensor: G-Link-200 (actual)
- BaseStation: WSDA-2000

**Software:**
```bash
# Modo normal (transmisión en tiempo real)
python -m app.main
```

**SensorConnect:**
- Log/Transmit: **"Transmit"**
- Protocol: **LXRS+** (16,000 samples/s)
- Frecuencia: **64 Hz**

**Resultado:**
- ✅ 100% de datos recibidos
- ✅ Gráficas en tiempo real funcionando
- ✅ CSVs generándose cada 2 minutos
- ✅ Suficiente para análisis de cables (frecuencias <30 Hz)

## 🎯 Justificación Técnica

### ¿Por qué 64 Hz es suficiente?

**Análisis de tensión en cables:**
- Frecuencia fundamental: ~1-10 Hz (según longitud)
- Primer armónico: ~2-20 Hz
- Segundo armónico: ~4-40 Hz
- **Nyquist**: Frecuencia de muestreo ≥ 2× frecuencia máxima

**Conclusión:**
- Frecuencias de interés: <30 Hz
- Frecuencia de muestreo mínima: 60 Hz
- **64 Hz**: Cubre perfectamente el rango necesario

### Ventajas de 64 Hz vs Frecuencias Altas

| Aspecto | 64 Hz | 512+ Hz |
|---------|-------|---------|
| Completitud de datos | 100% ✅ | <30% ❌ |
| Gráficas en tiempo real | ✅ SÍ | ⚠️ Limitado |
| Estabilidad | ✅ Alta | ❌ Baja |
| Análisis válido | ✅ SÍ | ⚠️ Datos incompletos |

## 🚫 Alternativas Descartadas

### 1. Modo Datalogging Programático
**Estado:** ❌ NO VIABLE
**Razón:** G-Link-200 no soporta descarga via API

### 2. Descargar Manualmente desde SensorConnect
**Estado:** ⚠️ POSIBLE pero NO PRÁCTICO
**Razón:**
- Requiere intervención manual
- No es automático
- Interrumpe workflow

### 3. Cambiar a Frecuencias Altas (>64 Hz)
**Estado:** ❌ NO VIABLE
**Razón:**
- Pérdida de datos >50%
- Datos incompletos invalidan análisis
- Hardware no soporta

### 4. Upgrade a SG-Link-200
**Estado:** ⚠️ VIABLE pero COSTOSO
**Razón:**
- Costo: ~$1,500-2,000 USD por sensor
- NO necesario para aplicación actual
- 64 Hz es suficiente

## 📁 Archivos Relacionados

**Documentación:**
- [LIMITACIONES_HARDWARE_GLINK200.md](LIMITACIONES_HARDWARE_GLINK200.md) - Análisis exhaustivo de limitaciones
- [MODO_DATALOGGING.md](MODO_DATALOGGING.md) - Implementación intentada (NO funcional)
- [INSTRUCCIONES_DATALOGGING.md](INSTRUCCIONES_DATALOGGING.md) - Instrucciones (NO aplicables)

**Código:**
- [app/acquisition/real_mscl_client.py](app/acquisition/real_mscl_client.py) - Implementación de datalogging (NO funciona con G-Link-200)
- [test_download_log.py](test_download_log.py) - Script de diagnóstico

**Scripts de Prueba:**
- [test_datalogging_mode.py](test_datalogging_mode.py) - Prueba de datalogging (NO funciona)
- [explore_datalogging_api.py](explore_datalogging_api.py) - Exploración de API
- [check_supported_modes.py](check_supported_modes.py) - Verificación de modos soportados

## ✅ Decisión Final

**Trabajar a 64 Hz en modo Transmisión normal es la solución correcta y suficiente para la aplicación.**

**Razones:**
1. ✅ Captura todas las frecuencias de interés (<30 Hz)
2. ✅ 100% de datos sin pérdida
3. ✅ Estable y confiable
4. ✅ No requiere inversión adicional
5. ✅ Cumple con los requisitos del proyecto

**Modo datalogging:**
- ❌ NO implementar para G-Link-200
- ❌ NO es soportado via API
- ⚠️ Solo disponible manualmente via SensorConnect

---

**Fecha de conclusión:** Noviembre 12, 2025
**Status:** Investigación completada
**Decisión:** Usar modo Transmisión a 64 Hz
