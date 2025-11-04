"""Application entry point."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.acquisition.mscl_client import (
    DemoMSCLClient,
    HttpMSCLClient,
    MSCLClient,
    create_demo_client,
)
from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.acquisition.streaming_coordinator import StreamingCoordinator
from app.ui.dash_app import DashApp
from app.utils.logging_setup import configure_logging
from app.utils.validators import Thresholds
from app.sinks.raw_writer import RawStreamingWriter

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
            sensor_id=str(entry["sensor_id"]),  # Convert to string for consistency
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


def create_client(
    app_config: Dict,
    stays: List[StayDefinition],
    streaming_coordinator: StreamingCoordinator,
    raw_writer: Optional[RawStreamingWriter],
) -> MSCLClient:
    default_fs = float(app_config.get("default_fs_hz", 256))
    demo_mode = app_config.get("modes", {}).get("demo", True)

    if demo_mode:
        LOGGER.info("Running in DEMO mode")
        stays_config = [
            {"sensor_id": stay.sensor_id, "stay_id": stay.stay_id} for stay in stays
        ]
        # NOTA: DemoMSCLClient aún no tiene soporte para StreamingCoordinator
        # Por ahora retornamos demo sin coordinator (se eliminará después)
        return create_demo_client(stays_config, default_fs)
    else:
        LOGGER.info("Connecting to real MSCL Gateway at 192.168.8.101:5000")
        try:
            import mscl  # Importar solo si se usa el cliente real
            from app.acquisition.real_mscl_client import RealMSCLClient
            
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
            
            # Crear y retornar cliente real CON streaming coordinator
            return RealMSCLClient(
                base_station,
                sensor_configs,
                default_fs,
                streaming_coordinator=streaming_coordinator,
                raw_writer=raw_writer,
            )
            
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

    streaming_cfg = app_config.get("streaming", {})
    buffer_duration = int(streaming_cfg.get("buffer_seconds", 300))
    buffer_fs = int(streaming_cfg.get("sample_rate_hz", app_config.get("default_fs_hz", 256)))

    streaming_coordinator = StreamingCoordinator(
        buffer_duration_sec=buffer_duration,
        sample_rate_hz=buffer_fs,
    )
    LOGGER.info("[OK] StreamingCoordinator creado")

    raw_writer: Optional[RawStreamingWriter] = None
    raw_stream_cfg = app_config.get("storage", {}).get("raw_stream", {})
    if raw_stream_cfg.get("enabled", True):
        try:
            raw_dir = raw_stream_cfg.get("base_dir")
            base_dir = Path(raw_dir).resolve() if raw_dir else (storage_base / "raw")
            raw_writer = RawStreamingWriter(base_dir)
            LOGGER.info("[OK] Raw streaming writer inicializado en %s", base_dir)
        except Exception as exc:
            LOGGER.warning("[RAW] No se pudo inicializar RawStreamingWriter: %s", exc)

    # Intentar inicializar InfluxDB writer (opcional)
    influxdb_writer = None
    influxdb_config = app_config.get("influxdb", {})
    if influxdb_config.get("enabled", False):
        try:
            from app.storage.influxdb_writer import InfluxDBWriter
            influxdb_writer = InfluxDBWriter(
                url=influxdb_config.get("url", "http://localhost:8086"),
                token=influxdb_config.get("token"),
                org=influxdb_config.get("org", "imt"),
                bucket=influxdb_config.get("bucket", "python"),
            )
            LOGGER.info("[OK] InfluxDB writer inicializado")
        except Exception as e:
            LOGGER.warning(f"[INFLUXDB] No se pudo inicializar InfluxDB: {e}")
            influxdb_writer = None

    client = create_client(app_config, stays, streaming_coordinator, raw_writer=raw_writer)

    ui_cfg = app_config.get("ui", {})
    display_buffer_seconds = int(
        ui_cfg.get("display_buffer_seconds", buffer_duration)
    )
    realtime_store = RealtimeDataStore(
        buffer_seconds=display_buffer_seconds,
        sample_rate_hz=buffer_fs,
    )
    manager = StreamManager(
        client=client,
        stays=stays,
        analysis_cfg=app_config.get("analysis", {}),
        rotation_cfg=app_config.get("storage", {}).get("rotation", {}),
        storage_base=storage_base,
        realtime_store=realtime_store,
        streaming_coordinator=streaming_coordinator,
        influxdb_writer=influxdb_writer,
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

    if manager.get_gateway_status().connected:
        try:
            if not manager.get_status():
                manager.discover()
            # CRÍTICO: NO iniciar automáticamente - esperar configuración manual desde UI
            # El usuario debe configurar e iniciar manualmente desde la pestaña "Control de Red"
            # manager.start_all()  # ← DESHABILITADO para control manual tipo SensorConnect
            
            # Iniciar thread de procesamiento FFT (se activa cuando hay datos)
            manager.start_fft_processing()
            
            mode_label = "Demo" if demo_mode else "Real hardware"
            LOGGER.info("%s mode enabled - System ready | Waiting for manual sensor configuration from UI", mode_label)
            LOGGER.info("Go to 'Control de Red' tab to configure and start sensor sampling")
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to initialize manager: %s", exc)

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