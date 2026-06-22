"""Deal-pipeline statuses for the watchlist."""
from typing import Optional

# (value, label, css colour) — order defines the pipeline funnel order.
WATCH_STATUSES = [
    ("interested", "Интересно", "#4f8cff"),
    ("contacted", "Связался", "#3fb6c8"),
    ("viewing", "Просмотр", "#f5a623"),
    ("offer", "Оффер", "#9acd32"),
    ("bought", "Куплено", "#2fbf71"),
    ("rejected", "Отказ", "#e5534b"),
]

WATCH_VALUES = {v for v, _, _ in WATCH_STATUSES}
WATCH_LABELS = {v: label for v, label, _ in WATCH_STATUSES}
WATCH_COLORS = {v: color for v, _, color in WATCH_STATUSES}


def normalize_status(value: Optional[str]) -> Optional[str]:
    """Return a valid status, or None to clear it."""
    value = (value or "").strip()
    return value if value in WATCH_VALUES else None
