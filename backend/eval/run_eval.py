"""`make eval`: golden-question evaluation.

Phase 0: validates benchmark/golden.jsonl and reports that the answering
pipeline does not exist yet. Exits non-zero so nobody mistakes this for a pass.
The real evaluation (retrieval + generation metrics, baselines) lands in Phase 8.
"""

from __future__ import annotations

import sys

from eval.datasets.golden import GOLDEN_PATH, load_golden


def main() -> int:
    items = load_golden()
    print(f"golden set: {GOLDEN_PATH} -> {len(items)} questions")
    if not items:
        print("FAIL: golden set is empty (Part C table not yet supplied)")
        return 1
    print(f"NOT RUN: answering pipeline not implemented yet. Benchmark status: 0/{len(items)} passing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
