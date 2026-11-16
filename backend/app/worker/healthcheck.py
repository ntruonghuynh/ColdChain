"""Docker liveness probe for the outbox relay; dependency degradation is reported separately."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

STATUS_PATH = Path(os.getenv("WORKER_STATUS_FILE", "/tmp/coldchain-worker-status.json"))
MAX_CYCLE_AGE_SECONDS = int(os.getenv("WORKER_MAX_CYCLE_AGE_SECONDS", "120"))


def inspect_status(path: Path = STATUS_PATH, now: datetime | None = None) -> tuple[bool, dict[str, object]]:
    now = now or datetime.now(UTC)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, {"status": "unhealthy", "reason": f"heartbeat_unavailable:{type(exc).__name__}"}
    pid = int(state.get("pid", -1))
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False, {"status": "unhealthy", "reason": "relay_process_not_alive", "pid": pid}

    cycle_at = (state.get("cycle_started_at") if state.get("phase") == "processing"
                else state.get("last_cycle_at")) or state.get("started_at")
    try:
        age = max(0.0, (now - datetime.fromisoformat(cycle_at)).total_seconds())
    except (TypeError, ValueError):
        return False, {"status": "unhealthy", "reason": "invalid_heartbeat_timestamp", "pid": pid}
    if age > MAX_CYCLE_AGE_SECONDS:
        return False, {"status": "unhealthy", "reason": "relay_cycle_stalled", "pid": pid,
                       "cycle": state.get("cycle", 0), "cycle_age_seconds": round(age, 1)}

    dependencies = {name: state.get(name, "unknown") for name in ("database", "chain")}
    degraded = any(value == "unavailable" for value in dependencies.values())
    return True, {
        "status": "alive_degraded" if degraded else "alive",
        "reason": "external_dependency_unavailable" if degraded else "relay_cycle_recent",
        "pid": pid,
        "cycle": state.get("cycle", 0),
        "last_result": state.get("last_result"),
        "cycle_age_seconds": round(age, 1),
        "dependencies": dependencies,
        "last_error": state.get("last_error"),
        "last_error_dependency": state.get("last_error_dependency"),
        "dependency_errors": state.get("dependency_errors", {}),
        "last_business_ref": state.get("last_business_ref"),
    }


def main() -> int:
    healthy, result = inspect_status()
    print(json.dumps(result, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
