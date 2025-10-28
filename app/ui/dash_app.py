"""Dash web application wiring."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import dash
from dash import Input, Output, State, dcc, html, dash_table, callback_context
import plotly.graph_objects as go
import yaml

from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
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
        fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 0], mode="lines", name="Ax"))
        fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 1], mode="lines", name="Ay"))
        fig_time.add_trace(go.Scatter(x=timestamps, y=samples[:, 2], mode="lines", name="Az"))
        fig_time.update_layout(title="Aceleración reciente", xaxis_title="Tiempo (s)", yaxis_title="g")
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
        fig_psd.update_layout(xaxis_title="Hz", yaxis_title="Power", title="PSD")
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
        self.dash_app = dash.Dash(__name__, suppress_callback_exceptions=True)
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

        self.dash_app.layout = html.Div(
            [
                html.H2("MSCL Tension Platform"),
                dcc.Tabs(
                    id="tabs",
                    value="network",
                    children=[
                        dcc.Tab(
                            label="Red",
                            value="network",
                            children=[
                                html.Div(
                                    [
                                        html.Button("Descubrir", id="btn-discover", n_clicks=0),
                                        html.Button("Start All", id="btn-start-all", n_clicks=0),
                                        html.Button("Stop All", id="btn-stop-all", n_clicks=0),
                                        dcc.Dropdown(
                                            id="sensor-selector",
                                            options=stay_options,
                                            placeholder="Selecciona sensor",
                                        ),
                                        html.Button("Start Sensor", id="btn-start-sensor", n_clicks=0),
                                        html.Button("Stop Sensor", id="btn-stop-sensor", n_clicks=0),
                                    ],
                                    style={"display": "flex", "gap": "0.5rem", "flexWrap": "wrap"},
                                ),
                                html.Div(id="network-content"),
                            ],
                        ),
                        dcc.Tab(
                            label="Tiempo real",
                            value="realtime",
                            children=[
                                dcc.Dropdown(
                                    id="realtime-sensor",
                                    options=stay_options,
                                    placeholder="Selecciona sensor",
                                    value=stay_options[0]["value"] if stay_options else None,
                                ),
                                dcc.RadioItems(
                                    id="mode-selector",
                                    options=[
                                        {"label": "AUTO", "value": "AUTO"},
                                        {"label": "GUIADA", "value": "GUIDED"},
                                    ],
                                    value="AUTO",
                                    inline=True,
                                ),
                                dcc.Input(
                                    id="guided-f1",
                                    type="number",
                                    placeholder="f1 propuesta (Hz)",
                                ),
                                dcc.Input(
                                    id="guided-tol",
                                    type="number",
                                    placeholder="Tolerancia %",
                                    value=10,
                                ),
                                html.Div(id="realtime-card"),
                                dcc.Graph(id="realtime-accel"),
                                dcc.Graph(id="realtime-psd"),
                                dcc.Graph(id="realtime-history"),
                            ],
                        ),
                        dcc.Tab(
                            label="Histórico",
                            value="history",
                            children=[
                                dcc.Dropdown(
                                    id="history-sensor",
                                    options=stay_options,
                                    placeholder="Selecciona sensor",
                                ),
                                dcc.Graph(id="history-graph"),
                                html.Button("Abrir carpeta datos", id="btn-open-folder"),
                                html.Div(id="history-status"),
                            ],
                        ),
                        dcc.Tab(
                            label="Configuración",
                            value="config",
                            children=[
                                html.H4("Análisis"),
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
                                    style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "0.5rem"},
                                ),
                                html.H4("Almacenamiento"),
                                html.Label("Directorio base"),
                                dcc.Input(id="cfg-base-dir", value=storage_dir, style={"width": "100%"}),
                                html.Label("Rotación (modo)"),
                                dcc.Dropdown(
                                    id="cfg-rotation-mode",
                                    options=[{"label": "Tiempo", "value": "time"}, {"label": "Tamaño", "value": "size"}],
                                    value=rotation_cfg.get("mode", "time"),
                                ),
                                html.Label("Minutos"),
                                dcc.Input(
                                    id="cfg-rotation-minutes",
                                    type="number",
                                    value=rotation_cfg.get("minutes", 10),
                                ),
                                html.Label("Tamaño (MB)"),
                                dcc.Input(
                                    id="cfg-rotation-mb",
                                    type="number",
                                    value=rotation_cfg.get("max_mb", 100),
                                ),
                                html.H4("Tirantes"),
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
                                html.Button("Guardar configuración", id="btn-save-config"),
                                html.Div(id="config-status"),
                            ],
                        ),
                    ],
                ),
                dcc.Interval(id="interval", interval=self.app_config.get("ui", {}).get("refresh_ms", 1000)),
            ]
        )

    def _register_callbacks(self) -> None:
        app = self.dash_app

        @app.callback(
            Output("network-content", "children"),
            Output("sensor-selector", "options"),
            Input("btn-discover", "n_clicks"),
            Input("interval", "n_intervals"),
        )
        def update_network(_, __):
            triggered = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
            if "btn-discover" in triggered:
                states = self.manager.discover()
            else:
                states = self.manager.get_status()
            stays_options = [
                {"label": state.info.stay_id, "value": state.info.sensor_id} for state in states if state.info
            ]
            table = components.network_table(states)
            return table, stays_options

        @app.callback(
            Output("history-status", "children"),
            Input("btn-open-folder", "n_clicks"),
            prevent_initial_call=True,
        )
        def open_folder(_):
            path = Path(self.app_config.get("storage", {}).get("base_dir", "./data")).resolve()
            return f"Datos en: {path}"

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
                times, values, qa = zip(*history)
                fig_hist.add_trace(go.Scatter(x=list(times), y=list(values), mode="lines+markers"))
                fig_hist.update_layout(title="Tensión (kN)")
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
                    times, values, qa = zip(*history)
                    fig.add_trace(go.Scatter(x=list(times), y=list(values), mode="lines+markers"))
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
        self.dash_app.run(host=host, port=port)


__all__ = ["DashApp"]
