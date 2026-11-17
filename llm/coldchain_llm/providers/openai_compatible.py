"""Minimal OpenAI Chat Completions-compatible client, including local endpoints."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .base import GenerationResult, ProviderError
from ..schemas import strict_explanation_json_schema

MAX_RESPONSE_BYTES = 1_000_000


class OpenAICompatibleProvider:
    name = "openai_compatible"
    version = "openai-chat-completions/v1"

    def __init__(self, *, base_url: str, api_key: str | None, timeout_s: float, max_retries: int = 1):
        parts = urlsplit(base_url)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password or parts.query:
            raise ValueError("LLM_API_BASE_URL must use http or https")
        if not base_url.endswith("/"):
            base_url += "/"
        self.url = base_url + "chat/completions"
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max(0, min(max_retries, 2))

    def generate(self, *, model: str, system_prompt: str, user_prompt: str,
                 max_output_tokens: int) -> GenerationResult:
        request_body: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model == "gpt-6-luna":
            # Luna supports strict Structured Outputs. Keep model-specific so
            # generic OpenAI-compatible endpoints retain their JSON-mode shape.
            request_body["max_completion_tokens"] = max_output_tokens
            request_body["reasoning_effort"] = "none"
            request_body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "coldchain_incident_explanation",
                    "strict": True,
                    "schema": strict_explanation_json_schema(),
                },
            }
        else:
            request_body["max_tokens"] = max_output_tokens
            request_body["response_format"] = {"type": "json_object"}
        payload = json.dumps(request_body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=payload, headers=headers, method="POST")
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ProviderError("provider_response_too_large", retryable=False)
                data = json.loads(body)
                choice = data["choices"][0]
                content = choice["message"]["content"]
                if isinstance(content, list):
                    content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
                if not isinstance(content, str) or not content:
                    raise ProviderError("provider_empty_response", retryable=False)
                usage = data.get("usage") or {}
                return GenerationResult(
                    content=content, provider=self.name, model=str(data.get("model") or model),
                    api_version=response.headers.get("openai-version"),
                    input_tokens=_int_or_none(usage.get("prompt_tokens", usage.get("input_tokens"))),
                    output_tokens=_int_or_none(usage.get("completion_tokens", usage.get("output_tokens"))),
                    finish_reason=(choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None),
                )
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if retryable and attempt < self.max_retries:
                    time.sleep(min(0.25 * (2**attempt), 1.0))
                    continue
                raise ProviderError(f"provider_http_{exc.code}", retryable=retryable) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < self.max_retries:
                    time.sleep(min(0.25 * (2**attempt), 1.0))
                    continue
                raise ProviderError("provider_unavailable", retryable=True) from None
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                raise ProviderError("provider_invalid_response", retryable=False) from None
        raise ProviderError("provider_unavailable", retryable=True)


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else None

