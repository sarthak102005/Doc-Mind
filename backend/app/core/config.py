"""Typed settings for DocMind.

This is the single place where configuration enters the application. Every
model ID, API key, base URL and provider choice is read from the environment
(or a ``.env`` file). No model names are hard-coded anywhere else: code asks
``get_settings()`` for what it needs.

The LLM fallback chain is declared as ``LLM_CHAIN=1,2,3`` plus a block of
``LLM_<n>_LABEL / _BASE_URL / _API_KEY / _MODEL`` variables per entry. Those
keys are dynamic, so they are parsed separately by :func:`_load_llm_chain`.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py -> repository root is three parents above backend/
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = Path(os.environ.get("DOCMIND_ENV_FILE", REPO_ROOT / ".env"))


class HardwareProfile(StrEnum):
    CPU_8GB = "cpu_8gb"
    CPU_16GB = "cpu_16gb"
    GPU = "gpu"


class VlmMode(StrEnum):
    OFF = "off"
    TRIAGED = "triaged"
    ALL = "all"


class Backend(StrEnum):
    API = "api"
    LOCAL = "local"


class RerankBackend(StrEnum):
    API = "api"
    LOCAL = "local"
    OFF = "off"


class ImageRetrievalMode(StrEnum):
    DESCRIPTIONS_ONLY = "descriptions_only"
    SIGLIP2 = "siglip2"
    BOTH = "both"


class LLMEndpoint(BaseModel):
    """One entry of the ordered LLM fallback chain."""

    index: str
    label: str
    base_url: str
    api_key: SecretStr
    model: str

    def is_configured(self) -> bool:
        key = self.api_key.get_secret_value()
        return bool(self.base_url and self.model and key and not key.startswith("your-"))


def _csv(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list | tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    raise TypeError(f"expected comma-separated string, got {type(value).__name__}")


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime profile -------------------------------------------------
    app_env: str = "dev"
    log_level: str = "INFO"
    dev_lite_mode: bool = True
    hardware_profile: HardwareProfile = HardwareProfile.CPU_8GB
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- auth --------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- data layer --------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "docmind"
    postgres_user: str = "docmind"
    postgres_password: SecretStr = SecretStr("")
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_text_collection: str = "docmind_text"
    qdrant_image_collection: str = "docmind_images"

    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: SecretStr = SecretStr("")
    minio_bucket: str = "docmind"
    minio_secure: bool = False

    health_timeout_seconds: float = 3.0

    # --- LLM chain (entries parsed in _load_llm_chain) ---------------------
    llm_chain_order: CsvList = Field(default_factory=list, validation_alias="LLM_CHAIN")
    llm_timeout_seconds: float = 60.0
    llm_retries_per_model: int = 1
    llm_cooldown_seconds: float = 60.0
    llm_fallback_on: CsvList = Field(default_factory=lambda: ["timeout", "429", "5xx", "invalid_output"])
    llm_max_output_tokens: int = 4096

    # --- vision model ------------------------------------------------------
    vlm_mode: VlmMode = VlmMode.TRIAGED
    vlm_backend: Backend = Backend.API
    vlm_model: str = ""
    vlm_base_url: str = ""
    vlm_api_key: SecretStr = SecretStr("")
    vlm_timeout_seconds: float = 90.0
    vlm_max_calls_per_document: int = 40
    vlm_max_output_tokens: int = 2048

    # --- text embeddings ---------------------------------------------------
    embed_backend: Backend = Backend.API
    embed_model: str = ""
    embed_base_url: str = ""
    embed_api_key: SecretStr = SecretStr("")
    embed_dim: int = 1024
    embed_batch_size: int = Field(default=8, ge=1)

    # --- reranker ----------------------------------------------------------
    rerank_backend: RerankBackend = RerankBackend.API
    rerank_model: str = ""
    rerank_base_url: str = ""
    rerank_api_key: SecretStr = SecretStr("")
    rerank_candidates: int = 20
    rerank_top_n: int = 6

    # --- image embeddings --------------------------------------------------
    image_embed_backend: Backend = Backend.LOCAL
    image_embed_model: str = ""
    image_embed_batch_size: int = Field(default=4, ge=1)
    image_embed_idle_unload_seconds: int = 120
    image_retrieval_mode: ImageRetrievalMode = ImageRetrievalMode.BOTH

    # --- OCR ---------------------------------------------------------------
    ocr_backend: str = "rapidocr_onnx"
    ocr_lang: str = "en"

    # --- ingestion / limits ------------------------------------------------
    max_concurrent_ingestion: int = Field(default=1, ge=1)
    cache_dir: Path = Path(".cache/docmind")
    max_upload_mb: int = 50
    profile_min_text_chars: int = 200
    complex_page_image_ratio: float = Field(default=0.6, ge=0.0, le=1.0)
    doctor_ram_headroom_mb: int = 1024

    # Populated by the model validator below; not read from a single env var.
    # (Named llm_endpoints, not llm_chain, so it cannot collide with LLM_CHAIN.)
    llm_endpoints: list[LLMEndpoint] = Field(default_factory=list, exclude=True)

    @field_validator("cors_origins", "llm_chain_order", "llm_fallback_on", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> list[str]:
        return _csv(value)

    @model_validator(mode="after")
    def _apply_profile_and_chain(self) -> Settings:
        if not self.llm_endpoints:
            self.llm_endpoints = _load_llm_chain(self.llm_chain_order)
        if self.hardware_profile is HardwareProfile.CPU_8GB:
            # A3.1: small, sequential work on the 8 GB machine.
            self.max_concurrent_ingestion = 1
            self.embed_batch_size = min(self.embed_batch_size, 8)
            self.image_embed_batch_size = min(self.image_embed_batch_size, 4)
        return self

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql://{self.postgres_user}:{pw}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cache_path(self) -> Path:
        """Absolute cache directory (relative CACHE_DIR is resolved from the repo root)."""
        return self.cache_dir if self.cache_dir.is_absolute() else REPO_ROOT / self.cache_dir

    @property
    def minio_url(self) -> str:
        scheme = "https" if self.minio_secure else "http"
        return f"{scheme}://{self.minio_endpoint}"


def _env_lookup() -> dict[str, str]:
    """Merge the .env file with the process environment (process env wins)."""
    merged: dict[str, str] = {}
    if ENV_FILE.is_file():
        merged.update({k.upper(): v for k, v in dotenv_values(ENV_FILE).items() if v is not None})
    merged.update({k.upper(): v for k, v in os.environ.items()})
    return merged


def _load_llm_chain(order: list[str]) -> list[LLMEndpoint]:
    env = _env_lookup()
    chain: list[LLMEndpoint] = []
    for idx in order:
        prefix = f"LLM_{idx}_"
        model = env.get(prefix + "MODEL", "")
        base_url = env.get(prefix + "BASE_URL", "")
        if not model or not base_url:
            raise ValueError(f"LLM_CHAIN lists '{idx}' but {prefix}MODEL / {prefix}BASE_URL is empty")
        chain.append(
            LLMEndpoint(
                index=idx,
                label=env.get(prefix + "LABEL", model),
                base_url=base_url,
                api_key=SecretStr(env.get(prefix + "API_KEY", "")),
                model=model,
            )
        )
    return chain


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
