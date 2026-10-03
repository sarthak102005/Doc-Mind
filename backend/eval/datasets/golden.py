"""Golden-question dataset loader (benchmark/golden.jsonl).

Schema per line (one JSON object):
  id           str   unique id, e.g. "G01"
  question     str   user question
  answer       str   reference answer (short, human-written)
  must_include list  strings/numbers that a passing answer must contain
  pages        list  1-based pages a correct citation may point to
  category     str   free label (spec_lookup, comparison, figure, inconsistency, ...)
  document     str   benchmark file the question targets (default sample_1.pdf)
  notes        str   optional
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = REPO_ROOT / "benchmark" / "golden.jsonl"


class GoldenQuestion(BaseModel):
    id: str
    question: str
    answer: str
    must_include: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    category: str = "general"
    document: str = "sample_1.pdf"
    notes: str | None = None


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
