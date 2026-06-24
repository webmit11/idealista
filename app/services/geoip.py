"""IP -> country (MaxMind GeoLite2) for phone dial-code prefill and lead-origin stats.

The DB is downloaded with the configured MaxMind license key and cached on the
mounted ./data volume; it is refreshed when older than _STALE_DAYS. Everything
degrades gracefully: with no key / no DB, lookups simply return None.
"""
import io
import logging
import os
import tarfile
import time
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("geoip")

_STALE_DAYS = 30
_reader = None  # lazily-opened geoip2.database.Reader

# ISO-3166 alpha-2 -> international dialling code. Covers Europe, CIS, the
# Americas, the Gulf, and major Asia/Africa/Oceania; anything missing -> None.
DIAL_CODES = {
    # Europe
    "PT": "+351", "ES": "+34", "FR": "+33", "DE": "+49", "IT": "+39", "GB": "+44",
    "IE": "+353", "NL": "+31", "BE": "+32", "LU": "+352", "CH": "+41", "AT": "+43",
    "PL": "+48", "CZ": "+420", "SK": "+421", "HU": "+36", "RO": "+40", "BG": "+359",
    "GR": "+30", "HR": "+385", "SI": "+386", "RS": "+381", "SE": "+46", "NO": "+47",
    "DK": "+45", "FI": "+358", "IS": "+354", "EE": "+372", "LV": "+371", "LT": "+370",
    "MT": "+356", "CY": "+357", "AL": "+355", "MK": "+389", "BA": "+387", "ME": "+382",
    "MD": "+373", "AD": "+376", "MC": "+377", "LI": "+423", "SM": "+378", "GI": "+350",
    "FO": "+298", "XK": "+383",
    # CIS / Eastern
    "RU": "+7", "UA": "+380", "BY": "+375", "KZ": "+7", "GE": "+995", "AM": "+374",
    "AZ": "+994", "UZ": "+998", "KG": "+996", "TJ": "+992", "TM": "+993",
    # Middle East / Gulf / Turkey
    "TR": "+90", "AE": "+971", "SA": "+966", "QA": "+974", "KW": "+965", "BH": "+973",
    "OM": "+968", "IL": "+972", "JO": "+962", "LB": "+961", "IQ": "+964", "IR": "+98",
    # Americas
    "US": "+1", "CA": "+1", "MX": "+52", "BR": "+55", "AR": "+54", "CL": "+56",
    "CO": "+57", "PE": "+51", "UY": "+598", "PY": "+595", "BO": "+591", "EC": "+593",
    "VE": "+58", "PA": "+507", "CR": "+506", "DO": "+1", "CU": "+53", "GT": "+502",
    # Asia
    "CN": "+86", "HK": "+852", "TW": "+886", "JP": "+81", "KR": "+82", "IN": "+91",
    "PK": "+92", "BD": "+880", "LK": "+94", "TH": "+66", "VN": "+84", "ID": "+62",
    "MY": "+60", "SG": "+65", "PH": "+63", "KH": "+855", "MM": "+95", "NP": "+977",
    # Africa
    "ZA": "+27", "EG": "+20", "MA": "+212", "DZ": "+213", "TN": "+216", "NG": "+234",
    "KE": "+254", "GH": "+233", "AO": "+244", "MZ": "+258", "CV": "+238", "ET": "+251",
    "TZ": "+255", "UG": "+256", "SN": "+221", "CI": "+225",
    # Oceania
    "AU": "+61", "NZ": "+64",
}


def ensure_db() -> bool:
    """Download/refresh the GeoLite2 DB when a license key is set. Best-effort."""
    path = settings.geoip_db_path
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path) < _STALE_DAYS * 86400)
    if fresh:
        return True
    if not settings.maxmind_license_key:
        return os.path.exists(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(
                "https://download.maxmind.com/app/geoip_download",
                params={
                    "edition_id": settings.geoip_edition,
                    "license_key": settings.maxmind_license_key,
                    "suffix": "tar.gz",
                },
            )
            resp.raise_for_status()
            archive = resp.content
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            member = next((m for m in tf.getmembers() if m.name.endswith(".mmdb")), None)
            if member is None:
                logger.warning("geoip: no .mmdb inside downloaded archive")
                return os.path.exists(path)
            extracted = tf.extractfile(member)
            tmp = path + ".tmp"
            with open(tmp, "wb") as out:
                out.write(extracted.read())
            os.replace(tmp, path)
        global _reader
        if _reader is not None:
            try:
                _reader.close()
            except Exception:
                pass
            _reader = None
        logger.info("geoip: GeoLite2 DB ready")
        return True
    except Exception:
        logger.exception("geoip: DB download failed")
        return os.path.exists(path)


def _get_reader():
    global _reader
    if _reader is None:
        if not os.path.exists(settings.geoip_db_path):
            return None
        try:
            import geoip2.database

            _reader = geoip2.database.Reader(settings.geoip_db_path)
        except Exception:
            logger.exception("geoip: failed to open reader")
            return None
    return _reader


def client_ip(request) -> Optional[str]:
    """The real client IP, honouring the X-Forwarded-For set by Caddy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


def country_for_ip(ip: Optional[str]) -> Optional[str]:
    """ISO-3166 alpha-2 country code for an IP, or None."""
    if not ip:
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        return reader.country(ip).country.iso_code
    except Exception:
        return None  # private/unknown IP, lookup error


def dial_code_for_country(iso: Optional[str]) -> Optional[str]:
    return DIAL_CODES.get(iso.upper()) if iso else None


def dial_code_for_ip(ip: Optional[str]) -> Optional[str]:
    return dial_code_for_country(country_for_ip(ip))
