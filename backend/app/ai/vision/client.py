"""Vision-Language Model (VLM) client for figure understanding and diagram extraction."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class VLMResult(BaseModel):
    """Result from vision-language model diagram analysis."""

    description: str
    model_used: str = ""
    success: bool = True
    error_message: str | None = None


class VLMClient:
    """Client for calling hosted Vision Language Models (e.g. Qwen2.5-VL-72B-Instruct)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.vlm_base_url.rstrip("/")
        self.api_key = self.settings.vlm_api_key.get_secret_value()
        self.model = self.settings.vlm_model or "qwen/qwen2.5-vl-72b-instruct"
        self.timeout = self.settings.vlm_timeout_seconds

    def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        prompt: str | None = None,
    ) -> VLMResult:
        """Call hosted VLM with image data URI to produce diagram description."""
        if not self.base_url or not self.api_key or "your-" in self.api_key:
            logger.warning("VLM is not configured or API key is missing. Skipping description.")
            return VLMResult(
                description="",
                model_used="none",
                success=False,
                error_message="VLM API key not configured",
            )

        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime_type};base64,{encoded_image}"

        user_instruction = (
            prompt
            or "Analyze this figure, diagram, or chart from a technical/academic document. "
            "Describe concisely what it illustrates, including key labels, axes, relationships, data points, or flows."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://docmind.internal",
            "X-Title": "DocMind Document RAG",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_instruction},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": min(self.settings.vlm_max_output_tokens, 512),
            "temperature": 0.1,
        }

        url = f"{self.base_url}/chat/completions"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return VLMResult(
                    description=content.strip(),
                    model_used=self.model,
                    success=True,
                )
        except Exception as exc:
            logger.warning("VLM inference failed for image: %s", exc)
            return VLMResult(
                description="",
                model_used=self.model,
                success=False,
                error_message=str(exc),
            )


_vlm_client: VLMClient | None = None


def get_vlm_client(settings: Settings | None = None) -> VLMClient:
    global _vlm_client
    current = settings or get_settings()
    if _vlm_client is None or _vlm_client.settings != current:
        _vlm_client = VLMClient(current)
    return _vlm_client
