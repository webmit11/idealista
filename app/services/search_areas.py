"""Default Grande Porto search areas (concelho name + Idealista search URL).

Each tuple is (municipality_hint, search_url). The hint tags every listing from
that URL with the concelho; the listing's own locality becomes the parish (see
`ApifyIdealistaProvider._normalize`).

Big concelhos exceed the actor's per-URL cap, which would block delisting for
them. So each concelho is split into PRICE BANDS — every band stays under the cap,
so the union fully covers the concelho and delisting stays accurate. The refresh
accumulates all bands of a concelho into one area (shared hint). Bands overlap
slightly at boundaries (Idealista price filters are inclusive) — harmless, since
listings de-dupe by id.

Filters: sale, T1-T3, FULL price range (no ceiling) — fine bands in the dense
mid-range keep every URL under the cap; high bands add the premium segment.
Matosinhos covers Senhora da Hora; Gondomar covers Rio Tinto; Gaia is line D.
"""

_BASE = "https://www.idealista.pt/comprar-casas"
_SUFFIX = "t1,t2,t3"

# (municipality_hint, Idealista concelho slug)
_CONCELHOS = [
    ("Porto", "porto"),
    ("Maia", "maia"),
    ("Matosinhos", "matosinhos"),
    ("Gondomar", "gondomar"),
    ("Vila Nova de Gaia", "vila-nova-de-gaia"),
]

# Price bands (the comma-joined filter segment after `com-`). `apartamentos`
# keeps only apartments (no houses/moradias) — also frees ~18% of the per-URL cap.
_PRICE_BANDS = [
    f"com-apartamentos,preco-max_150000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_150000,preco-max_200000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_200000,preco-max_250000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_250000,preco-max_300000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_300000,preco-max_375000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_375000,preco-max_500000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_500000,preco-max_750000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_750000,{_SUFFIX}",
]

DEFAULT_SEARCH_AREAS: list[tuple[str, str]] = [
    (label, f"{_BASE}/{slug}/{band}/")
    for label, slug in _CONCELHOS
    for band in _PRICE_BANDS
]
