"""Rebuild a deterministic, small JSON index manifest without model downloads."""

from __future__ import annotations

import json
import argparse
from pathlib import Path

from .corpus import load_corpus


def build_index_manifest(corpus_dir: Path) -> dict[str, object]:
    documents, chunks = load_corpus(corpus_dir)
    return {
        "index_version": "bm25-v1",
        "tokenizer": "unicode-word-casefold-v1",
        "scoring": {"algorithm": "BM25", "k1": 1.5, "b": 0.75},
        "documents": [
            {"doc_id": doc.doc_id, "version": doc.version, "status": doc.status,
             "procedure_version": doc.procedure_version, "content_sha256": doc.content_sha256,
             "source_path": doc.source_path}
            for doc in documents
        ],
        "chunks": [
            {"source_id": chunk.source_id, "section_id": chunk.section_id,
             "content_sha256": chunk.content_sha256}
            for chunk in chunks
        ],
    }


def write_index_manifest(corpus_dir: Path, output: Path) -> dict[str, object]:
    manifest = build_index_manifest(corpus_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return manifest


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Rebuild deterministic M6 SOP index manifest")
    parser.add_argument("--corpus", type=Path, default=root / "corpus" / "approved")
    parser.add_argument("--out", type=Path, default=root / "corpus" / "approved" / "manifest.json")
    args = parser.parse_args()
    result = write_index_manifest(args.corpus, args.out)
    print(json.dumps({"document_count": len(result["documents"]),
                      "chunk_count": len(result["chunks"]), "index_version": result["index_version"]},
                     ensure_ascii=False, sort_keys=True))

