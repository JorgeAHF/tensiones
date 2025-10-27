"""Reusable Dash components for the monitoring UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import dash
from dash import dash_table, dcc, html

from app.acquisition.stream_manager import AnalysisState, SensorState, StayDefinition
from app.utils.validators import QualityAssessment, Thresholds


@dataclass
class ThresholdView:
    label: str
    value: float


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
                "Sensor": info.sensor_id,
                "Stay": info.stay_id,
                "Fs (Hz)": f"{info.sample_rate_hz:.2f}",
                "Streaming": "Yes" if state.streaming else "No",
                "Last Sample": f"{state.last_sample_timestamp:.1f}" if state.last_sample_timestamp else "-",
            }
        )
    return dash_table.DataTable(
        id="network-table",
        data=data,
        columns=[{"name": k, "id": k} for k in ("Sensor", "Stay", "Fs (Hz)", "Streaming", "Last Sample")],
        style_table={"overflowX": "auto"},
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
    return html.Div(
        className=f"card border-{color}",
        children=[
            html.Div(className="card-header", children=stay.stay_id),
            html.Div(
                className="card-body",
                children=[
                    html.H3(tension_text, className="card-title"),
                    html.P(f"Sensor: {stay.sensor_id}", className="card-text"),
                    html.P(f"QA: {qa_text}", className="card-text"),
                ],
            ),
        ],
        style={"margin": "0.5rem", "minWidth": "220px"},
    )


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
]
