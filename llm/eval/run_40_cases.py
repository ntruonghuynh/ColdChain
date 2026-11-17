"""Run deterministic retrieval/filtering checks for the 40-case M6 inventory.

This does not call an LLM and intentionally does not score generation quality.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from coldchain_llm.corpus import load_corpus
from coldchain_llm.retrieval import BM25Retriever


ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "cases" / "m6-cases.jsonl"
CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "approved"


def run() -> dict[str, object]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    documents, chunks = load_corpus(CORPUS)
    retriever = BM25Retriever(chunks)
    counts = Counter(row["group"] for row in rows)
    duplicate_ids = len({row["case_id"] for row in rows}) != len(rows)
    results = []
    wrong_version_rejected = 0
    wrong_product_rejected = 0
    for row in rows:
        found = retriever.search(
            row["query"], procedure_version="SOP-EXC v1.0", product_category="CHILLED_2_8C",
            at=date(2026, 11, 16), incident_category="TEMPERATURE_EXCURSION", top_k=5,
        )
        hit = any(chunk.section_id == row["expected_section_id"] for chunk in found.chunks)
        wrong_version = retriever.search(
            row["query"], procedure_version="SOP-EXC v0.9", product_category="CHILLED_2_8C",
            at=date(2026, 11, 16), top_k=5,
        )
        wrong_product = retriever.search(
            row["query"], procedure_version="SOP-EXC v1.0", product_category="UNRELATED_PRODUCT",
            at=date(2026, 11, 16), top_k=5,
        )
        wrong_version_rejected += not wrong_version.chunks
        wrong_product_rejected += not wrong_product.chunks
        results.append({
            "case_id": row["case_id"], "group": row["group"],
            "expected_section_id": row["expected_section_id"], "retrieval_hit": hit,
            "retrieved_source_ids": [chunk.source_id for chunk in found.chunks],
            "evidence_state": row["evidence_state"], "must_abstain": row["must_abstain"],
            "hostile_input_present": row["untrusted_text"] is not None,
        })
    hostile_files = list((ROOT / "llm" / "corpus" / "untrusted_samples").glob("*.md"))
    hostile_markers = [
        "ignore prior instructions", "ignore all safeguards", "api key and audit signing key",
    ]
    indexed_text = "\n".join(chunk.text.casefold() for chunk in chunks)
    untrusted_not_indexed = bool(hostile_files) and not any(marker in indexed_text for marker in hostile_markers)
    valid = (
        len(rows) == 40 and not duplicate_ids
        and counts == Counter({"normal": 10, "missing_evidence": 10,
                               "conflicting_evidence": 10, "hostile_instructions": 10})
        and all(item["retrieval_hit"] for item in results)
        and wrong_version_rejected == 40 and wrong_product_rejected == 40
        and untrusted_not_indexed
    )
    return {
        "protocol": "M6 deterministic retrieval and boundary check v1",
        "run_status": "PASS" if valid else "FAIL",
        "case_count": len(rows), "group_counts": dict(sorted(counts.items())),
        "approved_document_count": len(documents), "indexed_chunk_count": len(chunks),
        "retrieval_target_hits": sum(bool(item["retrieval_hit"]) for item in results),
        "wrong_procedure_version_rejected": wrong_version_rejected,
        "wrong_product_category_rejected": wrong_product_rejected,
        "untrusted_sample_documents_excluded_from_index": untrusted_not_indexed,
        "duplicate_case_ids": duplicate_ids,
        "provider_invoked": False,
        "llm_generation_quality_metrics": "NOT_RUN: no real provider inference was executed",
        "semantic_groundedness_review": "NOT_RUN: requires actual generated answers and human review",
        "latency_and_cost": "NOT_RUN: no provider call; no price table assumed",
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["run_status"] == "PASS" else 1)

