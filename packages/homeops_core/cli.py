"""Command line entry point for local HomeOps operations.

    python -m homeops_core.cli seed     # load the fictional demo records
    python -m homeops_core.cli reset    # wipe and re-seed the local database
    python -m homeops_core.cli status   # show what is stored
    python -m homeops_core.cli init-db  # create the schema only

The ``homeops`` console script runs the same commands.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigurationError, get_settings
from .seed import SeedError, database_status, seed_database


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homeops", description="HomeOps local data management (fictional demo data only)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Load the fictional demo seed into the local database.")
    seed.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep existing rows instead of recreating the database first.",
    )

    sub.add_parser("reset", help="Delete the local database and re-create it from the seed.")
    sub.add_parser("init-db", help="Create the database schema without loading any data.")
    sub.add_parser("status", help="Print a summary of the local database.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "seed":
            counts = seed_database(settings, reset=not args.no_reset)
            _print({"action": "seed", "database": str(settings.db_path), "loaded": counts})
            return 0

        if args.command == "reset":
            counts = seed_database(settings, reset=True)
            _print({"action": "reset", "database": str(settings.db_path), "loaded": counts})
            return 0

        if args.command == "init-db":
            from . import db

            settings.ensure_directories()
            with db.session(settings) as conn:
                db.init_schema(conn)
            _print({"action": "init-db", "database": str(settings.db_path), "schema": "created"})
            return 0

        if args.command == "status":
            _print({"action": "status", **database_status(settings)})
            return 0
    except SeedError as exc:
        print(f"Seed error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - last resort, keep the CLI readable
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
