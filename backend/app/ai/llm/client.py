"""LLM generation client supporting ordered fallback chains across OpenAI-compatible providers."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import LLMEndpoint, Settings, get_settings

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    """Result of an LLM generation call with fallback tracking."""

    content: str
    model_used: str
    label_used: str = ""
    fallback_occurred: bool = False
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class LLMAllModelsFailedError(Exception):
    """Raised when all configured models in the fallback chain have failed."""


class LLMClient:
    """Dispatches chat completions with ordered fallback across configured endpoints."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.endpoints = self.settings.llm_endpoints
        self.timeout = self.settings.llm_timeout_seconds
        self.retries_per_model = self.settings.llm_retries_per_model
        self.max_output_tokens = self.settings.llm_max_output_tokens

    def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call LLM with ordered fallback.

        Attempts models in order:
        Endpoint 1 -> Endpoint 2 -> ... -> Endpoint N
        Only switches on transport error, timeout, 429 rate limit, or 5xx server error.
        """
        if not self.endpoints:
            raise LLMAllModelsFailedError("No LLM endpoints configured in LLM_CHAIN")

        formatted_messages: list[dict[str, str]] = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        token_limit = max_tokens or self.max_output_tokens
        attempts_log: list[dict[str, Any]] = []

        for ep_idx, ep in enumerate(self.endpoints):
            is_fallback = ep_idx > 0
            for attempt in range(self.retries_per_model + 1):
                url = f"{ep.base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ep.api_key.get_secret_value()}",
                }
                payload = {
                    "model": ep.model,
                    "messages": formatted_messages,
                    "max_tokens": token_limit,
                    "temperature": 0.1,
                }

                t0 = time.perf_counter()
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.post(url, headers=headers, json=payload)

                    elapsed = time.perf_counter() - t0

                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            msg = choices[0].get("message", {})
                            content = msg.get("content")
                            # If content is None, fallback to reasoning text if present
                            if not content and "reasoning" in msg and msg["reasoning"]:
                                content = msg["reasoning"]

                            if content and content.strip():
                                attempts_log.append({
                                    "endpoint": ep.label,
                                    "model": ep.model,
                                    "status": 200,
                                    "elapsed_s": round(elapsed, 2),
                                    "success": True,
                                })
                                return LLMResponse(
                                    content=content.strip(),
                                    model_used=ep.model,
                                    label_used=ep.label,
                                    fallback_occurred=is_fallback,
                                    attempts=attempts_log,
                                )

                        attempts_log.append({
                            "endpoint": ep.label,
                            "model": ep.model,
                            "status": 200,
                            "error": "Empty content in response",
                            "elapsed_s": round(elapsed, 2),
                            "success": False,
                        })

                    elif resp.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "LLM endpoint '%s' (%s) failed with status %d (attempt %d/%d).",
                            ep.label,
                            ep.model,
                            resp.status_code,
                            attempt + 1,
                            self.retries_per_model + 1,
                        )
                        attempts_log.append({
                            "endpoint": ep.label,
                            "model": ep.model,
                            "status": resp.status_code,
                            "error": resp.text[:200],
                            "elapsed_s": round(elapsed, 2),
                            "success": False,
                        })
                        time.sleep(1.0)
                    else:
                        logger.error(
                            "LLM endpoint '%s' (%s) returned non-retryable error: HTTP %d %s",
                            ep.label,
                            ep.model,
                            resp.status_code,
                            resp.text[:200],
                        )
                        attempts_log.append({
                            "endpoint": ep.label,
                            "model": ep.model,
                            "status": resp.status_code,
                            "error": resp.text[:200],
                            "elapsed_s": round(elapsed, 2),
                            "success": False,
                        })
                        # Break out of attempts for this endpoint and fall back to next
                        break

                except (httpx.TimeoutException, httpx.NetworkError) as err:
                    elapsed = time.perf_counter() - t0
                    logger.warning(
                        "LLM endpoint '%s' network/timeout (%s) on attempt %d/%d.",
                        ep.label,
                        type(err).__name__,
                        attempt + 1,
                        self.retries_per_model + 1,
                    )
                    attempts_log.append({
                        "endpoint": ep.label,
                        "model": ep.model,
                        "status": "network_error",
                        "error": str(err),
                        "elapsed_s": round(elapsed, 2),
                        "success": False,
                    })
                    time.sleep(1.0)

            logger.info("Falling back from '%s' to next model in chain...", ep.label)

        raise LLMAllModelsFailedError(f"All LLM fallback chain endpoints failed: {attempts_log}")


_llm_client: LLMClient | None = None


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    global _llm_client
    current = settings or get_settings()
    if _llm_client is None or _llm_client.settings != current:
        _llm_client = LLMClient(current)
    return _llm_client
