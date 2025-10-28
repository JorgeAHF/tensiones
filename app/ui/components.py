"""Reusable Dash components for the monitoring UI."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.acquisition.mscl_client import GatewayStatus
from app.acquisition.stream_manager import AnalysisState, SensorState, StayDefinition
from app.utils.timeutils import DEFAULT_TZ


SEM_COLOR_MAP = {
    "green": "success",
    "yellow": "warning",
    "orange": "orange",
    "red": "danger",
}


def _format_timestamp(timestamp: Optional[float]) -> str:
    if not timestamp:
        return "-"
    dt = datetime.fromtimestamp(timestamp, tz=DEFAULT_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_axes(axes: Iterable[str]) -> str:
    labels = [axis.upper() for axis in axes]
    return ", ".join(labels) if labels else "-"


def network_table(states: Iterable[SensorState]) -> dash.development.base_component.Component:
    header = html.Thead(
        html.Tr(
            [
                html.Th("Sensor"),
                html.Th("Tirante"),
                html.Th("Fs (Hz)"),
                html.Th("Fs estimado (Hz)"),
                html.Th("Streaming"),
                html.Th("Última muestra"),
                html.Th("Canales activos"),
                html.Th("Batería"),
            ]
        )
    )
    rows = []
    for state in states:
        info = state.info
        battery = (
            f"{info.battery_percent:.0f}%" if info.battery_percent is not None else "-"
        )
        rows.append(
            html.Tr(
                [
                    html.Td(info.sensor_id),
                    html.Td(info.stay_id),
                    html.Td(f"{info.sample_rate_hz:.2f}"),
                    html.Td(f"{state.estimated_fs:.2f}" if state.estimated_fs else "-"),
                    html.Td(dbc.Badge("Sí", color="success") if state.streaming else dbc.Badge("No", color="secondary")),
                    html.Td(_format_timestamp(state.last_sample_timestamp)),
                    html.Td(_format_axes(state.info.axes)),
                    html.Td(battery),
                ]
            )
        )
    body = html.Tbody(rows)
    return dbc.Table([header, body], bordered=True, hover=True, responsive=True, striped=True, className="bg-white shadow-sm")


def network_summary(
    states: Iterable[SensorState],
    *,
    demo_mode: bool = False,
) -> dash.development.base_component.Component:
    states_list = list(states)
    total = len(states_list)
    streaming = sum(1 for state in states_list if state.streaming)
    paused = total - streaming
    latest_timestamp = None
    for state in states_list:
        if state.last_sample_timestamp:
            if latest_timestamp is None or state.last_sample_timestamp > latest_timestamp:
                latest_timestamp = state.last_sample_timestamp
    mode_label = "Demo" if demo_mode else "Hardware real"
    badges = [
        dbc.Badge(f"Sensores: {total}", color="info", className="p-2 me-2"),
        dbc.Badge(f"Streaming: {streaming}", color="success", className="p-2 me-2"),
        dbc.Badge(f"Detenidos: {paused}", color="warning", className="p-2 me-2"),
    ]
    if streaming:
        badges.append(
            dbc.Badge(
                f"Adquisición activa ({mode_label})",
                color="success",
                className="p-2 me-2",
            )
        )
    else:
        badges.append(
            dbc.Badge(
                f"Adquisición detenida ({mode_label})",
                color="secondary",
                className="p-2 me-2",
            )
        )
    if latest_timestamp:
        badges.append(
            dbc.Badge(
                f"Última muestra: {_format_timestamp(latest_timestamp)}",
                color="secondary",
                className="p-2",
            )
        )
    return html.Div(badges, className="d-flex flex-wrap gap-2")


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
    "network_summary",
    "realtime_card",
    "acceleration_graph",
    "psd_graph",
    "history_graph",
    "stay_config_table",
    "gateway_status_badge",
]
