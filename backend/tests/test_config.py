"""Settings module tests: env parsing, LLM chain, cpu_8gb clamps, no hardcoded models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from app.core import config
from app.core.config import HardwareProfile, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point settings at an empty .env and strip DocMind vars from the process env."""
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    for key in list(__import__("os").environ):
        if key.upper().startswith(("LLM_", "VLM_", "EMBED_", "RERANK_", "IMAGE_", "HARDWARE", "MAX_CONC")):
            monkeypatch.delenv(key, raising=False)
    return env_file


def make(env_file: Path, **kwargs: object) -> Settings:
    factory = cast(Any, Settings)
    return cast(Settings, factory(_env_file=env_file, **kwargs))


def test_llm_chain_parsed_in_order(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated_env.write_text(
        "LLM_CHAIN=2,1\n"
        "LLM_1_LABEL=a\nLLM_1_BASE_URL=http://one\nLLM_1_API_KEY=k1\nLLM_1_MODEL=m1\n"
        "LLM_2_LABEL=b\nLLM_2_BASE_URL=http://two\nLLM_2_API_KEY=your-key\nLLM_2_MODEL=m2\n",
        encoding="utf-8",
    )
    s = make(isolated_env)
    assert [e.model for e in s.llm_endpoints] == ["m2", "m1"]
    assert s.llm_endpoints[0].is_configured() is False  # placeholder key
    assert s.llm_endpoints[1].is_configured() is True
    assert s.llm_endpoints[1].api_key.get_secret_value() == "k1"
    assert "k1" not in repr(s.llm_endpoints[1])  # secrets are masked


def test_process_env_overrides_env_file(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated_env.write_text(
        "LLM_CHAIN=1\nLLM_1_BASE_URL=http://file\nLLM_1_MODEL=file-model\n", encoding="utf-8"
    )
    monkeypatch.setenv("LLM_1_MODEL", "env-model")
    s = make(isolated_env)
    assert s.llm_endpoints[0].model == "env-model"


def test_chain_entry_missing_model_is_an_error(isolated_env: Path) -> None:
    isolated_env.write_text("LLM_CHAIN=1\nLLM_1_BASE_URL=http://x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="LLM_1_MODEL"):
        make(isolated_env)


def test_cpu_8gb_clamps_concurrency_and_batches(isolated_env: Path) -> None:
    isolated_env.write_text(
        "HARDWARE_PROFILE=cpu_8gb\nMAX_CONCURRENT_INGESTION=4\nEMBED_BATCH_SIZE=64\nIMAGE_EMBED_BATCH_SIZE=32\n",
        encoding="utf-8",
    )
    s = make(isolated_env)
    assert s.hardware_profile is HardwareProfile.CPU_8GB
    assert s.max_concurrent_ingestion == 1
    assert s.embed_batch_size == 8
    assert s.image_embed_batch_size == 4


def test_defaults_are_dev_lite_cpu_8gb_and_no_model_ids(isolated_env: Path) -> None:
    s = make(isolated_env)
    assert s.dev_lite_mode is True
    assert s.hardware_profile is HardwareProfile.CPU_8GB
    # No model IDs are baked into code: all come from env.
    assert s.vlm_model == "" and s.embed_model == "" and s.rerank_model == "" and s.image_embed_model == ""
    assert s.llm_endpoints == []


def test_env_example_loads_and_has_five_model_chain() -> None:
    factory = cast(Any, Settings)
    s = factory(_env_file=REPO_ROOT / ".env.example")
    labels = [e.label for e in s.llm_endpoints]
    assert labels[0] == "gpt-oss-120b" and len(labels) == 5
    assert s.vlm_model and s.embed_model and s.rerank_model and s.image_embed_model
    assert s.embed_dim == 1024


def test_database_url_built_from_parts(isolated_env: Path) -> None:
    s = make(isolated_env, postgres_user="u", postgres_password="p", postgres_host="h",
             postgres_port=1, postgres_db="d")
    assert s.database_url == "postgresql://u:p@h:1/d"
