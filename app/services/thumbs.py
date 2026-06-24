"""Local image cache (thumbnails + gallery).

Idealista image URLs are signed and expire in ~24h, but scraping runs every few
days, so listing photos go blank between runs. We download images once to the
mounted ./data volume and serve them from our own domain, where they never
expire. Image 0 is stored as ``{id}.jpg`` (the thumbnail); the rest of the
gallery as ``{id}_{n}.jpg``. Everything is best-effort and disk-guarded: a failed
or disk-starved download just falls back to a placeholder.
"""
import concurrent.futures
import logging
import os
import shutil
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("thumbs")


def path_for(pid: int) -> str:
    return os.path.join(settings.thumb_cache_dir, f"{pid}.jpg")


def gallery_path_for(pid: int, n: int) -> str:
    return os.path.join(settings.thumb_cache_dir, f"{pid}_{n}.jpg")


def _is_file(path: str) -> bool:
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def is_cached(pid: int) -> bool:
    return _is_file(path_for(pid))


def is_gallery_cached(pid: int, n: int) -> bool:
    return _is_file(gallery_path_for(pid, n))


def _free_mb() -> float:
    try:
        return shutil.disk_usage(settings.thumb_cache_dir).free / 1e6
    except OSError:
        return 1e9  # dir not created yet -> allow (makedirs happens below)


def _download_to(path: str, url: Optional[str]) -> bool:
    if not url:
        return False
    if _free_mb() < settings.min_free_disk_mb:  # disk safety: never fill the volume
        return False
    try:
        os.makedirs(settings.thumb_cache_dir, exist_ok=True)
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
        if not data:
            return False
        tmp = path + ".tmp"
        with open(tmp, "wb") as out:
            out.write(data)
        os.replace(tmp, path)
        return True
    except Exception:
        logger.debug("image download failed: %s", path)
        return False


def download(pid: int, url: Optional[str]) -> bool:
    return _download_to(path_for(pid), url)


def download_gallery(pid: int, n: int, url: Optional[str]) -> bool:
    return _download_to(gallery_path_for(pid, n), url)


def cache_missing(session, limit: int = 200000) -> int:
    """Download not-yet-cached thumbnails + gallery for active listings (fresh URLs)."""
    from sqlmodel import select

    from app.db.models import Property

    rows = session.exec(
        select(Property.id, Property.thumbnail_url, Property.image_urls).where(
            Property.is_active == True  # noqa: E712
        )
    ).all()
    cap = settings.gallery_cache_max
    tasks = []  # (path, url)
    for pid, thumb, urls in rows:
        if thumb and not is_cached(pid):
            tasks.append((path_for(pid), thumb))
        if urls:
            start = 1 if thumb else 0  # image 0 is the thumbnail when present
            for n in range(start, min(len(urls), cap)):
                if not is_gallery_cached(pid, n):
                    tasks.append((gallery_path_for(pid, n), urls[n]))
    tasks = tasks[:limit]
    if not tasks:
        return 0
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ok in pool.map(lambda t: _download_to(t[0], t[1]), tasks):
            if ok:
                done += 1
    logger.info("thumbs: cached %s images (%s tasks)", done, len(tasks))
    return done
