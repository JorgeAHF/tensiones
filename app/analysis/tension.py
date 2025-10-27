"""Tension estimation utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TensionResult:
    tension_newton: Optional[float]
    tension_kN: Optional[float]
    mode: str
    coefficient_used: Optional[float]


def tension_from_frequency(k_coefficient: float, f1_hz: float) -> float:
    """Compute tension using T = K * f1^2."""
    return k_coefficient * f1_hz ** 2


def physical_tension(length_m: float, mass_density: float, f1_hz: float) -> float:
    """Compute tension using T = (2 L f1)^2 * mu."""
    return (2.0 * length_m * f1_hz) ** 2 * mass_density


def estimate_tension(
    f1_hz: Optional[float],
    mode: str,
    k_coefficient: Optional[float] = None,
    length_m: Optional[float] = None,
    mass_density: Optional[float] = None,
) -> TensionResult:
    if f1_hz is None:
        return TensionResult(None, None, mode, None)

    tension_n: Optional[float] = None
    coeff_used: Optional[float] = None

    if mode == "physical" and length_m is not None and mass_density is not None:
        tension_n = physical_tension(length_m, mass_density, f1_hz)
        coeff_used = mass_density
    elif k_coefficient is not None:
        tension_n = tension_from_frequency(k_coefficient, f1_hz)
        coeff_used = k_coefficient

    if tension_n is None:
        return TensionResult(None, None, mode, coeff_used)

    return TensionResult(tension_n, tension_n / 1000.0, mode, coeff_used)


__all__ = [
    "TensionResult",
    "estimate_tension",
    "physical_tension",
    "tension_from_frequency",
]
