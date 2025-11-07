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

from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.utils.timeutils import DEFAULT_TZ
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

        # Nueva pestaña: Acelerómetro en Tiempo Real
        accel_tab = dbc.Tab(
            label="Acelerómetro",
            tab_id="accelerometer",
            children=[
                dcc.Store(id="accel-active-sensors", data=[]),  # Store para rastrear sensores activos
                html.Div(
                    id="accel-sensors-container",
                    children=[
                        dbc.Alert(
                            "⏳ Esperando sensores activos...",
                            color="info",
                            className="text-center"
                        )
                    ]
                ),
            ],
        )

        # Nueva pestaña "Control de Red" estilo SensorConnect
        network_control_tab = create_network_control_tab()

        self.dash_app.layout = dbc.Container(
            [
                html.H1("MSCL TENSION PLATFORM", className="mb-4 fw-bold"),
                dbc.Tabs(
                    [network_control_tab, realtime_tab, accel_tab],
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

        # ===== CALLBACKS PARA PESTAÑA ACELERÓMETRO DINÁMICO =====

        @app.callback(
            Output("accel-active-sensors", "data"),
            Input("interval", "n_intervals"),
            State("accel-active-sensors", "data"),
        )
        def track_active_sensors(n, current_sensors):
            """Detecta cambios en sensores activos para evitar recrear tarjetas innecesariamente."""
            streaming_sensor_ids = sorted([
                sensor_id
                for sensor_id, state in self.manager.sensors.items()
                if state.streaming
            ])

            # Solo actualizar si la lista cambió
            if streaming_sensor_ids != current_sensors:
                return streaming_sensor_ids

            raise dash.exceptions.PreventUpdate

        @app.callback(
            Output("accel-sensors-container", "children"),
            Input("accel-active-sensors", "data"),
        )
        def populate_accelerometer_sensors(active_sensors):
            """Genera tarjetas SOLO cuando cambia la lista de sensores activos (evita parpadeo)."""
            if not active_sensors:
                return [
                    dbc.Alert(
                        "⏸️ No hay sensores activos. Inicie el monitoreo desde la pestaña 'Control de Red'.",
                        color="warning",
                        className="text-center"
                    )
                ]

            cards = []
            for sensor_id in active_sensors:
                card = dbc.Card(
                    [
                        dbc.CardHeader(f"Acelerómetro en Tiempo Real - Sensor {sensor_id}"),
                        dbc.CardBody(
                            [
                                dcc.Graph(
                                    id={"type": "accel-graph", "index": sensor_id},
                                    config={
                                        "displayModeBar": False,  # Ocultar barra para menos overhead
                                        "staticPlot": False,
                                    },
                                    style={"height": "500px"},
                                ),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
                )
                cards.append(card)

            return cards

        @app.callback(
            Output({"type": "accel-graph", "index": dash.dependencies.MATCH}, "figure"),
            Input("interval", "n_intervals"),
            State({"type": "accel-graph", "index": dash.dependencies.MATCH}, "id"),
        )
        def update_accelerometer_graph(n, graph_id):
            """Actualiza gráfica de acelerómetro - OPTIMIZADO para fluidez."""
            sensor_id = graph_id["index"]

            try:
                # Verificar que el sensor siga activo
                sensor_state = self.manager.sensors.get(sensor_id)
                if not sensor_state or not sensor_state.streaming:
                    raise dash.exceptions.PreventUpdate

                # Obtener buffer más corto para menos datos y más fluidez (2 segundos)
                buffer_data = self.realtime.get_display_buffer(sensor_id, window_seconds=2.0)

                if buffer_data is None or len(buffer_data[0]) == 0:
                    raise dash.exceptions.PreventUpdate

                timestamps, samples = buffer_data

                # Ordenar por timestamp
                if len(timestamps) > 1:
                    sort_indices = np.argsort(timestamps)
                    timestamps = timestamps[sort_indices]
                    samples = samples[sort_indices]

                # Submuestreo más agresivo para menos puntos = más fluido (1 de cada 4)
                subsample_rate = 4
                timestamps = timestamps[::subsample_rate]
                samples = samples[::subsample_rate]

                # Calcular tiempos relativos
                if len(timestamps) > 0:
                    time_offset = timestamps[0]
                    times = timestamps - time_offset
                else:
                    raise dash.exceptions.PreventUpdate

                # Extraer cada eje
                if samples.ndim == 2 and samples.shape[1] >= 3:
                    x_data = samples[:, 0]
                    y_data = samples[:, 1]
                    z_data = samples[:, 2]
                else:
                    raise dash.exceptions.PreventUpdate

                # Obtener ejes activos
                active_axes = ['x', 'y', 'z']
                if sensor_state.info.axes:
                    active_axes = [axis.lower() for axis in sensor_state.info.axes]

                # Crear gráfica ULTRA-OPTIMIZADA
                fig = go.Figure()

                if 'x' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=x_data,
                        mode='lines',
                        name='X',
                        line=dict(color='#e74c3c', width=1.2),
                        hoverinfo='skip',  # Desactivar hover para mejor rendimiento
                    ))

                if 'y' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=y_data,
                        mode='lines',
                        name='Y',
                        line=dict(color='#3498db', width=1.2),
                        hoverinfo='skip',
                    ))

                if 'z' in active_axes:
                    fig.add_trace(go.Scattergl(
                        x=times, y=z_data,
                        mode='lines',
                        name='Z',
                        line=dict(color='#2ecc71', width=1.2),
                        hoverinfo='skip',
                    ))

                # Layout MINIMALISTA para mejor rendimiento
                axes_str = ', '.join([a.upper() for a in active_axes])
                fig.update_layout(
                    title={
                        'text': f"Sensor {sensor_id} | {len(times)} pts | {axes_str}",
                        'font': {'size': 14}
                    },
                    xaxis_title="Tiempo (s)",
                    yaxis_title="g",
                    template="plotly_white",
                    height=500,
                    hovermode=False,  # Desactivar hover mode
                    showlegend=True,
                    uirevision=f'accel-{sensor_id}',  # CRÍTICO: preserva zoom/pan
                    margin=dict(l=50, r=10, t=50, b=40),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.05,
                        xanchor="center",
                        x=0.5,
                    ),
                    # Optimizaciones de animación
                    transition={'duration': 0},  # Sin transiciones
                )

                # Ejes simplificados
                fig.update_xaxes(
                    showgrid=True,
                    gridwidth=0.5,
                    gridcolor='#e0e0e0',
                    fixedrange=False,  # Permitir zoom
                )
                fig.update_yaxes(
                    showgrid=True,
                    gridwidth=0.5,
                    gridcolor='#e0e0e0',
                    fixedrange=False,
                )

                return fig

            except dash.exceptions.PreventUpdate:
                raise
            except Exception as e:
                logger.error(f"[ACCEL] Error updating sensor {sensor_id}: {e}", exc_info=True)
                raise dash.exceptions.PreventUpdate

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
                is_sleeping = state.sleeping
                last_sample_time = getattr(state, '_last_sample_time', None)

                if is_sleeping:
                    status_badge = dbc.Badge("SLEEP", color="dark", className="me-2")
                    connection_msg = html.Small("Modo bajo consumo", className="text-muted")
                elif is_streaming:
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
                                                        "SLEEP" if is_sleeping else ("ACTIVO" if is_streaming else "IDLE"),
                                                        color="dark" if is_sleeping else ("success" if is_streaming else "secondary"),
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
                                                            [html.I(className="bi bi-pause-fill me-1"), "SET TO IDLE" if not is_sleeping else "WAKE UP"],
                                                            id={"type": "btn-node-idle", "index": sensor_id},
                                                            color="warning" if not is_sleeping else "success",
                                                            disabled=not (is_streaming or is_sleeping),
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="bi bi-power me-1"), "SLEEP"],
                                                            id={"type": "btn-node-sleep", "index": sensor_id},
                                                            color="secondary",
                                                            disabled=is_sleeping,
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
                            value=state.info.sample_rate_hz or 128,
                        )),
                        html.Td([
                            dbc.Checkbox(id={"type": "network-node-axis-x", "index": sensor_id}, value=False, label="X", className="me-2"),
                            dbc.Checkbox(id={"type": "network-node-axis-y", "index": sensor_id}, value=False, label="Y", className="me-2"),
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

                                    # Limpiar estado sleeping si estaba dormido
                                    if sensor_id in self.manager.sensors:
                                        self.manager.sensors[sensor_id].sleeping = False

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
            Input({"type": "btn-node-idle", "index": dash.dependencies.MATCH}, "n_clicks"),
            Input({"type": "btn-node-sleep", "index": dash.dependencies.MATCH}, "n_clicks"),
            State({"type": "btn-node-idle", "index": dash.dependencies.MATCH}, "id"),
            prevent_initial_call=True,
        )
        def handle_individual_node_actions(n_idle, n_sleep, button_id):
            """Maneja las acciones individuales de cada nodo (IDLE y SLEEP)."""
            ctx = callback_context
            if not ctx.triggered:
                return dash.no_update

            trigger_id = ctx.triggered[0]["prop_id"]
            sensor_id = button_id["index"]

            try:
                # Acción: Set to Idle (detener o despertar de Sleep)
                if "btn-node-idle" in trigger_id:
                    state = self.manager.sensors.get(sensor_id)

                    # Si está en modo Sleep, despertar el nodo
                    if state and state.sleeping:
                        if hasattr(self.manager.client, 'nodes'):
                            node = self.manager.client.nodes.get(sensor_id)
                            if node:
                                try:
                                    idle_status = node.setToIdle()
                                    for _ in range(50):
                                        if idle_status.complete():
                                            break
                                        time.sleep(0.1)

                                    # Marcar que ya no está en sleep
                                    state.sleeping = False
                                    logger.info(f"Nodo {sensor_id} despertado de SLEEP a IDLE")
                                    return dbc.Alert(f"Nodo {sensor_id} despertado correctamente", color="success")
                                except Exception as e:
                                    logger.error(f"Error despertando nodo {sensor_id}: {e}")
                                    return dbc.Alert(f"Error al despertar nodo: {str(e)}", color="danger")

                    # Si está en streaming, detener
                    else:
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
                if "btn-node-sleep" in trigger_id:
                    self.manager.stop(sensor_id)

                    if hasattr(self.manager.client, 'nodes'):
                        node = self.manager.client.nodes.get(sensor_id)
                        if node:
                            try:
                                node.sleep()

                                # Marcar el nodo como durmiendo
                                state = self.manager.sensors.get(sensor_id)
                                if state:
                                    state.sleeping = True

                                logger.info(f"Nodo {sensor_id} en modo SLEEP")
                                return dbc.Alert(
                                    [
                                        html.P(f"Nodo {sensor_id} en modo SLEEP"),
                                        html.P("Usa el botón 'WAKE UP' para despertar", className="mb-0 small"),
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
