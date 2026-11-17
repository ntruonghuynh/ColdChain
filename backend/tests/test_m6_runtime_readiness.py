"""Readiness reports protocol and schema versions without provider calls."""

from app.core.config import Settings
from app.integrations import llm_adapter
from coldchain_llm.prompts import PROMPT_VERSION
from coldchain_llm.providers.openai_compatible import OpenAICompatibleProvider
from coldchain_llm.retrieval import INDEX_VERSION
from coldchain_llm.schemas import OUTPUT_SCHEMA_VERSION


def test_readiness_exposes_runtime_prompt_schema_retriever_and_adapter_versions(monkeypatch) -> None:
    monkeypatch.setattr(llm_adapter, "load_retriever", lambda: ([object()], object()))
    result = llm_adapter.provider_readiness(Settings(
        llm_provider="disabled", m6_runtime_version="test-runtime-v1",
    ))
    assert result["runtime_version"] == "test-runtime-v1"
    assert result["prompt_version"] == PROMPT_VERSION
    assert len(result["prompt_sha256"]) == 64
    assert result["output_schema_version"] == OUTPUT_SCHEMA_VERSION
    assert len(result["output_schema_sha256"]) == 64
    assert result["provider_adapter_version"] == OpenAICompatibleProvider.version
    assert result["retrieval_version"] == INDEX_VERSION
    assert result["provider_status"] == "not_configured"
