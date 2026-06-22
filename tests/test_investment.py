import pytest

from app.services.investment import compute_investment, imt, monthly_payment


def test_imt_brackets():
    assert imt(0) == 0.0
    # €150,000 -> 5% bracket, deduction 5,201.53
    assert imt(150_000) == pytest.approx(150_000 * 0.05 - 5_201.53, abs=0.01)
    # €200,000 -> 7% bracket, deduction 9,003.25
    assert imt(200_000) == pytest.approx(200_000 * 0.07 - 9_003.25, abs=0.01)


def test_monthly_payment():
    # 140k loan, 3.5%/yr, 30y -> ~628.6 €/mo
    assert monthly_payment(140_000, 0.035, 30) == pytest.approx(628.6, abs=2.0)
    assert monthly_payment(0, 0.035, 30) == 0.0
    # zero interest -> straight division
    assert monthly_payment(120_000, 0.0, 10) == pytest.approx(1000.0, abs=0.01)


def test_compute_investment_shape_and_values():
    inv = compute_investment(200_000, 1000, "T2", ltv=0.7, rate=0.035, term_years=30)
    acq = inv["acquisition"]
    assert acq["stamp_duty"] == pytest.approx(1600.0, abs=0.01)  # 0.8%
    assert acq["furnishing"] == 9000.0  # T2
    assert acq["total_investment"] > 200_000
    inc = inv["income"]
    assert inc["annual_rent"] == 12000
    assert inc["net_yield"] < inc["gross_yield"]  # net is after costs
    m = inv["mortgage"]
    assert m["loan"] == pytest.approx(140_000.0, abs=0.01)
    assert m["down_payment"] == pytest.approx(60_000.0, abs=0.01)
    assert m["cash_needed"] == pytest.approx(60_000.0 + acq["total_costs"], abs=0.01)


def test_compute_investment_requires_price_and_rent():
    assert compute_investment(None, 1000, "T2") is None
    assert compute_investment(200_000, None, "T2") is None
