"""Application entry point."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, List

import yaml
import mscl  # ← AGREGAR ESTA LÍNEA

from app.acquisition.mscl_client import (
    DemoMSCLClient,
    HttpMSCLClient,
    MSCLClient,
    create_demo_client,
)
from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.ui.dash_app import DashApp
from app.utils.logging_setup import configure_logging
from app.utils.validators import Thresholds

LOGGER = logging.getLogger(__name__)


def load_yaml(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_stays(stays_cfg: Dict) -> List[StayDefinition]:
    stays = []
    for entry in stays_cfg.get("stays", []):
        thresholds_cfg = entry.get("thresholds_kN", {})
        stay = StayDefinition(
            stay_id=entry["stay_id"],
            sensor_id=entry["sensor_id"],
            k_coefficient=float(entry.get("k_coefficient_N_per_Hz2", 0.0)),
            thresholds=Thresholds(
                green_max=float(thresholds_cfg.get("green_max", 0)),
                yellow_max=float(thresholds_cfg.get("yellow_max", 0)),
                orange_max=float(thresholds_cfg.get("orange_max", 0)),
            ),
            length_m=entry.get("length_m"),
            mass_density=entry.get("mass_density"),
        )
        stays.append(stay)
    return stays


def create_client(app_config: Dict, stays: List[StayDefinition]) -> MSCLClient:
    default_fs = float(app_config.get("default_fs_hz", 256))
    demo_mode = app_config.get("modes", {}).get("demo", True)
    
    if demo_mode:
        LOGGER.info("Running in DEMO mode")
        stays_config = [
            {"sensor_id": stay.sensor_id, "stay_id": stay.stay_id} for stay in stays
        ]
        return create_demo_client(stays_config, default_fs)
    else:
        LOGGER.info("Connecting to real MSCL Gateway at 192.168.8.101:5000")
        try:
            from app.acquisition.real_mscl_client import RealMSCLClient  # ← AGREGAR
            
            connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
            base_station = mscl.BaseStation(connection)
            
            # Ping para verificar conexión
            if base_station.ping():
                LOGGER.info("Successfully connected to BaseStation")
            else:
                LOGGER.error("BaseStation ping failed")
            
            # Crear configuración de sensores
            sensor_configs = [
                {"sensor_id": stay.sensor_id, "stay_id": stay.stay_id} 
                for stay in stays
            ]
            
            # Crear y retornar cliente real
            return RealMSCLClient(base_station, sensor_configs, default_fs)
            
        except Exception as e:
            LOGGER.error(f"Failed to connect to Gateway: {e}")
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MSCL Tension Platform")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("app/config/app.yaml"),
        help="Path to app configuration file",
    )
    parser.add_argument(
        "--stays",
        type=Path,
        default=Path("app/config/stays.yaml"),
        help="Path to stays configuration file",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8050)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_config = load_yaml(args.config)
    stays_cfg = load_yaml(args.stays)
    stays = build_stays(stays_cfg)

    demo_mode = app_config.get("modes", {}).get("demo", True)

    storage_base = Path(app_config.get("storage", {}).get("base_dir", "./data")).resolve()
    storage_base.mkdir(parents=True, exist_ok=True)

    log_dir = storage_base / "logs"
    configure_logging(log_dir)

    client = create_client(app_config, stays)
    realtime_store = RealtimeDataStore()
    manager = StreamManager(
        client=client,
        stays=stays,
        analysis_cfg=app_config.get("analysis", {}),
        rotation_cfg=app_config.get("storage", {}).get("rotation", {}),
        storage_base=storage_base,
        realtime_store=realtime_store,
    )
    gateway_cfg = app_config.get("mscl_gateway", {})
    if gateway_cfg.get("auto_connect", False):
        host = gateway_cfg.get("host", "127.0.0.1")
        port = int(gateway_cfg.get("port", 5000))
        try:
            status = manager.connect_gateway(host, port)
            if not status.connected:
                LOGGER.warning("Gateway auto-connect reported disconnected: %s", status.message)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to auto-connect to gateway %s:%s -> %s", host, port, exc)

    if demo_mode and manager.get_gateway_status().connected:
        try:
            if not manager.get_status():
                manager.discover()
            manager.start_all()
            LOGGER.info("Demo mode enabled: auto-started streaming for all sensors")
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to auto-start demo streams: %s", exc)

    dash_app = DashApp(
        manager=manager,
        realtime=realtime_store,
        stays=stays,
        app_config_path=args.config,
        stays_config_path=args.stays,
        app_config=app_config,
    )
    LOGGER.info("Starting Dash application at %s:%s", args.host, args.port)
    dash_app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()