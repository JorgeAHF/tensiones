"""Validation helpers for signal quality and thresholds."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QualityFlag(str, Enum):
    """Quality assessment for estimated tension."""

    OK = "OK"
    LOW_SNR = "LOW_SNR"
    UNSTABLE = "UNSTABLE"
    NO_PEAK = "NO_PEAK"


@dataclass
class Thresholds:
    green_max: float
    yellow_max: float
    orange_max: float

    def level(self, value: float, qa: Optional[QualityFlag]) -> str:
        if qa is not None and qa is not QualityFlag.OK:
            return "red"
        if value <= self.green_max:
            return "green"
        if value <= self.yellow_max:
            return "yellow"
        if value <= self.orange_max:
            return "orange"
        return "red"


@dataclass
class QualityAssessment:
    flag: QualityFlag
    snr_db: float
    peak_prominence: float

    @property
    def ok(self) -> bool:
        return self.flag is QualityFlag.OK


def evaluate_quality(
    snr_db: float,
    prominence: float,
    snr_min_db: float,
    min_prominence: float,
    unstable: bool = False,
) -> QualityAssessment:
    if snr_db < snr_min_db:
        return QualityAssessment(QualityFlag.LOW_SNR, snr_db, prominence)
    if unstable:
        return QualityAssessment(QualityFlag.UNSTABLE, snr_db, prominence)
    if prominence <= 0:
        return QualityAssessment(QualityFlag.NO_PEAK, snr_db, prominence)
    return QualityAssessment(QualityFlag.OK, snr_db, prominence)


__all__ = [
    "QualityAssessment",
    "QualityFlag",
    "Thresholds",
    "evaluate_quality",
]
