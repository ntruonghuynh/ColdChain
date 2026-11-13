"""CLI: ``python -m app.seed`` loads reference data. Run after ``alembic upgrade head``."""

import sys

from app.db.session import get_sessionmaker
from app.seed.loader import SeedConflictError, run_seed


def main() -> int:
    session = get_sessionmaker()()
    try:
        report = run_seed(session)
    except SeedConflictError as exc:
        session.rollback()
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()
    print(f"Seed complete: {len(report.created)} created, {len(report.unchanged)} unchanged.")
    for item in report.created:
        print(f"  created   {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
