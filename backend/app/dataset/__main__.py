"""CLI for dataset import.

  python -m app.dataset verify <dataset_dir>   check files against manifest.json (no database)
  python -m app.dataset import <dataset_dir>   verify, then import (idempotent, all-or-nothing)
  python -m app.dataset status                 list imported datasets with stored row counts

Inside Docker: ``docker compose --profile tools run --rm data-tools python -m app.dataset import
data/release/coldchain-sim-v1.0.0-seed11``.
"""

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import select

from app.dataset.importer import DatasetConflictError, PolicyMismatchError, import_dataset, stored_counts
from app.dataset.manifest import DatasetIntegrityError, load_and_verify
from app.db.models import DatasetRelease
from app.db.session import get_sessionmaker


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        ds = load_and_verify(Path(args.dataset_dir))
    except DatasetIntegrityError as exc:
        print(f"VERIFY FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"OK  {ds.dataset_id}  fingerprint {ds.manifest['dataset_fingerprint']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    started = time.monotonic()
    session = get_sessionmaker()()
    try:
        report = import_dataset(session, Path(args.dataset_dir))
        session.commit()
    except (DatasetIntegrityError, DatasetConflictError, PolicyMismatchError) as exc:
        session.rollback()
        print(f"IMPORT FAILED (nothing was written): {exc}", file=sys.stderr)
        return 1
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    for line in report.lines():
        print(line)
    print(f"elapsed      {time.monotonic() - started:.1f} s")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    session = get_sessionmaker()()
    try:
        releases = session.scalars(select(DatasetRelease).order_by(DatasetRelease.imported_at)).all()
        if not releases:
            print("No dataset imported.")
        for rel in releases:
            print(f"{rel.dataset_id}  seed={rel.seed}  journeys={rel.journey_count}  "
                  f"imported_at={rel.imported_at.isoformat()}  fingerprint={rel.dataset_fingerprint}")
            for table, count in stored_counts(session, rel.dataset_id).items():
                print(f"  {table:<26} {count:>8}")
    finally:
        session.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.dataset")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("dataset_dir")
    v.set_defaults(func=cmd_verify)
    i = sub.add_parser("import")
    i.add_argument("dataset_dir")
    i.set_defaults(func=cmd_import)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
