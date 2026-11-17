"""Provider boundary for M6; no operational, signing or workflow write capabilities."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from app.core.config import Settings, get_settings
from coldchain_llm.corpus import SourceChunk, load_corpus
from coldchain_llm.providers import DisabledProvider, OpenAICompatibleProvider
from coldchain_llm.retrieval import BM25Retriever
from coldchain_llm.prompts import PROMPT_VERSION
from coldchain_llm.retrieval import INDEX_VERSION
from coldchain_llm.prompts import load_system_prompt
from coldchain_llm.schemas import OUTPUT_SCHEMA_VERSION, strict_explanation_json_schema


@lru_cache(maxsize=1)
def load_retriever() -> tuple[list[SourceChunk], BM25Retriever]:
    configured = get_settings().llm_corpus_dir
    corpus_dir = Path(configured) if configured else Path(__file__).resolve().parents[3] / "llm" / "corpus" / "approved"
    _, chunks = load_corpus(corpus_dir)
    return chunks, BM25Retriever(chunks)


def get_provider(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.llm_provider.casefold() == "disabled":
        return DisabledProvider()
    if settings.llm_provider.casefold() != "openai_compatible":
        raise ValueError("Unsupported LLM_PROVIDER")
    if not settings.llm_api_base_url or not settings.llm_model:
        return DisabledProvider()
    api_key = settings.llm_api_key.get_secret_value() or None
    return OpenAICompatibleProvider(
        base_url=settings.llm_api_base_url,
        api_key=api_key,
        timeout_s=max(1.0, min(float(settings.llm_timeout_s), 120.0)),
        max_retries=settings.llm_max_retries,
    )


def provider_readiness(settings: Settings | None = None) -> dict[str, str | bool | int]:
    settings = settings or get_settings()
    _, prompt_sha256 = load_system_prompt()
    schema_sha256 = hashlib.sha256(json.dumps(
        strict_explanation_json_schema(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    try:
        chunks, _ = load_retriever()
        corpus_ok = bool(chunks)
    except Exception as exc:
        return {"status": "degraded", "retrieval_status": "unavailable",
                "provider_status": "unknown", "detail": type(exc).__name__,
                "runtime_version": settings.m6_runtime_version, "prompt_version": PROMPT_VERSION,
                "prompt_sha256": prompt_sha256, "output_schema_version": OUTPUT_SCHEMA_VERSION,
                "output_schema_sha256": schema_sha256,
                "provider_adapter_version": OpenAICompatibleProvider.version,
                "retrieval_version": INDEX_VERSION}
    try:
        configured = get_provider(settings).name == "openai_compatible"
    except ValueError:
        configured = False
    provider_status = "configured" if configured else "not_configured"
    return {"status": "ok" if corpus_ok else "degraded",
            "retrieval_status": "ready" if corpus_ok else "unavailable",
            "provider_status": provider_status, "chunk_count": len(chunks),
            "runtime_version": settings.m6_runtime_version, "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256, "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "output_schema_sha256": schema_sha256,
            "provider_adapter_version": OpenAICompatibleProvider.version,
            "retrieval_version": INDEX_VERSION, "configured_model": settings.llm_model or ""}

