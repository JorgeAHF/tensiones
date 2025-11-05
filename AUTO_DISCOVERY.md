# Auto-Discovery de Sensores Wireless

## 📡 Descripción

La aplicación ahora soporta **detección automática** de sensores G-Link-200 en la red wireless. No es necesario conocer los IDs de los sensores de antemano.

---

## ✨ Funcionalidades Implementadas

### 1. **Auto-Discovery Automático al Iniciar**
Cuando la aplicación inicia, automáticamente escanea y detecta todos los sensores wireless disponibles.

### 2. **Tres Métodos de Detección**

#### Método 1: Beacon Auto-Discovery (Preferido)
```python
node_discoveries = base_station.getNodeDiscoveries()
```
- Los nodos se "auto-anuncian" a la base station
- **Más rápido** y no requiere ping
- Solo detecta nodos activos que están transmitiendo

#### Método 2: Ping de Configuración (Fallback)
```python
# Lee sensores desde stays.yaml y hace ping
```
- Intenta hacer ping a los sensores configurados en `stays.yaml`
- Útil para nodos que no se auto-anuncian
- Garantiza que los sensores conocidos sean detectados

#### Método 3: Scan de Rangos (Opcional)
```python
# Comentado por defecto para velocidad
for node_id in range(10000, 20000, 1000):
    # Ping cada 1000th ID
```
- Escanea rangos de IDs conocidos
- **Comentado por defecto** para evitar lentitud
- Descomenta si necesitas buscar nodos desconocidos

### 3. **Método refresh_nodes()**
Permite re-escanear la red **sin reiniciar la aplicación**:

```python
client.refresh_nodes()  # Re-escanea y detecta nuevos sensores
```

---

## 🎯 Sensores Configurados

Los siguientes sensores están configurados en [`stays.yaml`](app/config/stays.yaml):

| Sensor ID | Stay ID | Descripción |
|-----------|---------|-------------|
| **10603** | sensor_1 | G-Link-200 Acelerómetro #1 |
| **14031** | sensor_2 | G-Link-200 Acelerómetro #2 |

**Nota:** Incluso si agregas más sensores a la red, serán detectados automáticamente sin necesidad de editar el YAML.

---

## 🚀 Cómo Funciona

### Al Iniciar la Aplicación

1. **Auto-Discovery Desde Beacons**
   - La aplicación espera 2 segundos para que los nodos se anuncien
   - Lee los beacons de la base station
   - Extrae: node_address, frequency, RSSI

2. **Ping a Sensores Configurados**
   - Lee `stays.yaml` y hace ping a cada sensor configurado
   - Garantiza que los sensores conocidos sean detectados

3. **Conexión y Registro**
   - Para cada nodo descubierto:
     - Hace ping con 3 reintentos
     - Lee el modelo del sensor
     - Configura para muestreo continuo ilimitado
     - Registra el sensor en la aplicación

### Logs Esperados

```log
================================================================================
AUTO-DISCOVERY: Scanning for wireless nodes...
================================================================================
Method 1: Checking for node discoveries from base station...
Found 2 node(s) via auto-discovery
  - Node 10603: freq=2405, RSSI=-45 dBm
  - Node 14031: freq=2405, RSSI=-48 dBm
Method 2: Pinging nodes from configuration file...

Attempting to connect to 2 discovered node(s)...

--- Connecting to Node 10603 ---
Ping attempt 1/3 for node 10603...
✅ Node 10603 connected! (RSSI Base: -45, Node: -50)
Node 10603 model: node_gLink_200_8g
✅ Node 10603 configured for continuous sampling
✅ Registered sensor 10603 (sensor_1)

--- Connecting to Node 14031 ---
Ping attempt 1/3 for node 14031...
✅ Node 14031 connected! (RSSI Base: -48, Node: -52)
Node 14031 model: node_gLink_200_8g
✅ Node 14031 configured for continuous sampling
✅ Registered sensor 14031 (sensor_2)

================================================================================
AUTO-DISCOVERY COMPLETE: 2 node(s) registered
Nodes: ['10603', '14031']
================================================================================
```

---

## 🧪 Cómo Probar

### 1. **Preparar los Sensores**

Asegúrate de que **ambos sensores estén encendidos** y dentro del rango de la base station:
- Sensor 10603 (ya en uso)
- Sensor 14031 (nuevo)

### 2. **Reiniciar la Aplicación**

```bash
cd c:/Users/cesar/OneDrive/Documents/sensores-tensiones/tensiones

# Detener con Ctrl+C si está corriendo

# Reiniciar
python -m app.main
```

### 3. **Verificar Logs**

Busca en los logs que ambos sensores fueron detectados:

```bash
tail -f data/logs/mscl_tension.log
```

Deberías ver:
```
AUTO-DISCOVERY COMPLETE: 2 node(s) registered
Nodes: ['10603', '14031']
```

### 4. **Verificar en la UI**

1. Abre el dashboard: `http://localhost:8050`
2. Ve a la pestaña **"Control de Red"**
3. Deberías ver **2 nodos** en la lista de "Nodos Detectados":
   - NODO 10603 (IDLE) - sensor_1
   - NODO 14031 (IDLE) - sensor_2

### 5. **Configurar Ambos Sensores**

1. Click en **"Sampling Network"**
2. Verás una tabla con **2 filas** (una para cada sensor)
3. Configura ambos sensores:

   **Sensor 10603:**
   - Frecuencia: 64 Hz
   - Ejes: X, Y, Z
   - Formato: Float

   **Sensor 14031:**
   - Frecuencia: 128 Hz
   - Ejes: X, Y, Z
   - Formato: Float

4. Click **"Apply and Start Network"**

### 6. **Verificar Muestreo Sincronizado**

Ambos sensores deben iniciar en modo SYNC:

```log
[INFO] Node 10603 added to sync network
[INFO] Node 14031 added to sync network
[INFO] Starting SyncSamplingNetwork...
[INFO] ✅ Sync sampling started successfully!
```

### 7. **Verificar CSVs Generados**

```bash
ls -lt data/raw/10603/ | head -5
ls -lt data/raw/14031/ | head -5
```

Deberías ver CSVs para **ambos sensores**:
```
data/raw/10603/20251105.csv    (64 Hz)
data/raw/14031/20251105.csv    (128 Hz)
```

---

## 🔧 Agregar Más Sensores

### Opción 1: Auto-Discovery Automático (Recomendado)
1. Enciende el nuevo sensor
2. Espera ~5 segundos para que se anuncie
3. En la aplicación, llama `refresh_nodes()` (o reinicia)
4. El sensor aparecerá automáticamente

### Opción 2: Agregar al YAML
1. Edita `app/config/stays.yaml`:
```yaml
stays:
- sensor_id: 10603
  stay_id: sensor_1
  # ...
- sensor_id: 14031
  stay_id: sensor_2
  # ...
- sensor_id: NUEVO_ID  # <-- Agregar aquí
  stay_id: sensor_3
  k_coefficient_N_per_Hz2: 1.0
  thresholds_kN:
    green_max: 100.0
    orange_max: 200.0
    yellow_max: 150.0
```

2. Reinicia la aplicación

---

## 🐛 Troubleshooting

### Problema: Solo detecta 1 sensor en lugar de 2

**Posibles causas:**
1. El segundo sensor no está encendido
2. El sensor está fuera de rango
3. El sensor está en modo sleep

**Solución:**
```bash
# Ver logs completos
grep "AUTO-DISCOVERY" data/logs/mscl_tension.log
grep "Ping attempt" data/logs/mscl_tension.log

# Si el sensor no aparece en auto-discovery:
# 1. Verifica que esté encendido (LED parpadeando)
# 2. Acércalo a la base station
# 3. Reinicia el sensor (apagar/encender)
```

### Problema: Sensor detectado pero ping falla

```log
Ping attempt 1/3 for node 14031...
Ping attempt 1 failed: timeout
```

**Solución:**
1. Verifica batería del sensor
2. Acerca el sensor a la base station
3. Reinicia el sensor
4. Verifica que no haya interferencia wireless

### Problema: Sensores detectados pero no inician sampling

```log
❌ Could not start SyncSamplingNetwork
```

**Solución:**
1. Detén todos los sensores: Click "Set Nodes To Idle"
2. Espera 5 segundos
3. Intenta de nuevo

---

## 📊 Información Técnica

### MSCL API Usada

```python
import mscl

# 1. Obtener descubrimientos automáticos
discoveries = base_station.getNodeDiscoveries()

for discovery in discoveries:
    node_address = discovery.nodeAddress()  # int
    frequency = discovery.frequency()       # MHz
    rssi = discovery.rssi()                 # dBm

# 2. Crear nodo wireless
node = mscl.WirelessNode(node_address, base_station)

# 3. Hacer ping
ping_response = node.ping()
rssi_base = ping_response.baseRssi()
rssi_node = ping_response.nodeRssi()

# 4. Obtener información del nodo
model = node.model()  # "node_gLink_200_8g"

# 5. Configurar
config = node.getConfig()
config.unlimitedDuration(True)
node.applyConfig(config)
```

### Archivos Modificados

1. **[app/acquisition/real_mscl_client.py](app/acquisition/real_mscl_client.py)**
   - Líneas 73-188: Implementación de `_initialize_nodes()` con auto-discovery
   - Líneas 190-220: Implementación de `refresh_nodes()`

2. **[app/config/stays.yaml](app/config/stays.yaml)**
   - Líneas 9-15: Agregado sensor 14031

---

## 🎓 Próximos Pasos

### Mejoras Futuras (Opcionales)

1. **UI para Refresh Manual**
   - Agregar botón "Refresh Nodes" en la pestaña "Control de Red"
   - Permite re-escanear sin reiniciar

2. **Notificaciones de Nuevos Sensores**
   - Alert en UI cuando se detecta un nuevo sensor
   - Email/webhook notification

3. **Scan Periódico Automático**
   - Re-escanear cada 5 minutos automáticamente
   - Detectar sensores que se conectan/desconectan

4. **Configuración por Modelo**
   - Auto-configurar según el modelo detectado
   - Diferentes defaults para G-Link-200 vs otros modelos

---

**Fecha:** 2025-11-05
**Branch:** cesar-hardware
**Feature:** Auto-Discovery de Sensores Wireless
