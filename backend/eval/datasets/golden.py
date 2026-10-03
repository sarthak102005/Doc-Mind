r"""Golden-question dataset loader (benchmark/golden.jsonl).

Schema per line (one JSON object):
  id               str        unique id matching pattern G\d{2,}, e.g. "G01" to "G32"
  question         str        user question
  expected_answer  str        reference answer from PDF text
  expected_pages   list[int]  1-based page numbers for citations (empty if unanswerable)
  type             str        question category (spec, trap, compare, layout, text,
                              legend, figure, list, inconsistency, unanswerable,
                              image-retrieval)
  notes            str | None optional clarification notes
  document         str        target document file name (default: "sample_1.pdf")
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = REPO_ROOT / "benchmark" / "golden.jsonl"

QuestionType = Literal[
    "spec",
    "trap",
    "compare",
    "layout",
    "text",
    "legend",
    "figure",
    "list",
    "inconsistency",
    "unanswerable",
    "image-retrieval",
]

VALID_TYPES: set[str] = {
    "spec",
    "trap",
    "compare",
    "layout",
    "text",
    "legend",
    "figure",
    "list",
    "inconsistency",
    "unanswerable",
    "image-retrieval",
}


class GoldenQuestion(BaseModel):
    id: str
    question: str
    expected_answer: str = Field(validation_alias="expected_answer")
    expected_pages: list[int] = Field(default_factory=list, validation_alias="expected_pages")
    type: QuestionType
    notes: str | None = None
    document: str = "sample_1.pdf"

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^G\d{2,}$", v):
            raise ValueError(f"id must match pattern 'G\\d{{2,}}', got '{v}'")
        return v

    @property
    def answer(self) -> str:
        """Backward-compatible alias for expected_answer."""
        return self.expected_answer

    @property
    def pages(self) -> list[int]:
        """Backward-compatible alias for expected_pages."""
        return self.expected_pages


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    items: list[GoldenQuestion] = []
    if not path.is_file():
        return items
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            item = GoldenQuestion.model_validate(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{path.name}:{lineno}: {exc}") from exc
        if item.id in seen:
            raise ValueError(f"{path.name}:{lineno}: duplicate id {item.id}")
        seen.add(item.id)
        items.append(item)
    return items
