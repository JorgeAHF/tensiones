# MSCL Tension Platform

Plataforma integral en Python para adquirir aceleraciones de nodos MicroStrain (modo demo incluido), estimar tensión de tirantes en tiempo real a partir de la frecuencia fundamental y visualizar resultados en una UI basada en Dash.

## Características

- Descubrimiento, alta manual, configuración y control de nodos (modo demo con señales sintéticas).
- Adquisición continua XYZ, buffers deslizantes y reconexión automática.
- Procesamiento espectral configurable (filtros, Welch, modo AUTO/GUIADO, armónicos, QA).
- Estimación de tensión usando coeficientes K o parámetros físicos opcionales.
- Gestión de gateway MSCL por TCP/IP con control de conexión desde la UI.
- Edición directa de Fs, tipo de dato y duración de adquisición por sensor desde la pestaña de red.
- UI en Dash con pestañas para red, monitoreo en tiempo real, histórico y configuración.
- Registro de CSV para aceleración y tensión con rotación por tiempo o tamaño.
- Configuraciones persistentes en `app/config/app.yaml` y `app/config/stays.yaml`.
- Pruebas unitarias para espectro, tensión y escritura de CSV.

## Requisitos

- Python 3.10+
- Dependencias listadas en `requirements.txt` (`pip install -r requirements.txt`).
- (Opcional) SDK MSCL para hardware real. En esta entrega se incluye modo demo. Documente la instalación de MSCL según la plataforma:
  - **Windows**: Instalar el paquete HBK MSCL y agregar la ruta de la DLL a `PATH`.
  - **Linux**: Instalar las librerías MSCL y exportar `LD_LIBRARY_PATH` con la ruta de `libmscl.so`.

## Estructura

```
mscl-tension-platform/
├─ app/
│  ├─ acquisition/
│  ├─ analysis/
│  ├─ sinks/
│  ├─ ui/
│  ├─ utils/
│  ├─ config/
│  └─ main.py
├─ data/
│  ├─ acceleration/
│  └─ tension/
├─ tests/
├─ requirements.txt
├─ .env.example
└─ README.md
```

## Configuración

- `app/config/app.yaml`: parámetros globales (Fs por defecto, análisis, filtros, almacenamiento, UI, modo demo, gateway).
- `app/config/stays.yaml`: mapeo `stay_id ↔ sensor_id`, coeficientes K y límites de semáforo.

Puede editar estos valores desde la pestaña **Configuración** de la UI y guardar para persistir los cambios.

## Ejecución

1. Crear entorno virtual y activar.
2. Instalar dependencias: `pip install -r requirements.txt`.
3. Ejecutar en modo demo:

```bash
python -m app.main
```

La aplicación levanta un servidor Dash en `http://0.0.0.0:8050`.

### Guía "for dummies" para el modo demo

1. **Instala Python** (>=3.10) y, si no tienes experiencia con entornos virtuales, abre una terminal y ejecuta `python -m venv venv` seguido de `source venv/bin/activate` (Linux/macOS) o `venv\Scripts\activate` (Windows).
2. **Instala dependencias** con `pip install -r requirements.txt`.
3. **Inicia la app** con `python -m app.main`. Deja la terminal abierta; verás logs de conexión al gateway demo.
4. **Abre tu navegador** en `http://localhost:8050`.
5. En la pestaña **Red**, verifica que el badge indique "Gateway conectado". Si no, pulsa **Conectar** (los valores por defecto ya funcionan en demo).
6. Pulsa **Descubrir** para listar sensores demo. Puedes editar directamente las columnas *Fs (Hz)*, *Tipo de dato* y *Duración adquisición (s)* o agregar un sensor escribiendo su ID y pulsando **Agregar manual** (usa un ID existente de `stays.yaml`, por ejemplo `ACC-01`).
7. Pulsa **Start All** para comenzar la adquisición. En segundos aparecerán los gráficos de aceleración, PSD y tensión en la pestaña **Tiempo real**.
8. Consulta la pestaña **Histórico** para ver la traza acumulada o abre la carpeta de datos con el botón correspondiente.
9. Cuando termines, pulsa **Stop All** y cierra la ventana del navegador. Detén la app con `Ctrl+C` en la terminal.

### Conexión a gateway MSCL

- Por defecto el modo demo auto-conecta contra un gateway simulado según `mscl_gateway` en `app.yaml`.
- En hardware real, ingrese IP/puerto del gateway inalámbrico en la pestaña **Red** y pulse **Conectar**. El estado se refleja en un badge y, al conectarse, la plataforma descubre los nodos disponibles.
- Si desea preconfigurar la conexión, edite en `app/config/app.yaml`:

```yaml
mscl_gateway:
  host: "192.168.0.10"
  port: 5000
  auto_connect: true
```

Defina `auto_connect: false` si prefiere iniciar manualmente la sesión desde la UI.

### Argumentos opcionales

- `--config`: ruta personalizada al YAML de la aplicación.
- `--stays`: ruta al YAML de tirantes.
- `--host` y `--port`: dirección y puerto para la UI.

## CSV y almacenamiento

Los archivos se crean bajo `data/acceleration/` y `data/tension/` (configurable). La rotación puede basarse en tiempo o tamaño según `app.yaml`.

Cabeceras:

- Aceleración: `timestamp_local,timestamp_utc,stay_id,sensor_id,fs_hz,ax_g,ay_g,az_g`
- Tensión: `t_window_end_local,t_window_end_utc,stay_id,sensor_id,f1_hz,T_N,T_kN,SNR_dB,peak_prom,n_samples,fs_hz,mode,k_used,qa`

## Pruebas

Ejecutar pytest desde la raíz del proyecto:

```bash
pytest
```

## Notas

- El modo demo genera señales sinusoidales con ruido para validar toda la cadena de procesamiento.
- Para integrar hardware real, implemente la clase `MSCLClient` con el SDK oficial y actualice `create_client` en `app/main.py`.
- Logs estructurados se escriben en consola y en `data/logs/mscl_tension.log`.

## Licencia

MIT License.
