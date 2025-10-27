"""Manage sensor streams, analysis pipeline and storage."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.acquisition.mscl_client import GatewayStatus, MSCLClient, Sample, SensorInfo
from app.analysis.filters import BandpassConfig, preprocess
from app.analysis.spectral import FrequencyEstimator, PeakDetectionResult, WelchConfig
from app.analysis.tension import TensionResult, estimate_tension
from app.sinks.csv_writer import RotatingCsvWriter
from app.sinks.rotation import RotationPolicy
from app.utils.timeutils import DEFAULT_TZ, format_timestamp, now_local_utc
from app.utils.validators import QualityAssessment, Thresholds

logger = logging.getLogger(__name__)


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
    last_sample_timestamp: Optional[float] = None
    estimated_fs: Optional[float] = None
    battery_percent: Optional[float] = None


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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._analysis: Dict[str, AnalysisState] = {}

    def ensure_sensor(self, sensor_id: str) -> AnalysisState:
        with self._lock:
            state = self._analysis.get(sensor_id)
            if state is None:
                state = AnalysisState()
                self._analysis[sensor_id] = state
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

    def snapshot(self) -> Dict[str, AnalysisState]:
        with self._lock:
            return {k: v for k, v in self._analysis.items()}

    def drop(self, sensor_id: str) -> None:
        with self._lock:
            self._analysis.pop(sensor_id, None)


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
    ) -> None:
        self.client = client
        self.analysis_cfg = analysis_cfg
        self.rotation_cfg = rotation_cfg
        self.storage_base = storage_base
        self.realtime_store = realtime_store
        self.stays = {stay.sensor_id: stay for stay in stays}
        self.sensors: Dict[str, SensorState] = {}
        self.buffers: Dict[str, SensorBuffer] = {}
        self.estimators: Dict[str, FrequencyEstimator] = {}
        self.mode: Dict[str, str] = {}
        self.guided_f1: Dict[str, Optional[float]] = {}
        self.guided_tol: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._gateway_status = GatewayStatus(host=None, port=None, connected=False)
        self._accel_writer = self._create_writer("acceleration", [
            "timestamp_local",
            "timestamp_utc",
            "stay_id",
            "sensor_id",
            "fs_hz",
            "ax_g",
            "ay_g",
            "az_g",
        ])
        self._tension_writer = self._create_writer("tension", [
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
        ])

    def _create_writer(self, subdir: str, headers: List[str]) -> RotatingCsvWriter:
        policy = RotationPolicy(
            mode=self.rotation_cfg.get("mode", "time"),
            minutes=self.rotation_cfg.get("minutes"),
            max_mb=self.rotation_cfg.get("max_mb"),
        )
        path = self.storage_base / subdir
        return RotatingCsvWriter(path, subdir, headers, policy)

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
            else:
                state.info.sample_rate_hz = info.sample_rate_hz
                state.info.axes = info.axes
                state.info.data_format = getattr(info, "data_format", state.info.data_format)
                state.info.acquisition_duration_sec = getattr(
                    info, "acquisition_duration_sec", state.info.acquisition_duration_sec
                )
            states.append(state)
        return states

    def configure(self, sensor_id: str, sample_rate: float, axes: Iterable[str]) -> None:
        if not self._gateway_status.connected:
            logger.warning("Cannot configure sensor %s without gateway connection", sensor_id)
            return
        self.client.configure_node(sensor_id, sample_rate, axes)
        stay = self.stays.get(sensor_id)
        if stay is None:
            return
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

    def add_manual_sensor(
        self,
        sensor_id: str,
        sample_rate: float,
        data_format: str,
        acquisition_duration: float,
    ) -> SensorState:
        if not self._gateway_status.connected:
            raise RuntimeError("Gateway no conectado; conecta antes de registrar sensores manualmente")
        stay = self.stays.get(sensor_id)
        if stay is None:
            raise KeyError(f"Sensor {sensor_id} no está asociado a ningún tirante configurado")
        axes = ["x", "y", "z"]
        info = self.client.add_manual_sensor(
            sensor_id=sensor_id,
            stay_id=stay.stay_id,
            sample_rate_hz=sample_rate,
            axes=axes,
            data_format=data_format,
            acquisition_duration_sec=acquisition_duration,
        )
        state = self.sensors.get(sensor_id)
        if state is None:
            state = SensorState(info=info)
            self.sensors[sensor_id] = state
        else:
            state.info = info
        self.configure(sensor_id, sample_rate, axes)
        state.info.data_format = data_format
        state.info.acquisition_duration_sec = acquisition_duration
        logger.info(
            "Manual sensor ready sensor=%s stay=%s fs=%.2f data=%s duration=%.2fs",
            sensor_id,
            stay.stay_id,
            sample_rate,
            data_format,
            acquisition_duration,
        )
        return state

    def apply_sensor_configs(self, configs: List[Dict[str, object]]) -> None:
        for row in configs:
            sensor_id = str(row.get("sensor"))
            if not sensor_id or sensor_id not in self.sensors:
                continue
            info = self.sensors[sensor_id].info
            fs_value = row.get("fs")
            data_format = str(row.get("data_format") or info.data_format)
            acquisition = row.get("acq_duration") or info.acquisition_duration_sec
            try:
                fs_float = float(fs_value) if fs_value is not None else info.sample_rate_hz
                acquisition_float = float(acquisition)
            except (TypeError, ValueError):
                logger.warning("Valores inválidos para sensor %s en tabla de configuración", sensor_id)
                continue
            acquisition_float = max(0.1, acquisition_float)
            fs_changed = abs(fs_float - info.sample_rate_hz) > 1e-6
            if fs_changed:
                self.configure(sensor_id, fs_float, info.axes)
                info.sample_rate_hz = fs_float
            info.data_format = data_format
            info.acquisition_duration_sec = acquisition_float
            logger.debug(
                "Sensor actualizado desde UI sensor=%s fs=%.2f data=%s duration=%.2fs",
                sensor_id,
                info.sample_rate_hz,
                info.data_format,
                info.acquisition_duration_sec,
            )

    def start(self, sensor_id: str) -> None:
        if not self._gateway_status.connected:
            logger.warning("Cannot start sensor %s without gateway connection", sensor_id)
            return
        stay = self.stays.get(sensor_id)
        if stay is None:
            logger.warning("Cannot start unknown sensor %s", sensor_id)
            return
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

        self.client.start_streaming(sensor_id, callback)
        state.streaming = True

    def stop(self, sensor_id: str) -> None:
        self.client.stop_streaming(sensor_id)
        state = self.sensors.get(sensor_id)
        if state:
            state.streaming = False

    def start_all(self) -> None:
        for sensor_id in self.stays:
            self.start(sensor_id)

    def stop_all(self) -> None:
        for sensor_id in list(self.stays):
            self.stop(sensor_id)

    def _handle_sample(self, sensor_id: str, sample: Sample) -> None:
        stay = self.stays[sensor_id]
        state = self.sensors[sensor_id]
        state.last_sample_timestamp = sample.timestamp
        state.estimated_fs = sample.fs_hz

        dt = 1.0 / sample.fs_hz
        start_time = sample.timestamp - len(sample.acceleration_g) * dt

        timestamps = start_time + np.arange(len(sample.acceleration_g)) * dt
        records = []
        for idx, accel in enumerate(sample.acceleration_g):
            epoch = start_time + idx * dt
            ts_local_dt = datetime.fromtimestamp(epoch, tz=DEFAULT_TZ)
            ts_utc_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            ts_local = format_timestamp(ts_local_dt)
            ts_utc = format_timestamp(ts_utc_dt)
            records.append(
                [
                    ts_local,
                    ts_utc,
                    stay.stay_id,
                    sensor_id,
                    sample.fs_hz,
                    accel[0],
                    accel[1],
                    accel[2],
                ]
            )
        self._accel_writer.writerows(records)

        buffer = self.buffers[sensor_id]
        buffer.extend(sample.acceleration_g, start_time, dt)
        ts_arr, samples = buffer.get_array()
        if samples.size == 0:
            return
        magnitude = np.linalg.norm(samples, axis=1)

        estimator = self.estimators[sensor_id]
        estimator.update_fs(sample.fs_hz)
        bp = self._make_bandpass()
        try:
            processed = preprocess(
                magnitude,
                sample.fs_hz,
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
        self._tension_writer.writerow(tension_row)

    def connect_gateway(self, host: str, port: int) -> GatewayStatus:
        status = self.client.connect_gateway(host, port)
        self._gateway_status = status
        if status.connected:
            self.discover()
        return status

    def disconnect_gateway(self) -> GatewayStatus:
        status = self.client.disconnect_gateway()
        self._gateway_status = status
        for state in self.sensors.values():
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
            self._accel_writer = self._create_writer(
                "acceleration",
                [
                    "timestamp_local",
                    "timestamp_utc",
                    "stay_id",
                    "sensor_id",
                    "fs_hz",
                    "ax_g",
                    "ay_g",
                    "az_g",
                ],
            )
            self._tension_writer = self._create_writer(
                "tension",
                [
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
                ],
            )

    def reassign_stay_sensor(self, stay_id: str, new_sensor_id: str) -> StayDefinition:
        current_sensor_id = None
        stay_obj: Optional[StayDefinition] = None
        for sensor_key, stay in list(self.stays.items()):
            if stay.stay_id == stay_id:
                current_sensor_id = sensor_key
                stay_obj = stay
                break
        if stay_obj is None or current_sensor_id is None:
            raise KeyError(f"No se encontró tirante {stay_id}")
        if current_sensor_id == new_sensor_id:
            return stay_obj
        self.stays.pop(current_sensor_id, None)
        stay_obj.sensor_id = new_sensor_id
        self.stays[new_sensor_id] = stay_obj
        # limpiar estados previos
        self.sensors.pop(current_sensor_id, None)
        self.buffers.pop(current_sensor_id, None)
        self.estimators.pop(current_sensor_id, None)
        self.mode.pop(current_sensor_id, None)
        self.guided_f1.pop(current_sensor_id, None)
        self.guided_tol.pop(current_sensor_id, None)
        self.realtime_store.drop(current_sensor_id)
        logger.info(
            "Tirante %s reasignado de sensor %s a %s",
            stay_id,
            current_sensor_id,
            new_sensor_id,
        )
        return stay_obj


__all__ = [
    "StreamManager",
    "RealtimeDataStore",
    "StayDefinition",
    "SensorState",
]
