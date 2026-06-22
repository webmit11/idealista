"""Daily import job entrypoint.

Usage:
    python -m app.jobs.daily_import --provider mock
    python -m app.jobs.daily_import --provider apify --url "<idealista search url>"
"""
import argparse

from sqlmodel import Session

from app.core.logging import setup_logging
from app.db.database import engine, init_db
from app.services.ingest import run_import
from app.services.providers.apify_idealista import ApifyIdealistaProvider
from app.services.providers.base import SearchInput
from app.services.providers.mock_provider import MockProvider


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Daily property import job")
    parser.add_argument("--provider", choices=["mock", "apify"], default="mock")
    parser.add_argument("--file", help="Path to mock JSON file (mock provider)")
    parser.add_argument(
        "--url", action="append", help="Idealista search URL (apify; repeatable)"
    )
    parser.add_argument("--max-items", type=int, help="Max items to fetch (apify)")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Full refresh: mark listings not seen in this run as inactive",
    )
    args = parser.parse_args()

    init_db()

    if args.provider == "mock":
        provider = MockProvider(path=args.file)
        search = None
    else:
        provider = ApifyIdealistaProvider()
        search = SearchInput(urls=args.url or [], max_items=args.max_items)

    with Session(engine) as session:
        stats = run_import(session, provider, search, deactivate_missing=args.deactivate_missing)
    print(stats)


if __name__ == "__main__":
    main()
