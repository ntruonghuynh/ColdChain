"""Regression tests for safe M6 evaluator diagnostics reporting."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if not (REPO_ROOT / "llm" / "eval").is_dir():
    REPO_ROOT = Path("/workspace")
EVAL_DIR = REPO_ROOT / "llm" / "eval"
sys.path.insert(0, str(EVAL_DIR))
import run_explanation_eval as evaluator  # noqa: E402


def test_safe_validation_diagnostics_allowlist_excludes_raw_fields() -> None:
    item = {
        "validation_diagnostics": {
            "provider_call_status": "succeeded",
            "provider_finish_reason": "stop",
            "output_parse_status": "passed",
            "citation_failure_category": None,
            "prompt_token_count": 12,
            "raw_generated_text": "must never be copied",
            "authorization_header": "must never be copied",
        }
    }

    assert evaluator._safe_validation_diagnostics(item) == {
        "provider_call_status": "succeeded",
        "provider_finish_reason": "stop",
        "output_parse_status": "passed",
        "citation_failure_category": None,
        "prompt_token_count": 12,
    }
    assert evaluator._safe_validation_diagnostics({}) is None
    assert evaluator._safe_validation_diagnostics({"validation_diagnostics": "invalid"}) is None


def test_runner_records_available_and_missing_api_diagnostics_without_network(
    tmp_path: Path, monkeypatch,
) -> None:
    case_path = tmp_path / "cases.jsonl"
    case_path.write_text(json.dumps({
        "case_id": "M6R-TEST", "group": "fixture", "query": "offline fixture",
        "expected_section_id": "HIGH_EXCURSION", "must_abstain": False,
    }) + "\n")
    incident_path = tmp_path / "incidents.json"
    incident_path.write_text(json.dumps({"M6R-TEST": "00000000-0000-0000-0000-000000000001"}))
    monkeypatch.setenv("M6_EVAL_BEARER_TOKEN", "fixture-token")

    responses = [
        (200, {"data": {"provider_status": "configured"}}),
        (200, {"data": {"results": [{"section_id": "HIGH_EXCURSION"}]}}),
        (200, {"data": {
            "source_mode": "llm", "explanation_status": "draft", "provider": "openai_compatible",
            "model": "mock-fixture", "latency_ms": 10, "citation_verification": "passed",
            "citations": [{"source_id": "SOP-EXC@1.0#HIGH_EXCURSION"}],
            "human_authorization_disclaimer_vi": "required",
            "validation_diagnostics": {
                "provider_call_status": "succeeded", "application_validation_status": "passed",
                "provider_finish_reason": "stop", "output_parse_status": "passed",
                "output_schema_status": "passed", "citation_validation_status": "passed",
                "evidence_validation_status": "passed", "temporal_validation_status": "passed",
                "completion_token_count": 20,
                "raw_completion": "sensitive fixture must be dropped",
            },
        }}),
    ]
    monkeypatch.setattr(evaluator, "_read_json", lambda *args, **kwargs: responses.pop(0))

    result = evaluator.run(Namespace(
        cases=case_path, limit=1, confirm_provider_calls=True,
        api_base_url="http://localhost:3107/api/llm", incident_map=incident_path,
    ))

    case = result["results"][0]
    assert case["validation_diagnostics_status"] == "available"
    assert case["validation_diagnostics"]["provider_finish_reason"] == "stop"
    assert case["validation_diagnostics"]["application_validation_status"] == "passed"
    assert case["validation_diagnostics"]["temporal_validation_status"] == "passed"
    assert "raw_completion" not in case["validation_diagnostics"]
    assert result["provider_invoked"] is True


def test_runner_marks_diagnostics_missing_instead_of_inventing_them(
    tmp_path: Path, monkeypatch,
) -> None:
    case_path = tmp_path / "cases.jsonl"
    case_path.write_text(json.dumps({
        "case_id": "M6R-TEST", "group": "fixture", "query": "offline", "must_abstain": False,
    }) + "\n")
    incident_path = tmp_path / "incidents.json"
    incident_path.write_text(json.dumps({"M6R-TEST": "00000000-0000-0000-0000-000000000001"}))
    monkeypatch.setenv("M6_EVAL_BEARER_TOKEN", "fixture-token")
    responses = [
        (200, {"data": {"provider_status": "configured"}}),
        (200, {"data": {"results": []}}),
        (200, {"data": {
            "source_mode": "llm", "explanation_status": "draft", "provider": "openai_compatible",
            "model": "mock-fixture", "latency_ms": 10, "citation_verification": "passed",
            "citations": [], "human_authorization_disclaimer_vi": "required",
        }}),
    ]
    monkeypatch.setattr(evaluator, "_read_json", lambda *args, **kwargs: responses.pop(0))

    result = evaluator.run(Namespace(
        cases=case_path, limit=1, confirm_provider_calls=True,
        api_base_url="http://localhost:3107/api/llm", incident_map=incident_path,
    ))

    case = result["results"][0]
    assert case["validation_diagnostics_status"] == "not_returned_by_api"
    assert case["validation_diagnostics"] is None
