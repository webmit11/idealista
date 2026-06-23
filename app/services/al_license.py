"""Detect a short-term-rental (Alojamento Local) licence mention in listing text.

Heuristic over the ad's own description/title (Portuguese + English phrasings).
It flags ads that state an AL licence; it is NOT a check against the official
RNAL registry, so it can miss or over-report.
"""
import re

_AL_RE = re.compile(
    r"alojamento\s+local"
    r"|short[-\s]?term\s+rental\s+licen"
    r"|local\s+accommodation\s+licen"
    r"|\bAL\s+licen"
    r"|tourist\s+licen"
    r"|holiday[-\s]?rental\s+licen"
    r"|registo.{0,8}\bal\b"
    r"|\brnal\b"
    r"|licen[cç]a.{0,12}\bal\b",
    re.IGNORECASE | re.DOTALL,
)


def detect_al_license(*texts) -> bool:
    blob = " ".join(t for t in texts if t)
    return bool(_AL_RE.search(blob))
