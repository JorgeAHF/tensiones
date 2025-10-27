"""Signal preprocessing utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy import signal


@dataclass
class BandpassConfig:
    low_hz: float
    high_hz: float
    order: int = 4

    def as_sos(self, fs: float) -> np.ndarray:
        return signal.butter(
            self.order,
            [self.low_hz, self.high_hz],
            btype="band",
            fs=fs,
            output="sos",
        )


def detrend(data: np.ndarray) -> np.ndarray:
    """Remove linear trend from data using SciPy detrend."""
    return signal.detrend(data, type="linear")


def apply_bandpass(data: np.ndarray, fs: float, config: BandpassConfig) -> np.ndarray:
    """Apply Butterworth band-pass filter to the data."""
    if config.high_hz <= config.low_hz:
        raise ValueError("Bandpass high cutoff must be greater than low cutoff")
    sos = config.as_sos(fs)
    return signal.sosfiltfilt(sos, data)


def preprocess(
    data: np.ndarray,
    fs: float,
    bandpass: Optional[BandpassConfig] = None,
    remove_trend: bool = True,
) -> np.ndarray:
    processed = np.asarray(data)
    if processed.size == 0:
        return processed
    if remove_trend:
        processed = detrend(processed)
    if bandpass is not None:
        processed = apply_bandpass(processed, fs, bandpass)
    return processed


__all__ = ["BandpassConfig", "apply_bandpass", "detrend", "preprocess"]
