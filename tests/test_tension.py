from app.analysis.tension import estimate_tension


def test_tension_k_mode():
    result = estimate_tension(2.5, mode="K", k_coefficient=20000.0)
    assert result.tension_newton == 20000.0 * 2.5 ** 2
    assert result.tension_kN == result.tension_newton / 1000


def test_tension_physical_mode():
    result = estimate_tension(2.0, mode="physical", length_m=10.0, mass_density=5.0)
    expected = (2 * 10.0 * 2.0) ** 2 * 5.0
    assert result.tension_newton == expected
