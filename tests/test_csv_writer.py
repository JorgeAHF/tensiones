from pathlib import Path
import time

from app.sinks.csv_writer import RotatingCsvWriter
from app.sinks.rotation import RotationPolicy


def test_rotation_by_time(tmp_path):
    writer = RotatingCsvWriter(
        base_dir=tmp_path,
        prefix="accel",
        headers=["a", "b"],
        policy=RotationPolicy(mode="time", minutes=0),
    )
    first = writer.writerow([1, 2])
    time.sleep(0.01)
    second = writer.writerow([3, 4])
    assert first != second
    assert first.exists()
    assert second.exists()


def test_rotation_by_size(tmp_path):
    writer = RotatingCsvWriter(
        base_dir=tmp_path,
        prefix="accel",
        headers=["a", "b"],
        policy=RotationPolicy(mode="size", max_mb=0.0001),
    )
    path1 = writer.writerow(["x" * 100, "y" * 100])
    path2 = writer.writerow(["z" * 100, "w" * 100])
    assert path1.exists()
    assert path2.exists()
    assert path1 != path2
