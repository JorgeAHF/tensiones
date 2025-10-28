"""Integration-style tests for StreamManager signal processing."""

import csv
from pathlib import Path

import pytest

from app.utils.validators import QualityFlag

pytestmark = pytest.mark.filterwarnings(
    "ignore:datetime.datetime.utcnow:DeprecationWarning"
)


def _read_csv_rows(directory: Path) -> list[list[str]]:
    files = list(directory.glob("*.csv"))
    assert files, f"expected CSV files in {directory}"
    # Files are timestamped, the latest is the last one written
    files.sort()
    with files[-1].open(newline="") as handle:
        reader = csv.reader(handle)
        return list(reader)


def test_stream_manager_good_signal_produces_ok_quality(stream_manager, synthetic_sample):
    manager, store, sensor_info = stream_manager
    sample = synthetic_sample(freq_hz=2.0, noise_std=0.05)

    manager._handle_sample(sensor_info.sensor_id, sample)

    snapshot = store.snapshot()
    state = snapshot[sensor_info.sensor_id]
    _, tension_result, qa = state.history[-1]

    assert qa.flag is QualityFlag.OK
    assert tension_result.tension_newton is not None

    result = state.last_result
    assert result.f1_hz is not None
    expected_tension = 1500.0 * result.f1_hz**2
    assert tension_result.tension_newton == pytest.approx(expected_tension, rel=1e-3)

    accel_rows = _read_csv_rows(manager.storage_base / "acceleration")
    assert accel_rows[0] == [
        "timestamp_local",
        "timestamp_utc",
        "stay_id",
        "sensor_id",
        "fs_hz",
        "ax_g",
        "ay_g",
        "az_g",
    ]
    # 128 Hz * 2 seconds = 256 samples plus header
    assert len(accel_rows) == 257
    assert accel_rows[1][2] == "STAY-001"
    assert accel_rows[1][3] == "SYN-001"
    assert float(accel_rows[1][4]) == pytest.approx(128.0)

    tension_rows = _read_csv_rows(manager.storage_base / "tension")
    assert tension_rows[0] == [
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
    assert len(tension_rows) == 2
    data_row = tension_rows[1]
    assert data_row[2] == "STAY-001"
    assert data_row[3] == "SYN-001"
    assert float(data_row[4]) == pytest.approx(result.f1_hz)
    assert float(data_row[5]) == pytest.approx(tension_result.tension_newton)
    assert data_row[-1] == QualityFlag.OK.value


def test_stream_manager_no_peak_sets_quality_flag(stream_manager, synthetic_sample):
    manager, store, sensor_info = stream_manager
    sample = synthetic_sample(freq_hz=None, noise_std=0.0)

    manager._handle_sample(sensor_info.sensor_id, sample)

    state = store.snapshot()[sensor_info.sensor_id]
    _, tension_result, qa = state.history[-1]

    assert qa.flag is QualityFlag.NO_PEAK
    assert tension_result.tension_newton is None

    tension_rows = _read_csv_rows(manager.storage_base / "tension")
    data_row = tension_rows[1]
    # f1 and tension columns remain blank when there is no peak
    assert data_row[4] == ""
    assert data_row[5] == ""
    assert data_row[6] == ""
    assert data_row[-1] == QualityFlag.NO_PEAK.value


def test_stream_manager_detects_unstable_frequency(stream_manager, synthetic_sample):
    manager, store, sensor_info = stream_manager

    baseline = synthetic_sample(freq_hz=2.0, noise_std=0.05, start_time=1_000.0)
    changed = synthetic_sample(freq_hz=3.5, noise_std=0.05, start_time=1_002.0)

    manager._handle_sample(sensor_info.sensor_id, baseline)
    manager._handle_sample(sensor_info.sensor_id, changed)

    state = store.snapshot()[sensor_info.sensor_id]
    assert len(state.history) == 2
    _, _, qa = state.history[-1]
    assert qa.flag is QualityFlag.UNSTABLE

    tension_rows = _read_csv_rows(manager.storage_base / "tension")
    assert len(tension_rows) == 3  # header + two results
    last_row = tension_rows[-1]
    assert last_row[-1] == QualityFlag.UNSTABLE.value
