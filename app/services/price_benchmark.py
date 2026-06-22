"""Local price benchmarks (median €/m²).

Medians are computed in Python (not SQL percentile) so the code stays portable
across SQLite and PostgreSQL. Buckets need at least `min_samples` listings to be
trusted; otherwise lookups fall back parish -> municipality -> district ->
overall.
"""
import statistics
from collections import defaultdict
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Property


def compute_benchmarks(session: Session, min_samples: Optional[int] = None) -> dict:
    min_samples = min_samples or settings.benchmark_min_samples
    rows = session.exec(
        select(Property).where(Property.is_active == True)  # noqa: E712
    ).all()

    parish: dict = defaultdict(list)
    muni: dict = defaultdict(list)
    district: dict = defaultdict(list)
    overall: list[float] = []

    for p in rows:
        if not p.price_per_m2 or p.price_per_m2 <= 0:
            continue
        overall.append(p.price_per_m2)
        t = (p.typology or "NA").upper()
        if p.parish:
            parish[(p.parish.lower(), t)].append(p.price_per_m2)
        if p.municipality:
            muni[(p.municipality.lower(), t)].append(p.price_per_m2)
        if p.district:
            district[(p.district.lower(), t)].append(p.price_per_m2)

    def med(bucket: dict) -> dict:
        return {k: statistics.median(v) for k, v in bucket.items() if len(v) >= min_samples}

    return {
        "parish": med(parish),
        "municipality": med(muni),
        "district": med(district),
        "overall": statistics.median(overall) if overall else None,
        "min_samples": min_samples,
    }


def benchmark_for(benchmarks: dict, prop: Property) -> Optional[float]:
    t = (prop.typology or "NA").upper()
    if prop.parish:
        v = benchmarks["parish"].get((prop.parish.lower(), t))
        if v:
            return v
    if prop.municipality:
        v = benchmarks["municipality"].get((prop.municipality.lower(), t))
        if v:
            return v
    if prop.district:
        v = benchmarks["district"].get((prop.district.lower(), t))
        if v:
            return v
    return benchmarks.get("overall")
