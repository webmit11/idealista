"""Build a detailed, human-readable explanation of a property's score.

Works from the serialized property dict + the score's explanation_json (already
contains component scores, weights, contributions, benchmark, flags). Text is in
Russian, matching how the rest of the dashboard surfaces explanations.
"""
from typing import Optional

from app.services.scoring import RISK_PENALTIES

COMPONENT_ORDER = [
    "price", "metro", "liquidity", "rental_yield", "condition", "elevator_garage", "discount",
]
COMPONENT_LABELS = {
    "price": "Цена vs локальная медиана €/м²",
    "metro": "Близость к метро",
    "liquidity": "Ликвидность типологии",
    "rental_yield": "Арендная доходность",
    "condition": "Состояние",
    "elevator_garage": "Лифт / гараж",
    "discount": "Снижение цены / торг",
}
RISK_LABELS = {
    "missing_coordinates": "Нет координат",
    "missing_area": "Не указана площадь",
    "basement": "Подвал / цоколь",
    "ground_floor": "Первый этаж (рés-do-chão)",
    "no_elevator_high_floor": "Высокий этаж без лифта",
    "suspicious_low_price": "Подозрительно низкая цена/м² (риск плохих данных/проблем)",
    "legal_or_occupancy_risk": "Юр. риск: занято / арендовано / без лицензии",
    "needs_renovation": "Требует ремонта",
    "insufficient_condition_data": "Мало данных о состоянии",
    "bad_neighborhood": "Плохой / социальный район",
}
BONUS_LABELS = {"south_facing": "Окна на юг"}


def _price_detail(p, e) -> str:
    ppm2 = e.get("price_per_m2")
    med = e.get("median_price_per_m2_benchmark")
    if not ppm2 or not med:
        return "Нет надёжного бенчмарка по району/типологии — нейтральная оценка (50)."
    diff = (1 - ppm2 / med) * 100
    side = "дешевле" if diff >= 0 else "дороже"
    return f"{ppm2:.0f} €/м² при локальной медиане {med:.0f} €/м² → на {abs(diff):.0f}% {side} рынка."


def _metro_detail(p, e) -> str:
    st, d = p.get("nearest_metro_station"), p.get("distance_to_metro_m")
    if d is None:
        return "Координаты неизвестны — расстояние до метро не определено (0)."
    s = f"до «{st}» ~{d:.0f} м"
    if e.get("metro_reduced_for_approx_location"):
        s += "; адрес приблизительный → вклад метро снижен ×0.7"
    return s + "."


def _liquidity_detail(p, e) -> str:
    notes = {"T2": "самый ходовой формат", "T1": "высокий спрос на аренду",
             "T3": "хорошая ликвидность", "T0": "студия — ниже спрос", "T4": "крупные — менее ликвидны"}
    t = p.get("typology") or "—"
    return f"{t} — {notes.get(t, 'оценка по ликвидности типологии')}."


def _yield_detail(p, e) -> str:
    y = p.get("gross_yield_percent")
    rent = p.get("rental_estimate_mid")
    if y is None:
        return "Недостаточно данных для оценки доходности."
    return f"оценка аренды ~{rent:.0f} €/мес → валовая доходность {y:.1f}%."


def _condition_detail(p, e) -> str:
    return f"состояние: {p.get('condition') or 'неизвестно'}."


def _eg_detail(p, e) -> str:
    parts = ["лифт есть" if p.get("has_elevator") else "лифта нет",
             "гараж есть" if p.get("has_garage") else "гаража нет"]
    return ", ".join(parts) + "."


def _discount_detail(p, e) -> str:
    d = p.get("price_drop_percent")
    if d:
        return f"цена снижалась на {d:.1f}% → есть сигнал к торгу."
    return "снижений цены не зафиксировано → базовые баллы за потенциал торга."


_DETAIL_FNS = {
    "price": _price_detail, "metro": _metro_detail, "liquidity": _liquidity_detail,
    "rental_yield": _yield_detail, "condition": _condition_detail,
    "elevator_garage": _eg_detail, "discount": _discount_detail,
}


def explain_score(p: dict, explanation: Optional[dict]) -> Optional[dict]:
    if not explanation:
        return None
    cs = explanation.get("component_scores") or {}
    wc = explanation.get("weighted_contributions") or {}
    w = explanation.get("weights") or {}

    components = [
        {
            "label": COMPONENT_LABELS[k],
            "raw": cs.get(k),
            "weight": w.get(k),
            "contribution": wc.get(k),
            "detail": _DETAIL_FNS[k](p, explanation),
        }
        for k in COMPONENT_ORDER
    ]
    risks = [
        {"label": RISK_LABELS.get(f, f), "penalty": RISK_PENALTIES.get(f, 0)}
        for f in (explanation.get("risk_flags") or [])
    ]
    bonuses = [{"label": BONUS_LABELS.get(f, f)} for f in (explanation.get("bonus_flags") or [])]

    return {
        "components": components,
        "risks": risks,
        "bonuses": bonuses,
        "positive_subtotal": explanation.get("positive_subtotal"),
        "risk_penalty": explanation.get("risk_penalty"),
        "bonus_points": explanation.get("bonus_points") or 0,
        "total": p.get("total_score"),
    }
