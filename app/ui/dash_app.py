"""Dash web application wiring."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback_context, dcc, html, dash_table
import plotly.graph_objects as go
import yaml

from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.utils.timeutils import DEFAULT_TZ
from app.utils.validators import Thresholds
from app.ui import components

logger = logging.getLogger(__name__)


def _analysis_to_figures(analysis_state):
    if analysis_state is None:
        return go.Figure(), go.Figure(), []
    accel_records = list(analysis_state.recent_accel)
    if accel_records:
        timestamps = accel_records[-1].timestamps
        samples = accel_records[-1].samples
        fig_time = go.Figure()
        time_axis = [
            datetime.fromtimestamp(float(ts), tz=DEFAULT_TZ)
            if not isinstance(ts, datetime)
            else ts
            for ts in timestamps
        ]
        fig_time.add_trace(go.Scatter(x=time_axis, y=samples[:, 0], mode="lines", name="Ax"))
        fig_time.add_trace(go.Scatter(x=time_axis, y=samples[:, 1], mode="lines", name="Ay"))
        fig_time.add_trace(go.Scatter(x=time_axis, y=samples[:, 2], mode="lines", name="Az"))
        fig_time.update_layout(
            title="Aceleración reciente",
            xaxis_title="Tiempo",
            yaxis_title="g",
            template="plotly_white",
        )
    else:
        fig_time = go.Figure()

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
        storage_dir = self.app_config.get("storage", {}).get("base_dir", "./data")
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
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Sensor"),
                                            dcc.Dropdown(
                                                id="realtime-sensor",
                                                options=stay_options,
                                                placeholder="Selecciona sensor",
                                                value=stay_options[0]["value"] if stay_options else None,
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
                            )
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

        history_tab = dbc.Tab(
            label="Histórico",
            tab_id="history",
            children=[
                dbc.Card(
                    [
                        dbc.CardHeader("Consulta de tensión"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Sensor"),
                                                dcc.Dropdown(
                                                    id="history-sensor",
                                                    options=stay_options,
                                                    placeholder="Selecciona sensor",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Abrir carpeta datos",
                                                id="btn-open-folder",
                                                color="secondary",
                                                className="mt-4",
                                            ),
                                            md=3,
                                        ),
                                    ],
                                    className="g-3 align-items-end",
                                ),
                                dbc.Card(
                                    [
                                        dbc.CardBody(dcc.Graph(id="history-graph")),
                                    ],
                                    className="shadow-sm mt-3",
                                ),
                                html.Div(id="history-status", className="mt-3"),
                            ]
                        ),
                    ],
                    className="mb-4 shadow-sm",
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

        self.dash_app.layout = dbc.Container(
            [
                html.H1("MSCL Tension Platform", className="mb-4 fw-bold"),
                dbc.Tabs(
                    [network_tab, realtime_tab, history_tab, config_tab],
                    id="tabs",
                    active_tab="network",
                    className="mb-4",
                ),
                dcc.Interval(id="interval", interval=refresh_interval, n_intervals=0),
            ],
            fluid=True,
            className="bg-light min-vh-100 py-4",
        )

    def _register_callbacks(self) -> None:
        app = self.dash_app

        @app.callback(
            Output("network-content", "children"),
            Output("sensor-selector", "options"),
            Output("realtime-sensor", "options"),
            Output("history-sensor", "options"),
            Output("gateway-status", "children"),
            Input("btn-discover", "n_clicks"),
            Input("interval", "n_intervals"),
        )
        def update_network(_, __):
            triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
            if "btn-discover" in triggered:
                states = self.manager.discover()
            else:
                states = self.manager.get_status()
            stay_options = [
                {"label": stay.stay_id, "value": stay.sensor_id} for stay in self.stays
            ]
            table = components.network_table(states)
            gateway_badge = components.gateway_status_badge(self.manager.get_gateway_status())
            return table, stay_options, stay_options, stay_options, gateway_badge

        @app.callback(
            Output("network-feedback", "children"),
            Output("gateway-status", "children"),
            Input("btn-connect-gateway", "n_clicks"),
            Input("btn-disconnect-gateway", "n_clicks"),
            State("gateway-host", "value"),
            State("gateway-port", "value"),
            prevent_initial_call=True,
        )
        def control_gateway(connect_clicks, disconnect_clicks, host, port):
            triggered = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
            status = self.manager.get_gateway_status()
            feedback = dash.no_update
            try:
                if triggered == "btn-connect-gateway":
                    host_value = host or self.gateway_config.get("host", "127.0.0.1")
                    port_value = int(port) if port not in (None, "") else int(
                        self.gateway_config.get("port", 0)
                    )
                    if port_value <= 0:
                        raise ValueError("El puerto debe ser mayor a 0")
                    status = self.manager.connect_gateway(host_value, port_value)
                    self.gateway_config["host"] = host_value
                    self.gateway_config["port"] = port_value
                    color = "success" if status.connected else "warning"
                    message = status.message or "Gateway conectado"
                    feedback = dbc.Alert(message, color=color, dismissable=True)
                elif triggered == "btn-disconnect-gateway":
                    status = self.manager.disconnect_gateway()
                    message = status.message or "Gateway desconectado"
                    feedback = dbc.Alert(message, color="warning", dismissable=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Gateway control error")
                feedback = dbc.Alert(str(exc), color="danger", dismissable=True)
            badge = components.gateway_status_badge(status)
            return feedback, badge

        @app.callback(
            Output("history-status", "children"),
            Input("btn-open-folder", "n_clicks"),
            prevent_initial_call=True,
        )
        def open_folder(_):
            path = Path(self.app_config.get("storage", {}).get("base_dir", "./data")).resolve()
            return dbc.Alert(f"Datos en: {path}", color="info", dismissable=True)

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
            State("realtime-sensor", "value"),
        )
        def update_realtime(_, sensor_id):
            snapshot = self.realtime.snapshot()
            analysis = snapshot.get(sensor_id)
            stay = next((s for s in self.stays if s.sensor_id == sensor_id), None)
            card = components.realtime_card(stay, analysis) if stay else html.Div("Sin datos")
            fig_time, fig_psd, history = _analysis_to_figures(analysis)
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
            Output("history-graph", "figure"),
            Input("interval", "n_intervals"),
            State("history-sensor", "value"),
        )
        def update_history(_, sensor_id):
            snapshot = self.realtime.snapshot()
            analysis = snapshot.get(sensor_id)
            fig = go.Figure()
            if analysis:
                _, _, history = _analysis_to_figures(analysis)
                if history:
                    times, values, _qa = zip(*history)
                    fig.add_trace(go.Scatter(x=list(times), y=list(values), mode="lines+markers"))
            fig.update_layout(
                title="Tensión (kN)",
                xaxis_title="Tiempo",
                yaxis_title="kN",
                template="plotly_white",
            )
            return fig

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
            triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
            if "btn-start-all" in triggered:
                self.manager.start_all()
            elif "btn-stop-all" in triggered:
                self.manager.stop_all()
            elif "btn-start-sensor" in triggered and sensor_value:
                self.manager.start(sensor_value)
            elif "btn-stop-sensor" in triggered and sensor_value:
                self.manager.stop(sensor_value)
            return sensor_value

    def run(self, host: str = "0.0.0.0", port: int = 8050) -> None:
        self.dash_app.run_server(host=host, port=port)


__all__ = ["DashApp"]
