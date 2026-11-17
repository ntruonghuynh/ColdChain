"""Small deterministic BM25 retriever with strict applicability filtering."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .corpus import SourceChunk


INDEX_VERSION = "bm25-v2-title25-vn-aliases"
TITLE_WEIGHT = 2.5

# Query-only expansions grounded in terminology present in SOP-EXC v1.0. This is
# deliberately small and inspectable; it does not change document text or policy.
QUERY_ALIASES = (
    ("kiem tra", "theo doi"),
    ("giam sat", "theo doi"),
    ("hang ngay", "binh thuong"),
    ("quan trac", "so do"),
    ("so lieu", "so do"),
    ("khong co du lieu", "khoang trong unknown"),
    ("missing telemetry", "khoang trong unknown"),
    ("tau bien", "vung bien"),
    ("ngoai khoi", "vung bien"),
    ("mat song", "truyen du lieu tre"),
    ("dong bo muon", "du lieu den tre"),
    ("nhiet vuot nguong", "nhiet do cao"),
    ("tren muc cho phep", "nhiet do cao"),
    ("duoi muc toi thieu", "nhiet do thap"),
    ("lanh qua thap", "nhiet do thap"),
    ("dinh bat thuong don doc", "diem do bat thuong"),
    ("do tin cay logger kem", "cam bien khong chac chan"),
    ("cam bien loi", "cam bien khong chac chan"),
    ("logger", "cam bien"),
    ("audit trail", "evidence audit"),
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _terms(text: str) -> list[str]:
    # Accent-insensitive Unicode tokenization keeps Vietnamese and ASCII queries aligned.
    return re.findall(r"[^\W_]+", _fold(text), flags=re.UNICODE)


def _query_terms(text: str) -> set[str]:
    folded = _fold(text)
    expansions = [folded]
    for source, target in QUERY_ALIASES:
        if source in folded:
            expansions.append(target)
    return set(_terms(" ".join(expansions)))


@dataclass(frozen=True)
class RetrievalResult:
    status: str
    chunks: tuple[SourceChunk, ...]
    scores: tuple[float, ...]


class BM25Retriever:
    def __init__(self, chunks: list[SourceChunk], *, k1: float = 1.5, b: float = 0.75):
        self.chunks = tuple(chunks)
        self.k1 = k1
        self.b = b
        self.title_tokens = tuple(_terms(chunk.section_title) for chunk in self.chunks)
        self.body_tokens = tuple(_terms(chunk.text) for chunk in self.chunks)
        self.tokens = tuple(title + body for title, body in zip(self.title_tokens, self.body_tokens, strict=True))
        self.avgdl = sum(map(len, self.tokens)) / len(self.tokens) if self.tokens else 0.0
        self.df: dict[str, int] = {}
        for terms in self.tokens:
            for term in set(terms):
                self.df[term] = self.df.get(term, 0) + 1

    def search(
        self, query: str, *, procedure_version: str, product_category: str,
        at: date, incident_category: str | None = None, top_k: int = 5,
    ) -> RetrievalResult:
        eligible: list[tuple[float, SourceChunk]] = []
        query_terms = _query_terms(query + " " + (incident_category or ""))
        n_docs = max(1, len(self.chunks))
        for chunk, title_terms, body_terms in zip(
            self.chunks, self.title_tokens, self.body_tokens, strict=True
        ):
            if chunk.status != "teaching_approved" or chunk.procedure_version != procedure_version:
                continue
            if product_category not in chunk.product_categories:
                continue
            if chunk.effective_from and at < date.fromisoformat(chunk.effective_from):
                continue
            if chunk.effective_to and at >= date.fromisoformat(chunk.effective_to):
                continue
            body_tf: dict[str, int] = {}
            for term in body_terms:
                body_tf[term] = body_tf.get(term, 0) + 1
            title_tf: dict[str, int] = {}
            for term in title_terms:
                title_tf[term] = title_tf.get(term, 0) + 1
            score = 0.0
            for term in query_terms:
                freq = body_tf.get(term, 0) + TITLE_WEIGHT * title_tf.get(term, 0)
                if not freq:
                    continue
                df = self.df.get(term, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                denom = freq + self.k1 * (1 - self.b + self.b * len(body_terms) / (self.avgdl or 1))
                score += idf * freq * (self.k1 + 1) / denom
            if score > 0:
                eligible.append((score, chunk))
        eligible.sort(key=lambda pair: (-pair[0], pair[1].source_id))
        picked = eligible[:max(1, min(top_k, 10))]
        return RetrievalResult(
            status="sources_found" if picked else "no_applicable_sources",
            chunks=tuple(chunk for _, chunk in picked),
            scores=tuple(round(score, 8) for score, _ in picked),
        )

