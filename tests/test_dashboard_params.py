"""Regression: dashboard form submits empty strings for blank number inputs."""
from app.main import _opt_float, _opt_int


def test_opt_float_handles_blank_and_invalid():
    assert _opt_float("") is None
    assert _opt_float(None) is None
    assert _opt_float("abc") is None
    assert _opt_float("75") == 75.0
    assert _opt_float("6.5") == 6.5


def test_opt_int_falls_back_to_default():
    assert _opt_int("", 100) == 100
    assert _opt_int(None, 100) == 100
    assert _opt_int("xx", 100) == 100
    assert _opt_int("250", 100) == 250
