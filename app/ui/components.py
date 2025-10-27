"""Reusable Dash components for the monitoring UI."""
from __future__ import annotations

from typing import Iterable, List, Optional

import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.acquisition.mscl_client import GatewayStatus
from app.acquisition.stream_manager import AnalysisState, SensorState, StayDefinition


SEM_COLOR_MAP = {
    "green": "success",
    "yellow": "warning",
    "orange": "orange",
    "red": "danger",
}


def network_table(states: Iterable[SensorState]) -> dash.development.base_component.Component:
    data = []
    for state in states:
        info = state.info
        data.append(
            {
                "sensor": info.sensor_id,
                "stay": info.stay_id,
                "fs": round(info.sample_rate_hz, 4),
                "data_format": info.data_format,
                "acq_duration": round(info.acquisition_duration_sec, 2),
                "streaming": "Sí" if state.streaming else "No",
                "last_sample": f"{state.last_sample_timestamp:.1f}" if state.last_sample_timestamp else "-",
            }
        )
    columns = [
        {"name": "Sensor", "id": "sensor", "editable": False},
        {"name": "Tirante", "id": "stay", "editable": False},
        {"name": "Fs (Hz)", "id": "fs", "type": "numeric"},
        {
            "name": "Tipo de dato",
            "id": "data_format",
            "presentation": "dropdown",
        },
        {
            "name": "Duración adquisición (s)",
            "id": "acq_duration",
            "type": "numeric",
        },
        {"name": "Streaming", "id": "streaming", "editable": False},
        {"name": "Última muestra", "id": "last_sample", "editable": False},
    ]
    dropdown_map = {
        "data_format": {
            "options": [
                {"label": "Acc XYZ", "value": "acceleration_xyz"},
                {"label": "Acc X", "value": "acceleration_x"},
                {"label": "Acc Y", "value": "acceleration_y"},
                {"label": "Acc Z", "value": "acceleration_z"},
            ]
        }
    }
    return dash_table.DataTable(
        id="network-table",
        data=data,
        columns=columns,
        editable=True,
        dropdown=dropdown_map,
        style_table={"overflowX": "auto"},
        style_header={"fontWeight": "bold"},
        style_data_conditional=[
            {
                "if": {"filter_query": '{streaming} = "Sí"', "column_id": "streaming"},
                "backgroundColor": "#d4edda",
                "color": "#155724",
            },
            {
                "if": {"filter_query": '{streaming} = "No"', "column_id": "streaming"},
                "backgroundColor": "#f8f9fa",
                "color": "#6c757d",
            },
        ],
    )


def realtime_card(
    stay: StayDefinition,
    analysis: Optional[AnalysisState],
) -> dash.development.base_component.Component:
    if stay is None:
        return html.Div("Sin configuración")
    tension_text = "--"
    qa_text = "--"
    color = "secondary"
    if analysis and analysis.last_tension and analysis.last_tension.tension_kN is not None:
        tension = analysis.last_tension.tension_kN
        qa = analysis.last_result.quality if analysis.last_result else None
        qa_flag = qa.flag if qa else None
        qa_text = qa_flag.value if qa_flag else "--"
        level = stay.thresholds.level(tension, qa_flag if qa_flag else None)
        color = SEM_COLOR_MAP.get(level, "secondary")
        tension_text = f"{tension:.1f} kN"
    return dbc.Card(
        [
            dbc.CardHeader(stay.stay_id),
            dbc.CardBody(
                [
                    html.H3(tension_text, className="mb-2"),
                    html.P(f"Sensor: {stay.sensor_id}", className="mb-1"),
                    html.P(f"QA: {qa_text}", className="text-muted"),
                ]
            ),
        ],
        color=color if color != "secondary" else None,
        inverse=True if color in {"success", "warning", "danger"} else False,
        className="mb-3 shadow-sm",
        style={"minWidth": "240px"},
    )


def gateway_status_badge(status: GatewayStatus) -> dash.development.base_component.Component:
    color = "success" if status.connected else "secondary"
    text = "Gateway conectado" if status.connected else "Gateway desconectado"
    if status.host and status.port:
        text = f"{text} ({status.host}:{status.port})"
    return dbc.Badge(text, color=color, className="p-2")


def acceleration_graph(sensor_id: str) -> dash.development.base_component.Component:
    return dcc.Graph(id={"type": "accel-graph", "sensor": sensor_id})


def psd_graph(sensor_id: str) -> dash.development.base_component.Component:
    return dcc.Graph(id={"type": "psd-graph", "sensor": sensor_id})


def history_graph(sensor_id: str) -> dash.development.base_component.Component:
    return dcc.Graph(id={"type": "history-graph", "sensor": sensor_id})


def stay_config_table(stays: List[StayDefinition]) -> dash.development.base_component.Component:
    data = []
    for stay in stays:
        data.append(
            {
                "Stay": stay.stay_id,
                "Sensor": stay.sensor_id,
                "K (N/Hz^2)": stay.k_coefficient,
                "Green": stay.thresholds.green_max,
                "Yellow": stay.thresholds.yellow_max,
                "Orange": stay.thresholds.orange_max,
            }
        )
    return dash_table.DataTable(
        data=data,
        columns=[{"name": k, "id": k} for k in data[0].keys()] if data else [],
        editable=True,
    )


__all__ = [
    "network_table",
    "realtime_card",
    "acceleration_graph",
    "psd_graph",
    "history_graph",
    "stay_config_table",
    "gateway_status_badge",
]
