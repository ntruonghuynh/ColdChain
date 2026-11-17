"""Reproducible local retrieval diagnostics for a development-only query set."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

from coldchain_llm.corpus import load_corpus
from coldchain_llm.retrieval import BM25Retriever


ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "dev" / "m6-retrieval-dev-v1.jsonl"
CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "approved"


def run() -> dict[str, object]:
    raw = CASES.read_bytes()
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    docs, chunks = load_corpus(CORPUS)
    retriever = BM25Retriever(chunks)
    results = []
    groups: dict[str, list[dict[str, object]]] = {}
    for row in cases:
        found = retriever.search(
            row["query"], procedure_version="SOP-EXC v1.0",
            product_category="CHILLED_2_8C", at=date(2026, 11, 17), top_k=5,
        )
        ranks = [chunk.section_id for chunk in found.chunks]
        expected = row["expected_section_id"]
        rank = ranks.index(expected) + 1 if expected in ranks else None
        item = {
            "case_id": row["case_id"], "group": row["group"],
            "expected_section_id": expected, "ranked_sections": ranks,
            "expected_rank": rank, "top1_correct": rank == 1,
        }
        results.append(item)
        groups.setdefault(row["group"], []).append(item)

    def metrics(items: list[dict[str, object]]) -> dict[str, object]:
        ranks = [item["expected_rank"] for item in items]
        return {
            "top1_correct": sum(rank == 1 for rank in ranks),
            "hit_at_3": sum(rank is not None and rank <= 3 for rank in ranks),
            "mrr": round(sum(1 / rank if rank else 0 for rank in ranks) / len(items), 6) if items else None,
            "denominator": len(items),
        }

    return {
        "protocol": "M6 retrieval development diagnostics v1; not the independent challenge",
        "case_sha256": hashlib.sha256(raw).hexdigest(), "case_count": len(cases),
        "group_counts": dict(sorted(Counter(row["group"] for row in cases).items())),
        "document_count": len(docs), "chunk_count": len(chunks), "provider_invoked": False,
        "overall": metrics(results),
        "by_group": {group: metrics(items) for group, items in sorted(groups.items())},
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
