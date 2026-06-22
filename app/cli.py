"""Command line interface.

Commands:
    python -m app.cli import-mock [--file PATH]
    python -m app.cli import-apify [--url URL ...] [--max-items N]
    python -m app.cli recalculate-scores
    python -m app.cli export-xlsx [--output PATH]
"""
import argparse
import os

from sqlmodel import Session

from app.core.logging import setup_logging
from app.db.database import engine, init_db
from app.services.export import to_xlsx
from app.services.ingest import recalculate_scores, run_areas_refresh, run_import
from app.services.notifier import Notifier
from app.services.providers.apify_idealista import ApifyIdealistaProvider
from app.services.providers.base import SearchInput
from app.services.providers.mock_provider import MockProvider
from app.services.query import query_properties
from app.services.search_areas import DEFAULT_SEARCH_AREAS


def cmd_import_mock(args) -> None:
    with Session(engine) as session:
        print(run_import(session, MockProvider(path=args.file)))


def cmd_import_apify(args) -> None:
    search = SearchInput(urls=args.url or [], max_items=args.max_items)
    with Session(engine) as session:
        print(run_import(
            session, ApifyIdealistaProvider(), search,
            deactivate_missing=args.deactivate_missing,
        ))


def cmd_refresh(args) -> None:
    with Session(engine) as session:
        print(run_areas_refresh(
            session, ApifyIdealistaProvider(), DEFAULT_SEARCH_AREAS, max_items=args.max_items,
        ))


def cmd_recalculate_scores(args) -> None:
    with Session(engine) as session:
        print({"scored": recalculate_scores(session)})


def cmd_test_alert(args) -> None:
    notifier = Notifier()
    if not notifier.is_configured():
        print(f"No alert channel configured (channel={notifier.channel}). Set Telegram/SMTP in .env.")
        return
    notifier.send("✅ Test alert from Porto Investment Finder", subject="Test alert")
    print("test alert sent via", notifier.channel)


def cmd_export_xlsx(args) -> None:
    with Session(engine) as session:
        results = query_properties(session, sort="score_desc", limit=5000)
        data = to_xlsx(results)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as fh:
        fh.write(data)
    print(f"wrote {args.output} ({len(data)} bytes, {len(results)} rows)")


def main() -> None:
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(prog="idealista")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import-mock", help="Import listings from the mock JSON file")
    p.add_argument("--file", help="Path to mock JSON file")
    p.set_defaults(func=cmd_import_mock)

    p = sub.add_parser("import-apify", help="Import listings via the Apify actor")
    p.add_argument("--url", action="append", help="Idealista search URL (repeatable)")
    p.add_argument("--max-items", type=int)
    p.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Full refresh: mark listings not returned by this run as inactive",
    )
    p.set_defaults(func=cmd_import_apify)

    p = sub.add_parser(
        "refresh", help="Full Grande Porto refresh: all default areas + deactivate missing"
    )
    p.add_argument("--max-items", type=int, default=100, help="Max results per area")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("recalculate-scores", help="Recompute benchmarks and scores")
    p.set_defaults(func=cmd_recalculate_scores)

    p = sub.add_parser("test-alert", help="Send a test alert via the configured channel")
    p.set_defaults(func=cmd_test_alert)

    p = sub.add_parser("export-xlsx", help="Export properties to an XLSX file")
    p.add_argument("--output", default="exports/properties.xlsx")
    p.set_defaults(func=cmd_export_xlsx)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
