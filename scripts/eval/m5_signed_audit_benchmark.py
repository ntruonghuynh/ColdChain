"""Measure append/commit and verification time for the M5 signed DB audit log.

Run against a disposable migrated PostgreSQL database with AUDIT_SIGNING_KEY set:
  PYTHONPATH=backend POSTGRES_DB=coldchain_m5_test python scripts/eval/m5_signed_audit_benchmark.py
"""

import argparse
import json
import statistics
import time
import uuid
from pathlib import Path

from app.db.session import get_sessionmaker
from app.integrations.audit_log import append_audit_entry, verify_audit_log


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, int((q * len(ordered) + 0.999999)) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path,
                        default=Path("docs/milestones/m5/raw/signed-audit-benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.samples <= 1000:
        parser.error("--samples must be in [1, 1000]")

    run_id = uuid.uuid4().hex
    session = get_sessionmaker()()
    append_ms: list[float] = []
    try:
        for index in range(args.samples):
            started = time.perf_counter()
            append_audit_entry(
                session,
                business_ref=f"m5-audit-benchmark:{run_id}:{index}",
                actor_user_id=None,
                actor_org_id="ORG-PLATFORM",
                action="M5_BENCHMARK_EVENT",
                record={"sample": index, "run_id": run_id, "payload_sha256": "0" * 64},
            )
            session.commit()
            append_ms.append((time.perf_counter() - started) * 1000)

        verify_started = time.perf_counter()
        verification = verify_audit_log(session)
        verify_ms = (time.perf_counter() - verify_started) * 1000
        if not verification["valid"]:
            raise RuntimeError(f"signed audit verification failed: {verification['errors']}")
        output = {
            "benchmark": "m5-signed-audit-append-and-verify",
            "run_id": run_id,
            "database": "disposable local PostgreSQL; no chain operations",
            "sample_count": len(append_ms),
            "units": "milliseconds",
            "accepted": len(append_ms),
            "rejected": 0,
            "append_commit_p50": statistics.median(append_ms),
            "append_commit_p95": percentile(append_ms, 0.95),
            "append_commit_min": min(append_ms),
            "append_commit_max": max(append_ms),
            "append_commit_timings": append_ms,
            "verify_ms": verify_ms,
            "entries_verified": verification["entries_checked"],
            "verification_valid": verification["valid"],
            "note": "Wall time includes local PostgreSQL commit, canonical JSON hashing, HMAC key derivation and Ed25519 signing; same-process test environment, not production capacity data.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
