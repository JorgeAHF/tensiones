import numpy as np

from app.analysis.spectral import FrequencyEstimator, WelchConfig


def test_frequency_estimator_detects_peak():
    fs = 256
    t = np.arange(0, 60, 1 / fs)
    f1 = 2.5
    signal = np.sin(2 * np.pi * f1 * t)
    estimator = FrequencyEstimator(
        fs=fs,
        welch_config=WelchConfig(window="hann", nperseg=int(fs * 4), noverlap=int(fs * 2)),
        band=(0.5, 5.0),
        snr_min_db=5.0,
        max_rel_change=0.1,
        min_prominence=0.01,
    )
    result = estimator.estimate(signal)
    assert result.f1_hz is not None
    assert abs(result.f1_hz - f1) < 0.05
    assert result.quality.ok
