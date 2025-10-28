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


def _make_estimator(**kwargs) -> FrequencyEstimator:
    config = WelchConfig(window="hann", nperseg=1024, noverlap=512)
    config = WelchConfig(**{**config.__dict__, **kwargs})
    return FrequencyEstimator(
        fs=256,
        welch_config=config,
        band=(0.1, 10.0),
        snr_min_db=10.0,
        max_rel_change=0.2,
    )


def test_psd_handles_short_windows_with_large_overlap():
    estimator = _make_estimator()
    data = np.random.normal(size=256)

    freqs, psd = estimator.power_spectral_density(data)

    assert freqs.size == psd.size
    assert freqs.size > 0


def test_psd_clamps_custom_overlap_to_window_size():
    estimator = _make_estimator(noverlap=2000)
    data = np.random.normal(size=300)

    freqs, psd = estimator.power_spectral_density(data)

    assert freqs.size == psd.size
    assert freqs.size > 0
