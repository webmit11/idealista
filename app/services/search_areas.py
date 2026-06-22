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

Filters: sale, T1-T3, price <= 400k. Matosinhos covers Senhora da Hora; Gondomar
covers Rio Tinto; Gaia is line D across the river.
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
    f"com-apartamentos,preco-max_175000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_175000,preco-max_275000,{_SUFFIX}",
    f"com-apartamentos,preco-desde_275000,preco-max_400000,{_SUFFIX}",
]

DEFAULT_SEARCH_AREAS: list[tuple[str, str]] = [
    (label, f"{_BASE}/{slug}/{band}/")
    for label, slug in _CONCELHOS
    for band in _PRICE_BANDS
]
