"""One-shot, frozen M6 retrieval challenge; does not call an LLM."""

from __future__ import annotations

import hashlib
import json
import argparse
from collections import Counter
from datetime import date
from pathlib import Path

from coldchain_llm.corpus import load_corpus
from coldchain_llm.retrieval import BM25Retriever


ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "challenge" / "m6-retrieval-challenge-v1.jsonl"
CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "approved"
PROTOCOL = "M6 independent retrieval challenge v1; single run; no tuning"


def run(cases_path: Path = CASES) -> dict[str, object]:
    raw_cases = cases_path.read_bytes()
    cases = [json.loads(line) for line in raw_cases.decode("utf-8").splitlines() if line.strip()]
    docs, chunks = load_corpus(CORPUS)
    retriever = BM25Retriever(chunks)
    group_counts = Counter(row["group"] for row in cases)
    results = []
    for row in cases:
        scope = row["scope"]
        version = "SOP-EXC v0.9" if scope == "wrong_version" else "SOP-EXC v1.0"
        product = "UNRELATED_PRODUCT" if scope == "wrong_product" else "CHILLED_2_8C"
        found = retriever.search(
            row["query"], procedure_version=version, product_category=product,
            at=date(2026, 11, 16), top_k=5,
        )
        ranked = [chunk.section_id for chunk in found.chunks]
        expected = row["expected_top1_section"]
        rank = ranked.index(expected) + 1 if expected in ranked else None
        distractor = row["distractor_section_id"]
        distractor_rank = ranked.index(distractor) + 1 if distractor in ranked else None
        results.append({
            "case_id": row["case_id"], "group": row["group"], "scope": scope,
            "expected_top1_section": expected, "ranked_sections": ranked,
            "expected_rank": rank, "top1_correct": rank == 1 if expected else None,
            "distractor_section_id": distractor, "distractor_rank": distractor_rank,
            "expected_no_result": expected is None, "actual_no_result": not ranked,
            "no_result_correct": (not ranked) if expected is None else None,
        })
    relevant = [r for r in results if r["group"] == "relevant"]
    insufficient = [r for r in results if r["group"] == "insufficient_source"]
    wrong_version = [r for r in results if r["group"] == "wrong_version"]
    wrong_product = [r for r in results if r["group"] == "wrong_product"]
    comparisons = [r for r in relevant if r["distractor_section_id"] and r["expected_rank"]
                  and r["distractor_rank"]]
    return {
        "protocol": f"{PROTOCOL}; cases={cases_path.name}",
        "challenge_sha256": hashlib.sha256(raw_cases).hexdigest(),
        "case_count": len(cases), "group_counts": dict(sorted(group_counts.items())),
        "approved_document_count": len(docs), "indexed_chunk_count": len(chunks),
        "relevant_cases": {
            "top1_correct": sum(bool(r["top1_correct"]) for r in relevant), "denominator": len(relevant),
            "hit_at_3": sum(r["expected_rank"] is not None and r["expected_rank"] <= 3 for r in relevant),
            "mean_reciprocal_rank": round(sum(1 / r["expected_rank"] if r["expected_rank"] else 0
                                               for r in relevant) / len(relevant), 6) if relevant else None,
            "target_outranks_distractor": sum(
                r["expected_rank"] is not None and r["distractor_rank"] is not None
                and r["expected_rank"] < r["distractor_rank"] for r in relevant
            ),
            "target_distractor_comparisons": len(comparisons),
        },
        "insufficient_source_no_result_correct": sum(bool(r["no_result_correct"]) for r in insufficient),
        "insufficient_source_denominator": len(insufficient),
        "wrong_version_rejected": sum(bool(r["no_result_correct"]) for r in wrong_version),
        "wrong_version_denominator": len(wrong_version),
        "wrong_product_rejected": sum(bool(r["no_result_correct"]) for r in wrong_product),
        "wrong_product_denominator": len(wrong_product),
        "provider_invoked": False,
        "answer_grounding_citation_semantics_latency": "NOT RUN: retrieval-only challenge",
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES)
    args = parser.parse_args()
    print(json.dumps(run(args.cases), ensure_ascii=False, indent=2, sort_keys=True))
