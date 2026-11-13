#!/usr/bin/env python3
"""End-to-end smoke test of the Docker Compose stack (Milestone 1).

Checks, in order:
  1. docker compose configuration is valid
  2. the stack starts and every service becomes healthy (compose up --wait)
  3. the React app is served at http://localhost:<FRONTEND_PORT>/ (and SPA deep links)
  4. the frontend proxy reaches the backend: /api/health ok, migration at head
  5. the seeded teaching policy is returned by the API
  6. backend outage: the proxy answers a JSON "api_unreachable" error; recovery works
  7. shutdown: `docker compose down` (WITHOUT -v) removes the containers
  8. persistence: after restarting, the same database cluster and the same policy row exist

Data is never deleted (no `down -v`). Uses only the Python standard library.
Usage:  python3 scripts/smoke_test.py [--keep-running]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


def env_value(key: str, default: str) -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip() or default
    return default


BASE = f"http://localhost:{env_value('FRONTEND_PORT', '3000')}"
PG_USER = env_value("POSTGRES_USER", "coldchain")
PG_DB = env_value("POSTGRES_DB", "coldchain")


def compose(*args: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True,
                          check=check, timeout=timeout)


def http_get(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}", flush=True)


def wait_for(predicate, timeout_s: int = 90) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001 - keep polling
            pass
        time.sleep(2)
    return False


def psql(sql: str) -> str:
    return compose("exec", "-T", "db", "psql", "-U", PG_USER, "-d", PG_DB, "-tA", "-c", sql).stdout.strip()


def snapshot() -> tuple[str, str]:
    cluster = psql("SELECT system_identifier FROM pg_control_system()")
    policy = psql("SELECT policy_id FROM policy WHERE policy_code='POL-CHILL-01' AND policy_version='1.0'")
    return cluster, policy


def check_running_stack(label: str) -> None:
    status, body = http_get("/")
    record(f"{label}: React app served at /", status == 200 and '<div id="root">' in body, f"HTTP {status}")
    status, body = http_get("/shipments")
    record(f"{label}: SPA deep link /shipments", status == 200 and '<div id="root">' in body, f"HTTP {status}")
    status, body = http_get("/api/health")
    health = json.loads(body)["data"] if status in (200, 503) else {}
    db = health.get("database", {})
    record(f"{label}: /api/health via proxy", status == 200 and health.get("status") == "ok",
           f"HTTP {status}, db={db.get('status')}, revision={db.get('migration_revision')}")
    record(f"{label}: migration at head", bool(db) and db.get("migration_revision") == db.get("expected_revision"))


def main() -> int:
    keep_running = "--keep-running" in sys.argv

    try:
        compose("version")
    except Exception as exc:  # noqa: BLE001
        print(f"Docker Compose is not available: {exc}")
        return 2

    result = compose("config", "--quiet", check=False)
    record("compose configuration valid", result.returncode == 0, result.stderr.strip()[:200])
    if result.returncode != 0:
        return 1

    started = time.time()
    result = compose("up", "-d", "--build", "--wait", "--wait-timeout", "300", check=False)
    record("stack starts and becomes healthy", result.returncode == 0, f"{time.time() - started:.0f}s")
    if result.returncode != 0:
        print(result.stderr[-2000:])
        return 1

    check_running_stack("start")

    status, body = http_get("/api/policies?status=ACTIVE")
    policy = json.loads(body)["data"][0] if status == 200 else {}
    record("seeded teaching policy returned",
           policy.get("limits") == {"min_temp_c": "2.00", "max_temp_c": "8.00"}
           and policy.get("release_authority_role") == "QUALITY",
           f"{policy.get('policy_code')} v{policy.get('policy_version')}")

    # Backend outage: UI stays up, proxy returns a JSON error, recovery restores health.
    compose("stop", "backend")
    status, body = http_get("/api/health")
    code = json.loads(body).get("error", {}).get("code") if body.startswith("{") else None
    record("backend outage reported as JSON api_unreachable", status == 502 and code == "api_unreachable",
           f"HTTP {status}, code={code}")
    status, _ = http_get("/")
    record("frontend still served during backend outage", status == 200, f"HTTP {status}")
    compose("start", "backend")
    record("backend recovers after restart",
           wait_for(lambda: http_get("/api/health")[0] == 200), "health 200 again")

    before = snapshot()
    compose("down")
    remaining = compose("ps", "-a", "-q").stdout.strip()
    record("shutdown removes containers (data volume kept)", remaining == "")

    result = compose("up", "-d", "--wait", "--wait-timeout", "300", check=False)
    record("stack restarts after shutdown", result.returncode == 0)
    check_running_stack("restart")
    after = snapshot()
    record("database cluster persisted across restart", before[0] == after[0] and before[0] != "",
           f"system_identifier {after[0]}")
    record("policy row persisted (same policy_id)", before[1] == after[1] and before[1] != "", after[1])

    if not keep_running:
        compose("down")
        print("Stack stopped (data kept). Use --keep-running to leave it running.")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
