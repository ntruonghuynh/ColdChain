"""Development-only BM25 v3 intent-reranker comparison; never called by API."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from coldchain_llm.corpus import load_corpus
from coldchain_llm.retrieval import BM25Retriever

ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "dev" / "m6-retrieval-dev-v1.jsonl"
CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "approved"
INTENTS = {
    "HIGH_EXCURSION": ("high", "warm", "hot", "above", "upper", "vuot nguong tren", "nhiet do cao", "nhiet vuot"),
    "LOW_EXCURSION": ("low", "cold", "below minimum", "lower limit", "duoi muc toi thieu", "nhiet do thap", "lanh qua thap"),
    "QUALITY_REVIEW": ("quality officer", "quarantine", "release", "disposition", "phê duyệt", "phe duyet", "xuat kho", "quyen quyet dinh"),
    "MISSING_TELEMETRY": ("missing", "gap", "no reading", "no telemetry", "khoang trong", "thieu du lieu", "khong co du lieu"),
    "DELAYED_OCEAN": ("delayed", "ocean", "ship", "received_at", "event_at", "mat song", "tau bien", "den tre"),
    "ISOLATED_SPIKE": ("spike", "single point", "isolated", "don doc", "diem do bat thuong"),
    "SENSOR_UNCERTAINTY": ("sensor fault", "uncertain", "battery", "logger", "cam bien loi", "khong chac chan"),
    "EVIDENCE_AUDIT": ("audit", "citation", "hash", "evidence", "trich dan", "kiem tra lich su"),
    "MONITORING": ("normal", "monitoring", "routine", "theo doi", "kiem tra so lieu"),
}


def fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def intent(query: str) -> str | None:
    text = fold(query)
    counts = {section: sum(fold(term) in text for term in terms) for section, terms in INTENTS.items()}
    maximum = max(counts.values(), default=0)
    winners = [section for section, count in counts.items() if count == maximum and count > 0]
    return winners[0] if len(winners) == 1 else None


def metrics(rows: list[dict]) -> dict[str, object]:
    ranks = [row["rank"] for row in rows]
    return {"denominator": len(rows), "top1": sum(r == 1 for r in ranks),
            "hit_at_3": sum(r is not None and r <= 3 for r in ranks),
            "mrr": round(sum(1 / r if r else 0 for r in ranks) / len(ranks), 6) if ranks else None}


def run() -> dict[str, object]:
    raw = CASES.read_bytes()
    cases = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    docs, chunks = load_corpus(CORPUS)
    retriever = BM25Retriever(chunks)
    baseline, candidate = [], []
    for row in cases:
        found = retriever.search(row["query"], procedure_version="SOP-EXC v1.0",
                                 product_category="CHILLED_2_8C", at=date(2026, 11, 17), top_k=9)
        expected = row["expected_section_id"]
        base_ids = [chunk.section_id for chunk in found.chunks]
        section_intent = intent(row["query"])
        candidate_ids = list(base_ids)
        # Only rerank an applicable, BM25-retrieved chunk. No pilot cases or labels
        # participate in the selection. Applicability filtering remains in BM25.
        if section_intent in candidate_ids:
            candidate_ids.remove(section_intent)
            candidate_ids.insert(0, section_intent)
        base_rank = base_ids.index(expected) + 1 if expected in base_ids else None
        cand_rank = candidate_ids.index(expected) + 1 if expected in candidate_ids else None
        baseline.append({"case_id": row["case_id"], "group": row["group"], "expected_section_id": expected,
                         "intent": section_intent, "rank": base_rank})
        candidate.append({"case_id": row["case_id"], "group": row["group"], "expected_section_id": expected,
                          "intent": section_intent, "rank": cand_rank,
                          "ranked_sections": candidate_ids[:5]})
    return {
        "protocol": "bm25-v3-intent-prototype; development-only, not independent validation",
        "provider_invoked": False, "case_sha256": hashlib.sha256(raw).hexdigest(),
        "document_count": len(docs), "chunk_count": len(chunks), "case_count": len(cases),
        "configuration_sha256": hashlib.sha256(json.dumps(INTENTS, sort_keys=True).encode()).hexdigest(),
        "baseline_bm25_v2": metrics(baseline), "candidate_bm25_v3_intent_rerank": metrics(candidate),
        "candidate_intent_coverage": sum(item["intent"] is not None for item in candidate),
        "intent_denominator": len(candidate), "limitations": [
            "The same 27-case development set is used only for diagnostics; no independent claim.",
            "Intent lexicon can misroute ambiguous requests; unresolved ties preserve BM25 order.",
            "Rank boost does not measure semantic entailment or select a minimum relevance threshold.",
            "Product/version/status/effective-date applicability is inherited from BM25 filters.",
        ],
        "results": candidate,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
