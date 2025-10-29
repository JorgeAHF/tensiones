"""
Script para grabar 2 minutos de datos del acelerómetro y luego reproducirlos.

Uso:
    1. Modo GRABACIÓN (con hardware real):
       python record_and_play.py --mode record --duration 120
    
    2. Modo REPRODUCCIÓN (sin hardware, leyendo CSV):
       python record_and_play.py --mode playback --file data/playback/recording_20251029_XXXXXX.csv
"""

import argparse
import logging
import time
from pathlib import Path

import yaml

from app.acquisition.playback_client import PlaybackClient, RecordingSession
from app.acquisition.real_mscl_client import RealMSCLClient
from app.acquisition.stream_manager import RealtimeDataStore, StayDefinition, StreamManager
from app.ui.dash_app import DashApp
from app.utils.logging_setup import configure_logging
from app.utils.validators import Thresholds

LOGGER = logging.getLogger(__name__)


class PlaybackMSCLClient:
    """
    Adaptador que envuelve PlaybackClient para que se comporte como MSCLClient.
    """
    
    def __init__(self, playback: PlaybackClient, sensor_configs: list):
        self.playback = playback
        self._sensor_configs = sensor_configs
        self._callbacks = {}
        
        # Configurar callback del playback
        self.playback.set_data_callback(self._on_playback_data)
    
    def _on_playback_data(self, timestamp: float, x: float, y: float, z: float, sensor_id: str):
        """Callback que recibe datos del playback y los reenvía al stream manager."""
        if sensor_id in self._callbacks:
            # Crear objeto Sample compatible con MSCLClient
            import numpy as np
            from app.acquisition.mscl_client import Sample
            
            # Encontrar configuración del sensor
            sensor_config = next((cfg for cfg in self._sensor_configs if cfg["sensor_id"] == sensor_id), None)
            if not sensor_config:
                return
            
            sample = Sample(
                sensor_id=sensor_id,
                stay_id=sensor_config["stay_id"],
                fs_hz=256.0,  # Frecuencia de muestreo
                timestamp=timestamp,
                acceleration_g=np.array([[x, y, z]])  # Array 2D: (1, 3) - una muestra, 3 ejes
            )
            self._callbacks[sensor_id](sample)
    
    def start_streaming(self, sensor_id: str, callback):
        """Inicia el stream con callback (interfaz compatible con MSCLClient)."""
        self._callbacks[sensor_id] = callback
        LOGGER.info(f"Starting playback for sensor {sensor_id}")
        if not self.playback._is_playing:
            # loop=False para probar sesiones continuas largas sin repetir
            self.playback.start_playback(loop=False, speed_multiplier=1.0)
    
    def stop_streaming(self, sensor_id: str):
        """Detiene el stream."""
        LOGGER.info(f"Stopping playback for sensor {sensor_id}")
        if sensor_id in self._callbacks:
            del self._callbacks[sensor_id]
        if len(self._callbacks) == 0:
            self.playback.stop_playback()
    
    def get_sensor_state(self, sensor_id: str) -> dict:
        """Retorna estado del sensor."""
        return {
            "streaming": self.playback._is_playing,
            "battery": 100.0,
            "rssi": -50.0,
            "lost_beacons": 0
        }
    
    def list_sensors(self) -> list:
        """Lista sensores disponibles."""
        from app.acquisition.mscl_client import SensorInfo
        return [
            SensorInfo(
                sensor_id=cfg["sensor_id"],
                stay_id=cfg["stay_id"],
                sample_rate_hz=256.0,
                axes=["x", "y", "z"],
                battery_percent=100.0
            )
            for cfg in self._sensor_configs
        ]
    
    def list_nodes(self) -> list:
        """Alias de list_sensors para compatibilidad."""
        return self.list_sensors()
    
    def configure_node(self, sensor_id: str, sample_rate_hz: float, axes):
        """No-op para playback."""
        pass
    
    def connect_gateway(self, host: str, port: int):
        """Simula conexión al gateway."""
        from app.acquisition.mscl_client import GatewayStatus
        return GatewayStatus(host=host, port=port, connected=True, message="Playback mode")
    
    def disconnect_gateway(self):
        """Simula desconexión del gateway."""
        from app.acquisition.mscl_client import GatewayStatus
        return GatewayStatus(host="", port=0, connected=False, message="Playback disconnected")
    
    def gateway_status(self):
        """Retorna estado del gateway simulado."""
        from app.acquisition.mscl_client import GatewayStatus
        return GatewayStatus(host="playback", port=0, connected=True, message="Playback mode")
    
    def get_sensor_state(self, sensor_id: str) -> dict:
        """Retorna estado del sensor."""
        return {
            "streaming": self.playback._is_playing,
            "battery": 100.0,
            "rssi": -50.0,
            "lost_beacons": 0
        }


def load_config():
    """Carga configuración desde archivos YAML."""
    app_config_path = Path("app/config/app.yaml")
    stays_config_path = Path("app/config/stays.yaml")
    
    with open(app_config_path) as f:
        app_config = yaml.safe_load(f)
    
    with open(stays_config_path) as f:
        stays_config = yaml.safe_load(f)
    
    # Construir stays
    stays = []
    for entry in stays_config.get("stays", []):
        thresholds_cfg = entry.get("thresholds_kN", {})
        stay = StayDefinition(
            stay_id=entry["stay_id"],
            sensor_id=str(entry["sensor_id"]),
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
    
    return app_config, stays


def record_mode(duration: int):
    """
    Modo GRABACIÓN: Conecta al hardware y graba datos por N segundos.
    """
    import mscl  # Solo necesario en modo recording
    
    LOGGER.info(f"=== RECORDING MODE: {duration} seconds ===")
    
    # Configurar logging
    configure_logging(Path("data/logs"))
    
    # Cargar configuración
    app_config, stays = load_config()
    default_fs = float(app_config.get("default_fs_hz", 256))
    
    # Conectar al hardware real
    LOGGER.info("Connecting to real hardware at 192.168.8.101:5000...")
    connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
    base_station = mscl.BaseStation(connection)
    
    if not base_station.ping():
        LOGGER.error("Failed to connect to BaseStation")
        return
    
    LOGGER.info("Connected to BaseStation successfully")
    
    # Crear cliente real
    sensor_configs = [
        {"sensor_id": stay.sensor_id, "stay_id": stay.stay_id} 
        for stay in stays
    ]
    client = RealMSCLClient(base_station, sensor_configs, default_fs)
    
    # Crear sesión de grabación
    recording = RecordingSession(output_dir="data/playback")
    
    # Configurar callback para capturar datos
    # El callback recibe un objeto Sample con acceleration_g (numpy array de shape [N, 3])
    def capture_callback(sample):
        # acceleration_g es un array de shape (num_samples, 3)
        # Necesitamos guardar cada muestra individualmente
        acc_data = sample.acceleration_g
        if acc_data.ndim == 1:
            # Una sola muestra
            recording.add_sample(
                timestamp=sample.timestamp,
                x=float(acc_data[0]),
                y=float(acc_data[1]),
                z=float(acc_data[2]),
                sensor_id=sample.sensor_id
            )
        else:
            # Múltiples muestras (batch)
            for i in range(len(acc_data)):
                recording.add_sample(
                    timestamp=sample.timestamp + (i / sample.fs_hz),  # timestamp incremental
                    x=float(acc_data[i, 0]),
                    y=float(acc_data[i, 1]),
                    z=float(acc_data[i, 2]),
                    sensor_id=sample.sensor_id
                )
    
    # Iniciar grabación
    recording.start_recording(duration_seconds=duration)
    
    # Iniciar streaming con callback
    for stay in stays:
        client.start_streaming(stay.sensor_id, capture_callback)
    
    LOGGER.info(f"Recording started - waiting {duration} seconds...")
    
    # Esperar duración completa
    time.sleep(duration + 2)  # +2 segundos de margen
    
    # Detener streaming
    for stay in stays:
        client.stop_streaming(stay.sensor_id)
    
    # Guardar datos
    output_file = recording.stop_recording()
    
    if output_file:
        LOGGER.info(f"SUCCESS: Recording complete! Saved to: {output_file}")
        LOGGER.info(f"To play back, run:")
        LOGGER.info(f"   python record_and_play.py --mode playback --file {output_file}")
    else:
        LOGGER.error("ERROR: Recording failed - no data captured")


def playback_mode(csv_file: str):
    """
    Modo REPRODUCCIÓN: Lee CSV pregrabado y simula streaming en tiempo real.
    """
    LOGGER.info(f"=== PLAYBACK MODE: {csv_file} ===")
    
    # Configurar logging
    configure_logging(Path("data/logs"))
    
    # Cargar configuración
    app_config, stays = load_config()
    default_fs = float(app_config.get("default_fs_hz", 256))
    
    # Crear cliente de reproducción
    playback = PlaybackClient(csv_file, sample_rate_hz=default_fs)
    
    sensor_configs = [
        {"sensor_id": stay.sensor_id, "stay_id": stay.stay_id} 
        for stay in stays
    ]
    client = PlaybackMSCLClient(playback, sensor_configs)
    
    # Crear stream manager
    realtime_store = RealtimeDataStore()
    manager = StreamManager(
        client=client,
        stays=stays,
        analysis_cfg=app_config.get("analysis", {}),
        rotation_cfg=app_config.get("storage", {}).get("rotation", {}),
        storage_base=Path("data"),
        realtime_store=realtime_store,
    )
    
    # Iniciar streams
    LOGGER.info("Starting playback streams...")
    manager.start_all()
    
    # Crear aplicación Dash
    dash_app = DashApp(
        manager=manager,
        realtime=realtime_store,
        stays=stays,
        app_config_path=Path("app/config/app.yaml"),
        stays_config_path=Path("app/config/stays.yaml"),
        app_config=app_config,
    )
    
    LOGGER.info("Starting Dash application at http://127.0.0.1:8050")
    LOGGER.info("Open your browser and watch the playback!")
    dash_app.run(host="127.0.0.1", port=8050)


def main():
    parser = argparse.ArgumentParser(description="Record and playback accelerometer data")
    parser.add_argument(
        "--mode",
        choices=["record", "playback"],
        required=True,
        help="Operation mode: record data or playback from CSV"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=120,
        help="Recording duration in seconds (default: 120)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="CSV file to playback (required for playback mode)"
    )
    
    args = parser.parse_args()
    
    if args.mode == "record":
        record_mode(args.duration)
    elif args.mode == "playback":
        if not args.file:
            parser.error("--file is required for playback mode")
        playback_mode(args.file)


if __name__ == "__main__":
    main()
