"""Command line: ``python -m app.monitoring <command>`` (inside Docker: ``docker compose --profile
tools run --rm data-tools python -m app.monitoring ...``).

  replay   [--shipment ID ...] [--limit N]   causal replay of imported shipments (recorded receipt times)
  demo-ocean [--source SHIPMENT_ID]          ocean coverage demonstration on a new demo shipment
  summary  [--as-of ISO]                     monitoring summary

These are the only paths that use recorded (trusted) receipt times; the HTTP API always uses
the server clock (C-09).
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Shipment
from app.db.session import get_sessionmaker
from app.services.demo import format_report, run_ocean_demo
from app.services.detection import replay_shipment
from app.services.queries import monitoring_summary


def cmd_replay(args: argparse.Namespace) -> int:
    session = get_sessionmaker()()
    started = time.monotonic()
    try:
        ids = (
            args.shipment
            or session.scalars(
                select(Shipment.shipment_id)
                .where(Shipment.source_dataset_id.is_not(None))
                .order_by(Shipment.shipment_id)
            ).all()
        )
        if args.limit:
            ids = ids[: args.limit]
        totals = {
            "replayed": 0,
            "already_evaluated": 0,
            "evaluations": 0,
            "incidents_opened": 0,
            "incident_revisions": 0,
        }
        for sid in ids:
            for res in replay_shipment(session, sid):
                totals[res.status] += 1
                totals["evaluations"] += res.evaluations
                totals["incidents_opened"] += res.incidents_opened
                totals["incident_revisions"] += res.incident_revisions
            session.commit()
        print(
            f"shipments: {len(ids)}  sensors replayed: {totals['replayed']}  "
            f"already evaluated: {totals['already_evaluated']}"
        )
        print(
            f"evaluations written: {totals['evaluations']}  incidents opened: {totals['incidents_opened']}  "
            f"incident revisions: {totals['incident_revisions']}  ({time.monotonic() - started:.1f} s)"
        )
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cmd_demo(args: argparse.Namespace) -> int:
    session = get_sessionmaker()()
    try:
        report = run_ocean_demo(session, args.source)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print("\n".join(format_report(report)))
    return 0 if report.causal_recheck_identical in (True, None) else 1


def cmd_summary(args: argparse.Namespace) -> int:
    as_of = datetime.fromisoformat(args.as_of).astimezone(UTC) if args.as_of else datetime.now(UTC)
    session = get_sessionmaker()()
    try:
        print(json.dumps(monitoring_summary(session, as_of), indent=2, default=str))
    finally:
        session.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.monitoring")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("replay", help="Causal replay of imported shipments through the baseline detector.")
    r.add_argument("--shipment", action="append", help="Shipment ID (repeatable). Default: all imported shipments.")
    r.add_argument("--limit", type=int, default=None)
    r.set_defaults(func=cmd_replay)
    d = sub.add_parser("demo-ocean", help="Ocean coverage demonstration (causal, simulated).")
    d.add_argument("--source", default=None, help="Imported shipment to copy (default: chosen from observed data).")
    d.set_defaults(func=cmd_demo)
    s = sub.add_parser("summary", help="Monitoring summary.")
    s.add_argument("--as-of", default=None)
    s.set_defaults(func=cmd_summary)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
