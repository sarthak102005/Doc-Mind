"""`make bench`: ingestion timing / peak-RAM / query-latency benchmark.

Phase 0: placeholder. Phase 8 records per-stage timings and peak RAM for the
benchmark PDFs (A3.1) and end-to-end query latency.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("NOT RUN: benchmark harness is implemented in Phase 8 (needs the ingestion pipeline).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
