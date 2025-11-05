# Fix: Soporte para Ejes Individuales

## 🐛 Bug Identificado

El código asumía **siempre 3 canales** (X, Y, Z) al procesar los datos del sensor, incluso cuando se configuraba solo 1 o 2 ejes.

### Problema en el Código

```python
# ❌ ANTES (línea 477)
num_channels = 3  # Hardcoded - SIEMPRE 3

# Esto causaba:
# Si configuraste solo Z (1 canal):
#   len(data) = 1
#   num_samples = 1 // 3 = 0  ← Error!
#   Los datos se descartaban
```

### Logs del Error

```
WARNING: Sweep has 1 data points, expected multiple of 3
```

Esto pasaba porque:
- Usuario configuró: **solo eje Z**
- Sensor envió: **1 valor por sweep**
- Código esperaba: **3 valores** (múltiplo de 3)
- Resultado: `num_samples = 0` → datos descartados → sin CSV

---

## ✅ Solución Implementada

### 1. Calcular Canales Dinámicamente

```python
# ✅ AHORA (línea 479)
num_channels = len(info.axes)  # Dinámico basado en configuración
if num_channels == 0:
    num_channels = 3  # Fallback por seguridad

num_samples = len(data) // num_channels
```

### 2. Parsing Dinámico de Canales

```python
# ✅ AHORA (líneas 495-522)
# Parsear solo los canales configurados
channel_values = []
for ch in range(num_channels):
    channel_values.append(data[idx_base + ch].as_float())

# Construir array [x, y, z] con valores reales o 0.0
x, y, z = 0.0, 0.0, 0.0
axes_lower = [a.lower() for a in info.axes]

for idx, axis in enumerate(axes_lower):
    if axis == 'x':
        x = channel_values[idx]
    elif axis == 'y':
        y = channel_values[idx]
    elif axis == 'z':
        z = channel_values[idx]

# Siempre guardar 3 valores para compatibilidad
accumulated_samples.append([x, y, z])
```

### Ejemplo: Solo Eje Z Configurado

```python
# Configuración:
info.axes = ['z']
num_channels = 1

# Datos del sensor:
sweep.data() = [z_value]

# Procesamiento:
channel_values = [z_value]
x, y, z = 0.0, 0.0, z_value  # Solo Z tiene valor real

# Array guardado:
[0.0, 0.0, z_value]  # X e Y en 0, Z con valor real
```

---

## 🧪 Cómo Probar

### 1. Detener el Muestreo Actual

```
1. Ir a "Control de Red"
2. Click "SET NODES TO IDLE"
3. Esperar confirmación
```

### 2. Reiniciar la Aplicación

```bash
cd c:/Users/cesar/OneDrive/Documents/sensores-tensiones/tensiones
# Detener el servidor (Ctrl+C)
# Reiniciar
python -m app.main
```

### 3. Configurar de Nuevo

```
1. Ir a "Control de Red"
2. Click "Sampling Network"
3. Configurar:
   - Frecuencia: 128 Hz
   - Ejes: Solo Z ✓
4. Click "Apply and Start Network"
```

### 4. Verificar Logs

Buscar en logs que ahora procesa correctamente:

```bash
cd c:/Users/cesar/OneDrive/Documents/sensores-tensiones/tensiones
tail -f data/logs/mscl_tension.log
```

**Antes (Error):**
```
WARNING: Sweep has 1 data points, expected multiple of 3
```

**Ahora (Correcto):**
```
INFO: Received sweep #1 from node 10603: 1 samples, accumulated: 1
INFO: Batch #1: 128 samples, shape (128, 3)
```

### 5. Verificar CSV Generado

```bash
# Buscar CSV recién creado
ls -lt data/csv/
```

Debería ver un archivo nuevo:
```
sensor_10603_20251105_HHMMSS.csv
```

Contenido esperado:
```csv
timestamp,sensor_id,x_g,y_g,z_g,fs_hz
1730822400.0,10603,0.0,0.0,1.234,128.0
1730822400.0078,10603,0.0,0.0,1.235,128.0
...
```

**Nota:** X e Y estarán en 0.0, solo Z tendrá valores reales.

---

## 📊 Impacto de la Corrección

### Antes
- ❌ Solo funcionaba con los 3 ejes (X, Y, Z)
- ❌ Configurar 1 o 2 ejes causaba `num_samples = 0`
- ❌ No se generaban CSVs
- ❌ No aparecían datos en UI

### Ahora
- ✅ Funciona con 1, 2 o 3 ejes
- ✅ `num_samples` se calcula correctamente
- ✅ CSVs se generan con los ejes configurados
- ✅ Los ejes no configurados se rellenan con 0.0
- ✅ Mantiene compatibilidad con código que espera 3 columnas

---

## 🔄 Casos de Uso Soportados

### Solo Z (tu configuración actual)
```python
axes = ['z']
→ Arrays guardados: [0.0, 0.0, z_value]
```

### X y Y
```python
axes = ['x', 'y']
→ Arrays guardados: [x_value, y_value, 0.0]
```

### Los 3 ejes (modo completo)
```python
axes = ['x', 'y', 'z']
→ Arrays guardados: [x_value, y_value, z_value]
```

---

## 📝 Archivos Modificados

1. **[real_mscl_client.py](c:\Users\cesar\OneDrive\Documents\sensores-tensiones\tensiones\app\acquisition\real_mscl_client.py)**
   - Línea 479: `num_channels = len(info.axes)`  (dinámico)
   - Líneas 495-522: Parsing dinámico de canales

---

**Fecha:** 2025-11-05
**Branch:** cesar-hardware
**Issue:** Soporte para configuración de ejes individuales
