"""Heuristic 'expert' commentary for a property: what's interesting and for whom.

Derived from the metrics we already compute (yield, price vs area median, metro
walk time, condition, risk/bonus flags). Deterministic, no external API.
"""
from typing import Optional


def _f1(x: float) -> str:
    return f"{x:.1f}"


def _f0(x: float) -> str:
    return f"{x:.0f}"


def expert_note(data: dict, explanation: Optional[dict]) -> Optional[dict]:
    expl = explanation or {}
    risks = set(expl.get("risk_flags") or [])
    bonuses = set(expl.get("bonus_flags") or [])
    median = expl.get("median_price_per_m2_benchmark")

    yld = data.get("gross_yield_percent")
    ppm2 = data.get("price_per_m2")
    walk = data.get("walking_minutes_to_metro_estimate")
    station = data.get("nearest_metro_station")
    typ = (data.get("typology") or "").upper()
    needs_reno = "needs_renovation" in risks
    cheap = bool(ppm2 and median and ppm2 < median)

    pros: list[str] = []
    cons: list[str] = []
    audience: list[str] = []

    if yld is not None:
        if yld >= 6.5:
            pros.append(f"высокая доходность ~{_f1(yld)}%")
            audience.append("инвесторов под аренду")
        elif yld >= 5:
            pros.append(f"доходность ~{_f1(yld)}% — на уровне рынка")
        else:
            cons.append(f"невысокая доходность ~{_f1(yld)}%")

    if ppm2 and median:
        diff = (ppm2 / median - 1) * 100
        if diff <= -10:
            pros.append(f"цена на {_f0(abs(diff))}% ниже медианы района")
            audience.append("охотников за сделками ниже рынка")
        elif diff >= 12:
            cons.append(f"цена на {_f0(diff)}% выше медианы района")

    if walk is not None and station:
        if walk <= 10:
            pros.append(f"{_f0(walk)} мин пешком до метро {station}")
        elif walk >= 25:
            cons.append(f"далеко от метро (~{_f0(walk)} мин пешком)")

    if needs_reno:
        pros.append("требует ремонта — потенциал роста стоимости")
        audience.append("покупателей под ремонт и перепродажу (флиппинг)")
    elif data.get("condition") == "new":
        pros.append("новое / в отличном состоянии")

    if data.get("has_elevator"):
        pros.append("есть лифт")
    if data.get("has_garage"):
        pros.append("есть гараж")
    if data.get("has_terrace"):
        pros.append("терраса")
    if "south_facing" in bonuses:
        pros.append("окна на юг — больше солнца")
    if data.get("price_drop_percent"):
        pros.append(f"продавец снизил цену на {_f1(data['price_drop_percent'])}%")

    if "basement" in risks:
        cons.append("полуподвал / цоколь")
    if "ground_floor" in risks:
        cons.append("первый этаж")
    if "bad_neighborhood" in risks:
        cons.append("спорный район — проверь окружение")
    if not data.get("exact_location"):
        cons.append("точный адрес скрыт — локация приблизительная")

    if typ in ("T0", "T1"):
        audience.append("сдачи студентам и молодым специалистам")
    elif typ in ("T3", "T4", "T5"):
        audience.append("семей")

    al = bool(data.get("has_al_license"))
    if al:
        pros.insert(0, "действующая AL-лицензия — готовый бизнес под краткосрочную аренду (новые AL в Порту во многих зонах заморожены)")
        audience.insert(0, "инвесторов под краткосрочную аренду / Airbnb")

    score = data.get("total_score") or 0
    if al:
        verdict = "Готовый AL-бизнес — под краткосрочную аренду"
    elif needs_reno and cheap:
        verdict = "Value-add: под ремонт и рост стоимости"
    elif yld is not None and yld >= 6.5:
        verdict = "Инвестиционно привлекателен — под аренду"
    elif score >= 65:
        verdict = "Сильный сбалансированный вариант"
    elif cons and not pros:
        verdict = "На любителя — есть нюансы"
    else:
        verdict = "Умеренно интересный вариант"

    if not audience:
        audience.append("широкого круга покупателей")
    seen: set = set()
    aud: list[str] = []
    for a in audience:
        if a not in seen:
            seen.add(a)
            aud.append(a)

    return {
        "verdict": verdict,
        "pros": pros,
        "cons": cons,
        "audience": "Кому подойдёт: " + ", ".join(aud[:3]) + ".",
    }
