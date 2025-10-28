"""Shared testing fixtures."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pytest
import threading

from app.acquisition.mscl_client import MSCLClient, Sample, SensorInfo
from app.acquisition.stream_manager import (
    RealtimeDataStore,
    SensorBuffer,
    SensorState,
    StayDefinition,
    StreamManager,
)
from app.utils.validators import Thresholds


class _DummyClient(MSCLClient):
    """Minimal MSCL client stub for unit testing."""

    def connect_gateway(self, host: str, port: int):  # pragma: no cover - unused in tests
        raise NotImplementedError

    def disconnect_gateway(self):  # pragma: no cover - unused in tests
        raise NotImplementedError

    def gateway_status(self):  # pragma: no cover - unused in tests
        raise NotImplementedError

    def list_nodes(self):  # pragma: no cover - unused in tests
        return []

    def configure_node(self, sensor_id, sample_rate_hz, axes):  # pragma: no cover - unused in tests
        return None

    def start_streaming(self, sensor_id, callback):  # pragma: no cover - unused in tests
        return None

    def stop_streaming(self, sensor_id):  # pragma: no cover - unused in tests
        return None


@pytest.fixture
def stream_manager(tmp_path):
    """Return a StreamManager configured with a synthetic sensor."""

    stays = [
        StayDefinition(
            stay_id="STAY-001",
            sensor_id="SYN-001",
            k_coefficient=1500.0,
            thresholds=Thresholds(green_max=5.0, yellow_max=10.0, orange_max=15.0),
        )
    ]

    analysis_cfg = {
        "window_sec": 2.0,
        "nperseg_sec": 1.0,
        "overlap": 0.5,
        "welch_window": "hann",
        "fmin_hz": 0.2,
        "fmax_hz": 10.0,
        "snr_min_db": -10.0,
        "max_rel_f1_change": 0.05,
        "min_prominence": 0.05,
        "bandpass": [0.2, 10.0, 4],
    }

    rotation_cfg = {"mode": "size", "max_mb": 50}
    realtime_store = RealtimeDataStore()
    realtime_store._lock = threading.RLock()
    manager = StreamManager(
        client=_DummyClient(),
        stays=stays,
        analysis_cfg=analysis_cfg,
        rotation_cfg=rotation_cfg,
        storage_base=tmp_path,
        realtime_store=realtime_store,
    )

    sensor_info = SensorInfo(
        sensor_id="SYN-001",
        stay_id="STAY-001",
        sample_rate_hz=128.0,
        axes=["x", "y", "z"],
    )
    manager.sensors[sensor_info.sensor_id] = SensorState(info=sensor_info, streaming=True)
    manager.buffers[sensor_info.sensor_id] = SensorBuffer(
        analysis_cfg["window_sec"], sensor_info.sample_rate_hz
    )
    manager.estimators[sensor_info.sensor_id] = manager._create_estimator(sensor_info.sample_rate_hz)
    manager.mode[sensor_info.sensor_id] = "AUTO"
    manager.guided_f1[sensor_info.sensor_id] = None
    manager.guided_tol[sensor_info.sensor_id] = analysis_cfg["max_rel_f1_change"]

    return manager, realtime_store, sensor_info


@pytest.fixture
def synthetic_sample():
    """Factory for generating synthetic accelerometer samples."""

    def _factory(
        *,
        freq_hz: float | None,
        duration_s: float = 2.0,
        fs_hz: float = 128.0,
        amplitude: float = 0.6,
        offset: float = 1.0,
        noise_std: float = 0.02,
        seed: int = 123,
        start_time: float = 1_000.0,
        sensor_id: str = "SYN-001",
        stay_id: str = "STAY-001",
    ) -> Sample:
        n_samples = int(fs_hz * duration_s)
        t = np.arange(n_samples) / fs_hz
        base = np.full(n_samples, offset, dtype=float)
        if freq_hz is not None:
            base += amplitude * np.sin(2 * np.pi * freq_hz * t)

        rng = np.random.default_rng(seed)
        noise = rng.normal(scale=noise_std, size=(n_samples, 3)) if noise_std > 0 else 0.0

        accel = np.zeros((n_samples, 3), dtype=float)
        accel[:, 0] = base
        if noise_std > 0:
            accel += noise
            accel[:, 0] = np.maximum(accel[:, 0], 1e-6)

        end_timestamp = start_time + duration_s
        return Sample(
            sensor_id=sensor_id,
            stay_id=stay_id,
            fs_hz=fs_hz,
            timestamp=end_timestamp,
            acceleration_g=accel,
        )

    return _factory


__all__ = ["stream_manager", "synthetic_sample"]
