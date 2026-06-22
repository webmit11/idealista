"""CSV / XLSX export of property rows."""
import csv
import io
from datetime import datetime
from typing import Optional

from openpyxl import Workbook

from app.db.models import Property, Score
from app.services.query import serialize

# (serialized_key, Column header)
EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("total_score", "Score"),
    ("title", "Title"),
    ("price", "Price"),
    ("price_per_m2", "EUR/m2"),
    ("typology", "Typology"),
    ("area_m2", "Area m2"),
    ("municipality", "Municipality"),
    ("parish", "Parish"),
    ("nearest_metro_station", "Nearest metro"),
    ("distance_to_metro_m", "Distance to metro (m)"),
    ("walking_minutes_to_metro_estimate", "Walk min"),
    ("rental_estimate_mid", "Est. rent (mid)"),
    ("gross_yield_percent", "Gross yield %"),
    ("price_drop_percent", "Price drop %"),
    ("has_garage", "Garage"),
    ("has_elevator", "Elevator"),
    ("risk_flags_str", "Risk flags"),
    ("url", "URL"),
    ("first_seen_at", "First seen"),
    ("last_seen_at", "Last seen"),
    ("days_on_market", "Days on market"),
    ("delisted_at", "Delisted at"),
]


def _rows(results: list[tuple[Property, Optional[Score]]]) -> list[dict]:
    rows = []
    for prop, score in results:
        data = serialize(prop, score)
        data["risk_flags_str"] = ", ".join(data.get("risk_flags") or [])
        rows.append(data)
    return rows


def _fmt(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def to_csv(results: list[tuple[Property, Optional[Score]]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for _, header in EXPORT_COLUMNS])
    for data in _rows(results):
        writer.writerow([_fmt(data.get(key)) for key, _ in EXPORT_COLUMNS])
    return buf.getvalue()


def to_xlsx(results: list[tuple[Property, Optional[Score]]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Properties"
    ws.append([header for _, header in EXPORT_COLUMNS])
    for data in _rows(results):
        ws.append([_fmt(data.get(key)) for key, _ in EXPORT_COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
