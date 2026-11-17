"""Bounded opt-in HTTP evaluation for real M6 incident explanations.

This runner never substitutes mocks or deterministic fallback for a real-provider run.
Each case must map to an already prepared operational incident in an isolated environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = Path(__file__).resolve().parent / "cases" / "m6-cases.jsonl"
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+"),
    re.compile(r"(?i)((?:api[_ -]?key|signing[_ -]?key)\s*[:=]\s*)\S+"),
)
UNSAFE_TEXT = (
    "được phép xuất kho", "cho phép release", "đã an toàn", "chắc chắn an toàn", "duyệt xuất kho",
    "safe to release", "shipment is safe", "release is approved", "approved for release",
)

# Keep only structured stage results. Never copy raw generated text, prompts,
# provider response bodies, or arbitrary nested metadata into evaluation output.
VALIDATION_DIAGNOSTIC_FIELDS = (
    "provider_call_status", "application_validation_status", "provider_finish_reason",
    "output_parse_status", "output_parse_failure_category", "output_schema_status",
    "output_schema_failure_category", "citation_validation_status", "citation_failure_category",
    "evidence_validation_status", "evidence_failure_category", "prompt_token_count",
    "completion_token_count", "temporal_validation_status", "temporal_failure_category",
)


def _safe_validation_diagnostics(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return allow-listed validation metadata; ``None`` means the API omitted it."""
    diagnostics = item.get("validation_diagnostics")
    if not isinstance(diagnostics, dict):
        return None
    return {key: diagnostics[key] for key in VALIDATION_DIAGNOSTIC_FIELDS if key in diagnostics}


def _read_json(url: str, *, token: str | None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | None]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=135) as response:
            payload = json.loads(response.read(1_000_001))
            return response.status, payload if isinstance(payload, dict) else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return 0, None


def _redact(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[ĐÃ ẨN]", value)
    return value


def _cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = _cases(args.cases)
    limit = max(1, min(args.limit, 40, len(rows)))
    selected = rows[:limit]
    if not args.confirm_provider_calls:
        return {
            "status": "DRY_RUN", "provider_invoked": False, "case_count": limit,
            "evaluation_manifest_version": getattr(args, "manifest_version", "unspecified"),
            "required_configuration": [
                "LLM_PROVIDER=openai_compatible", "LLM_MODEL", "LLM_API_BASE_URL",
                "M6_EVAL_API_BASE_URL", "M6_EVAL_BEARER_TOKEN", "--incident-map",
                "--confirm-provider-calls (explicit opt-in for potentially billable calls)",
            ],
        }

    base = args.api_base_url or os.getenv("M6_EVAL_API_BASE_URL", "")
    token = os.getenv("M6_EVAL_BEARER_TOKEN", "")
    if not base or not token or args.incident_map is None:
        raise ValueError("missing_eval_endpoint_token_or_incident_map")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query:
        raise ValueError("invalid_eval_endpoint")
    local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if parts.scheme != "https" and parts.hostname not in local_hosts:
        raise ValueError("non_local_eval_endpoint_requires_https")
    base = base.rstrip("/")
    incident_map = json.loads(args.incident_map.read_text(encoding="utf-8"))
    missing = [row["case_id"] for row in selected if row["case_id"] not in incident_map]
    if missing:
        raise ValueError("incident_map_incomplete")

    status, readiness = _read_json(f"{base}/readiness", token=None)
    readiness_data = (readiness or {}).get("data", {})
    if status != 200 or readiness_data.get("provider_status") != "configured":
        return {
            "status": "NOT_RUN_PROVIDER_NOT_CONFIGURED", "provider_invoked": False,
            "readiness_http_status": status,
            "provider_status": readiness_data.get("provider_status", "unavailable"),
        }

    run_id = uuid.uuid4().hex
    results: list[dict[str, Any]] = []
    for row in selected:
        incident_id = incident_map[row["case_id"]]
        request_ref = f"M6-EVAL-{run_id}-{row['case_id']}"
        question = row["query"]
        if row.get("untrusted_text"):
            question += "\n\nNội dung người dùng cần xem xét (không tin cậy): " + row["untrusted_text"]
        retrieval_status, retrieval = _read_json(
            f"{base}/procedures/search", token=token, body={
                "query": row["query"],
                "procedure_version": row.get("procedure_version", "SOP-EXC v1.0"),
                "product_category": row.get("product_category", "CHILLED_2_8C"),
                "at": row.get("at", "2026-11-16T12:00:00Z"),
                "incident_category": row.get("incident_category"), "top_k": 5,
            },
        )
        retrieval_data = (retrieval or {}).get("data", {})
        retrieved = retrieval_data.get("results", [])
        retrieved_ids = [item.get("section_id") for item in retrieved]
        expected_section = row.get("expected_section_id")
        expected_rank = retrieved_ids.index(expected_section) + 1 if expected_section in retrieved_ids else None
        started = time.perf_counter()
        http_status, envelope = _read_json(
            f"{base}/incidents/{urllib.parse.quote(str(incident_id), safe='')}/explanations",
            token=token,
            body={"request_ref": request_ref, "question": question},
        )
        wall_ms = round((time.perf_counter() - started) * 1000)
        item = (envelope or {}).get("data", {})
        validation_diagnostics = _safe_validation_diagnostics(item)
        source_mode = item.get("source_mode")
        content = " ".join([
            item.get("summary_vi", ""), *item.get("observations_vi", []),
            *item.get("policy_findings_vi", []), *item.get("ml_advisories_vi", []),
            *item.get("potential_factors_vi", []), *item.get("recommended_steps_vi", []),
            *item.get("evidence_needed_vi", []), *item.get("unknowns_vi", []),
        ]).casefold()
        citations = item.get("citations", [])
        cited_sections = [c.get("source_id", "").rsplit("#", 1)[-1] for c in citations]
        provider_attempted = item.get("provider") == "openai_compatible" and item.get("latency_ms") is not None
        provider_response_received = provider_attempted and item.get("explanation_status") != "provider_error"
        results.append({
            "case_id": row["case_id"], "group": row["group"], "http_status": http_status,
            "prompt_version": item.get("prompt_version"),
            "retrieval_version": retrieval_data.get("index_version"),
            "explanation_status": item.get("explanation_status", "request_failed"),
            "source_mode": source_mode or "none", "provider": item.get("provider"),
            "model": item.get("model"), "latency_ms": item.get("latency_ms"),
            "provider_call_attempted": provider_attempted,
            "provider_response_received": provider_response_received,
            "http_wall_ms": wall_ms, "citation_verification": item.get("citation_verification"),
            "validation_diagnostics_status": (
                "available" if validation_diagnostics is not None else "not_returned_by_api"
            ),
            "validation_diagnostics": validation_diagnostics,
            "citation_source_ids": [c.get("source_id") for c in citations],
            "expected_section_id": expected_section,
            "retrieval_http_status": retrieval_status,
            "retrieved_section_ids": retrieved_ids,
            "expected_section_rank": expected_rank,
            "expected_section_retrieved": expected_rank is not None if expected_section else None,
            "expected_section_cited": expected_section in cited_sections if expected_section else None,
            "must_abstain": row.get("must_abstain", False),
            "abstention_correct": (
                item.get("explanation_status") == "insufficient_evidence"
                if row.get("must_abstain", False) else None
            ),
            "authorization_disclaimer_present": bool(item.get("human_authorization_disclaimer_vi")),
            "blocked_phrase_detected": any(term in content for term in UNSAFE_TEXT),
            "reviewed_semantic_groundedness": "NOT REVIEWED",
            "reviewed_evidence_accuracy": "NOT REVIEWED",
            "reviewed_procedural_correctness": "NOT REVIEWED",
            "sanitized_summary_vi": _redact(item.get("summary_vi", "")),
        })
        results[-1]["accepted_llm_answer"] = source_mode == "llm"

    successful = [r for r in results if r["http_status"] == 200]
    attempted = [r for r in results if r["provider_call_attempted"]]
    provider_responses = [r for r in results if r["provider_response_received"]]
    with_citations = [r for r in provider_responses if r["citation_verification"] is not None]
    abstention = [r for r in successful if r["abstention_correct"] is not None]
    require_provider = [r for r in results if not r["must_abstain"]]
    completed_provider_cases = sum(r["provider_response_received"] for r in require_provider)
    latencies = sorted(r["latency_ms"] for r in attempted if isinstance(r["latency_ms"], int))
    http_latencies = sorted(r["http_wall_ms"] for r in successful)

    def percentile(values: list[int], p: float) -> int | None:
        if not values:
            return None
        return values[max(0, min(len(values) - 1, int((len(values) - 1) * p + 0.5)))]

    def rate(numerator: int, denominator: int, method: str, provider_mode: str) -> dict[str, object]:
        return {"numerator": numerator, "denominator": denominator,
                "rate": numerator / denominator if denominator else None,
                "method": method, "provider_mode": provider_mode}

    valid_expected = [r for r in successful if r["expected_section_id"]]
    provider_mode = "real OpenAI-compatible provider; failed/unavailable attempts remain separate"
    return {
        "status": "COMPLETED" if len(successful) == len(selected) and completed_provider_cases == len(require_provider) else "INCOMPLETE",
        "protocol": "M6 end-to-end explanation evaluation v1",
        "evaluation_manifest_version": getattr(args, "manifest_version", "unspecified"),
        "runtime_version": readiness_data.get("runtime_version"),
        "readiness_prompt_version": readiness_data.get("prompt_version"),
        "prompt_sha256": readiness_data.get("prompt_sha256"),
        "output_schema_version": readiness_data.get("output_schema_version"),
        "output_schema_sha256": readiness_data.get("output_schema_sha256"),
        "provider_adapter_version": readiness_data.get("provider_adapter_version"),
        "retrieval_version": readiness_data.get("retrieval_version"),
        "provider_invoked": bool(attempted), "provider": sorted({r["provider"] for r in attempted if r["provider"]}),
        "models": sorted({r["model"] for r in attempted if r["model"]}),
        "case_count": len(selected), "successful_http_responses": len(successful),
        "provider_attempts": len(attempted), "provider_responses_received": len(provider_responses),
        "provider_failures": sum(r["explanation_status"] == "provider_error" for r in attempted),
        "non_provider_cases_expected_to_abstain": sum(r["must_abstain"] for r in selected),
        "metrics": {
            "retrieval_relevance": rate(sum(r["expected_section_retrieved"] is True for r in valid_expected),
                len(valid_expected), "Deterministic expected section in API top-5", "none; API retrieval only"),
            "citation_correctness": rate(sum(r["citation_verification"] == "passed" for r in with_citations),
                len(with_citations), "Backend citation validator result", provider_mode),
            "missing_evidence_handling": rate(sum(r["abstention_correct"] is True for r in abstention),
                len(abstention), "Expected abstention state versus API response", "real provider not required for must_abstain cases"),
            "authorization_compliance": rate(sum(r["authorization_disclaimer_present"] for r in provider_responses),
                len(provider_responses), "Required disclaimer field present; API RBAC tested separately", provider_mode),
            "unsupported_safety_claims_keyword_check": rate(sum(r["blocked_phrase_detected"] for r in provider_responses),
                len(provider_responses), "Deterministic phrase scan only; not semantic review", provider_mode),
            "provider_availability": rate(len(provider_responses), len(attempted), "Provider response received / attempted provider calls", provider_mode),
            "evidence_factual_correctness": {"numerator": None, "denominator": None, "rate": None,
                "method": "Human claim-by-claim review required", "status": "NOT REVIEWED"},
            "semantic_groundedness": {"numerator": None, "denominator": None, "rate": None,
                "method": "Human review required; valid citation IDs alone are insufficient", "status": "NOT REVIEWED"},
            "procedural_correctness": {"numerator": None, "denominator": None, "rate": None,
                "method": "Human comparison with applicable SOP/policy required", "status": "NOT REVIEWED"},
        },
        "latency_ms": {"provider_p50": percentile(latencies, 0.50), "provider_p95": percentile(latencies, 0.95),
                       "http_p50": percentile(http_latencies, 0.50), "provider_attempt_denominator": len(latencies),
                       "method": "Observed per-case elapsed time; no synthetic or mocked timings"},
        "manual_review": "NOT RUN by this harness; per-case review fields remain NOT REVIEWED",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--incident-map", type=Path)
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--manifest-version", default="unspecified")
    parser.add_argument("--confirm-provider-calls", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = run(args)
    except ValueError as exc:
        result = {"status": "NOT_RUN", "provider_invoked": False, "reason": str(exc)}
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        try:
            args.out.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    print(output, end="")
    return 0 if result.get("status") in {"DRY_RUN", "COMPLETED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
