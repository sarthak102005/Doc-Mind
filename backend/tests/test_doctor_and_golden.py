"""Doctor and golden-dataset tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.core import doctor
from app.core.config import Settings
from eval.datasets.golden import GOLDEN_PATH, VALID_TYPES, load_golden

REPO_ROOT = Path(__file__).resolve().parents[2]


def _example_settings(**overrides: object) -> Settings:
    factory = cast(Any, Settings)
    return cast(Settings, factory(_env_file=REPO_ROOT / ".env.example", **overrides))


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
        json.dumps({
            "id": "G01",
            "question": "q",
            "expected_answer": "a",
            "expected_pages": [11],
            "type": "spec",
        })
        + "\n\n",
        encoding="utf-8",
    )
    items = load_golden(good)
    assert items[0].expected_pages == [11]
    assert items[0].pages == [11]
    assert items[0].answer == "a"
    assert items[0].type == "spec"

    dup = tmp_path / "d.jsonl"
    line_dup = json.dumps({
        "id": "G01",
        "question": "q",
        "expected_answer": "a",
        "expected_pages": [11],
        "type": "spec",
    })
    dup.write_text(f"{line_dup}\n{line_dup}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_golden(dup)


def test_repo_golden_file_has_exactly_32_rows_g01_to_g32() -> None:
    assert GOLDEN_PATH.is_file()
    items = load_golden(GOLDEN_PATH)
    assert len(items) == 32, f"Expected exactly 32 questions, got {len(items)}"
    expected_ids = [f"G{i:02d}" for i in range(1, 33)]
    actual_ids = [item.id for item in items]
    assert actual_ids == expected_ids

    # Validate that all types are valid types and include image-retrieval
    types_found = {item.type for item in items}
    assert types_found.issubset(VALID_TYPES)
    assert "image-retrieval" in types_found
    assert "inconsistency" in types_found
    assert "trap" in types_found
    assert "unanswerable" in types_found

    for item in items:
        assert item.question.strip()
        assert item.expected_answer.strip()
