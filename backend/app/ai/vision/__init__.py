"""Vision-model interface, configured by VLM_* settings."""

from app.ai.vision.client import VLMClient, VLMResult, get_vlm_client

__all__ = ["VLMClient", "VLMResult", "get_vlm_client"]
