"""Reference data for Metro do Porto stations.

NOTE: Coordinates are approximate (hand-curated to ~3 decimal places) and are
good enough for haversine-based proximity scoring in this MVP. For production,
replace them with the official Metro do Porto GTFS feed / OpenStreetMap data.
See README ("How to add new metro stations").
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MetroStation:
    name: str
    latitude: float
    longitude: float
    lines: tuple[str, ...] = ()
    municipality: str = ""


# (name, lat, lon, lines, municipality)
_STATIONS: list[tuple[str, float, float, tuple[str, ...], str]] = [
    # --- Central Porto ---
    ("Trindade", 41.1519, -8.6093, ("A", "B", "C", "E", "F"), "Porto"),
    ("Aliados", 41.1486, -8.6109, ("D",), "Porto"),
    ("São Bento", 41.1457, -8.6107, ("D",), "Porto"),
    ("Bolhão", 41.1503, -8.6072, ("A", "B", "C", "E", "F"), "Porto"),
    ("Campo 24 de Agosto", 41.1480, -8.5985, ("A", "B", "C", "E", "F"), "Porto"),
    ("Heroísmo", 41.1472, -8.5916, ("A", "B", "C", "E", "F"), "Porto"),
    ("Campanhã", 41.1485, -8.5852, ("A", "B", "C", "E", "F"), "Porto"),
    ("Estádio do Dragão", 41.1620, -8.5836, ("A", "B", "E", "F"), "Porto"),
    ("Contumil", 41.1626, -8.5806, ("B",), "Porto"),
    ("Marquês", 41.1606, -8.6041, ("C",), "Porto"),
    ("Faria Guimarães", 41.1599, -8.6079, ("C",), "Porto"),
    ("Salgueiros", 41.1689, -8.6047, ("C", "D"), "Porto"),
    ("Combatentes", 41.1731, -8.6041, ("C", "D"), "Porto"),
    ("Pólo Universitário", 41.1781, -8.6010, ("D",), "Porto"),
    ("IPO", 41.1830, -8.6010, ("D",), "Porto"),
    ("Hospital São João", 41.1860, -8.6010, ("D",), "Porto"),
    ("Lapa", 41.1560, -8.6140, ("A", "B", "C", "E", "F"), "Porto"),
    ("Carolina Michaëlis", 41.1610, -8.6190, ("A", "B", "C", "E", "F"), "Porto"),
    ("Casa da Música", 41.1588, -8.6300, ("A", "B", "C", "E", "F"), "Porto"),
    ("Francos", 41.1645, -8.6420, ("A", "B", "C", "E", "F"), "Porto"),
    ("Viso", 41.1742, -8.6470, ("A", "B", "C", "E", "F"), "Porto"),
    ("Ramalde", 41.1718, -8.6360, ("A", "B", "C", "E", "F"), "Porto"),

    # --- Gondomar branch (line F towards Fânzeres) ---
    ("Nasoni", 41.1719, -8.5717, ("F",), "Porto"),
    ("Levada", 41.1740, -8.5640, ("F",), "Gondomar"),
    ("Rio Tinto", 41.1796, -8.5560, ("F",), "Gondomar"),
    ("Campainha", 41.1850, -8.5460, ("F",), "Gondomar"),
    ("Baguim", 41.1900, -8.5360, ("F",), "Gondomar"),
    ("Fânzeres", 41.1900, -8.5250, ("F",), "Gondomar"),

    # --- Matosinhos / Senhora da Hora ---
    ("Senhora da Hora", 41.1862, -8.6555, ("A", "B", "C"), "Matosinhos"),
    ("Sete Bicas", 41.1840, -8.6680, ("A",), "Matosinhos"),
    ("Fonte do Cuco", 41.1880, -8.6740, ("A",), "Matosinhos"),
    ("Câmara de Matosinhos", 41.1860, -8.6930, ("A",), "Matosinhos"),
    ("Matosinhos Sul", 41.1812, -8.6962, ("A",), "Matosinhos"),

    # --- Maia (line C towards ISMAI / Trofa) ---
    ("Vasco da Gama", 41.2070, -8.6480, ("C",), "Maia"),
    ("Parque Maia", 41.2330, -8.6190, ("C",), "Maia"),
    ("Fórum Maia", 41.2350, -8.6210, ("C",), "Maia"),
    ("Castêlo da Maia", 41.2560, -8.6230, ("C",), "Maia"),
    ("ISMAI", 41.2700, -8.6280, ("C",), "Maia"),

    # --- Airport line (E) ---
    ("Aeroporto", 41.2400, -8.6700, ("E",), "Maia"),

    # --- Vila Nova de Gaia (line D, south of the Douro) ---
    ("Jardim do Morro", 41.1377, -8.6090, ("D",), "Vila Nova de Gaia"),
    ("General Torres", 41.1265, -8.6105, ("D",), "Vila Nova de Gaia"),
    ("Câmara de Gaia", 41.1230, -8.6098, ("D",), "Vila Nova de Gaia"),
    ("Joaquim Sampaio", 41.1193, -8.6082, ("D",), "Vila Nova de Gaia"),
    ("João de Deus (Gaia)", 41.1148, -8.6045, ("D",), "Vila Nova de Gaia"),
    ("D. João II", 41.1110, -8.6010, ("D",), "Vila Nova de Gaia"),
    ("Santo Ovídio", 41.1042, -8.6008, ("D",), "Vila Nova de Gaia"),
    ("Vila d'Este", 41.0905, -8.6045, ("D",), "Vila Nova de Gaia"),

    # --- Póvoa line (B) ---
    ("Varziela", 41.2950, -8.7180, ("B",), "Vila do Conde"),
    ("Mindelo", 41.3120, -8.7280, ("B",), "Vila do Conde"),
    ("Azurara", 41.3430, -8.7390, ("B",), "Vila do Conde"),
    ("Vila do Conde", 41.3530, -8.7440, ("B",), "Vila do Conde"),
    ("Póvoa de Varzim", 41.3830, -8.7660, ("B",), "Póvoa de Varzim"),
]

METRO_STATIONS: list[MetroStation] = [MetroStation(*s) for s in _STATIONS]


def get_stations() -> list[MetroStation]:
    return METRO_STATIONS
