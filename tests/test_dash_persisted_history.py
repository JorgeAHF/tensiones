"""Tests for persisted tension loading in the Dash UI."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("dash_bootstrap_components")

from app.ui.dash_app import TENSION_CSV_HEADERS, load_persisted_tension
from app.utils.timeutils import DEFAULT_TZ


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TENSION_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _make_row(ts_local: datetime, sensor: str, stay: str, tension_kn: float):
    ts_utc = ts_local.astimezone(timezone.utc)
    return {
        "t_window_end_local": ts_local.isoformat(),
        "t_window_end_utc": ts_utc.isoformat(),
        "stay_id": stay,
        "sensor_id": sensor,
        "f1_hz": "2.5",
        "T_N": str(tension_kn * 1000),
        "T_kN": str(tension_kn),
        "SNR_dB": "12.5",
        "peak_prom": "0.8",
        "n_samples": "128",
        "fs_hz": "64.0",
        "mode": "AUTO",
        "k_used": "20000",
        "qa": "green",
    }


def test_load_persisted_tension_rotated_files(tmp_path):
    tension_dir = tmp_path / "tension"
    tension_dir.mkdir()

    base_ts = DEFAULT_TZ.localize(datetime(2024, 1, 1, 12, 0, 0))
    row1 = _make_row(base_ts, "S1", "Stay-1", 5.5)
    row2 = _make_row(base_ts + timedelta(minutes=10), "S1", "Stay-1", 6.0)

    _write_csv(tension_dir / "tension_20240101_120000.csv", [row1])
    _write_csv(tension_dir / "tension_20240101_130000.csv", [row2])

    records = load_persisted_tension(tmp_path, sensor_id="S1", target_date=base_ts.date())
    assert len(records) == 2
    assert [round(rec["T_kN"], 2) for rec in records] == [5.5, 6.0]
    assert [rec["t_window_end_local"] for rec in records] == [
        base_ts,
        base_ts + timedelta(minutes=10),
    ]

    # Different date should yield no records
    next_day = base_ts.date() + timedelta(days=1)
    assert load_persisted_tension(tmp_path, sensor_id="S1", target_date=next_day) == []

    # Other sensor should not be included
    row3 = _make_row(base_ts + timedelta(minutes=20), "S2", "Stay-2", 7.0)
    _write_csv(tension_dir / "tension_20240101_140000.csv", [row3])
    filtered = load_persisted_tension(tmp_path, sensor_id="S1", target_date=base_ts.date())
    assert len(filtered) == 2
