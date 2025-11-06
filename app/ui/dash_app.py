"""Dash web application wiring."""
from __future__ import annotations

import csv
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback_context, dcc, html, dash_table
import numpy as np
import plotly.graph_objects as go
import yaml

from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.utils.timeutils import DEFAULT_TZ
from app.utils.validators import Thresholds
from app.ui import components
from app.ui.network_control_tab import create_network_control_tab

logger = logging.getLogger(__name__)


TENSION_CSV_HEADERS = [
    "t_window_end_local",
    "t_window_end_utc",
    "stay_id",
    "sensor_id",
    "f1_hz",
    "T_N",
    "T_kN",
    "SNR_dB",
    "peak_prom",
    "n_samples",
    "fs_hz",
    "mode",
    "k_used",
    "qa",
]


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        logger.warning("No se pudo parsear timestamp: %s", value)
        return None
    if dt.tzinfo is None:
        dt = DEFAULT_TZ.localize(dt)
    else:
        dt = dt.astimezone(DEFAULT_TZ)
    return dt


def _parse_date_value(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:  # pragma: no cover - defensive
        logger.warning("Fecha inválida recibida: %s", value)
        return None


def load_persisted_tension(
    storage_base: Path,
    sensor_id: Optional[str] = None,
    target_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Read persisted tension CSV files and return typed records."""

    tension_dir = storage_base / "tension"
    if not tension_dir.exists():
        return []

    records: List[Dict[str, Any]] = []
    for path in sorted(tension_dir.glob("tension_*.csv")):
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    continue
                missing = [h for h in TENSION_CSV_HEADERS if h not in reader.fieldnames]
                if missing:
                    logger.warning(
                        "Cabeceras faltantes en %s: %s", path.name, ", ".join(missing)
                    )
                for row in reader:
                    if sensor_id and row.get("sensor_id") != sensor_id:
                        continue
                    local_ts = _parse_datetime(row.get("t_window_end_local"))
                    utc_ts = _parse_datetime(row.get("t_window_end_utc"))
                    if local_ts is None and utc_ts is None:
                        continue
                    timestamp = local_ts or utc_ts
                    if target_date and timestamp.date() != target_date:
                        continue
                    record = {
                        "t_window_end_local": timestamp,
                        "t_window_end_utc": utc_ts,
                        "stay_id": row.get("stay_id"),
                        "sensor_id": row.get("sensor_id"),
                        "f1_hz": _parse_float(row.get("f1_hz")),
                        "T_N": _parse_float(row.get("T_N")),
                        "T_kN": _parse_float(row.get("T_kN")),
                        "SNR_dB": _parse_float(row.get("SNR_dB")),
                        "peak_prom": _parse_float(row.get("peak_prom")),
                        "n_samples": _parse_int(row.get("n_samples")),
                        "fs_hz": _parse_float(row.get("fs_hz")),
                        "mode": row.get("mode"),
                        "k_used": _parse_float(row.get("k_used")),
                        "qa": row.get("qa"),
                    }
                    records.append(record)
        except FileNotFoundError:  # pragma: no cover - rotated during read
            continue

    fallback_ts = datetime.min.replace(tzinfo=DEFAULT_TZ)
    records.sort(
        key=lambda rec: rec["t_window_end_local"] if rec["t_window_end_local"] else fallback_ts
    )
    return records


def _analysis_to_figures(analysis_state, sensor_id=None, manager=None):
    """Convert pre-calculated analysis data to Plotly figures (READ-ONLY).
    
    This function ONLY reads from RealtimeDataStore - NO FFT processing.
    All analysis (PSD, frequency detection, tension calculation) is done
    by the dedicated FFT thread in StreamManager.
    """
    if analysis_state is None:
        return go.Figure(), go.Figure(), []
    
    # Gráfica de aceleración (solo renderizado)
    accel_records = list(analysis_state.recent_accel)
    if accel_records:
        last_record = accel_records[-1]
        timestamps = last_record.timestamps
        samples = last_record.samples
        fig_time = go.Figure()
        
        # Obtener ejes activos desde la configuración del sensor en el manager
        active_axes = ['x', 'y', 'z']  # Por defecto todos
        if sensor_id and manager:
            sensor_state = manager.sensors.get(sensor_id)
            if sensor_state and sensor_state.info.axes:
                active_axes = [axis.lower() for axis in sensor_state.info.axes]
        
        # Timestamps ya vienen como datetime del coordinator
        # Solo agregar trazas para los ejes configurados
        if 'x' in active_axes and samples.shape[1] > 0:
            fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 0], mode="lines", name="Ax"))
        if 'y' in active_axes and samples.shape[1] > 1:
            fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 1], mode="lines", name="Ay"))
        if 'z' in active_axes and samples.shape[1] > 2:
            fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 2], mode="lines", name="Az"))
        
        axes_str = ''.join([a.upper() for a in active_axes])
        fig_time.update_layout(
            title=f"Aceleración reciente - Ejes activos: {axes_str}",
            xaxis_title="Tiempo",
            yaxis_title="g",
            template="plotly_white",
        )
    else:
        fig_time = go.Figure()

    # Gráfica PSD (ya calculada por FFT thread)
    psd = analysis_state.psd_cache
    if psd is not None:
        freqs, power = psd
        fig_psd = go.Figure()
        fig_psd.add_trace(go.Scatter(x=freqs, y=power, mode="lines", name="PSD"))
        if analysis_state.last_result and analysis_state.last_result.f1_hz:
            f1 = analysis_state.last_result.f1_hz
            fig_psd.add_vline(x=f1, line_dash="dash", line_color="red")
        fig_psd.update_layout(
            xaxis_title="Hz",
            yaxis_title="Potencia",
            title="PSD",
            template="plotly_white",
        )
    else:
        fig_psd = go.Figure()

    # Historial (solo extracción de datos)
    history_points = []
    for timestamp, tension, qa in analysis_state.history:
        if tension.tension_kN is not None:
            history_points.append((timestamp, tension.tension_kN, qa.flag.value))
    
    return fig_time, fig_psd, history_points


class DashApp:
    def __init__(
        self,
        manager: StreamManager,
        realtime: RealtimeDataStore,
        stays: List[StayDefinition],
        app_config_path: Path,
        stays_config_path: Path,
        app_config: Dict,
    ) -> None:
        self.manager = manager
        self.realtime = realtime
        self.stays = stays
        self.app_config_path = app_config_path
        self.stays_config_path = stays_config_path
        self.app_config = app_config
        self.gateway_config = app_config.get("mscl_gateway", {})
        self.storage_base = Path(
            app_config.get("storage", {}).get("base_dir", "./data")
        ).resolve()
        
        external_stylesheets = [dbc.themes.LUX]
        self.dash_app = dash.Dash(
            __name__,
            suppress_callback_exceptions=True,
            external_stylesheets=external_stylesheets,
        )
        self.dash_app.title = "MSCL Tension Platform"
        self._build_layout()
        self._register_callbacks()

    def _build_layout(self) -> None:
        stay_options = [{"label": stay.stay_id, "value": stay.sensor_id} for stay in self.stays]
        analysis_cfg = self.app_config.get("analysis", {})
        rotation_cfg = self.app_config.get("storage", {}).get("rotation", {})
        storage_dir = str(self.storage_base)
        bandpass_cfg = self.manager.analysis_cfg.get("bandpass", [0.2, 10.0])
        if isinstance(bandpass_cfg, dict):
            band_low = bandpass_cfg.get("low", 0.2)
            band_high = bandpass_cfg.get("high", 10.0)
        else:
            band_low = bandpass_cfg[0]
            band_high = bandpass_cfg[1]
        gateway_host = self.gateway_config.get("host", "127.0.0.1")
        gateway_port = self.gateway_config.get("port", 5000)
        refresh_interval = self.app_config.get("ui", {}).get("refresh_ms", 1000)

        network_tab = dbc.Tab(
            label="Red",
            tab_id="network",
            children=[
                dbc.Card(
                    [
                        dbc.CardHeader("Gateway MSCL"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Host"),
                                                dbc.Input(
                                                    id="gateway-host",
                                                    type="text",
                                                    value=gateway_host,
                                                    placeholder="IP / DNS",
                                                ),
                                            ],
                                            md=5,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Puerto"),
                                                dbc.Input(
                                                    id="gateway-port",
                                                    type="number",
                                                    value=gateway_port,
                                                    min=1,
                                                ),
                                            ],
                                            md=3,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Acciones"),
                                                html.Div(
                                                    [
                                                        dbc.Button(
                                                            "Conectar",
                                                            id="btn-connect-gateway",
                                                            color="success",
                                                            className="me-2",
                                                        ),
                                                        dbc.Button(
                                                            "Desconectar",
                                                            id="btn-disconnect-gateway",
                                                            color="secondary",
                                                        ),
                                                    ],
                                                    className="d-flex gap-2",
                                                ),
                                            ],
                                            md=4,
                                            className="d-flex align-items-end",
                                        ),
                                    ],
                                    className="g-3",
                                ),
                                html.Div(id="network-feedback", className="mt-3"),
                                html.Div(
                                    components.gateway_status_badge(
                                        self.manager.get_gateway_status()
                                    ),
                                    id="gateway-status",
                                    className="mt-3",
                                ),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
                dbc.Card(
                    [
                        dbc.CardHeader("Sensores"),
                        dbc.CardBody(
                            [
                                html.Div(id="network-summary", className="mb-3"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Button(
                                                "Descubrir",
                                                id="btn-discover",
                                                color="primary",
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Start All",
                                                id="btn-start-all",
                                                color="success",
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Stop All",
                                                id="btn-stop-all",
                                                color="danger",
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Sensor"),
                                                dcc.Dropdown(
                                                    id="sensor-selector",
                                                    options=stay_options,
                                                    placeholder="Selecciona sensor",
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Start sensor",
                                                id="btn-start-sensor",
                                                color="success",
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Stop sensor",
                                                id="btn-stop-sensor",
                                                color="secondary",
                                            ),
                                            width="auto",
                                        ),
                                    ],
                                    className="g-2 flex-wrap",
                                ),
                                html.Div(id="network-content", className="mt-3"),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
                dbc.Card(
                    [
                        dbc.CardHeader("Configuración de nodos"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Sensor"),
                                                dcc.Dropdown(
                                                    id="config-sensor",
                                                    options=stay_options,
                                                    placeholder="Selecciona sensor",
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Frecuencia (Hz)"),
                                                dbc.Input(
                                                    id="config-sample-rate",
                                                    type="number",
                                                    min=0.1,
                                                    step=0.1,
                                                    placeholder="Ej. 128",
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Canales"),
                                                dbc.Checklist(
                                                    id="config-axes",
                                                    options=[
                                                        {"label": "X", "value": "x"},
                                                        {"label": "Y", "value": "y"},
                                                        {"label": "Z", "value": "z"},
                                                    ],
                                                    value=["x", "y", "z"],
                                                    switch=True,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                    ],
                                    className="g-3",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Button(
                                                "Aplicar configuración",
                                                id="btn-apply-config",
                                                color="primary",
                                            ),
                                            width="auto",
                                        ),
                                    ],
                                    className="g-2 mt-2",
                                ),
                                html.Div(id="config-feedback", className="mt-3"),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
            ],
        )

        # Nueva pestaña: Configuración de Sensores
        config_sensor_tab = dbc.Tab(
            label="Configuración de Sensores",
            tab_id="sensor_config",
            children=[
                dbc.Card(
                    [
                        dbc.CardHeader("Configuración de Sensores para Monitoreo"),
                        dbc.CardBody(
                            [
                                # Sección 1: Selección de Sensor
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Sensor", className="fw-bold"),
                                                dcc.Dropdown(
                                                    id="config-sensor-select",
                                                    options=[],
                                                    placeholder="Selecciona un sensor",
                                                    clearable=False,
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                
                                html.Hr(),
                                
                                # Sección 2: Parámetros de Muestreo
                                html.H5("Parámetros de Muestreo", className="mb-3"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Frecuencia de Muestreo (Hz)"),
                                                dcc.Dropdown(
                                                    id="config-sample-rate-new",
                                                    options=[
                                                        {"label": "256 Hz (Mínimo soportado)", "value": 256},
                                                        {"label": "512 Hz", "value": 512},
                                                        {"label": "1024 Hz (1 kHz)", "value": 1024},
                                                        {"label": "2048 Hz (2 kHz)", "value": 2048},
                                                        {"label": "4096 Hz (4 kHz) - High Speed", "value": 4096},
                                                    ],
                                                    value=256,
                                                    clearable=False,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Duración"),
                                                dcc.RadioItems(
                                                    id="config-duration-mode",
                                                    options=[
                                                        {"label": "Ilimitada (hasta detener manualmente)", "value": "unlimited"},
                                                        {"label": "Tiempo específico", "value": "timed"},
                                                    ],
                                                    value="unlimited",
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Minutos (si es tiempo específico)"),
                                                dbc.Input(
                                                    id="config-duration-minutes",
                                                    type="number",
                                                    placeholder="Minutos",
                                                    min=1,
                                                    max=1440,
                                                    disabled=True,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                    ],
                                    className="g-3 mb-3",
                                ),
                                
                                html.Hr(),
                                
                                # Sección 3: Canales Activos
                                html.H5("Canales Activos", className="mb-3"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Checklist(
                                                    id="config-active-axes",
                                                    options=[
                                                        {"label": "Eje X", "value": "x"},
                                                        {"label": "Eje Y", "value": "y"},
                                                        {"label": "Eje Z (vertical - recomendado)", "value": "z"},
                                                    ],
                                                    value=["x", "y", "z"],
                                                    switch=True,
                                                    inline=True,
                                                ),
                                            ],
                                            md=12,
                                        ),
                                    ],
                                    className="mb-2",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.Div(
                                                    dbc.Alert(
                                                        "💡 Tip: Activar menos canales permite usar más sensores simultáneos",
                                                        color="info",
                                                    ),
                                                    id="bandwidth-warning",
                                                ),
                                            ],
                                            md=12,
                                        ),
                                    ],
                                ),
                                
                                html.Hr(),
                                
                                # Sección 4: Formato de Datos
                                html.H5("Formato de Datos", className="mb-3"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dcc.RadioItems(
                                                    id="config-data-format",
                                                    options=[
                                                        {"label": "Float 32-bit (precisión completa)", "value": "float"},
                                                    ],
                                                    value="float",
                                                ),
                                                dbc.Alert(
                                                    [
                                                        html.I(className="bi bi-info-circle me-2"),
                                                        "El G-Link-200 solo soporta formato Float en modo SYNC. "
                                                        "El formato UInt16 (raw) no está disponible para este hardware."
                                                    ],
                                                    color="info",
                                                    className="mt-2 small",
                                                ),
                                            ],
                                            md=12,
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                
                                html.Hr(),
                                
                                # Sección 5: Botones de Acción
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Button(
                                                    "Aplicar Configuración y Monitorear",
                                                    id="btn-apply-and-monitor",
                                                    color="success",
                                                    size="lg",
                                                    className="w-100",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Button(
                                                    "Detener Monitoreo",
                                                    id="btn-stop-monitoring",
                                                    color="danger",
                                                    size="lg",
                                                    className="w-100",
                                                    disabled=True,
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                    className="g-2",
                                ),
                                
                                # Área de feedback
                                html.Div(id="config-sensor-feedback", className="mt-3"),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
            ],
        )

        realtime_tab = dbc.Tab(
            label="Tiempo real",
            tab_id="realtime",
            children=[
                            dbc.Card(
                                [
                                    dbc.CardHeader("Controles"),
                                    dbc.CardBody(
                                        [
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            dbc.Label("Sensor"),
                                                            dcc.Dropdown(
                                                                id="realtime-sensor",
                                                                options=stay_options,
                                                                placeholder="Selecciona sensor",
                                                                value=stay_options[0]["value"]
                                                                if stay_options
                                                                else None,
                                                                clearable=False,
                                                            ),
                                                        ],
                                                        md=4,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            dbc.Label("Modo"),
                                                            dcc.RadioItems(
                                                                id="mode-selector",
                                                                options=[
                                                                    {"label": "AUTO", "value": "AUTO"},
                                                                    {"label": "GUIADA", "value": "GUIDED"},
                                                                ],
                                                                value="AUTO",
                                                                inline=True,
                                                            ),
                                                        ],
                                                        md=4,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            dbc.Label("f₁ propuesta (Hz)"),
                                                            dbc.Input(
                                                                id="guided-f1",
                                                                type="number",
                                                                placeholder="Ej. 2.5",
                                                            ),
                                                        ],
                                                        md=2,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            dbc.Label("Tolerancia (%)"),
                                                            dbc.Input(
                                                                id="guided-tol",
                                                                type="number",
                                                                value=10,
                                                                min=0,
                                                                max=100,
                                                            ),
                                                        ],
                                                        md=2,
                                                    ),
                                                ],
                                                className="g-3",
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            dbc.Label("Fecha (local)"),
                                                            dcc.DatePickerSingle(
                                                                id="realtime-date",
                                                                date=datetime.now(
                                                                    DEFAULT_TZ
                                                                )
                                                                .date()
                                                                .isoformat(),
                                                                display_format="YYYY-MM-DD",
                                                            ),
                                                        ],
                                                        md=3,
                                                    ),
                                                ],
                                                className="g-3 mt-1",
                                            ),
                                        ]
                                    ),
                                ],
                                className="mb-4 shadow-sm",
                            ),
                html.Div(id="realtime-card", className="mb-4"),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Card(
                                [
                                    dbc.CardHeader("Aceleración"),
                                    dbc.CardBody(dcc.Graph(id="realtime-accel")),
                                ],
                                className="shadow-sm",
                            ),
                            md=6,
                        ),
                        dbc.Col(
                            dbc.Card(
                                [
                                    dbc.CardHeader("PSD"),
                                    dbc.CardBody(dcc.Graph(id="realtime-psd")),
                                ],
                                className="shadow-sm",
                            ),
                            md=6,
                        ),
                    ],
                    className="g-4",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Card(
                                [
                                    dbc.CardHeader("Histórico reciente"),
                                    dbc.CardBody(dcc.Graph(id="realtime-history")),
                                ],
                                className="shadow-sm",
                            ),
                            md=12,
                        ),
                    ],
                    className="g-4",
                ),
            ],
        )

        config_tab = dbc.Tab(
            label="Configuración",
            tab_id="config",
            children=[
                dbc.Card(
                    [
                        dbc.CardHeader("Parámetros de análisis"),
                        dbc.CardBody(
                            html.Div(
                                [
                                    html.Label("Ventana (s)"),
                                    dcc.Input(
                                        id="cfg-window",
                                        type="number",
                                        value=analysis_cfg.get("window_sec", 30),
                                    ),
                                    html.Label("Periodo actualización (s)"),
                                    dcc.Input(
                                        id="cfg-update",
                                        type="number",
                                        value=analysis_cfg.get("update_period_sec", 5),
                                    ),
                                    html.Label("fmin (Hz)"),
                                    dcc.Input(
                                        id="cfg-fmin",
                                        type="number",
                                        value=analysis_cfg.get("fmin_hz", 0.3),
                                    ),
                                    html.Label("fmax (Hz)"),
                                    dcc.Input(
                                        id="cfg-fmax",
                                        type="number",
                                        value=analysis_cfg.get("fmax_hz", 8.0),
                                    ),
                                    html.Label("nperseg (s)"),
                                    dcc.Input(
                                        id="cfg-nperseg",
                                        type="number",
                                        value=analysis_cfg.get("nperseg_sec", 4),
                                    ),
                                    html.Label("overlap"),
                                    dcc.Input(
                                        id="cfg-overlap",
                                        type="number",
                                        value=analysis_cfg.get("overlap", 0.5),
                                    ),
                                    html.Label("Banda baja (Hz)"),
                                    dcc.Input(
                                        id="cfg-band-low",
                                        type="number",
                                        value=band_low,
                                    ),
                                    html.Label("Banda alta (Hz)"),
                                    dcc.Input(
                                        id="cfg-band-high",
                                        type="number",
                                        value=band_high,
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(4, 1fr)",
                                    "gap": "0.75rem",
                                },
                            )
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
                dbc.Card(
                    [
                        dbc.CardHeader("Almacenamiento"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Directorio base"),
                                                dcc.Input(
                                                    id="cfg-base-dir",
                                                    value=storage_dir,
                                                    style={"width": "100%"},
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Rotación"),
                                                dcc.Dropdown(
                                                    id="cfg-rotation-mode",
                                                    options=[
                                                        {"label": "Tiempo", "value": "time"},
                                                        {"label": "Tamaño", "value": "size"},
                                                    ],
                                                    value=rotation_cfg.get("mode", "time"),
                                                ),
                                            ],
                                            md=3,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Minutos"),
                                                dcc.Input(
                                                    id="cfg-rotation-minutes",
                                                    type="number",
                                                    value=rotation_cfg.get("minutes", 10),
                                                ),
                                            ],
                                            md=1,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Tamaño (MB)"),
                                                dcc.Input(
                                                    id="cfg-rotation-mb",
                                                    type="number",
                                                    value=rotation_cfg.get("max_mb", 100),
                                                ),
                                            ],
                                            md=2,
                                        ),
                                    ],
                                    className="g-3",
                                ),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
                dbc.Card(
                    [
                        dbc.CardHeader("Tirantes"),
                        dbc.CardBody(
                            [
                                dash_table.DataTable(
                                    id="cfg-stays-table",
                                    columns=[
                                        {"name": "Stay", "id": "stay"},
                                        {"name": "Sensor", "id": "sensor"},
                                        {"name": "K (N/Hz^2)", "id": "k"},
                                        {"name": "Green", "id": "green"},
                                        {"name": "Yellow", "id": "yellow"},
                                        {"name": "Orange", "id": "orange"},
                                    ],
                                    data=[
                                        {
                                            "stay": stay.stay_id,
                                            "sensor": stay.sensor_id,
                                            "k": stay.k_coefficient,
                                            "green": stay.thresholds.green_max,
                                            "yellow": stay.thresholds.yellow_max,
                                            "orange": stay.thresholds.orange_max,
                                        }
                                        for stay in self.stays
                                    ],
                                    editable=True,
                                ),
                                dbc.Button(
                                    "Guardar configuración",
                                    id="btn-save-config",
                                    color="primary",
                                    className="mt-3",
                                ),
                                html.Div(id="config-status", className="mt-3"),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
            ],
        )

        # Nueva pestaña: Acelerómetro en Tiempo Real
        accel_tab = dbc.Tab(
            label="Acelerómetro",
            tab_id="accelerometer",
            children=[
                # Store para mantener el estado de pausa/reanudación
                dcc.Store(id="accel-paused", data=False),
                
                dbc.Card(
                    [
                        dbc.CardHeader("Datos del Acelerómetro en Tiempo Real - Sensor 10603"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.Div(id="accel-status", className="mt-2"),
                                            ],
                                            md=9,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Button(
                                                    "⏸ Detener Gráfico",
                                                    id="accel-pause-btn",
                                                    color="warning",
                                                    className="w-100",
                                                ),
                                            ],
                                            md=3,
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dcc.Graph(
                                                    id="accel-graph-combined",
                                                    config={"displayModeBar": True},
                                                    style={"height": "600px"},
                                                ),
                                            ],
                                            md=12,
                                        ),
                                    ],
                                ),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
            ],
        )
        
        # Nueva pestaña: Análisis Histórico con Grafana
        grafana_config = self.app_config.get("grafana", {})
        grafana_url = grafana_config.get("url", "http://localhost:3000")
        dashboard_uid = grafana_config.get("dashboard_uid", "adwxmbh")
        grafana_tab = dbc.Tab(
            label="Análisis Histórico",
            tab_id="grafana",
            children=[
                dbc.Card(
                    [
                        dbc.CardHeader("Visualización Histórica con Grafana"),
                        dbc.CardBody(
                            [
                                dbc.Alert(
                                    [
                                        html.I(className="bi bi-info-circle-fill me-2"),
                                        "Los datos de los sensores se almacenan automáticamente en InfluxDB y pueden visualizarse en Grafana para análisis histórico.",
                                    ],
                                    color="info",
                                    className="mb-3",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.H5("Acceso a Grafana", className="mb-3"),
                                                html.P("Haz clic en los botones para abrir Grafana en una nueva pestaña:"),
                                                dbc.ButtonGroup(
                                                    [
                                                        dbc.Button(
                                                            [html.I(className="bi bi-bar-chart-line me-2"), "Dashboard Principal"],
                                                            href=f"{grafana_url}/d/{dashboard_uid}",
                                                            target="_blank",
                                                            color="primary",
                                                            size="lg",
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="bi bi-gear me-2"), "Configuración"],
                                                            href=f"{grafana_url}",
                                                            target="_blank",
                                                            color="secondary",
                                                            size="lg",
                                                        ),
                                                    ],
                                                    className="mb-4",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                html.H5("Información", className="mb-3"),
                                                dbc.ListGroup(
                                                    [
                                                        dbc.ListGroupItem([
                                                            html.Strong("URL: "),
                                                            html.Code(grafana_url),
                                                        ]),
                                                        dbc.ListGroupItem([
                                                            html.Strong("Dashboard: "),
                                                            html.Code(dashboard_uid),
                                                        ]),
                                                        dbc.ListGroupItem([
                                                            html.Strong("Base de datos: "),
                                                            "InfluxDB (localhost:8086)",
                                                        ]),
                                                        dbc.ListGroupItem([
                                                            html.Strong("Retención: "),
                                                            "Datos históricos completos",
                                                        ]),
                                                    ],
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                ),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                ),
            ],
        )

        # Nueva pestaña "Control de Red" estilo SensorConnect
        network_control_tab = create_network_control_tab()

        self.dash_app.layout = dbc.Container(
            [
                html.H1("MSCL TENSION PLATFORM", className="mb-4 fw-bold"),
                dbc.Tabs(
                    [network_control_tab, realtime_tab, config_tab, accel_tab, grafana_tab],
                    id="tabs",
                    active_tab="network-control",
                    className="mb-4",
                ),
                dcc.Interval(id="interval", interval=refresh_interval, n_intervals=0),
                # Interval y Stores para Control de Red (siempre activos)
                dcc.Interval(id="node-detection-interval", interval=5000, n_intervals=0),
                dcc.Store(id="network-state-store", data={}),
                dcc.Store(id="network-control-state", data={"nodes_config": {}}),
                dcc.Store(id="selected-node-for-config", data=None),
            ],
            fluid=True,
            className="bg-light min-vh-100 py-4",
        )

    def _register_callbacks(self) -> None:
        app = self.dash_app

        @app.callback(
            Output("config-feedback", "children"),
            Output("config-sample-rate", "value"),
            Output("config-axes", "value"),
            Input("config-sensor", "value"),
            Input("btn-apply-config", "n_clicks"),
            State("config-sample-rate", "value"),
            State("config-axes", "value"),
            prevent_initial_call=True,
        )
        def handle_configuration(sensor_id, apply_clicks, sample_rate, axes):
            triggered_list = callback_context.triggered or []
            triggered = triggered_list[0]["prop_id"].split(".")[0] if triggered_list else ""
            if triggered == "config-sensor":
                if not sensor_id:
                    return dash.no_update, None, []
                state = self.manager.sensors.get(sensor_id)
                if state is None:
                    return dash.no_update, None, []
                return dash.no_update, state.info.sample_rate_hz, list(state.info.axes)
            if triggered == "btn-apply-config":
                if not sensor_id:
                    alert = dbc.Alert(
                        "Selecciona un sensor antes de aplicar la configuración",
                        color="warning",
                        dismissable=True,
                    )
                    return alert, sample_rate, axes
                try:
                    sr_value = float(sample_rate) if sample_rate is not None else None
                    if sr_value is None or sr_value <= 0:
                        raise ValueError("La frecuencia debe ser mayor a 0")
                    axes_list = list(axes or [])
                    if not axes_list:
                        raise ValueError("Selecciona al menos un canal")
                    self.manager.configure(sensor_id, sr_value, axes_list)
                    alert = dbc.Alert(
                        "Configuración aplicada correctamente",
                        color="success",
                        dismissable=True,
                    )
                    state = self.manager.sensors.get(sensor_id)
                    if state is not None:
                        return alert, state.info.sample_rate_hz, list(state.info.axes)
                    return alert, sr_value, axes_list
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Error al configurar nodo")
                    alert = dbc.Alert(str(exc), color="danger", dismissable=True)
                    return alert, sample_rate, axes
            return dash.no_update, sample_rate, axes

        @app.callback(
            Output("config-status", "children"),
            Input("btn-save-config", "n_clicks"),
            State("cfg-window", "value"),
            State("cfg-update", "value"),
            State("cfg-fmin", "value"),
            State("cfg-fmax", "value"),
            State("cfg-nperseg", "value"),
            State("cfg-overlap", "value"),
            State("cfg-band-low", "value"),
            State("cfg-band-high", "value"),
            State("cfg-base-dir", "value"),
            State("cfg-rotation-mode", "value"),
            State("cfg-rotation-minutes", "value"),
            State("cfg-rotation-mb", "value"),
            State("cfg-stays-table", "data"),
            prevent_initial_call=True,
        )
        def save_config(
            _,
            window,
            update,
            fmin,
            fmax,
            nperseg,
            overlap,
            band_low,
            band_high,
            base_dir,
            rotation_mode,
            rotation_minutes,
            rotation_mb,
            stays_table,
        ):
            self.app_config["analysis"].update(
                {
                    "window_sec": window,
                    "update_period_sec": update,
                    "fmin_hz": fmin,
                    "fmax_hz": fmax,
                    "nperseg_sec": nperseg,
                    "overlap": overlap,
                    "bandpass": [band_low, band_high],
                }
            )
            self.app_config.setdefault("storage", {}).update(
                {
                    "base_dir": base_dir,
                    "rotation": {
                        "mode": rotation_mode,
                        "minutes": rotation_minutes,
                        "max_mb": rotation_mb,
                    },
                }
            )
            with open(self.app_config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.app_config, f)

            stays_yaml = {"stays": []}
            new_stays: List[StayDefinition] = []
            for row in stays_table:
                stays_yaml["stays"].append(
                    {
                        "stay_id": row["stay"],
                        "sensor_id": row["sensor"],
                        "k_coefficient_N_per_Hz2": float(row["k"]),
                        "thresholds_kN": {
                            "green_max": float(row["green"]),
                            "yellow_max": float(row["yellow"]),
                            "orange_max": float(row["orange"]),
                        },
                    }
                )
                new_stays.append(
                    StayDefinition(
                        stay_id=row["stay"],
                        sensor_id=row["sensor"],
                        k_coefficient=float(row["k"]),
                        thresholds=Thresholds(
                            green_max=float(row["green"]),
                            yellow_max=float(row["yellow"]),
                            orange_max=float(row["orange"]),
                        ),
                    )
                )
            with open(self.stays_config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(stays_yaml, f)

            self.manager.update_analysis_config(self.app_config["analysis"])
            self.manager.update_storage_config(Path(base_dir), self.app_config["storage"]["rotation"])
            self.stays = new_stays
            self.manager.stays = {stay.sensor_id: stay for stay in new_stays}
            return "Configuración guardada"

        @app.callback(
            Output("realtime-card", "children"),
            Output("realtime-accel", "figure"),
            Output("realtime-psd", "figure"),
            Output("realtime-history", "figure"),
            Input("interval", "n_intervals"),
            Input("realtime-sensor", "value"),
            Input("realtime-date", "date"),
        )
        def update_realtime(_, sensor_id, date_value):
            if not sensor_id and self.stays:
                sensor_id = self.stays[0].sensor_id
            target_date = _parse_date_value(date_value)
            snapshot = self.realtime.snapshot()
            analysis = snapshot.get(sensor_id) if sensor_id else None
            stay = next((s for s in self.stays if s.sensor_id == sensor_id), None)
            card = components.realtime_card(stay, analysis) if stay else html.Div("Sin datos")
            fig_time, fig_psd, history = _analysis_to_figures(analysis, sensor_id, self.manager)
            if target_date is not None:
                history = [
                    (ts, tension, qa)
                    for ts, tension, qa in history
                    if ts.date() == target_date
                ]
            if not history and sensor_id:
                persisted = load_persisted_tension(
                    self.storage_base, sensor_id=sensor_id, target_date=target_date
                )
                history = [
                    (
                        rec["t_window_end_local"],
                        rec["T_kN"],
                        rec["qa"],
                    )
                    for rec in persisted
                    if rec["t_window_end_local"] is not None and rec["T_kN"] is not None
                ]
            fig_hist = go.Figure()
            if history:
                times, values, _qa = zip(*history)
                fig_hist.add_trace(go.Scatter(x=list(times), y=list(values), mode="lines+markers"))
            fig_hist.update_layout(
                title="Tensión (kN)",
                xaxis_title="Tiempo",
                yaxis_title="kN",
                template="plotly_white",
            )
            return card, fig_time, fig_psd, fig_hist

        @app.callback(
            Output("mode-selector", "value"),
            Input("mode-selector", "value"),
            Input("guided-f1", "value"),
            Input("guided-tol", "value"),
            State("realtime-sensor", "value"),
        )
        def update_mode(mode, guided_f1, guided_tol, sensor_id):
            if sensor_id:
                tolerance = (guided_tol or 10) / 100.0
                self.manager.set_mode(sensor_id, mode, guided_f1, tolerance)
            return mode

        @app.callback(
            Output("sensor-selector", "value"),
            Input("btn-start-all", "n_clicks"),
            Input("btn-stop-all", "n_clicks"),
            Input("btn-start-sensor", "n_clicks"),
            Input("btn-stop-sensor", "n_clicks"),
            State("sensor-selector", "value"),
        )
        def control_streams(start_all, stop_all, start_sensor, stop_sensor, sensor_value):
            triggered_list = callback_context.triggered or []
            triggered = triggered_list[0]["prop_id"] if triggered_list else ""
            if "btn-start-all" in triggered:
                self.manager.start_all()
            elif "btn-stop-all" in triggered:
                self.manager.stop_all()
            elif "btn-start-sensor" in triggered and sensor_value:
                self.manager.start(sensor_value)
            elif "btn-stop-sensor" in triggered and sensor_value:
                self.manager.stop(sensor_value)
            return sensor_value

        # Callback para controlar el botón de pausa
        @app.callback(
            Output("accel-paused", "data"),
            Output("accel-pause-btn", "children"),
            Output("accel-pause-btn", "color"),
            Input("accel-pause-btn", "n_clicks"),
            State("accel-paused", "data"),
        )
        def toggle_pause(n_clicks, is_paused):
            """Alterna entre pausar y reanudar la actualización del gráfico."""
            # Manejar el caso inicial (n_clicks es None)
            if n_clicks is None or n_clicks == 0:
                return False, "⏸ Detener Gráfico", "warning"
            
            # Alternar el estado (manejar caso cuando is_paused es None)
            new_paused = not (is_paused or False)
            
            if new_paused:
                # Ahora está pausado
                return True, "▶️ Reanudar Gráfico", "success"
            else:
                # Ahora está activo
                return False, "⏸ Detener Gráfico", "warning"

        @app.callback(
            Output("accel-graph-combined", "figure"),
            Output("accel-status", "children"),
            Input("interval", "n_intervals"),
            State("accel-paused", "data"),
        )
        def update_accelerometer(n, is_paused):
            """Actualiza la gráfica del acelerómetro en tiempo real - Sensor 10603."""
            import numpy as np
            
            # Si está pausado, no actualizar
            if is_paused:
                raise dash.exceptions.PreventUpdate
            
            # Siempre usar sensor 10603
            sensor_id = "10603"
            
            try:
                # Obtener buffer continuo (últimos 3 segundos - balance entre suavidad y performance)
                buffer_data = self.realtime.get_display_buffer(sensor_id, window_seconds=3.0)
                
                if buffer_data is None:
                    empty_fig = go.Figure()
                    empty_fig.update_layout(title="⏳ Esperando datos...", template="plotly_white", height=600)
                    status = dbc.Alert("⏸️ Sin datos - Configure el sensor en la pestaña 'Configuración de Sensores'", color="warning")
                    return empty_fig, status
                
                timestamps, samples = buffer_data
                
                # CRÍTICO: Ordenar por timestamp para evitar líneas verticales extrañas
                if len(timestamps) > 0:
                    sort_indices = np.argsort(timestamps)
                    timestamps = timestamps[sort_indices]
                    samples = samples[sort_indices]
                
                # Submuestreo moderado: tomar 1 de cada 2 muestras (128Hz efectivo)
                # Esto da ~384 puntos por 3 segundos - óptimo para WebGL
                subsample_rate = 2
                timestamps = timestamps[::subsample_rate]
                samples = samples[::subsample_rate]
                
                # Calcular tiempos relativos
                if len(timestamps) > 0:
                    time_offset = timestamps[0]
                    times = timestamps - time_offset
                else:
                    times = np.array([])
                
                # Extraer cada eje
                if samples.ndim == 2 and samples.shape[1] >= 3:
                    x_data = samples[:, 0]
                    y_data = samples[:, 1]
                    z_data = samples[:, 2]
                else:
                    x_data = np.zeros(len(times))
                    y_data = np.zeros(len(times))
                    z_data = np.zeros(len(times))
                
                # NUEVO: Obtener configuración actual del sensor para saber qué ejes mostrar
                sensor_state = self.manager.sensors.get(sensor_id)
                active_axes = ['x', 'y', 'z']  # Por defecto todos
                if sensor_state and sensor_state.info.axes:
                    active_axes = [axis.lower() for axis in sensor_state.info.axes]
                
                # Crear gráfica OPTIMIZADA con Scattergl (aceleración WebGL)
                fig = go.Figure()
                
                # Solo agregar trazas para los ejes activos
                if 'x' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=x_data, mode='lines', name='X',
                        line=dict(color='#e74c3c', width=1.5),
                        visible=True,
                    ))
                
                if 'y' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=y_data, mode='lines', name='Y',
                        line=dict(color='#3498db', width=1.5),
                        visible=True,
                    ))
                
                if 'z' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=z_data, mode='lines', name='Z',
                        line=dict(color='#2ecc71', width=1.5),
                        visible=True,
                    ))
                
                # Título dinámico con ejes activos
                axes_str = ', '.join([a.upper() for a in active_axes])
                fig.update_layout(
                    title=f"Acelerómetro 10603 - {len(times)} puntos @ 128Hz | Ejes: {axes_str}",
                    xaxis_title="Tiempo (s)",
                    yaxis_title="Aceleración (g)",
                    template="plotly_white",
                    height=600,
                    hovermode='x unified',  # Mejor para tiempo real
                    showlegend=True,
                    uirevision='accel-10603',  # ID único y constante - preserva TODOS los estados de UI
                    margin=dict(l=50, r=20, t=80, b=50),  # Más margen superior para la leyenda
                    legend=dict(
                        orientation="h",  # Leyenda horizontal
                        yanchor="bottom",
                        y=1.15,  # Más separación del área de gráfica
                        xanchor="center",  # Centrada
                        x=0.5,  # En el centro horizontal
                        bgcolor="rgba(255, 255, 255, 0.8)",  # Fondo semi-transparente
                        bordercolor="#ddd",
                        borderwidth=1
                    ),
                )
                
                # Configuración optimizada de ejes
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                
                status = dbc.Alert(
                    f"✅ ACTIVO | {len(times)} muestras | Ejes: {axes_str} | Actualización: 500ms",
                    color="success"
                )
                
                return fig, status
                
            except Exception as e:
                logger.error(f"[ACCEL] Error: {e}", exc_info=True)
                error_fig = go.Figure()
                error_fig.update_layout(title=f"❌ Error", template="plotly_white", height=600)
                status = dbc.Alert(f"❌ Error: {str(e)}", color="danger")
                return error_fig, status

        # ===== CALLBACKS PARA PESTAÑA DE CONFIGURACIÓN DE SENSORES =====
        
        @app.callback(
            Output("config-sensor-select", "options"),
            Input("interval", "n_intervals")
        )
        def actualizar_lista_sensores(_):
            """Actualiza la lista de sensores disponibles."""
            states = self.manager.get_status()
            options = [
                {"label": f"{state.info.sensor_id} - {state.info.stay_id}", "value": state.info.sensor_id}
                for state in states
            ]
            return options
        
        @app.callback(
            Output("config-duration-minutes", "disabled"),
            Input("config-duration-mode", "value")
        )
        def toggle_duration_input(mode):
            """Habilita el input de minutos solo si se selecciona 'timed'."""
            return mode != "timed"
        
        @app.callback(
            Output("config-active-axes", "value"),
            Output("bandwidth-warning", "children"),
            Input("config-active-axes", "value")
        )
        def validar_ejes(axes_selected):
            """Asegura que al menos un eje esté seleccionado."""
            if not axes_selected or len(axes_selected) == 0:
                # Forzar al menos el eje Z
                axes_selected = ["z"]
                warning = dbc.Alert(
                    "⚠️ Al menos un eje debe estar activo. Se seleccionó Z por defecto.",
                    color="warning"
                )
            else:
                n_axes = len(axes_selected)
                if n_axes == 1:
                    warning = dbc.Alert(
                        "✅ 1 canal activo - máxima capacidad de sensores simultáneos",
                        color="success"
                    )
                elif n_axes == 2:
                    warning = dbc.Alert(
                        "⚠️ 2 canales activos - capacidad media",
                        color="info"
                    )
                else:
                    warning = dbc.Alert(
                        "💡 3 canales activos - menor capacidad de sensores simultáneos",
                        color="info"
                    )
            
            return axes_selected, warning
        
        @app.callback(
            Output("config-sensor-feedback", "children"),
            Output("btn-apply-and-monitor", "disabled"),
            Output("btn-stop-monitoring", "disabled"),
            Input("btn-apply-and-monitor", "n_clicks"),
            Input("btn-stop-monitoring", "n_clicks"),
            State("config-sensor-select", "value"),
            State("config-sample-rate-new", "value"),
            State("config-active-axes", "value"),
            State("config-data-format", "value"),
            State("config-duration-mode", "value"),
            State("config-duration-minutes", "value"),
            prevent_initial_call=True
        )
        def controlar_monitoreo(
            n_clicks_start, 
            n_clicks_stop, 
            sensor_id, 
            sample_rate, 
            axes, 
            data_format,
            duration_mode,
            duration_minutes
        ):
            """Aplica configuración e inicia/detiene monitoreo."""
            triggered_list = callback_context.triggered or []
            triggered = triggered_list[0]["prop_id"].split(".")[0] if triggered_list else ""
            
            if triggered == "btn-apply-and-monitor":
                # Validaciones
                if not sensor_id:
                    return (
                        dbc.Alert("❌ Selecciona un sensor primero", color="danger"),
                        False,  # btn-apply habilitado
                        True    # btn-stop deshabilitado
                    )
                
                if not axes or len(axes) == 0:
                    return (
                        dbc.Alert("❌ Selecciona al menos un eje", color="danger"),
                        False,
                        True
                    )
                
                try:
                    # 1. Configurar el nodo
                    logger.info(f"Configurando sensor {sensor_id}: fs={sample_rate}Hz, ejes={axes}, formato={data_format}")
                    
                    self.manager.configure(
                        sensor_id=sensor_id,
                        sample_rate=sample_rate,
                        axes=axes,
                        data_format=data_format
                    )
                    
                    # 2. Iniciar streaming
                    self.manager.start(sensor_id)
                    
                    # 3. Si es duración limitada, programar detención
                    if duration_mode == "timed" and duration_minutes:
                        # TODO: Implementar timer para detener automáticamente
                        # (puede ser con threading.Timer en manager)
                        logger.info(f"Monitoreo programado por {duration_minutes} minutos (detención automática no implementada)")
                    
                    feedback = dbc.Alert(
                        [
                            html.H5("✅ Monitoreo iniciado correctamente", className="alert-heading"),
                            html.Hr(),
                            html.P(f"Sensor: {sensor_id}"),
                            html.P(f"Frecuencia: {sample_rate} Hz"),
                            html.P(f"Canales: {', '.join([a.upper() for a in axes])}"),
                            html.P(f"Formato: {data_format}"),
                            html.P(f"Duración: {'Ilimitada' if duration_mode == 'unlimited' else f'{duration_minutes} minutos'}"),
                            html.Hr(),
                            html.P("Los datos se están guardando en InfluxDB automáticamente.", className="mb-0"),
                        ],
                        color="success"
                    )
                    
                    return (
                        feedback,
                        True,   # btn-apply deshabilitado (ya está monitoreando)
                        False   # btn-stop habilitado
                    )
                    
                except Exception as e:
                    logger.exception(f"Error al iniciar monitoreo de {sensor_id}")
                    return (
                        dbc.Alert(f"❌ Error: {str(e)}", color="danger"),
                        False,
                        True
                    )
            
            elif triggered == "btn-stop-monitoring":
                try:
                    if sensor_id:
                        self.manager.stop(sensor_id)
                        logger.info(f"Monitoreo detenido para sensor {sensor_id}")
                    
                    return (
                        dbc.Alert("⏹️ Monitoreo detenido", color="warning"),
                        False,  # btn-apply habilitado
                        True    # btn-stop deshabilitado
                    )
                except Exception as e:
                    logger.exception(f"Error al detener monitoreo de {sensor_id}")
                    return (
                        dbc.Alert(f"❌ Error al detener: {str(e)}", color="danger"),
                        True,
                        False
                    )
            
            return dash.no_update, dash.no_update, dash.no_update

        # ===== CALLBACKS PARA CONTROL DE RED (ESTILO SENSORCONNECT) =====
        
        @app.callback(
            Output("detected-nodes-list", "children"),
            Output("individual-node-control-panel", "children"),
            Input("node-detection-interval", "n_intervals"),
        )
        def update_detected_nodes_list(n):
            """Actualiza la lista de nodos detectados y sus controles individuales cada 5 segundos."""
            logger.info(f"[CONTROL-RED] Actualizando lista de nodos (intervalo #{n})")
            logger.info(f"[CONTROL-RED] Sensores disponibles: {list(self.manager.sensors.keys())}")
            nodes_cards = []
            control_panels = []

            for sensor_id, state in self.manager.sensors.items():
                # Determinar estado
                is_streaming = state.streaming
                last_sample_time = getattr(state, '_last_sample_time', None)

                if is_streaming:
                    if last_sample_time and (time.time() - last_sample_time) > 15:
                        status_badge = dbc.Badge("DESCONECTADO", color="danger", className="me-2")
                        connection_msg = html.Small(f"Sin datos por {int(time.time() - last_sample_time)}s", className="text-danger")
                    else:
                        status_badge = dbc.Badge("ACTIVO", color="success", className="me-2")
                        connection_msg = html.Small("Conectado", className="text-success")
                else:
                    status_badge = dbc.Badge("IDLE", color="secondary", className="me-2")
                    connection_msg = html.Small("Listo", className="text-muted")

                # Crear tarjeta del nodo (lista de la izquierda)
                card = dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H6([
                                    f"NODO {sensor_id}",
                                    status_badge,
                                ]),
                                connection_msg,
                                html.Hr(),
                                html.P([
                                    html.Strong("Stay: "),
                                    state.info.stay_id,
                                ], className="mb-1 small"),
                                html.P([
                                    html.Strong("Frecuencia: "),
                                    f"{state.info.sample_rate_hz} Hz" if state.info.sample_rate_hz else "No configurado",
                                ], className="mb-1 small"),
                                html.P([
                                    html.Strong("Ejes: "),
                                    ", ".join([a.upper() for a in state.info.axes]) if state.info.axes else "---",
                                ], className="mb-0 small"),
                            ]
                        ),
                    ],
                    className="mb-3",
                )
                nodes_cards.append(card)

                # Crear panel de control individual (panel de la derecha)
                control_panel = dbc.Card(
                    [
                        dbc.CardHeader(
                            html.H5(f"CONTROL INDIVIDUAL - NODO {sensor_id}", className="mb-0")
                        ),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.P([
                                                    html.Strong("Stay: "),
                                                    state.info.stay_id,
                                                ]),
                                                html.P([
                                                    html.Strong("Estado: "),
                                                    dbc.Badge(
                                                        "ACTIVO" if is_streaming else "IDLE",
                                                        color="success" if is_streaming else "secondary",
                                                    ),
                                                ]),
                                                html.P([
                                                    html.Strong("Frecuencia: "),
                                                    f"{state.info.sample_rate_hz} Hz" if state.info.sample_rate_hz else "No configurado",
                                                ]),
                                                html.P([
                                                    html.Strong("Ejes: "),
                                                    ", ".join([a.upper() for a in state.info.axes]) if state.info.axes else "---",
                                                ]),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                html.H6("ACCIONES:", className="mb-3"),
                                                dbc.ButtonGroup(
                                                    [
                                                        dbc.Button(
                                                            [html.I(className="bi bi-play-fill me-1"), "SAMPLE"],
                                                            id={"type": "btn-node-sample", "index": sensor_id},
                                                            color="primary",
                                                            disabled=is_streaming,
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="bi bi-pause-fill me-1"), "SET TO IDLE"],
                                                            id={"type": "btn-node-idle", "index": sensor_id},
                                                            color="warning",
                                                            disabled=not is_streaming,
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="bi bi-power me-1"), "SLEEP"],
                                                            id={"type": "btn-node-sleep", "index": sensor_id},
                                                            color="secondary",
                                                        ),
                                                    ],
                                                    className="w-100",
                                                    vertical=False,
                                                ),
                                                html.Div(
                                                    id={"type": "individual-node-feedback", "index": sensor_id},
                                                    className="mt-3",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                ),
                            ]
                        ),
                    ],
                    className="shadow-sm mb-3",
                )
                control_panels.append(control_panel)

            logger.info(f"[CONTROL-RED] Total de tarjetas de nodos creadas: {len(nodes_cards)}")
            logger.info(f"[CONTROL-RED] Total de paneles de control creados: {len(control_panels)}")

            if not nodes_cards:
                logger.warning("[CONTROL-RED] No se detectaron nodos")
                return dbc.Alert("No se detectaron nodos. Esperando...", color="info"), []

            logger.info(f"[CONTROL-RED] Retornando {len(nodes_cards)} nodos detectados")
            return nodes_cards, control_panels

        @app.callback(
            Output("sampling-network-modal", "is_open"),
            Output("network-config-table", "children"),
            Input("btn-sampling-network", "n_clicks"),
            Input("btn-close-network-modal", "n_clicks"),
            Input("btn-apply-network", "n_clicks"),
            State("sampling-network-modal", "is_open"),
        )
        def toggle_sampling_network_modal(n_open, n_close, n_apply, is_open):
            """Abre/cierra modal de configuración de red."""
            ctx = callback_context
            if not ctx.triggered:
                return is_open, dash.no_update
            
            trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
            
            if trigger_id == "btn-sampling-network":
                # Generar tabla de configuración
                table_rows = []
                for sensor_id, state in self.manager.sensors.items():
                    row = html.Tr([
                        html.Td(dbc.Checkbox(id={"type": "network-node-enable", "index": sensor_id}, value=True)),
                        html.Td(sensor_id),
                        html.Td(state.info.stay_id),
                        html.Td(dbc.Select(
                            id={"type": "network-node-rate", "index": sensor_id},
                            options=[
                                {"label": "32 Hz", "value": 32},
                                {"label": "64 Hz", "value": 64},
                                {"label": "128 Hz", "value": 128},
                                {"label": "256 Hz (default)", "value": 256},
                                {"label": "512 Hz", "value": 512},
                                {"label": "1024 Hz", "value": 1024},
                                {"label": "2048 Hz", "value": 2048},
                                {"label": "4096 Hz", "value": 4096},
                            ],
                            value=state.info.sample_rate_hz or 256,
                        )),
                        html.Td([
                            dbc.Checkbox(id={"type": "network-node-axis-x", "index": sensor_id}, value=True, label="X", className="me-2"),
                            dbc.Checkbox(id={"type": "network-node-axis-y", "index": sensor_id}, value=True, label="Y", className="me-2"),
                            dbc.Checkbox(id={"type": "network-node-axis-z", "index": sensor_id}, value=True, label="Z"),
                        ]),
                        html.Td(dbc.Select(
                            id={"type": "network-node-format", "index": sensor_id},
                            options=[
                                {"label": "Float (32-bit)", "value": "float"},
                            ],
                            value="float",
                            disabled=True,  # Solo Float soportado en modo SYNC
                        )),
                    ])
                    table_rows.append(row)
                
                table = dbc.Table(
                    [
                        html.Thead(html.Tr([
                            html.Th("Habilitar"),
                            html.Th("Nodo"),
                            html.Th("Stay"),
                            html.Th("Frecuencia"),
                            html.Th("Ejes"),
                            html.Th("Formato"),
                        ])),
                        html.Tbody(table_rows),
                    ],
                    bordered=True,
                    hover=True,
                    responsive=True,
                    striped=True,
                )
                
                return True, table
            
            elif trigger_id == "btn-close-network-modal":
                return False, dash.no_update
            
            # Si se presiona Apply, dejar abierto (será cerrado después de aplicar)
            elif trigger_id == "btn-apply-network":
                return False, dash.no_update
            
            return is_open, dash.no_update

        @app.callback(
            Output("network-feedback", "children"),
            Output("network-state-store", "data"),
            Input("btn-apply-network", "n_clicks"),
            State({"type": "network-node-enable", "index": dash.dependencies.ALL}, "value"),
            State({"type": "network-node-enable", "index": dash.dependencies.ALL}, "id"),
            State({"type": "network-node-rate", "index": dash.dependencies.ALL}, "value"),
            State({"type": "network-node-axis-x", "index": dash.dependencies.ALL}, "value"),
            State({"type": "network-node-axis-y", "index": dash.dependencies.ALL}, "value"),
            State({"type": "network-node-axis-z", "index": dash.dependencies.ALL}, "value"),
            State({"type": "network-node-format", "index": dash.dependencies.ALL}, "value"),
            prevent_initial_call=True,
        )
        def apply_and_start_sampling_network(n_clicks, enabled_list, id_list, rates, axis_x, axis_y, axis_z, formats):
            """Configura e inicia múltiples nodos (Sampling Network)."""
            import traceback  # Importar al inicio del callback
            
            logger.info(f"[SAMPLING NETWORK] Callback ejecutado - n_clicks={n_clicks}, enabled_list={enabled_list}")
            
            if not n_clicks:
                logger.warning("[SAMPLING NETWORK] n_clicks es None o 0 - abortando")
                return dash.no_update, dash.no_update
            
            try:
                success_sensors = []
                failed_sensors = []
                state_data = {}
                enabled_sensor_ids = []

                # PASO 1: Configurar todos los nodos habilitados
                logger.info("[SAMPLING NETWORK] PASO 1: Configurando todos los nodos...")
                for i, (enabled, node_id_dict) in enumerate(zip(enabled_list, id_list)):
                    if not enabled:
                        continue

                    sensor_id = node_id_dict["index"]
                    rate = rates[i]

                    # Construir lista de ejes activos
                    axes = []
                    if axis_x[i]:
                        axes.append("x")
                    if axis_y[i]:
                        axes.append("y")
                    if axis_z[i]:
                        axes.append("z")

                    data_format = formats[i]

                    # Guardar configuración en state
                    state_data[sensor_id] = {
                        "rate": rate,
                        "axes": axes,
                        "format": data_format,
                    }

                    try:
                        # Solo configurar, NO iniciar todavía
                        logger.info(f"Configurando nodo {sensor_id}: {rate}Hz, {axes}, {data_format}")
                        self.manager.configure(sensor_id, sample_rate=rate, axes=axes, data_format=data_format)
                        enabled_sensor_ids.append(sensor_id)
                        logger.info(f"Nodo {sensor_id} configurado correctamente")
                    except Exception as e:
                        error_detail = traceback.format_exc()
                        logger.error(f"Error configurando nodo {sensor_id}: {e}\n{error_detail}")
                        failed_sensors.append((sensor_id, f"Config error: {str(e)}"))

                # PASO 2: Inicializar SyncSamplingNetwork con TODOS los nodos habilitados
                if enabled_sensor_ids and hasattr(self.manager.client, 'initialize_sync_network'):
                    try:
                        logger.info(f"[SAMPLING NETWORK] PASO 2: Inicializando SyncSamplingNetwork con {len(enabled_sensor_ids)} nodos: {enabled_sensor_ids}")
                        self.manager.client.initialize_sync_network(enabled_sensor_ids)
                        logger.info("SyncSamplingNetwork inicializada correctamente")
                    except Exception as e:
                        logger.warning(f"No se pudo inicializar SyncSamplingNetwork: {e}")
                        logger.info("Los nodos intentarán métodos alternativos individualmente")

                # PASO 3: Iniciar threads de streaming para cada nodo
                logger.info("[SAMPLING NETWORK] PASO 3: Iniciando streaming threads...")
                for sensor_id in enabled_sensor_ids:
                    try:
                        logger.info(f"Iniciando streaming para nodo {sensor_id}...")
                        self.manager.start(sensor_id)
                        success_sensors.append(sensor_id)
                        logger.info(f"Nodo {sensor_id} iniciado correctamente")
                    except Exception as e:
                        # CRÍTICO: Capturar traceback completo
                        error_detail = traceback.format_exc()

                        # Registrar en el logger con TODOS los detalles
                        logger.error(
                            f"Error iniciando nodo {sensor_id}:\n"
                            f"Tipo de error: {type(e).__name__}\n"
                            f"Mensaje: {str(e)}\n"
                            f"Traceback completo:\n{error_detail}"
                        )

                        # También imprimir a consola para debugging inmediato
                        print(f"\n{'='*80}")
                        print(f"ERROR DETALLADO - Nodo {sensor_id}")
                        print(f"{'='*80}")
                        print(f"Tipo: {type(e).__name__}")
                        print(f"Mensaje: {str(e)}")
                        print(f"\nTraceback completo:")
                        print(error_detail)
                        print(f"{'='*80}\n")

                        failed_sensors.append((sensor_id, str(e)))
                        logger.error(f"Error iniciando nodo {sensor_id}: {e}")
                
                # Iniciar procesamiento FFT para visualización en tiempo real
                if success_sensors:
                    try:
                        self.manager.start_fft_processing()
                        logger.info("Procesamiento FFT iniciado para visualización en tiempo real")
                    except Exception as e:
                        logger.warning(f"No se pudo iniciar procesamiento FFT: {e}")
                
                # Generar feedback
                if success_sensors and not failed_sensors:
                    feedback = dbc.Alert(
                        [
                            html.H5("Sampling Network Iniciado", className="alert-heading"),
                            html.P(f"Nodos activos: {', '.join(map(str, success_sensors))}"),
                        ],
                        color="success",
                    )
                elif success_sensors and failed_sensors:
                    feedback = dbc.Alert(
                        [
                            html.H5("Sampling Network Iniciado Parcialmente", className="alert-heading"),
                            html.P(f"Nodos exitosos: {', '.join(map(str, success_sensors))}"),
                            html.P(f"Nodos fallidos: {', '.join([str(f[0]) for f in failed_sensors])}"),
                            html.Hr(),
                            html.P("Errores:", className="mb-0 font-weight-bold"),
                            html.Ul([html.Li(f"Nodo {f[0]}: {f[1]}") for f in failed_sensors]),
                        ],
                        color="warning",
                    )
                else:
                    feedback = dbc.Alert(
                        [
                            html.H5("No se pudo iniciar ningún nodo", className="alert-heading"),
                            html.P("Errores:", className="mb-0"),
                            html.Ul([html.Li(f"Nodo {f[0]}: {f[1]}") for f in failed_sensors]),
                        ],
                        color="danger",
                    )
                
                logger.info(f"[SAMPLING NETWORK] Retornando feedback - success: {len(success_sensors)}, failed: {len(failed_sensors)}")
                return feedback, state_data
                
            except Exception as e:
                logger.exception("Error crítico en apply_and_start_sampling_network")
                return dbc.Alert(f"Error crítico: {str(e)}", color="danger"), {}

        @app.callback(
            Output("idle-feedback", "children"),
            Input("btn-set-nodes-idle", "n_clicks"),
            prevent_initial_call=True,
        )
        def set_all_nodes_to_idle(n_clicks):
            """Detiene todos los nodos y los pone en modo IDLE."""
            if not n_clicks:
                return dash.no_update
            
            try:
                # Detener todos los streams
                stopped_sensors = []
                for sensor_id in list(self.manager.sensors.keys()):
                    if self.manager.sensors[sensor_id].streaming:
                        self.manager.stop(sensor_id)
                        stopped_sensors.append(sensor_id)

                logger.info("Todos los streams detenidos (CSV cerrados, InfluxDB detenido)")

                # Resetear el estado de SyncSamplingNetwork para permitir reinicio
                if hasattr(self.manager.client, 'reset_sync_network'):
                    try:
                        self.manager.client.reset_sync_network()
                        logger.info("SyncSamplingNetwork reseteada - lista para nuevo muestreo")
                    except Exception as e:
                        logger.warning(f"No se pudo resetear SyncSamplingNetwork: {e}")

                # Poner nodos en IDLE (solo en modo REAL)
                if hasattr(self.manager.client, 'nodes'):
                    idle_results = []
                    for sensor_id, node in self.manager.client.nodes.items():
                        try:
                            logger.info(f"Poniendo nodo {sensor_id} en IDLE...")
                            idle_status = node.setToIdle()
                            
                            # Esperar confirmación (máx 5 segundos)
                            for _ in range(50):
                                if idle_status.complete():
                                    idle_results.append((sensor_id, True))
                                    logger.info(f"Nodo {sensor_id} en IDLE")
                                    break
                                time.sleep(0.1)
                            else:
                                idle_results.append((sensor_id, False))
                                logger.warning(f"Timeout esperando IDLE para nodo {sensor_id}")
                        except Exception as e:
                            idle_results.append((sensor_id, False))
                            logger.error(f"Error poniendo nodo {sensor_id} en IDLE: {e}")
                    
                    success_count = sum(1 for r in idle_results if r[1])
                    success_msg = f"Streams detenidos. Nodos en IDLE: {success_count}/{len(idle_results)}"
                else:
                    # Modo DEMO
                    success_msg = f"Streams detenidos (modo DEMO). Sensores afectados: {len(stopped_sensors)}"
                
                # Feedback de éxito
                feedback = dbc.Alert(
                        [
                            html.I(className="bi bi-check-circle-fill me-2"),
                            html.Span(success_msg),
                        ],
                        color="success",
                    )
                
                return feedback
                
            except Exception as e:
                logger.exception("Error en set_all_nodes_to_idle")
                return dbc.Alert(f"Error: {str(e)}", color="danger")

        @app.callback(
            Output("network-control-feedback", "children"),
            Input("btn-discover-sensors", "n_clicks"),
            prevent_initial_call=True,
        )
        def discover_sensors(n_clicks):
            """Discover wireless sensors and update the nodes list."""
            if not n_clicks:
                return dash.no_update

            try:
                # Call refresh_nodes on the client
                logger.info("Manual sensor discovery requested")
                new_sensors = self.manager.client.refresh_nodes()

                # Trigger manager discovery to update internal state
                self.manager.discover()

                # Build feedback message
                if new_sensors:
                    sensor_list = ", ".join([s.sensor_id for s in new_sensors])
                    feedback = dbc.Alert(
                        [
                            html.I(className="bi bi-check-circle-fill me-2"),
                            html.Span(f"Descubrimiento exitoso: {len(new_sensors)} sensor(es) encontrado(s) - {sensor_list}"),
                        ],
                        color="success",
                    )
                else:
                    feedback = dbc.Alert(
                        [
                            html.I(className="bi bi-info-circle-fill me-2"),
                            html.Span("No se encontraron nuevos sensores"),
                        ],
                        color="info",
                    )

                logger.info(f"Sensor discovery completed: {len(new_sensors)} sensor(s) found")
                return feedback

            except Exception as e:
                logger.exception("Error en discover_sensors")
                return dbc.Alert(f"Error: {str(e)}", color="danger")

        # Callback eliminado: show_individual_node_controls
        # Los controles individuales ahora se generan automáticamente en update_detected_nodes_list

        @app.callback(
            Output({"type": "individual-node-feedback", "index": dash.dependencies.MATCH}, "children"),
            Input({"type": "btn-node-sample", "index": dash.dependencies.MATCH}, "n_clicks"),
            Input({"type": "btn-node-idle", "index": dash.dependencies.MATCH}, "n_clicks"),
            Input({"type": "btn-node-sleep", "index": dash.dependencies.MATCH}, "n_clicks"),
            State({"type": "btn-node-sample", "index": dash.dependencies.MATCH}, "id"),
            prevent_initial_call=True,
        )
        def handle_individual_node_actions(n_sample, n_idle, n_sleep, button_id):
            """Maneja las acciones individuales de cada nodo."""
            ctx = callback_context
            if not ctx.triggered:
                return dash.no_update
            
            trigger_id = ctx.triggered[0]["prop_id"]
            sensor_id = button_id["index"]
            
            try:
                # Acción: Sample (configurar e iniciar)
                if "btn-node-sample" in trigger_id:
                    # Usar configuración actual del nodo
                    state = self.manager.sensors.get(sensor_id)
                    if state:
                        rate = state.info.sample_rate_hz or 256
                        axes = state.info.axes or ["x", "y", "z"]
                        self.manager.configure_sensor(sensor_id, sample_rate_hz=rate, axes=axes)
                    
                    self.manager.start(sensor_id)
                    logger.info(f"Nodo {sensor_id} iniciado individualmente")
                    return dbc.Alert(f"Nodo {sensor_id} iniciado correctamente", color="success")
                
                # Acción: Set to Idle (detener)
                elif "btn-node-idle" in trigger_id:
                    self.manager.stop(sensor_id)
                    
                    # Poner en IDLE (solo modo REAL)
                    if hasattr(self.manager.client, 'nodes'):
                        node = self.manager.client.nodes.get(sensor_id)
                        if node:
                            try:
                                idle_status = node.setToIdle()
                                for _ in range(50):
                                    if idle_status.complete():
                                        break
                                    time.sleep(0.1)
                            except Exception as e:
                                logger.warning(f"Error poniendo nodo {sensor_id} en IDLE: {e}")
                    
                    logger.info(f"Nodo {sensor_id} detenido")
                    return dbc.Alert(f"Nodo {sensor_id} detenido", color="warning")
                
                # Acción: Sleep (modo ultra bajo consumo)
                elif "btn-node-sleep" in trigger_id:
                    self.manager.stop(sensor_id)
                    
                    if hasattr(self.manager.client, 'nodes'):
                        node = self.manager.client.nodes.get(sensor_id)
                        if node:
                            try:
                                node.sleep()
                                logger.info(f"Nodo {sensor_id} en modo SLEEP")
                                return dbc.Alert(
                                    [
                                        html.P(f"Nodo {sensor_id} en modo SLEEP"),
                                        html.P("Requiere ciclo de power para despertar", className="mb-0 small"),
                                    ],
                                    color="secondary",
                                )
                            except Exception as e:
                                logger.error(f"Error poniendo nodo {sensor_id} en SLEEP: {e}")
                                return dbc.Alert(f"Nodo {sensor_id} no encontrado", color="danger")
                    else:
                        return dbc.Alert("Modo SLEEP no disponible en modo DEMO", color="info")
                
                return dash.no_update
                
            except Exception as e:
                logger.exception(f"Error en acción individual para nodo {sensor_id}")
                return dbc.Alert(f"Error: {str(e)}", color="danger")

    def run(self, host: str = "0.0.0.0", port: int = 8050) -> None:
        self.dash_app.run(host=host, port=port)


__all__ = ["DashApp", "load_persisted_tension", "TENSION_CSV_HEADERS"]
