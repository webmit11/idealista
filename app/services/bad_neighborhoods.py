"""Blocklist of problematic / social-housing neighbourhoods (Porto area).

To avoid street-name false positives (e.g. "Rua do Outeiro", a surname like
"Manuel Regado"), bairro names are matched ONLY against a listing's zona
(`district`) and parish — never the free-text address. Explicit social-housing
phrases are matched against the listing text.

These are well-known social housing complexes (public knowledge); a whole bairro
is not uniformly bad, so review/curate for your strategy. Add your own bairro
names via the BAD_NEIGHBORHOODS env var (comma/newline separated).
"""
from app.core.config import settings

# Bairro names -> matched against zona (district) + parish only.
DEFAULT_ZONE_KEYWORDS: list[str] = [
    "aleixo",
    "pasteleira",
    "lagarteiro",
    "cerco",            # Bairro do Cerco (Campanhã)
    "falcão", "falcao",  # Bairro do Falcão (Campanhã / Gondomar)
    "pinheiro torres",
    "fonte da moura",
    "agra do amial",
    "regado",
    "são joão de deus", "sao joao de deus",
    "carriçal", "carrical",
    "biquinha",         # Matosinhos
]

# Explicit social-housing mentions -> matched against the full listing text.
DEFAULT_TEXT_PHRASES: list[str] = [
    "bairro social",
    "habitação social", "habitacao social",
    "habitação municipal", "habitacao municipal",
]


def get_zone_keywords() -> list[str]:
    extra = [
        c.strip().lower()
        for c in (settings.bad_neighborhoods or "").replace("\n", ",").split(",")
        if c.strip()
    ]
    return list(dict.fromkeys(DEFAULT_ZONE_KEYWORDS + extra))


def get_text_phrases() -> list[str]:
    return list(DEFAULT_TEXT_PHRASES)
