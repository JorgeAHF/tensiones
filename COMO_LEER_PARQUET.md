# Cómo Leer Archivos Parquet Sin Python

Este documento explica las diferentes formas de leer y graficar datos de archivos Parquet sin necesidad de programar en Python.

## 📊 Opción 1: Convertir a CSV (Más Simple)

### Usar el Script de Conversión

```bash
# Convertir un archivo individual
python convert_parquet_to_csv.py data.parquet

# Convertir todos los archivos de un sensor
python convert_parquet_to_csv.py data/acceleration/sensor_10603/

# Convertir todo incluyendo subdirectorios
python convert_parquet_to_csv.py data/acceleration/ --recursive
```

Una vez convertido a CSV, puedes:
- Abrir en Excel
- Abrir en Google Sheets
- Usar en MATLAB
- Usar en cualquier herramienta de gráficas

## 🔧 Opción 2: Excel con Power Query (Excel 2016+)

Excel puede leer Parquet directamente usando Power Query:

### Pasos:
1. Abrir Excel
2. **Datos → Obtener datos → De archivo → De Parquet**
3. Seleccionar tu archivo `.parquet`
4. Excel carga los datos en una tabla
5. Crear gráficas normalmente

### Ventajas:
- ✅ No necesita conversión
- ✅ Lectura directa muy rápida
- ✅ Actualización automática si cambia el archivo

### Limitaciones:
- ❌ Solo en Excel 2016 o posterior
- ❌ Requiere activar Power Query

## 🗄️ Opción 3: DBeaver (Gratis, Muy Recomendado)

DBeaver es un visor universal de bases de datos que soporta Parquet:

### Instalación:
1. Descargar: https://dbeaver.io/download/
2. Instalar (versión Community Edition es gratis)

### Uso:
1. **File → Open File** → Seleccionar `.parquet`
2. Ver datos en tabla
3. Exportar a CSV: Click derecho → **Export Data**
4. Ejecutar queries SQL sobre los datos

### Ventajas:
- ✅ Completamente gratis
- ✅ Interfaz gráfica muy fácil
- ✅ Puede ejecutar queries (filtros, agregaciones)
- ✅ Exporta a CSV, Excel, JSON, etc.

## 📈 Opción 4: Apache Superset (Para Análisis Avanzado)

Si necesitas dashboards profesionales:

```bash
pip install apache-superset
superset db upgrade
superset fab create-admin
superset init
superset run -p 8088
```

Luego acceder a http://localhost:8088 y conectar tus archivos Parquet.

## 🐍 Opción 5: Jupyter Notebook (Interactivo)

Para análisis exploratorio sin escribir mucho código:

```bash
pip install jupyter pandas pyarrow matplotlib
jupyter notebook
```

Luego en una celda:
```python
import pandas as pd
import matplotlib.pyplot as plt

# Leer datos
df = pd.read_parquet('sensor_10603_acceleration_20251111.parquet')

# Graficar
df.plot(x='timestamp_local', y='az_g', figsize=(15, 5))
plt.show()
```

## 🔄 Opción 6: Configuración Dual

Puedes configurar el sistema para guardar en ambos formatos simultáneamente.

**Ventajas**:
- CSV para análisis rápido
- Parquet para análisis de gran volumen

**Desventaja**:
- Usa el doble de espacio en disco

Para implementar esto, podemos modificar `stream_manager.py` para escribir en ambos formatos.

## 📋 Comparación de Opciones

| Método | Dificultad | Velocidad | Ventajas |
|--------|-----------|-----------|----------|
| **Convertir a CSV** | ⭐ Muy Fácil | ⭐⭐ Media | Compatible con todo |
| **Excel Power Query** | ⭐⭐ Fácil | ⭐⭐⭐ Rápida | Sin conversión |
| **DBeaver** | ⭐⭐ Fácil | ⭐⭐⭐ Rápida | Queries SQL, gratis |
| **Superset** | ⭐⭐⭐ Media | ⭐⭐⭐ Rápida | Dashboards profesionales |
| **Jupyter** | ⭐⭐⭐ Media | ⭐⭐⭐ Rápida | Análisis interactivo |

## 💡 Recomendación

**Para tu caso de uso actual (graficar datos rápidamente)**:

1. **Mantener CSV como formato default** ✅ (Ya configurado)
   - Fácil de abrir en Excel
   - Compatible con todas tus herramientas actuales
   - Sin cambios en tu workflow

2. **Usar Parquet solo para pruebas de alto rendimiento**
   - Cuando hagas pruebas a 1024 Hz y necesites máximo throughput
   - Cambiar temporalmente en `app.yaml`: `format: parquet`
   - Convertir a CSV después con el script si necesitas graficar

3. **Tener el script de conversión disponible**
   - Para cuando uses Parquet y necesites CSV
   - Conversión rápida con un comando

## 🚀 Workflow Recomendado

```bash
# 1. Pruebas normales (usar CSV - default actual)
#    Los archivos se pueden abrir directamente en Excel

# 2. Pruebas de alto rendimiento (cambiar a Parquet)
#    Editar app.yaml: format: parquet
#    Ejecutar prueba a 1024 Hz

# 3. Convertir resultados a CSV para análisis
python convert_parquet_to_csv.py data/acceleration/sensor_10603/ --recursive

# 4. Abrir CSV en Excel y graficar normalmente
```

## 📝 Notas

- **CSV**: Mejor para datasets pequeños (<100 MB), compatibilidad universal
- **Parquet**: Mejor para datasets grandes (>100 MB), análisis de alto rendimiento
- **Ambos formatos tienen las mismas columnas y datos**, solo cambia el formato de almacenamiento
