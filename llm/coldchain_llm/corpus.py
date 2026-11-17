"""Deterministic Markdown front-matter and section-aware SOP ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SourceDocument:
    doc_id: str
    title: str
    version: str
    status: str
    procedure_version: str
    product_categories: tuple[str, ...]
    effective_from: str | None
    effective_to: str | None
    language: str
    origin: str
    approval_scope: str
    content_sha256: str
    source_path: str


@dataclass(frozen=True)
class SourceChunk:
    source_id: str
    doc_id: str
    title: str
    version: str
    section_id: str
    section_title: str
    text: str
    content_sha256: str
    procedure_version: str
    product_categories: tuple[str, ...]
    effective_from: str | None
    effective_to: str | None
    language: str
    origin: str
    status: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"Missing YAML front matter: {path.name}")
    _, front, body = raw.split("---", 2)
    metadata = yaml.safe_load(front)
    if not isinstance(metadata, dict):
        raise ValueError(f"Front matter must be a mapping: {path.name}")
    body = body.strip() + "\n"
    return metadata, body


def load_corpus(directory: Path) -> tuple[list[SourceDocument], list[SourceChunk]]:
    """Load approved teaching SOPs; duplicate IDs/versions and malformed files fail closed."""
    documents: list[SourceDocument] = []
    chunks: list[SourceChunk] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(directory.glob("*.md"), key=lambda item: item.name):
        metadata, body = _parse_markdown(path)
        required = {
            "doc_id", "title", "version", "status", "procedure_version", "product_categories",
            "language", "origin", "approval_scope",
        }
        missing = required - metadata.keys()
        if missing:
            raise ValueError(f"Missing corpus metadata {sorted(missing)}: {path.name}")
        key = (str(metadata["doc_id"]), str(metadata["version"]))
        if key in seen:
            raise ValueError(f"Duplicate document version: {key}")
        seen.add(key)
        digest = sha256_text(path.read_text(encoding="utf-8"))
        doc = SourceDocument(
            doc_id=key[0], title=str(metadata["title"]), version=key[1], status=str(metadata["status"]),
            procedure_version=str(metadata["procedure_version"]),
            product_categories=tuple(sorted(str(v) for v in metadata["product_categories"])),
            effective_from=str(metadata["effective_from"]) if metadata.get("effective_from") else None,
            effective_to=str(metadata["effective_to"]) if metadata.get("effective_to") else None,
            language=str(metadata["language"]), origin=str(metadata["origin"]),
            approval_scope=str(metadata["approval_scope"]), content_sha256=digest,
            source_path=path.name,
        )
        documents.append(doc)
        section_title: str | None = None
        section_id: str | None = None
        lines: list[str] = []

        def emit() -> None:
            if section_id is None or not "\n".join(lines).strip():
                return
            text = "\n".join(lines).strip()
            chunks.append(SourceChunk(
                source_id=f"{doc.doc_id}@{doc.version}#{section_id}", doc_id=doc.doc_id,
                title=doc.title, version=doc.version, section_id=section_id,
                section_title=section_title or section_id, text=text,
                content_sha256=sha256_text(text), procedure_version=doc.procedure_version,
                product_categories=doc.product_categories, effective_from=doc.effective_from,
                effective_to=doc.effective_to, language=doc.language, origin=doc.origin,
                status=doc.status,
            ))

        for line in body.splitlines():
            match = re.match(r"^##\s+([^\[]+?)\s+\[([A-Z0-9_-]+)\]\s*$", line)
            if match:
                emit()
                section_title, section_id = match.group(1).strip(), match.group(2)
                lines = []
            elif section_id is not None:
                lines.append(line)
        emit()
        if not any(chunk.doc_id == doc.doc_id and chunk.version == doc.version for chunk in chunks):
            raise ValueError(f"Document has no section chunks: {path.name}")
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = {(doc.doc_id, doc.version): doc.content_sha256 for doc in documents}
        for previous in manifest.get("documents", []):
            key = (str(previous["doc_id"]), str(previous["version"]))
            if key not in current:
                raise ValueError(f"A pinned document version was removed: {key}")
            if current[key] != previous["content_sha256"]:
                raise ValueError(f"A pinned document version was modified in place: {key}; add a new version")
    return documents, chunks

