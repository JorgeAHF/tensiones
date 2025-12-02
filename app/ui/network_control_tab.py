"""
Pestaña de Control de Red - Similar a SensorConnect

Esta pestaña implementa la interfaz principal para:
- Detectar nodos automáticamente
- Configurar nodos individualmente
- Iniciar/detener muestreo sincronizado
- Controles individuales por nodo
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_network_control_tab():
    """Crea la pestaña de Control de Red."""
    
    # Modal para configuración de muestreo de red
    sampling_modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Configuración de Sampling Network")),
            dbc.ModalBody(
                [
                    # Tabla de configuración por nodo
                    html.H5("Configurar Nodos", className="mb-3"),
                    html.Div(id="network-config-table"),
                    
                    html.Hr(),
                    
                    # Botones de acción
                    dbc.Alert(
                        "Cada nodo puede tener configuración independiente de frecuencia, ejes y formato de datos.",
                        color="info",
                        className="mb-3",
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Cancelar",
                        id="btn-close-network-modal",
                        className="me-auto",
                        color="secondary",
                    ),
                    dbc.Button(
                        "Apply and Start Network",
                        id="btn-apply-network",
                        color="success",
                        size="lg",
                    ),
                ]
            ),
        ],
        id="sampling-network-modal",
        size="xl",
        is_open=False,
    )
    
    # Modal para configuración de nodo individual
    individual_node_modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id="individual-node-modal-title")),
            dbc.ModalBody(
                [
                    html.Div(id="individual-node-modal-body"),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancelar", id="individual-modal-cancel", className="me-auto"),
                    dbc.Button("Aplicar", id="individual-modal-apply", color="primary"),
                ]
            ),
        ],
        id="individual-node-modal",
        size="lg",
        is_open=False,
    )
    
    # Layout principal de la pestaña
    tab_content = dbc.Tab(
        label="Control de Red",
        tab_id="network-control",
        children=[
            # Modales
            sampling_modal,
            individual_node_modal,
            
            # Layout principal
            dbc.Row(
                [
                    # Columna izquierda: Lista de nodos detectados
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader(
                                        html.H5("Nodos Detectados", className="mb-0")
                                    ),
                                    dbc.CardBody(
                                        [
                                            html.Div(id="detected-nodes-list"),
                                        ],
                                        style={"maxHeight": "600px", "overflowY": "auto"},
                                    ),
                                ],
                                className="shadow-sm mb-3",
                            ),
                        ],
                        width=3,
                    ),
                    
                    # Columna derecha: Base Station Control
                    dbc.Col(
                        [
                            # Card de Base Station
                            dbc.Card(
                                [
                                    dbc.CardHeader(
                                        html.H5("Base Station Control", className="mb-0")
                                    ),
                                    dbc.CardBody(
                                        [
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            dbc.Button(
                                                                [
                                                                    html.I(className="bi bi-broadcast me-2"),
                                                                    "Sampling Network",
                                                                ],
                                                                id="btn-sampling-network",
                                                                color="primary",
                                                                size="lg",
                                                                className="w-100 mb-3",
                                                            ),
                                                            dbc.Button(
                                                                [
                                                                    html.I(className="bi bi-pause-circle me-2"),
                                                                    "Set Nodes To Idle",
                                                                ],
                                                                id="btn-set-nodes-idle",
                                                                color="warning",
                                                                size="lg",
                                                                className="w-100 mb-3",
                                                            ),
                                                            dbc.Button(
                                                                [
                                                                    html.I(className="bi bi-search me-2"),
                                                                    "Descubrir Sensores",
                                                                ],
                                                                id="btn-discover-sensors",
                                                                color="info",
                                                                size="lg",
                                                                className="w-100",
                                                            ),
                                                        ],
                                                        md=6,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            html.Div(id="base-station-status"),
                                                        ],
                                                        md=6,
                                                    ),
                                                ],
                                            ),
                                            html.Hr(),
                                            html.Div(id="network-feedback"),
                                            html.Div(id="idle-feedback"),
                                            html.Div(id="network-control-feedback"),
                                        ]
                                    ),
                                ],
                                className="shadow-sm mb-3",
                            ),
                            
                            # Card de control de nodo individual (se muestra al seleccionar)
                            html.Div(id="individual-node-control-panel"),
                        ],
                        width=9,
                    ),
                ],
                className="g-3",
            ),
        ],
    )
    
    return tab_content
