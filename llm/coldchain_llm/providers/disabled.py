from __future__ import annotations

from .base import GenerationResult, ProviderError


class DisabledProvider:
    name = "disabled"

    def generate(self, **_: object) -> GenerationResult:
        raise ProviderError("provider_not_configured", retryable=False)

