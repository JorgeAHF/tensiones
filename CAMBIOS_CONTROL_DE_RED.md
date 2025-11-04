# Cambios Implementados - Control de Red (Estilo SensorConnect)

## Resumen

Se ha reestructurado completamente la aplicación para funcionar de manera similar a SensorConnect de LORD MicroStrain. El sistema ya NO inicia el monitoreo automáticamente, sino que espera configuración manual del usuario.

## Cambios Principales

### 1. Nueva Pestaña: "Control de Red" (Primera pestaña)

**Ubicación**: `app/ui/network_control_tab.py` + `app/ui/dash_app.py`

#### Componentes:
- **Sidebar Izquierdo**: Lista de nodos detectados automáticamente
  - Actualización cada 5 segundos
  - Muestra estado: ACTIVO, IDLE, DESCONECTADO
  - Indicador visual de estado de conexión
  - Información de configuración (frecuencia, ejes)

- **Panel Principal - Base Station Control**:
  - **Botón "Sampling Network"**: Abre modal para configurar e iniciar múltiples nodos
  - **Botón "Set Nodes To Idle"**: Detiene todos los nodos y los pone en modo IDLE

- **Panel de Control Individual** (se muestra al seleccionar un nodo):
  - **Botón "Sample"**: Configura e inicia solo ese nodo
  - **Botón "Set to Idle"**: Detiene ese nodo específico
  - **Botón "Sleep"**: Pone el nodo en modo ultra bajo consumo

### 2. Modal de Configuración de Sampling Network

**Características**:
- Configuración **individual** por nodo (no global)
- Cada nodo puede tener:
  - Frecuencia de muestreo: 128, 256 o 512 Hz
  - Ejes activos: X, Y, Z (checkboxes)
  - Formato de datos: Float (32-bit) o UInt16
- Selección de nodos a iniciar (checkboxes)
- Botón "Apply and Start Network" que:
  1. Configura cada nodo según su configuración
  2. Inicia muestreo sincronizado (Lossless mode)
  3. Guarda datos en CSV e InfluxDB automáticamente

### 3. Pestaña "Gráficas en Tiempo Real" (antes "Acelerómetro")

**Modificaciones**:
- Soporta **múltiples sensores simultáneamente**
- Muestra subplots verticales (uno por cada sensor activo)
- Cada subplot muestra sus ejes configurados (X, Y, Z)
- Altura dinámica según cantidad de sensores (300px por sensor)
- Actualización en tiempo real cada 500ms

### 4. Detección Automática de Nodos

**Funcionamiento**:
- Escaneo cada 5 segundos (dcc.Interval)
- Los nodos nuevos **solo aparecen** en el sidebar
- **NO se inician automáticamente** (requiere configuración manual)
- Detección de nodos desconectados:
  - Si un nodo activo no envía datos por >15s → marcado como "DESCONECTADO"
  - Badge rojo y mensaje de tiempo sin datos
  - El resto de los nodos continúan funcionando normalmente

### 5. Manejo de Formato de Datos

**Implementación**:
- Configuración en `real_mscl_client.py` → método `configure_node()`
- Opciones:
  - **Float (32-bit)**: Precisión completa, calibrado (recomendado)
  - **UInt16**: Menor ancho de banda, datos raw
- Afecta:
  - Transmisión desde el hardware
  - Almacenamiento en CSV
  - Almacenamiento en InfluxDB

### 6. Inicio Manual (NO Automático)

**Cambios en `app/main.py`**:
```python
# ANTES:
manager.start_all()  # Iniciaba automáticamente

# AHORA:
# manager.start_all()  # ← DESHABILITADO
# Sistema espera configuración manual desde UI
```

**Flujo actual**:
1. Aplicación se inicia
2. Se conecta al Gateway
3. Descubre nodos disponibles
4. **ESPERA** a que el usuario configure manualmente
5. Usuario va a "Control de Red" → configura → inicia

### 7. Orden de Pestañas Final

1. **Control de Red** (nueva - principal)
2. **Gráficas en Tiempo Real** (modificada - múltiples sensores)
3. **Tiempo real** (mantener)
4. **Configuración** (mantener)
5. **Análisis Histórico** (mantener - Grafana)

**Eliminadas**:
- ❌ "Red" (funcionalidad movida a "Control de Red")
- ❌ "Configuración de Sensores" (funcionalidad movida a "Control de Red")

## Archivos Modificados

### Nuevos Archivos:
- `app/ui/network_control_tab.py`: Layout de la nueva pestaña

### Archivos Modificados:
1. **`app/ui/dash_app.py`**:
   - Importa `network_control_tab`
   - Agrega nueva pestaña como primera
   - Renombra pestaña Acelerómetro → "Gráficas en Tiempo Real"
   - Implementa 8 callbacks nuevos para Control de Red
   - Modifica callback de acelerómetro para múltiples sensores

2. **`app/main.py`**:
   - Deshabilita `manager.start_all()`
   - Agrega mensajes de log indicando espera de configuración manual

3. **`app/acquisition/stream_manager.py`**:
   - Agrega import `Any` para typing correcto

4. **`app/acquisition/real_mscl_client.py`**:
   - Ya tenía soporte para formato de datos (no requirió cambios)

## Callbacks Implementados

### 1. `update_detected_nodes_list`
- Input: `node-detection-interval` (cada 5s)
- Output: Lista de nodos en sidebar
- Detecta estado de conexión por última muestra

### 2. `toggle_sampling_network_modal`
- Abre/cierra modal de configuración
- Genera tabla de configuración por nodo

### 3. `apply_and_start_sampling_network`
- Configura cada nodo según su configuración
- Inicia muestreo sincronizado
- Guarda configuración en Store

### 4. `set_all_nodes_to_idle`
- Detiene todos los streams
- Llama a `node.setToIdle()` para cada nodo
- Cierra archivos CSV
- Detiene escritura a InfluxDB

### 5. `show_individual_node_controls`
- Muestra panel de control para nodo seleccionado
- Controles: Sample, Set to Idle, Sleep

### 6. `handle_individual_node_actions`
- Maneja acciones individuales por nodo
- Pattern-matching MATCH para nodo específico

### 7. `update_accelerometer` (modificado)
- Genera subplots verticales para todos los sensores activos
- Altura dinámica según cantidad de sensores

## Flujo de Uso

### Escenario 1: Iniciar Sampling Network (múltiples nodos)
1. Ir a pestaña "Control de Red"
2. Esperar detección automática de nodos (máx 5s)
3. Click en "Sampling Network"
4. Configurar cada nodo individualmente:
   - Marcar checkbox para habilitar
   - Seleccionar frecuencia
   - Seleccionar ejes activos
   - Seleccionar formato
5. Click "Apply and Start Network"
6. Ir a "Gráficas en Tiempo Real" para ver datos

### Escenario 2: Iniciar un solo nodo
1. Ir a "Control de Red"
2. Click en "Controlar" del nodo deseado
3. Click en "Sample"
4. Nodo inicia con última configuración guardada

### Escenario 3: Detener todo
1. Ir a "Control de Red"
2. Click en "Set Nodes To Idle"
3. Todos los nodos se detienen
4. Archivos CSV se cierran
5. InfluxDB detiene escritura

### Escenario 4: Modo Sleep individual
1. Seleccionar nodo específico
2. Click en "Sleep"
3. Nodo entra en modo ultra bajo consumo
4. Requiere ciclo de power físico para despertar

## Compatibilidad con Código Existente

✅ **Mantiene**:
- Guardado en CSV (stream_manager.py)
- Guardado en InfluxDB (stream_manager.py)
- Análisis FFT en background
- Cálculo de tensión
- Pestaña "Tiempo real"
- Pestaña "Configuración"
- Pestaña "Análisis Histórico"

❌ **Elimina**:
- Inicio automático al ejecutar la app
- Pestaña "Red" antigua
- Pestaña "Configuración de Sensores" antigua

## Manejo de Errores

### Nodo pierde conexión durante muestreo:
- **Detección**: Si no hay datos por >15 segundos
- **Acción**: Marcado como "DESCONECTADO" en sidebar
- **Comportamiento**: Los demás nodos continúan funcionando
- **UI**: Badge rojo + mensaje "Desconectado (XXs sin datos)"

### Error al configurar nodo:
- Muestra alert de error
- No afecta a otros nodos
- Permite reintentar configuración

### Error al iniciar Sampling Network:
- Muestra nodos exitosos vs fallidos
- Continúa con nodos que sí iniciaron
- Lista errores específicos por nodo

## Notas Técnicas

### Formato de Datos (float vs uint16)
- Se configura en `WirelessNodeConfig` usando:
  - `mscl.WirelessTypes.dataFormat_cal_float` (float)
  - `mscl.WirelessTypes.dataFormat_raw_uint16` (uint16)
- La conversión es manejada por el hardware MSCL
- Los datos ya vienen en el formato correcto al recibirlos

### Sync Sampling Mode
- Todos los nodos se sincronizan con el Base Station
- Timestamp común para todas las muestras
- Modo Lossless habilitado por defecto
- Configurado con `mscl.SyncSamplingNetwork`

### Duración Ilimitada
- Configurado con `node_config.unlimitedDuration(True)`
- Los nodos muestrean continuamente hasta que se detengan manualmente
- NO hay timeout automático

## Pruebas Recomendadas

1. ✅ Detección automática de nodos
2. ✅ Configuración individual por nodo
3. ✅ Inicio de Sampling Network (múltiples nodos)
4. ✅ Inicio individual de nodo
5. ✅ Detención global (Set Nodes To Idle)
6. ✅ Detención individual (Set to Idle)
7. ✅ Modo Sleep
8. ✅ Múltiples gráficas simultáneas
9. ✅ Guardado en CSV
10. ✅ Guardado en InfluxDB
11. ✅ Detección de nodos desconectados
12. ✅ Manejo de errores de configuración

## Comando de Inicio

```powershell
venv\Scripts\activate
python -m app.main
```

**Comportamiento esperado**:
- NO inicia monitoreo automáticamente
- Muestra mensaje en log: "waiting for manual sensor configuration from UI"
- Usuario debe ir a "Control de Red" para configurar e iniciar
