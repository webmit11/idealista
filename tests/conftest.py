"""Shared test fixtures and helpers."""
import types

import pytest

# Attributes the scoring layer may read from a property-like object.
_DEFAULTS = dict(
    title=None,
    description=None,
    address_raw=None,
    latitude=None,
    longitude=None,
    area_m2=None,
    price=None,
    price_per_m2=None,
    typology=None,
    distance_to_metro_m=None,
    nearest_metro_station=None,
    gross_yield_percent=None,
    condition=None,
    energy_certificate=None,
    has_elevator=None,
    has_garage=None,
    price_drop_percent=None,
    floor=None,
    rental_estimate_low=None,
    rental_estimate_mid=None,
    rental_estimate_high=None,
)


def make_property(**overrides):
    data = dict(_DEFAULTS)
    data.update(overrides)
    return types.SimpleNamespace(**data)


@pytest.fixture
def make_prop():
    return make_property
