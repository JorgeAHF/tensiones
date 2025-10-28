"""Spectral analysis utilities for fundamental frequency estimation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np
from scipy import signal

from app.utils.validators import QualityAssessment, QualityFlag, evaluate_quality


@dataclass
class WelchConfig:
    window: str = "hann"
    nperseg: Optional[int] = None
    noverlap: Optional[int] = None
    detrend: str = "constant"


@dataclass
class PeakDetectionResult:
    f1_hz: Optional[float]
    harmonics_hz: Dict[int, Optional[float]]
    snr_db: float
    peak_prominence: float
    quality: QualityAssessment
    mode: str


class FrequencyEstimator:
    """Estimate fundamental frequency using Welch PSD and harmonic search."""

    def __init__(
        self,
        fs: float,
        welch_config: WelchConfig,
        band: Sequence[float],
        snr_min_db: float,
        max_rel_change: float,
        min_prominence: float = 0.0,
    ) -> None:
        self.fs = fs
        self.welch_config = welch_config
        self.band = band
        self.snr_min_db = snr_min_db
        self.max_rel_change = max_rel_change
        self.min_prominence = min_prominence
        self._last_f1: Optional[float] = None

    def update_fs(self, fs: float) -> None:
        self.fs = fs

    def power_spectral_density(self, data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        requested_nperseg = self.welch_config.nperseg or int(self.fs * 4)
        nperseg = min(requested_nperseg, len(data))
        if nperseg < 8:
            raise ValueError("nperseg too small for PSD estimation")
        noverlap = self.welch_config.noverlap
        if noverlap is None:
            noverlap = nperseg // 2
        else:
            noverlap = max(0, min(noverlap, nperseg - 1))
        freqs, psd = signal.welch(
            data,
            fs=self.fs,
            window=self.welch_config.window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend=self.welch_config.detrend,
        )
        return freqs, psd

    def _band_mask(self, freqs: np.ndarray) -> np.ndarray:
        fmin, fmax = self.band
        return (freqs >= fmin) & (freqs <= fmax)

    def _estimate_snr(self, psd: np.ndarray, peak_idx: int, guard_bins: int = 1) -> float:
        peak_power = psd[peak_idx]
        noise = np.delete(psd, slice(max(0, peak_idx - guard_bins), peak_idx + guard_bins + 1))
        if noise.size == 0:
            return 0.0
        noise_power = float(np.mean(noise))
        if noise_power <= 0:
            return 0.0
        return 10 * np.log10(peak_power / noise_power)

    def _find_peak(
        self,
        freqs: np.ndarray,
        psd: np.ndarray,
        mode: str,
        guided_f1: Optional[float] = None,
        tolerance: float = 0.1,
    ) -> tuple[Optional[float], float, float, Dict[int, Optional[float]]]:
        mask = self._band_mask(freqs)
        candidate_freqs = freqs[mask]
        candidate_psd = psd[mask]
        if candidate_freqs.size == 0:
            return None, 0.0, 0.0, {1: None, 2: None, 3: None}

        if mode == "GUIDED" and guided_f1 is not None:
            lower = guided_f1 * (1 - tolerance)
            upper = guided_f1 * (1 + tolerance)
            guided_mask = (candidate_freqs >= lower) & (candidate_freqs <= upper)
            if not np.any(guided_mask):
                return None, 0.0, 0.0, {1: None, 2: None, 3: None}
            sub_freqs = candidate_freqs[guided_mask]
            sub_psd = candidate_psd[guided_mask]
        else:
            sub_freqs = candidate_freqs
            sub_psd = candidate_psd

        if sub_freqs.size == 0:
            return None, 0.0, 0.0, {1: None, 2: None, 3: None}

        peak_indices, properties = signal.find_peaks(sub_psd, prominence=self.min_prominence)
        if peak_indices.size == 0:
            return None, 0.0, 0.0, {1: None, 2: None, 3: None}

        prominences = properties.get("prominences", np.zeros_like(peak_indices, dtype=float))
        best_idx = int(peak_indices[np.argmax(prominences)])
        f1 = float(sub_freqs[best_idx])
        prom = float(prominences[np.argmax(prominences)])
        global_idx = np.where(freqs == sub_freqs[best_idx])[0][0]
        snr_db = self._estimate_snr(psd, global_idx)

        harmonics = {}
        for harmonic in (2, 3):
            target = harmonic * f1
            harmonic_mask = (freqs >= target * 0.95) & (freqs <= target * 1.05)
            if np.any(harmonic_mask):
                harmonic_idx = np.argmax(psd[harmonic_mask])
                harmonic_freqs = freqs[harmonic_mask]
                harmonics[harmonic] = float(harmonic_freqs[harmonic_idx])
            else:
                harmonics[harmonic] = None
        harmonics[1] = f1
        return f1, snr_db, prom, harmonics

    def estimate(
        self,
        data: np.ndarray,
        mode: str = "AUTO",
        guided_f1: Optional[float] = None,
        tolerance: float = 0.1,
    ) -> PeakDetectionResult:
        if data.size == 0:
            qa = evaluate_quality(0.0, 0.0, self.snr_min_db, self.min_prominence)
            return PeakDetectionResult(
                f1_hz=None,
                harmonics_hz={1: None, 2: None, 3: None},
                snr_db=0.0,
                peak_prominence=0.0,
                quality=qa,
                mode=mode,
            )
        freqs, psd = self.power_spectral_density(data)
        f1, snr_db, prom, harmonics = self._find_peak(freqs, psd, mode, guided_f1, tolerance)

        unstable = False
        if f1 is not None and self._last_f1 is not None:
            rel_change = abs(f1 - self._last_f1) / max(self._last_f1, 1e-6)
            unstable = rel_change > self.max_rel_change

        qa = evaluate_quality(snr_db, prom, self.snr_min_db, self.min_prominence, unstable)
        if qa.ok and f1 is not None:
            self._last_f1 = f1
        elif not qa.ok:
            self._last_f1 = None

        return PeakDetectionResult(
            f1_hz=f1,
            harmonics_hz=harmonics,
            snr_db=snr_db,
            peak_prominence=prom,
            quality=qa,
            mode=mode,
        )


__all__ = ["FrequencyEstimator", "PeakDetectionResult", "WelchConfig"]
