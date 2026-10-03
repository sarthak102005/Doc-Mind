"""Doctor and golden-dataset tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import doctor
from app.core.config import Settings
from eval.datasets.golden import GOLDEN_PATH, load_golden

REPO_ROOT = Path(__file__).resolve().parents[2]


def _example_settings(**overrides: object) -> Settings:
    return Settings(_env_file=REPO_ROOT / ".env.example", **overrides)  # type: ignore[call-arg]


def test_doctor_flags_placeholder_keys() -> None:
    findings = doctor.check_settings(_example_settings())
    warns = [f.message for f in findings if f.level == "WARN"]
    assert any("API key missing/placeholder" in m for m in warns)
    assert not [f for f in findings if f.level == "FAIL"]


def test_doctor_peak_uses_largest_single_stage() -> None:
    hosted, stages = doctor.estimate_peak_mb(_example_settings())
    assert hosted == doctor.BASE_PROCESS_MB + max(stages.values())
    assert "text_embed_bge_m3_local" not in stages  # hosted embeddings by default
    local, _ = doctor.estimate_peak_mb(_example_settings(embed_backend="local"))
    assert local > hosted


def test_golden_loader_validates_schema(tmp_path: Path) -> None:
    good = tmp_path / "g.jsonl"
    good.write_text(
        json.dumps({"id": "G1", "question": "q", "answer": "a", "pages": [11]}) + "\n\n", encoding="utf-8"
    )
    items = load_golden(good)
    assert items[0].pages == [11] and items[0].document == "sample_1.pdf"

    dup = tmp_path / "d.jsonl"
    line_dup = json.dumps({"id": "G1", "question": "q", "answer": "a"})
    dup.write_text(f"{line_dup}\n{line_dup}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_golden(dup)


def test_repo_golden_file_is_valid() -> None:
    assert GOLDEN_PATH.is_file()
    load_golden()  # raises on schema errors
