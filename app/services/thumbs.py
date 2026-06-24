"""Local thumbnail cache.

Idealista image URLs are signed and expire in ~24h, but scraping runs every few
days, so listing photos go blank between runs. We download each thumbnail once
to the mounted ./data volume and serve it from our own domain, where it never
expires. Everything is best-effort: a failed download just falls back to a
placeholder.
"""
import logging
import os
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("thumbs")


def path_for(pid: int) -> str:
    return os.path.join(settings.thumb_cache_dir, f"{pid}.jpg")


def is_cached(pid: int) -> bool:
    try:
        return os.path.getsize(path_for(pid)) > 0
    except OSError:
        return False


def download(pid: int, url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        os.makedirs(settings.thumb_cache_dir, exist_ok=True)
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
        if not data:
            return False
        tmp = path_for(pid) + ".tmp"
        with open(tmp, "wb") as out:
            out.write(data)
        os.replace(tmp, path_for(pid))
        return True
    except Exception:
        logger.debug("thumb download failed for %s", pid)
        return False


def cache_missing(session, limit: int = 5000) -> int:
    """Download thumbnails for active listings not yet cached (fresh URLs only)."""
    from sqlmodel import select

    from app.db.models import Property

    rows = session.exec(
        select(Property.id, Property.thumbnail_url).where(
            Property.is_active == True,  # noqa: E712
            Property.thumbnail_url != None,  # noqa: E711
        )
    ).all()
    cached = 0
    for pid, url in rows:
        if cached >= limit:
            break
        if is_cached(pid):
            continue
        if download(pid, url):
            cached += 1
    if cached:
        logger.info("thumbs: cached %s new thumbnails", cached)
    return cached
