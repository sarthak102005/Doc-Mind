"""Doctor and golden-dataset tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.core import doctor
from app.core.config import Settings
from eval.datasets.golden import GOLDEN_PATH, VALID_TYPES, load_golden

pytestmark = pytest.mark.unit

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
        json.dumps(
            {
                "id": "G01",
                "question": "q",
                "expected_answer": "a",
                "expected_pages": [11],
                "type": "spec",
            }
        )
        + "\n\n",
        encoding="utf-8",
    )
    items = load_golden(good)
    assert items[0].expected_pages == [11]
    assert items[0].pages == [11]
    assert items[0].answer == "a"
    assert items[0].type == "spec"
    assert items[0].document == "sample_1.pdf"

    # Test loose pattern G\d{2,} accepts higher digit IDs
    good_multi_digit = tmp_path / "g_multi.jsonl"
    good_multi_digit.write_text(
        json.dumps(
            {
                "id": "G105",
                "question": "q",
                "expected_answer": "a",
                "type": "spec",
                "document": "other.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    items_multi = load_golden(good_multi_digit)
    assert items_multi[0].id == "G105"
    assert items_multi[0].document == "other.pdf"

    # Test invalid id pattern (e.g. single digit G1 or non-G prefix)
    bad_id = tmp_path / "bad_id.jsonl"
    bad_id.write_text(
        json.dumps(
            {
                "id": "G1",
                "question": "q",
                "expected_answer": "a",
                "type": "spec",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="G\\\\d\\{2,\\}"):
        load_golden(bad_id)

    dup = tmp_path / "d.jsonl"
    line_dup = json.dumps(
        {
            "id": "G01",
            "question": "q",
            "expected_answer": "a",
            "expected_pages": [11],
            "type": "spec",
        }
    )
    dup.write_text(f"{line_dup}\n{line_dup}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_golden(dup)


def test_repo_golden_file_has_exactly_32_rows_g01_to_g32() -> None:
    assert GOLDEN_PATH.is_file()
    items = load_golden(GOLDEN_PATH)
    sample_1_items = [item for item in items if item.document == "sample_1.pdf"]
    count = len(sample_1_items)
    assert count == 32, f"Expected 32 questions for sample_1.pdf, got {count}"
    expected_ids = [f"G{i:02d}" for i in range(1, 33)]
    actual_ids = [item.id for item in sample_1_items]
    assert actual_ids == expected_ids

    # Validate that all types are valid types and include image-retrieval
    types_found = {item.type for item in sample_1_items}
    assert types_found.issubset(VALID_TYPES)
    assert "image-retrieval" in types_found
    assert "inconsistency" in types_found
    assert "trap" in types_found
    assert "unanswerable" in types_found

    for item in sample_1_items:
        assert item.question.strip()
        assert item.expected_answer.strip()
