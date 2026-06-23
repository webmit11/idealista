"""Investment economics for a purchase in Portugal (Continente).

Computes acquisition taxes/costs (IMT, Imposto do Selo, notary/registration),
yields (gross / net) and a mortgage scenario (monthly payment, cashflow,
cash-on-cash).

NOTE: IMT brackets are the 2024 Continente values for housing that is NOT a
primary/permanent residence (investment). They are updated by the State Budget
each year — verify/update yearly. All other rates are configurable in .env.
This is an estimator, not tax/financial advice.
"""
from typing import Optional

from app.core.config import settings
from app.services.rental_estimator import furnishing_cost

# (upper_bound, marginal_rate, deduction). Last bracket: upper_bound = None.
# Secondary/investment housing, Continente, 2024.
IMT_BRACKETS_SECONDARY = [
    (101_917, 0.01, 0.0),
    (139_412, 0.02, 1_019.17),
    (190_086, 0.05, 5_201.53),
    (316_772, 0.07, 9_003.25),
    (607_528, 0.08, 12_170.97),
    (1_034_830, 0.06, 0.0),   # single flat rate band
    (None, 0.075, 0.0),       # above the last threshold
]


def imt(price: float, brackets=IMT_BRACKETS_SECONDARY) -> float:
    if not price or price <= 0:
        return 0.0
    for upper, rate, deduction in brackets:
        if upper is None or price <= upper:
            return round(max(0.0, price * rate - deduction), 2)
    return 0.0


def al_multiplier(typology: Optional[str]) -> float:
    """Short-term (AL) gross revenue multiplier over long-term rent, tilted by
    typology — smaller units command a bigger short-term premium in Porto."""
    base = settings.al_gross_multiplier
    t = (typology or "").upper()
    if t in ("T0", "T1", "STUDIO"):
        return round(base * 1.15, 3)
    if t in ("T3", "T4", "T5", "T6"):
        return round(base * 0.85, 3)
    return base


def monthly_payment(loan: float, annual_rate: float, years: int) -> float:
    if loan <= 0:
        return 0.0
    n = years * 12
    r = annual_rate / 12
    if r == 0:
        return round(loan / n, 2)
    return round(loan * r / (1 - (1 + r) ** (-n)), 2)


def compute_investment(
    price: Optional[float],
    rent_mid: Optional[float],
    typology: Optional[str],
    ltv: Optional[float] = None,
    rate: Optional[float] = None,
    term_years: Optional[int] = None,
) -> Optional[dict]:
    if not price or not rent_mid:
        return None

    ltv = settings.mortgage_ltv if ltv is None else max(0.0, min(0.95, ltv))
    rate = settings.mortgage_rate if rate is None else max(0.0, rate)
    term_years = settings.mortgage_term_years if term_years is None else max(1, term_years)

    # --- Acquisition costs ---
    imt_val = imt(price)
    stamp = round(price * settings.stamp_duty_rate, 2)
    notary = settings.notary_registration_eur
    furnishing = float(furnishing_cost(typology))
    acquisition_costs = round(imt_val + stamp + notary + furnishing, 2)
    total_investment = round(price + acquisition_costs, 2)

    # --- Income & yields ---
    annual_rent = rent_mid * 12
    imi = round(price * settings.imi_rate, 2)               # annual, proxy on price
    opex = round(annual_rent * settings.operating_cost_pct, 2)  # vacancy/maintenance/mgmt/condo
    operating_costs = round(imi + opex, 2)
    noi = round(annual_rent - operating_costs, 2)           # net operating income
    gross_yield = round(annual_rent / total_investment * 100, 2)
    net_yield = round(noi / total_investment * 100, 2)

    # --- Short-term rental (Alojamento Local) scenario ---
    al_mult = al_multiplier(typology)
    al_annual_gross = round(annual_rent * al_mult, 2)
    al_opex = round(al_annual_gross * settings.al_operating_cost_pct, 2)
    al_noi = round(al_annual_gross - al_opex - imi, 2)
    al_gross_yield = round(al_annual_gross / total_investment * 100, 2)
    al_net_yield = round(al_noi / total_investment * 100, 2)

    # --- Mortgage scenario ---
    loan = round(price * ltv, 2)
    down_payment = round(price - loan, 2)
    cash_needed = round(down_payment + acquisition_costs, 2)
    mpay = monthly_payment(loan, rate, term_years)
    annual_debt = round(mpay * 12, 2)
    annual_cashflow = round(noi - annual_debt, 2)
    cash_on_cash = round(annual_cashflow / cash_needed * 100, 2) if cash_needed else None

    return {
        "price": price,
        "acquisition": {
            "imt": imt_val, "stamp_duty": stamp, "notary_registration": notary,
            "furnishing": furnishing, "total_costs": acquisition_costs,
            "total_investment": total_investment,
        },
        "income": {
            "rent_mid": rent_mid, "annual_rent": annual_rent, "imi": imi, "opex": opex,
            "operating_costs": operating_costs, "noi": noi,
            "gross_yield": gross_yield, "net_yield": net_yield,
        },
        "al": {
            "multiplier": al_mult,
            "monthly_gross": round(al_annual_gross / 12, 2),
            "annual_gross": al_annual_gross,
            "opex": al_opex, "opex_pct": round(settings.al_operating_cost_pct * 100),
            "noi": al_noi, "gross_yield": al_gross_yield, "net_yield": al_net_yield,
        },
        "mortgage": {
            "ltv_pct": round(ltv * 100, 1), "rate_pct": round(rate * 100, 2),
            "term_years": term_years, "loan": loan, "down_payment": down_payment,
            "cash_needed": cash_needed, "monthly_payment": mpay,
            "annual_debt_service": annual_debt, "annual_cashflow": annual_cashflow,
            "monthly_cashflow": round(annual_cashflow / 12, 2), "cash_on_cash": cash_on_cash,
        },
    }
