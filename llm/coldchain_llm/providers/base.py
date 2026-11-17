from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    content: str
    provider: str
    model: str
    api_version: str | None
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None = None


class LLMProvider(Protocol):
    name: str

    def generate(self, *, model: str, system_prompt: str, user_prompt: str,
                 max_output_tokens: int) -> GenerationResult: ...


class ProviderError(RuntimeError):
    """Sanitized failure; never includes authorization headers or request bodies."""

    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable

