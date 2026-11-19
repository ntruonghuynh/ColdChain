#!/usr/bin/env python3
"""Read-only M1-M6 HTTP smoke checks for a seeded local deployment.

Run from the repository root after importing seed 11 and replaying monitoring:
    python3 scripts/deployment_smoke.py

The only POST is local demo login. No workflow, prediction, ingestion, explanation
generation, or provider endpoint is called. Demo credentials are read from .env
and are never printed.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


ENV = read_env()
BASE = f"http://127.0.0.1:{ENV.get('FRONTEND_PORT', '3000')}"
RESULTS: list[tuple[str, str, str]] = []


def request(path: str, method: str = "GET", body: dict[str, Any] | None = None,
            token: str | None = None) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}


def check(name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if passed else "FAIL", detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}{' — ' + detail if detail else ''}")


def skip(name: str, detail: str) -> None:
    RESULTS.append((name, "SKIP", detail))
    print(f"[SKIP] {name} — {detail}")


def main() -> int:
    for route in ("/", "/temperature", "/excursions", "/quality-review", "/audit", "/settings"):
        try:
            with urllib.request.urlopen(BASE + route, timeout=10) as response:
                page = response.read().decode("utf-8", errors="replace")
                check(f"frontend route {route}", response.status == 200 and '<div id="root">' in page,
                      f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001 - report all route failures in one run
            check(f"frontend route {route}", False, type(exc).__name__)

    status, health = request("/api/health")
    db = health.get("data", {}).get("database", {})
    check("backend readiness and migration", status == 200 and health.get("data", {}).get("status") == "ok"
          and str(db.get("migration_revision", "")).startswith("0006"),
          f"HTTP {status}; revision={db.get('migration_revision')}")

    live_status, _ = request("/api/health/live")
    check("backend liveness", live_status == 200, f"HTTP {live_status}")
    chain_status, chain = request("/api/health/ledger")
    check("isolated blockchain readiness", chain_status == 200 and chain.get("data", {}).get("status") == "ok",
          f"HTTP {chain_status}")

    system_status, _ = request("/api/system/info")
    check("system information", system_status == 200, f"HTTP {system_status}")
    policy_status, policies = request("/api/policies?status=ACTIVE")
    policy_rows = policies.get("data", [])
    policy_ok = bool(policy_rows) and policy_rows[0].get("limits", {}).get("min_temp_c") == "2.00" \
        and policy_rows[0].get("limits", {}).get("max_temp_c") == "8.00"
    check("active teaching policy", policy_status == 200 and policy_ok, f"HTTP {policy_status}")

    shipment_status, shipment_response = request("/api/shipments?limit=500&offset=0")
    shipments = shipment_response.get("data", [])
    source_count = sum(1 for item in shipments if item.get("source_dataset_id"))
    check("canonical simulated journeys imported", shipment_status == 200 and source_count == 200,
          f"HTTP {shipment_status}; imported seed journeys={source_count}")

    incident_status, incident_response = request("/api/incidents?limit=500")
    incidents = incident_response.get("data", [])
    directions = {item.get("latest", {}).get("direction") for item in incidents if item.get("latest")}
    has_gap = any(item.get("category") == "DATA_GAP" for item in incidents)
    check("incident queue and HIGH/LOW examples", incident_status == 200 and {"HIGH", "LOW"} <= directions,
          f"HTTP {incident_status}; directions={','.join(sorted(str(x) for x in directions if x)) or 'none'}")
    check("missing-data incident remains explicit", incident_status == 200 and has_gap,
          f"HTTP {incident_status}; DATA_GAP present={has_gap}")
    if incident_status == 200 and incidents:
        chosen = next((row for row in incidents if row.get("category") == "DATA_GAP"), incidents[0])
        detail_status, detail = request(f"/api/incidents/{chosen['incident_id']}")
        detail_data = detail.get("data", {})
        revisions = detail_data.get("revisions", [])
        check("incident detail includes revisions and evidence", detail_status == 200 and bool(revisions)
              and isinstance(detail_data.get("evidence", {}).get("gaps", []), list),
              f"HTTP {detail_status}; revisions={len(revisions)}")
    else:
        chosen = None
        check("incident detail includes revisions and evidence", False, "no incident available")

    model_status, model = request("/api/predictions/model")
    check("M4 frozen model readiness (GET only)", model_status == 200
          and model.get("data", {}).get("status") == "ready", f"HTTP {model_status}")
    llm_status, llm = request("/api/llm/readiness")
    llm_data = llm.get("data", {})
    check("M6 offline retrieval readiness; provider disabled", llm_status == 200
          and llm_data.get("retrieval_status") == "ready"
          and llm_data.get("provider_status") == "not_configured", f"HTTP {llm_status}")

    unauth_status, _ = request("/api/ledger/transactions?limit=1")
    check("protected GET rejects logged-out request", unauth_status == 401, f"HTTP {unauth_status}")

    quality_password = ENV.get("QUALITY_DEMO_PASSWORD", "")
    if not quality_password:
        check("QUALITY login and role check", False, "QUALITY_DEMO_PASSWORD missing from .env")
        token = None
    else:
        login_status, login = request("/api/auth/login", "POST",
                                      {"username": "quality.demo", "password": quality_password})
        token = login.get("data", {}).get("access_token")
        me_status, me = request("/api/auth/me", token=token) if token else (login_status, {})
        roles = me.get("data", {}).get("roles", [])
        check("QUALITY login and GET /auth/me", login_status == 200 and me_status == 200
              and "QUALITY" in roles, f"login={login_status}; me={me_status}; role present={'QUALITY' in roles}")

    if token:
        quality_list_status, quality_list = request("/api/incidents?status=OPEN&limit=10", token=token)
        quality_rows = quality_list.get("data", [])
        if quality_list_status == 200 and quality_rows:
            quality_detail_status, quality_detail = request(
                f"/api/incidents/{quality_rows[0]['incident_id']}", token=token)
            quality_data = quality_detail.get("data", {})
            check("QUALITY can read incident evidence and revisions", quality_detail_status == 200
                  and bool(quality_data.get("revisions"))
                  and isinstance(quality_data.get("evidence", {}).get("readings", []), list),
                  f"list={quality_list_status}; detail={quality_detail_status}; "
                  f"revisions={len(quality_data.get('revisions', []))}")
        else:
            check("QUALITY can read incident evidence and revisions", False,
                  f"incident list HTTP {quality_list_status}; no open incidents returned")
        ledger_status, ledger_body = request("/api/ledger/transactions?limit=500", token=token)
        audit_status, audit_body = request("/api/ledger/audit?limit=500", token=token)
        ledger_rows = ledger_body.get("data", [])
        audit_rows = audit_body.get("data", [])
        confirmed_txs = sum(1 for row in ledger_rows if row.get("transaction"))
        check("authenticated ledger and signed-audit reads", ledger_status == 200 and audit_status == 200,
              f"transactions HTTP {ledger_status} ({len(ledger_rows)} business events, {confirmed_txs} chain tx); "
              f"audit HTTP {audit_status} ({len(audit_rows)} entries)")
        forbidden_status, _ = request("/api/ledger/audit/verify", token=token)
        check("QUALITY is forbidden from ADMIN-only audit verification", forbidden_status == 403,
              f"HTTP {forbidden_status}")
        if chosen:
            history_status, history = request(
                f"/api/llm/incidents/{chosen['incident_id']}/explanations?limit=25", token=token)
            items = history.get("data", [])
            check("stored M6 explanation history GET (empty is valid)", history_status == 200,
                  f"HTTP {history_status}; stored explanations={len(items)}")
            if items:
                exp_status, exp = request(f"/api/llm/explanations/{items[0]['explanation_id']}", token=token)
                citations = exp.get("data", {}).get("citations", [])
                check("stored M6 explanation detail GET", exp_status == 200,
                      f"HTTP {exp_status}; citations={len(citations)}")
            else:
                skip("stored M6 explanation detail GET", "no stored explanation exists in this fresh demo database")

    passed = sum(1 for _, status, _ in RESULTS if status == "PASS")
    failed = [name for name, status, _ in RESULTS if status == "FAIL"]
    skipped = sum(1 for _, status, _ in RESULTS if status == "SKIP")
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped; only POST was local demo login.")
    print("No prediction, workflow, ingestion, explanation-generation, blockchain-write, or provider endpoint was called.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
