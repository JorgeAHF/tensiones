"""Manage sensor streams, analysis pipeline and storage."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np

from app.acquisition.mscl_client import GatewayStatus, MSCLClient, Sample, SensorInfo
from app.acquisition.streaming_coordinator import StreamingCoordinator
from app.analysis.filters import BandpassConfig, preprocess
from app.analysis.spectral import FrequencyEstimator, PeakDetectionResult, WelchConfig
from app.analysis.tension import TensionResult, estimate_tension
from app.sinks.csv_writer import RotatingCsvWriter
from app.sinks.parquet_writer import RotatingParquetWriter
from app.sinks.rotation import RotationPolicy
from app.sinks.chunk_writer import RealtimeChunkWriter
from app.utils.timeutils import DEFAULT_TZ, format_timestamp, now_local_utc
from app.utils.validators import QualityAssessment, Thresholds

logger = logging.getLogger(__name__)


def create_session_logger(sensor_id: str, base_dir: Path) -> logging.Logger:
    """
    Crea un logger dedicado para una sesión de monitoreo específica.
    Escribe a un archivo separado: data/logs/sessions/session_{sensor_id}_{timestamp}.log
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Crear directorio de sesiones si no existe
    sessions_dir = base_dir / "logs" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Generar nombre de archivo con timestamp
    cst_tz = ZoneInfo("America/Mexico_City")
    timestamp = datetime.now(cst_tz).strftime("%Y%m%d_%H%M%S")
    log_filename = f"session_{sensor_id}_{timestamp}.log"
    log_path = sessions_dir / log_filename

    # Crear logger único para esta sesión
    session_logger = logging.getLogger(f"session.{sensor_id}.{timestamp}")
    session_logger.setLevel(logging.DEBUG)
    session_logger.propagate = False  # No propagar al logger principal

    # Remover handlers existentes (por si se llama múltiples veces)
    session_logger.handlers.clear()

    # Crear file handler
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Formato simple y claro
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
    file_handler.setFormatter(formatter)

    session_logger.addHandler(file_handler)

    # Log inicial
    session_logger.info("="*80)
    session_logger.info(f"SESIÓN DE MONITOREO INICIADA - Sensor {sensor_id}")
    session_logger.info(f"Log file: {log_path}")
    session_logger.info("="*80)
    session_logger.info("")

    return session_logger


def is_valid_acceleration_sample(accel_values: np.ndarray, expected_range: tuple = (-10.0, 10.0)) -> bool:
    """
    Valida si una muestra de aceleración es confiable.

    Args:
        accel_values: Array [x, y, z] con valores de aceleración
        expected_range: Rango válido para valores en g's
            - Default (-10.0, 10.0): Para datos calibrados en g's
            - Usar (-600000, 600000): Para datos raw sin calibrar

    Returns:
        True si la muestra es válida, False si es sospechosa

    Criterios de validación:
    - No debe tener todos los ejes en cero (muestra corrupta)
    - Debe estar dentro de rango físicamente posible

    Nota: Para acelerómetros estáticos o vibraciones, valores normales
    están en el rango [-3, 3] g. Valores > 10g indican datos corruptos.
    """
    if len(accel_values) < 3:
        return False
    
    x, y, z = accel_values[0], accel_values[1], accel_values[2]
    
    # 1. Verificar que no todos sean cero (muestra claramente corrupta)
    if x == 0.0 and y == 0.0 and z == 0.0:
        return False
    
    # 2. Verificar rangos físicos razonables
    # Para G-Link-200: valores raw típicos están entre -500000 y 500000
    if not (expected_range[0] <= x <= expected_range[1] and
            expected_range[0] <= y <= expected_range[1] and
            expected_range[0] <= z <= expected_range[1]):
        return False
    
    return True


@dataclass
class StayDefinition:
    stay_id: str
    sensor_id: str
    k_coefficient: float
    thresholds: Thresholds
    length_m: Optional[float] = None
    mass_density: Optional[float] = None


@dataclass
class SensorState:
    info: SensorInfo
    streaming: bool = False
    sleeping: bool = False  # True when node is in sleep mode
    last_sample_timestamp: Optional[float] = None
    estimated_fs: Optional[float] = None
    battery_percent: Optional[float] = None
    samples_received_total: int = 0  # Total samples received from hardware
    samples_written_total: int = 0   # Total samples written to CSV
    session_logger: Optional[logging.Logger] = None  # Logger dedicado para esta sesión


@dataclass
class AccelerationRecord:
    timestamps: np.ndarray
    samples: np.ndarray


@dataclass
class AnalysisState:
    last_result: Optional[PeakDetectionResult] = None
    last_tension: Optional[TensionResult] = None
    history: Deque[Tuple[datetime, TensionResult, QualityAssessment]] = field(
        default_factory=lambda: deque(maxlen=500)
    )
    recent_accel: Deque[AccelerationRecord] = field(
        default_factory=lambda: deque(maxlen=10)
    )
    psd_cache: Optional[Tuple[np.ndarray, np.ndarray]] = None


class RealtimeDataStore:
    """Thread-safe storage for UI consumption."""

    def __init__(self, buffer_seconds: int = 300, sample_rate_hz: int = 256) -> None:
        self._lock = threading.RLock()
        self._analysis: Dict[str, AnalysisState] = {}
        # Buffer continuo para visualización suave configurable
        self._display_buffers: Dict[str, Tuple[deque, deque]] = {}  # sensor_id -> (timestamps, samples)
        # Índice del último dato leído por la UI (para streaming incremental)
        self._last_read_index: Dict[str, int] = {}
        self._buffer_seconds = max(1, buffer_seconds)
        self._sample_rate_hz = max(1, sample_rate_hz)

    def ensure_sensor(self, sensor_id: str) -> AnalysisState:
        with self._lock:
            state = self._analysis.get(sensor_id)
            if state is None:
                state = AnalysisState()
                self._analysis[sensor_id] = state
            # Inicializar buffer de visualización si no existe
            if sensor_id not in self._display_buffers:
                maxlen = self._buffer_seconds * self._sample_rate_hz
                self._display_buffers[sensor_id] = (deque(maxlen=maxlen), deque(maxlen=maxlen))
                self._last_read_index[sensor_id] = 0
            return state

    def update_analysis(
        self,
        sensor_id: str,
        result: PeakDetectionResult,
        tension: TensionResult,
        qa: QualityAssessment,
        timestamp: datetime,
        psd: Tuple[np.ndarray, np.ndarray],
        accel: AccelerationRecord,
    ) -> None:
        with self._lock:
            state = self.ensure_sensor(sensor_id)
            state.last_result = result
            state.last_tension = tension
            state.history.append((timestamp, tension, qa))
            state.recent_accel.append(accel)
            state.psd_cache = psd
            
            # Actualizar buffer continuo de visualización
            timestamps_buf, samples_buf = self._display_buffers[sensor_id]
            for i, ts in enumerate(accel.timestamps):
                timestamps_buf.append(ts)
                samples_buf.append(accel.samples[i])  # Cada muestra es un array [x, y, z]

    def snapshot(self) -> Dict[str, AnalysisState]:
        with self._lock:
            return {k: v for k, v in self._analysis.items()}
    
    def get_display_buffer(self, sensor_id: str, window_seconds: float = 10.0) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Obtiene los últimos N segundos del buffer continuo para visualización suave.
        
        Args:
            sensor_id: ID del sensor
            window_seconds: Ventana de tiempo a mostrar (en segundos)
            
        Returns:
            Tupla (timestamps, samples) o None si no hay datos
            - timestamps: array 1D con timestamps
            - samples: array 2D con shape (n_samples, 3) para [x, y, z]
        """
        with self._lock:
            if sensor_id not in self._display_buffers:
                return None
            
            timestamps_buf, samples_buf = self._display_buffers[sensor_id]
            
            if len(timestamps_buf) == 0:
                return None
            
            # Convertir deque a arrays
            all_timestamps = np.array(list(timestamps_buf))
            all_samples = np.array(list(samples_buf))
            
            # Filtrar solo los últimos N segundos
            latest_time = all_timestamps[-1]
            cutoff_time = latest_time - window_seconds
            
            mask = all_timestamps >= cutoff_time
            filtered_timestamps = all_timestamps[mask]
            filtered_samples = all_samples[mask]
            
            return filtered_timestamps, filtered_samples
    
    def get_new_data_since_last_read(self, sensor_id: str) -> Optional[Tuple[np.ndarray, np.ndarray, int]]:
        """Obtiene solo los datos nuevos desde la última lectura (para streaming incremental).
        
        Args:
            sensor_id: ID del sensor
            
        Returns:
            Tupla (timestamps, samples, total_count) o None si no hay datos nuevos
            - timestamps: array 1D con timestamps de datos nuevos
            - samples: array 2D con shape (n_samples, 3) para [x, y, z]
            - total_count: cantidad total de datos en el buffer (para detectar reset)
        """
        with self._lock:
            if sensor_id not in self._display_buffers:
                return None
            
            timestamps_buf, samples_buf = self._display_buffers[sensor_id]
            total_count = len(timestamps_buf)
            
            if total_count == 0:
                return None
            
            last_index = self._last_read_index.get(sensor_id, 0)
            
            # Si el buffer se limpió o es más pequeño que el último índice, reiniciar
            if last_index >= total_count:
                last_index = max(0, total_count - 256)  # Tomar los últimos 256 puntos (1 segundo @ 256Hz)
            
            # Obtener solo los datos nuevos
            new_timestamps = list(timestamps_buf)[last_index:]
            new_samples = list(samples_buf)[last_index:]
            
            if len(new_timestamps) == 0:
                return None
            
            # Actualizar el índice de última lectura
            self._last_read_index[sensor_id] = total_count
            
            return np.array(new_timestamps), np.array(new_samples), total_count
    
    def reconfigure_sensor(self, sensor_id: str, sample_rate_hz: int) -> None:
        """Reconfigura un sensor con nueva frecuencia de muestreo.
        
        Args:
            sensor_id: ID del sensor a reconfigurar
            sample_rate_hz: Nueva frecuencia de muestreo en Hz
        """
        with self._lock:
            # Recrear buffer de visualización con nueva frecuencia
            maxlen = self._buffer_seconds * sample_rate_hz
            self._display_buffers[sensor_id] = (deque(maxlen=maxlen), deque(maxlen=maxlen))
            self._last_read_index[sensor_id] = 0
            logger.info(f"[REALTIME-STORE] Sensor {sensor_id} reconfigurado: {sample_rate_hz}Hz (buffer: {maxlen} samples)")


class SensorBuffer:
    """Rolling buffer of acceleration samples for analysis."""

    def __init__(self, window_seconds: float, fs: float) -> None:
        self.window_seconds = window_seconds
        self.fs = fs
        self.max_samples = int(window_seconds * fs)
        self.samples = deque()  # type: Deque[np.ndarray]
        self.timestamps = deque()  # type: Deque[float]

    def update_fs(self, fs: float) -> None:
        self.fs = fs
        self.max_samples = int(self.window_seconds * fs)

    def extend(self, batch: np.ndarray, start_time: float, dt: float) -> None:
        for idx, sample in enumerate(batch):
            self.samples.append(sample)
            self.timestamps.append(start_time + idx * dt)
        while len(self.samples) > self.max_samples:
            self.samples.popleft()
            self.timestamps.popleft()

    def get_array(self) -> Tuple[np.ndarray, np.ndarray]:
        samples = np.array(self.samples)
        timestamps = np.array(self.timestamps)
        return timestamps, samples


class StreamManager:
    def __init__(
        self,
        client: MSCLClient,
        stays: List[StayDefinition],
        analysis_cfg: Dict,
        rotation_cfg: Dict,
        storage_base: Path,
        realtime_store: RealtimeDataStore,
        streaming_coordinator: Optional[StreamingCoordinator] = None,
    ) -> None:
        self.client = client
        self.analysis_cfg = analysis_cfg
        self.rotation_cfg = rotation_cfg
        self.storage_base = storage_base
        self.realtime_store = realtime_store
        self.streaming_coordinator = streaming_coordinator
        self.stays = {stay.sensor_id: stay for stay in stays}
        self.sensors: Dict[str, SensorState] = {}
        self.buffers: Dict[str, SensorBuffer] = {}
        self.estimators: Dict[str, FrequencyEstimator] = {}
        self.mode: Dict[str, str] = {}
        self.guided_f1: Dict[str, Optional[float]] = {}
        self.guided_tol: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Thread dedicado para procesamiento FFT en background
        self._processing_thread: Optional[threading.Thread] = None
        self._processing_stop_event = threading.Event()
        self._processing_interval_sec = 1.0  # Calcular tensión cada 1 segundo

        if self.streaming_coordinator:
            logger.info("[OK] StreamManager integrado con StreamingCoordinator")
        
        try:
            self._gateway_status = self.client.gateway_status()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to obtain initial gateway status: %s", exc)
            self._gateway_status = GatewayStatus(host=None, port=None, connected=False, message=str(exc))
        else:
            if self._gateway_status.connected:
                try:
                    self.discover()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Initial discovery failed: %s", exc)

        # Crear diccionarios de writers por sensor (para archivos separados)
        # Determinar formato de almacenamiento desde config (default: CSV)
        self._storage_format = self.rotation_cfg.get("format", "csv").lower()
        logger.info(f"[STORAGE] Data format: {self._storage_format.upper()}")

        # Writers por formato
        self._accel_writers: Dict[str, RotatingCsvWriter] = {}
        self._tension_writers: Dict[str, RotatingCsvWriter] = {}
        self._accel_parquet_writers: Dict[str, RotatingParquetWriter] = {}
        self._tension_parquet_writers: Dict[str, RotatingParquetWriter] = {}

        # Chunk writers para generación en tiempo real
        self._chunk_writers: Dict[str, RealtimeChunkWriter] = {}
        self._chunk_duration_minutes = 2.0  # Default: chunks de 2 minutos
        logger.info(f"[CHUNK WRITER] Chunks en tiempo real habilitados (duración: {self._chunk_duration_minutes} min)")

        # Headers para archivos CSV
        self._accel_headers = [
            "timestamp_local",
            "timestamp_utc",
            "stay_id",
            "sensor_id",
            "fs_hz",
            "ax_g",
            "ay_g",
            "az_g",
            "is_valid",
        ]
        self._tension_headers = [
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

    def _create_csv_writer(self, subdir: str, prefix: str, headers: List[str]) -> RotatingCsvWriter:
        """Create a RotatingCsvWriter with custom prefix for file naming."""
        policy = RotationPolicy(
            mode=self.rotation_cfg.get("mode", "time"),
            minutes=self.rotation_cfg.get("minutes"),
            max_mb=self.rotation_cfg.get("max_mb"),
        )
        path = self.storage_base / subdir
        return RotatingCsvWriter(path, prefix, headers, policy)

    def _create_parquet_writer(self, subdir: str, prefix: str, headers: List[str]) -> RotatingParquetWriter:
        """Create a RotatingParquetWriter with custom prefix for file naming."""
        policy = RotationPolicy(
            mode=self.rotation_cfg.get("mode", "time"),
            minutes=self.rotation_cfg.get("minutes"),
            max_mb=self.rotation_cfg.get("max_mb"),
        )
        path = self.storage_base / subdir
        compression = self.rotation_cfg.get("compression", "snappy")
        return RotatingParquetWriter(path, prefix, headers, policy, compression=compression)

    def _get_or_create_accel_writer(self, sensor_id: str) -> Optional[Union[RotatingCsvWriter, RotatingParquetWriter]]:
        """Get or create acceleration writer (CSV or Parquet) for a specific sensor.

        Returns None if sensor is not streaming (prevents creating files after stop).
        """
        # Verificar que el sensor esté en streaming
        sensor_state = self.sensors.get(sensor_id)
        if not sensor_state or not sensor_state.streaming:
            # No crear nuevo writer si el sensor no está en streaming
            # Esto previene crear archivos vacíos después de stop()
            return None

        # Crear writer según formato configurado
        if self._storage_format == "parquet":
            if sensor_id not in self._accel_parquet_writers:
                subdir = f"acceleration/sensor_{sensor_id}"
                prefix = f"sensor_{sensor_id}_acceleration"
                self._accel_parquet_writers[sensor_id] = self._create_parquet_writer(
                    subdir,
                    prefix,
                    self._accel_headers
                )
                logger.info(f"Created acceleration Parquet writer for sensor {sensor_id} in {subdir}/")
            return self._accel_parquet_writers[sensor_id]
        else:  # Default to CSV
            if sensor_id not in self._accel_writers:
                # Crear carpeta por sensor: acceleration/sensor_XXXXX/
                subdir = f"acceleration/sensor_{sensor_id}"
                prefix = f"sensor_{sensor_id}_acceleration"
                self._accel_writers[sensor_id] = self._create_csv_writer(
                    subdir,
                    prefix,
                    self._accel_headers
                )
                logger.info(f"Created acceleration CSV writer for sensor {sensor_id} in {subdir}/")
            return self._accel_writers[sensor_id]

    def _get_or_create_tension_writer(self, sensor_id: str) -> Optional[Union[RotatingCsvWriter, RotatingParquetWriter]]:
        """Get or create tension writer (CSV or Parquet) for a specific sensor.

        Returns None if sensor is not streaming (prevents creating files after stop).
        """
        # Verificar que el sensor esté en streaming
        sensor_state = self.sensors.get(sensor_id)
        if not sensor_state or not sensor_state.streaming:
            # No crear nuevo writer si el sensor no está en streaming
            # Esto previene crear archivos vacíos después de stop()
            return None

        # Crear writer según formato configurado
        if self._storage_format == "parquet":
            if sensor_id not in self._tension_parquet_writers:
                subdir = f"tension/sensor_{sensor_id}"
                prefix = f"sensor_{sensor_id}_tension"
                self._tension_parquet_writers[sensor_id] = self._create_parquet_writer(
                    subdir,
                    prefix,
                    self._tension_headers
                )
                logger.info(f"Created tension Parquet writer for sensor {sensor_id} in {subdir}/")
            return self._tension_parquet_writers[sensor_id]
        else:  # Default to CSV
            if sensor_id not in self._tension_writers:
                # Crear carpeta por sensor: tension/sensor_XXXXX/
                subdir = f"tension/sensor_{sensor_id}"
                prefix = f"sensor_{sensor_id}_tension"
                self._tension_writers[sensor_id] = self._create_csv_writer(
                    subdir,
                    prefix,
                    self._tension_headers
                )
                logger.info(f"Created tension CSV writer for sensor {sensor_id} in {subdir}/")
            return self._tension_writers[sensor_id]

    def _make_bandpass(self) -> BandpassConfig:
        bandpass_cfg = self.analysis_cfg.get("bandpass", [0.2, 10.0])
        if isinstance(bandpass_cfg, dict):
            return BandpassConfig(
                low_hz=bandpass_cfg.get("low", 0.2),
                high_hz=bandpass_cfg.get("high", 10.0),
                order=bandpass_cfg.get("order", 4),
            )
        values = list(bandpass_cfg)
        order = 4
        if len(values) == 3:
            order = values[2]
        return BandpassConfig(values[0], values[1], order)

    def _create_estimator(self, sample_rate: float) -> FrequencyEstimator:
        nperseg = int(sample_rate * self.analysis_cfg.get("nperseg_sec", 4))
        noverlap = int(nperseg * self.analysis_cfg.get("overlap", 0.5))
        return FrequencyEstimator(
            fs=sample_rate,
            welch_config=WelchConfig(
                window=self.analysis_cfg.get("welch_window", "hann"),
                nperseg=nperseg,
                noverlap=noverlap,
            ),
            band=(
                self.analysis_cfg.get("fmin_hz", 0.2),
                self.analysis_cfg.get("fmax_hz", 10.0),
            ),
            snr_min_db=self.analysis_cfg.get("snr_min_db", 10.0),
            max_rel_change=self.analysis_cfg.get("max_rel_f1_change", 0.1),
            min_prominence=self.analysis_cfg.get("min_prominence", 0.0),
        )

    def discover(self) -> List[SensorState]:
        try:
            self._gateway_status = self.client.gateway_status()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to refresh gateway status before discovery: %s", exc)
            self._gateway_status = GatewayStatus(host=None, port=None, connected=False, message=str(exc))

        if not self._gateway_status.connected:
            logger.warning("Gateway not connected; discovery skipped")
            return []
        nodes = self.client.list_nodes()
        states = []
        for info in nodes:
            state = self.sensors.get(info.sensor_id)
            if state is None:
                state = SensorState(info=info)
                self.sensors[info.sensor_id] = state
            states.append(state)
        return states

    def configure(
        self,
        sensor_id: str,
        sample_rate: float,
        axes: Iterable[str],
        data_format: str = "float",
        sampling_mode: str = "continuous",
        duration_seconds: Optional[int] = None,
    ) -> None:
        """Configure sensor sampling parameters.

        Args:
            sensor_id: ID del sensor
            sample_rate: Frecuencia de muestreo en Hz
            axes: Lista de ejes activos
            data_format: Formato de datos ('float' o 'uint16')
            sampling_mode: Modo de sampling ('continuous', 'duration', 'burst', 'event')
            duration_seconds: Duración en segundos (solo para modo 'duration')
        """
        if not self._gateway_status.connected:
            logger.warning("Cannot configure sensor %s without gateway connection", sensor_id)
            return
        self.client.configure_node(
            sensor_id,
            sample_rate,
            axes,
            data_format,
            sampling_mode=sampling_mode,
            duration_seconds=duration_seconds,
        )
        stay = self.stays.get(sensor_id)
        if stay is None:
            return
        state = self.sensors.get(sensor_id)
        if state is not None:
            state.info.sample_rate_hz = sample_rate
            state.info.axes = list(axes)
        buffer = self.buffers.get(sensor_id)
        if buffer is None:
            buffer = SensorBuffer(self.analysis_cfg["window_sec"], sample_rate)
            self.buffers[sensor_id] = buffer
        else:
            buffer.update_fs(sample_rate)
        self.estimators[sensor_id] = self._create_estimator(sample_rate)
        self.mode.setdefault(sensor_id, "AUTO")
        self.guided_f1.setdefault(sensor_id, None)
        self.guided_tol.setdefault(sensor_id, 0.1)

        # Reconfigurar RealtimeDataStore con nueva frecuencia
        if self.realtime_store:
            self.realtime_store.reconfigure_sensor(sensor_id, int(sample_rate))

    def start(self, sensor_id: str) -> None:
        try:
            self._gateway_status = self.client.gateway_status()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to refresh gateway status before starting %s: %s", sensor_id, exc)
            self._gateway_status = GatewayStatus(host=None, port=None, connected=False, message=str(exc))

        if not self._gateway_status.connected:
            logger.warning("Cannot start sensor %s without gateway connection", sensor_id)
            return
        stay = self.stays.get(sensor_id)
        if stay is None:
            logger.warning("Cannot start unknown sensor %s", sensor_id)
            return
        state = self.sensors.get(sensor_id)
        if state is None:
            logger.debug(
                "Sensor %s missing from cache, triggering discovery before start", sensor_id
            )
            try:
                self.discover()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Discovery failed when starting %s: %s", sensor_id, exc)
            state = self.sensors.get(sensor_id)
            if state is None:
                logger.warning("Sensor %s not discovered", sensor_id)
                return
        buffer = self.buffers.get(sensor_id)
        if buffer is None:
            self.configure(sensor_id, state.info.sample_rate_hz, state.info.axes)
            buffer = self.buffers[sensor_id]

        def callback(sample: Sample) -> None:
            self._handle_sample(sensor_id, sample)

        try:
            import traceback
            # Resetear contadores de samples al iniciar nuevo stream
            state.samples_received_total = 0
            state.samples_written_total = 0

            # Crear logger dedicado para esta sesión
            state.session_logger = create_session_logger(sensor_id, self.storage_base)
            state.session_logger.info(f"Iniciando streaming para sensor {sensor_id}")
            state.session_logger.info(f"Frecuencia configurada: {state.info.sample_rate_hz} Hz")
            state.session_logger.info(f"Ejes activos: {state.info.axes}")
            state.session_logger.info("")

            # Crear chunk writer para escritura en paralelo
            from datetime import datetime
            # Convertir sample_rate a float (puede venir como string)
            fs_hz = float(state.info.sample_rate_hz)
            chunk_writer = RealtimeChunkWriter(
                base_dir=self.storage_base / "acceleration",
                sensor_id=sensor_id,
                chunk_duration_minutes=self._chunk_duration_minutes,
                sample_rate_hz=fs_hz
            )
            chunk_writer.start_session(datetime.now())
            self._chunk_writers[sensor_id] = chunk_writer
            state.session_logger.info(f"[CHUNK WRITER] ✅ Inicializado para escritura en paralelo (chunks cada {self._chunk_duration_minutes} min, {int(fs_hz * 60 * self._chunk_duration_minutes):,} samples/chunk)")

            logger.info(f"[STREAM_MANAGER] Calling start_streaming for {sensor_id}...")
            self.client.start_streaming(sensor_id, callback)
            state.streaming = True
            logger.info(f"[STATE CHANGE] 🟢 Sensor {sensor_id} streaming state: False → True (counters reset)")
            state.session_logger.info(f"[STATE CHANGE] 🟢 Streaming activado (streaming=True)")
            logger.info(f"[STREAM_MANAGER] start_streaming completed for {sensor_id}")
        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(
                f"[STREAM_MANAGER] FATAL ERROR starting streaming for {sensor_id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error message: {str(e)}\n"
                f"Full traceback:\n{error_detail}"
            )
            print(f"\n{'='*80}")
            print(f"[STREAM_MANAGER] FATAL ERROR starting streaming for {sensor_id}")
            print(f"{'='*80}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"\nFull traceback:")
            print(error_detail)
            print(f"{'='*80}\n")
            raise

    def stop(self, sensor_id: str) -> None:
        self.client.stop_streaming(sensor_id)
        state = self.sensors.get(sensor_id)
        if state:
            logger.info(f"[STATE CHANGE] 🔴 Sensor {sensor_id} streaming state: True → False")

            # Loggear estadísticas finales en session_logger si existe
            if state.session_logger:
                samples_lost = state.samples_received_total - state.samples_written_total
                loss_percent = (samples_lost / state.samples_received_total * 100) if state.samples_received_total > 0 else 0

                state.session_logger.info("")
                state.session_logger.info("="*80)
                state.session_logger.info("SESIÓN DE MONITOREO FINALIZADA")
                state.session_logger.info("="*80)
                state.session_logger.info(f"[STATE CHANGE] 🔴 Streaming desactivado (streaming=False)")
                state.session_logger.info(f"Total samples recibidos:  {state.samples_received_total:,}")
                state.session_logger.info(f"Total samples escritos:   {state.samples_written_total:,}")
                state.session_logger.info(f"Samples perdidos:         {samples_lost:,} ({loss_percent:.2f}%)")
                state.session_logger.info("="*80)

                # Cerrar session_logger
                for handler in state.session_logger.handlers[:]:
                    handler.close()
                    state.session_logger.removeHandler(handler)
                state.session_logger = None

            # Finalizar chunk writer si existe
            chunk_writer = self._chunk_writers.pop(sensor_id, None)
            if chunk_writer:
                chunk_writer.finalize_session()
                logger.info(f"[CHUNK WRITER] Sesión finalizada para {sensor_id}")

            state.streaming = False

        # Limpiar writers del sensor para forzar creación de nuevos archivos en próximo start
        self._accel_writers.pop(sensor_id, None)
        self._tension_writers.pop(sensor_id, None)
        logger.info(f"[CSV CLEANUP] CSV writers cleared for sensor {sensor_id} - new files will be created on next start")

    def start_all(self) -> None:
        for sensor_id in self.stays:
            self.start(sensor_id)

    def stop_all(self) -> None:
        for sensor_id in list(self.stays):
            self.stop(sensor_id)
    
    def start_fft_processing(self) -> None:
        """Inicia thread dedicado para procesamiento FFT en background."""
        if self._processing_thread is not None and self._processing_thread.is_alive():
            logger.warning("Thread de procesamiento FFT ya está corriendo")
            return
        
        if not self.streaming_coordinator:
            logger.warning("No se puede iniciar procesamiento FFT sin StreamingCoordinator")
            return
        
        self._processing_stop_event.clear()
        self._processing_thread = threading.Thread(
            target=self._fft_processing_worker,
            daemon=True,
            name="FFT-Processor"
        )
        self._processing_thread.start()
        logger.info(f"[FFT] Thread de procesamiento FFT iniciado (intervalo={self._processing_interval_sec}s)")
    
    def stop_fft_processing(self) -> None:
        """Detiene thread de procesamiento FFT."""
        if self._processing_thread is None:
            return
        
        logger.info("Deteniendo thread de procesamiento FFT...")
        self._processing_stop_event.set()
        self._processing_thread.join(timeout=3.0)
        self._processing_thread = None
        logger.info("[FFT] Thread de procesamiento FFT detenido")
    
    def _fft_processing_worker(self) -> None:
        """Worker thread que procesa FFT cada intervalo configurado."""
        logger.info("Worker FFT iniciado - procesando datos del StreamingCoordinator")
        
        import time
        
        while not self._processing_stop_event.is_set():
            try:
                # Obtener lista de sensores activos
                active_sensors = self.streaming_coordinator.get_all_sensor_ids()
                
                for sensor_id in active_sensors:
                    # Verificar que el sensor esté configurado
                    if sensor_id not in self.stays:
                        continue
                    
                    if sensor_id not in self.buffers:
                        continue
                    
                    # Procesar datos de este sensor
                    self._process_sensor_fft(sensor_id)
                
                # Esperar antes del siguiente ciclo
                self._processing_stop_event.wait(self._processing_interval_sec)
                
            except Exception as e:
                logger.error(f"Error en worker FFT: {e}", exc_info=True)
                time.sleep(1.0)  # Esperar antes de reintentar
        
        logger.info("Worker FFT finalizado")
    
    def _process_sensor_fft(self, sensor_id: str) -> None:
        """Procesa FFT para un sensor específico leyendo del StreamingCoordinator."""
        try:
            # Obtener ventana de datos del coordinator
            window_sec = self.analysis_cfg.get("window_sec", 30)
            n_samples = int(window_sec * 256)  # Asumir 256 Hz por defecto
            
            samples = self.streaming_coordinator.get_latest_data(sensor_id, n_samples)
            
            if len(samples) < 256:  # Mínimo 1 segundo de datos
                return
            
            # Convertir a formato que espera el análisis
            timestamps = np.array([s.timestamp for s in samples])
            accel_data = np.array([[s.x, s.y, s.z] for s in samples])
            
            # Calcular magnitud
            magnitude = np.linalg.norm(accel_data, axis=1)
            
            # Obtener configuración del sensor
            stay = self.stays[sensor_id]
            estimator = self.estimators[sensor_id]
            
            # Preprocesar (filtro pasa-banda)
            bp = self._make_bandpass()
            try:
                processed = preprocess(magnitude, 256.0, bp)  # TODO: obtener fs real
            except ValueError:
                processed = magnitude
            
            # Calcular PSD
            freqs, psd = estimator.power_spectral_density(processed)
            
            # Estimar frecuencia fundamental
            result = estimator.estimate(
                processed,
                mode=self.mode.get(sensor_id, "AUTO"),
                guided_f1=self.guided_f1.get(sensor_id),
                tolerance=self.guided_tol.get(sensor_id, 0.1),
            )
            
            # Calcular tensión
            tension = estimate_tension(
                result.f1_hz,
                mode="physical"
                if (stay.length_m is not None and stay.mass_density is not None)
                else "K",
                k_coefficient=stay.k_coefficient,
                length_m=stay.length_m,
                mass_density=stay.mass_density,
            )
            
            # Quality assessment - already handled by spectral estimator
            qa = result.quality
            
            # Almacenar resultados en RealtimeDataStore
            now_utc, now_local = now_local_utc()
            accel_record = AccelerationRecord(timestamps=timestamps, samples=accel_data)
            
            self.realtime_store.update_analysis(
                sensor_id=sensor_id,
                result=result,
                tension=tension,
                qa=qa,
                timestamp=now_local,
                psd=(freqs, psd),
                accel=accel_record,
            )
            
            # Escribir a CSV (archivo separado por sensor)
            tension_writer = self._get_or_create_tension_writer(sensor_id)
            if tension_writer is not None:
                tension_writer.writerow([
                    format_timestamp(now_local),
                    format_timestamp(now_utc),
                    stay.stay_id,
                    sensor_id,
                    result.f1_hz,
                    tension.tension_newton,
                    tension.tension_kN,
                    result.snr_db,
                    result.peak_prominence,
                    len(samples),
                    256.0,  # TODO: obtener fs real
                    self.mode.get(sensor_id, "AUTO"),
                    stay.k_coefficient,
                    qa.flag.value,
                ])
            else:
                logger.debug(f"Sensor {sensor_id} not streaming, skipping tension CSV write")
            
        except Exception as e:
            logger.error(f"Error procesando FFT para sensor {sensor_id}: {e}", exc_info=True)

    def _handle_sample(self, sensor_id: str, sample: Sample) -> None:
        num_samples = len(sample.acceleration_g)
        logger.info(f"_handle_sample called for {sensor_id}: {num_samples} samples")
        stay = self.stays[sensor_id]
        state = self.sensors[sensor_id]
        state.last_sample_timestamp = sample.timestamp
        state.estimated_fs = sample.fs_hz

        # Incrementar contador de samples recibidos
        state.samples_received_total += num_samples

        # Conversión defensiva: asegurar que fs_hz sea float
        fs_hz = float(sample.fs_hz) if isinstance(sample.fs_hz, str) else sample.fs_hz
        dt = 1.0 / fs_hz
        start_time = sample.timestamp - len(sample.acceleration_g) * dt

        # Generar timestamps para cada muestra
        timestamps_epoch = start_time + np.arange(len(sample.acceleration_g)) * dt

        # CRITICAL: Ordenar por timestamp para evitar datos desordenados
        # Crear array de (timestamp, accel) para ordenar juntos
        data_with_ts = [(timestamps_epoch[i], sample.acceleration_g[i])
                        for i in range(len(sample.acceleration_g))]
        data_with_ts.sort(key=lambda x: x[0])  # Ordenar por timestamp

        timestamps_epoch_sorted = np.array([x[0] for x in data_with_ts])
        acceleration_sorted = np.array([x[1] for x in data_with_ts])

        records = []
        valid_samples = []  # Para análisis: solo muestras válidas

        # Obtener ejes configurados del sensor
        sensor_state = self.sensors.get(sensor_id)
        active_axes = ['x', 'y', 'z']  # Por defecto todos
        if sensor_state and sensor_state.info.axes:
            active_axes = [axis.lower() for axis in sensor_state.info.axes]

        for epoch, accel in zip(timestamps_epoch_sorted, acceleration_sorted):
            ts_local_dt = datetime.fromtimestamp(epoch, tz=DEFAULT_TZ)
            ts_utc_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            ts_local = format_timestamp(ts_local_dt)
            ts_utc = format_timestamp(ts_utc_dt)

            # Para CSV: mantener 3 columnas pero poner NaN en ejes no configurados
            accel_x = accel[0] if 'x' in active_axes else float('nan')
            accel_y = accel[1] if 'y' in active_axes else float('nan')
            accel_z = accel[2] if 'z' in active_axes else float('nan')

            # Validar la muestra (datos calibrados en g's)
            is_valid = is_valid_acceleration_sample(accel, expected_range=(-10.0, 10.0))

            # Guardar en CSV con flag de validez
            records.append(
                [
                    ts_local,
                    ts_utc,
                    stay.stay_id,
                    sensor_id,
                    sample.fs_hz,
                    accel_x,
                    accel_y,
                    accel_z,
                    is_valid,
                ]
            )

            # Solo agregar a valid_samples si pasó validación
            if is_valid:
                valid_samples.append(accel)

        # Escribir a archivo (CSV o Parquet según configuración)
        accel_writer = self._get_or_create_accel_writer(sensor_id)
        format_name = self._storage_format.upper()

        if accel_writer is not None:
            accel_writer.writerows(records)
            state.samples_written_total += len(records)
            samples_lost = state.samples_received_total - state.samples_written_total

            log_msg = (
                f"[{format_name} WRITE] ✅ Wrote {len(records)} samples at {fs_hz} Hz "
                f"(streaming={state.streaming}, total_received={state.samples_received_total}, "
                f"total_written={state.samples_written_total}, lost={samples_lost})"
            )
            logger.info(log_msg)

            # También loggear en session_logger si existe
            if state.session_logger:
                state.session_logger.info(log_msg)

            # Escribir también a los chunks en paralelo
            chunk_writer = self._chunk_writers.get(sensor_id)
            if chunk_writer:
                try:
                    chunk_writer.append_samples(records)
                except Exception as chunk_err:
                    logger.warning(f"[CHUNK WRITER] Error escribiendo a chunks: {chunk_err}")
        else:
            samples_lost = state.samples_received_total - state.samples_written_total

            log_msg = (
                f"[{format_name} SKIP] ❌ NOT streaming, SKIPPING write for {len(records)} samples "
                f"(streaming={state.streaming}, total_received={state.samples_received_total}, "
                f"total_written={state.samples_written_total}, lost={samples_lost})"
            )
            logger.warning(log_msg)

            # También loggear en session_logger si existe
            if state.session_logger:
                state.session_logger.warning(log_msg)
        
        # Usar solo muestras válidas para el análisis
        if len(valid_samples) == 0:
            logger.warning(f"[ANALYSIS] No valid samples for {sensor_id}, skipping analysis")
            return
        
        valid_samples_array = np.array(valid_samples)

        buffer = self.buffers[sensor_id]
        buffer.extend(valid_samples_array, start_time, dt)  # Solo muestras válidas
        ts_arr, samples = buffer.get_array()
        if samples.size == 0:
            return
        magnitude = np.linalg.norm(samples, axis=1)

        # Conversión defensiva: asegurar que fs_hz sea float
        fs_hz = float(sample.fs_hz) if isinstance(sample.fs_hz, str) else sample.fs_hz
        
        estimator = self.estimators[sensor_id]
        estimator.update_fs(fs_hz)
        bp = self._make_bandpass()
        try:
            processed = preprocess(
                magnitude,
                fs_hz,
                bp,
            )
        except ValueError:
            processed = magnitude
        freqs, psd = estimator.power_spectral_density(processed)
        result = estimator.estimate(
            processed,
            mode=self.mode.get(sensor_id, "AUTO"),
            guided_f1=self.guided_f1.get(sensor_id),
            tolerance=self.guided_tol.get(sensor_id, 0.1),
        )

        tension = estimate_tension(
            result.f1_hz,
            mode="physical"
            if (stay.length_m is not None and stay.mass_density is not None)
            else "K",
            k_coefficient=stay.k_coefficient,
            length_m=stay.length_m,
            mass_density=stay.mass_density,
        )

        qa = result.quality
        window_end_dt = datetime.fromtimestamp(sample.timestamp, tz=DEFAULT_TZ)
        f1_str = f"{result.f1_hz:.2f}Hz" if result.f1_hz is not None else "N/A"
        tension_str = f"{tension.tension_newton:.1f}N" if tension.tension_newton is not None else "N/A"
        logger.info(f"Updating realtime_store for {sensor_id}: f1={f1_str}, tension={tension_str}, samples={len(samples)}")
        self.realtime_store.update_analysis(
            sensor_id,
            result,
            tension,
            qa,
            window_end_dt,
            (freqs, psd),
            AccelerationRecord(timestamps=ts_arr, samples=samples),
        )

        local_ts, utc_ts = now_local_utc()
        tension_row = [
            format_timestamp(local_ts),
            format_timestamp(utc_ts),
            stay.stay_id,
            sensor_id,
            result.f1_hz if result.f1_hz is not None else "",
            tension.tension_newton if tension.tension_newton is not None else "",
            tension.tension_kN if tension.tension_kN is not None else "",
            result.snr_db,
            result.peak_prominence,
            samples.shape[0],
            sample.fs_hz,
            result.mode,
            tension.coefficient_used if tension.coefficient_used is not None else "",
            qa.flag.value,
        ]
        # Escribir a CSV (archivo separado por sensor)
        tension_writer = self._get_or_create_tension_writer(sensor_id)
        if tension_writer is not None:
            tension_writer.writerow(tension_row)
        else:
            logger.debug(f"Sensor {sensor_id} not streaming, skipping tension CSV write (alt path)")

    def connect_gateway(self, host: str, port: int) -> GatewayStatus:
        logger.info("Connecting to gateway at %s:%s", host, port)
        try:
            status = self.client.connect_gateway(host, port)
        except Exception as exc:
            logger.exception("Gateway connection raised an exception")
            status = GatewayStatus(host=host, port=port, connected=False, message=str(exc))
        self._gateway_status = status
        if status.connected:
            logger.info("Gateway connected, starting discovery")
            try:
                self.discover()
            except Exception as exc:
                logger.exception("Failed to discover sensors after connection")
                self._gateway_status = GatewayStatus(
                    host=status.host,
                    port=status.port,
                    connected=status.connected,
                    message=f"Conectado con errores: {exc}",
                )
        else:
            logger.warning(
                "Gateway connection failed for %s:%s -> %s", host, port, status.message
            )
        return self._gateway_status

    def disconnect_gateway(self) -> GatewayStatus:
        logger.info("[STATE CHANGE] 🔴 Disconnecting gateway - setting ALL sensors streaming to False")
        status = self.client.disconnect_gateway()
        self._gateway_status = status
        for sensor_id, state in self.sensors.items():
            if state.streaming:
                logger.info(f"[STATE CHANGE] 🔴 Sensor {sensor_id} streaming state: True → False (gateway disconnect)")
            state.streaming = False
        return status

    def get_gateway_status(self) -> GatewayStatus:
        return self._gateway_status

    def set_mode(self, sensor_id: str, mode: str, guided_f1: Optional[float], tolerance: float) -> None:
        self.mode[sensor_id] = mode
        self.guided_f1[sensor_id] = guided_f1
        self.guided_tol[sensor_id] = tolerance

    def get_status(self) -> List[SensorState]:
        return list(self.sensors.values())

    def update_analysis_config(self, new_cfg: Dict) -> None:
        with self._lock:
            self.analysis_cfg = new_cfg
            for sensor_id, buffer in self.buffers.items():
                self.estimators[sensor_id] = self._create_estimator(buffer.fs)

    def update_storage_config(self, base_dir: Path, rotation_cfg: Dict) -> None:
        with self._lock:
            self.storage_base = base_dir
            self.rotation_cfg = rotation_cfg
            # Limpiar writers existentes - se recrearán on-demand con nueva config
            self._accel_writers.clear()
            self._tension_writers.clear()
            logger.info("Storage config updated - CSV writers will be recreated on-demand")


__all__ = [
    "StreamManager",
    "RealtimeDataStore",
    "StayDefinition",
    "SensorState",
]
