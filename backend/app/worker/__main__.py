"""Worker entry point placeholder: the ingestion worker arrives in Phase 2."""

from __future__ import annotations

import logging
import time

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    log = logging.getLogger("docmind.worker")
    log.info(
        "worker placeholder started (max_concurrent_ingestion=%s); no jobs until Phase 2",
        settings.max_concurrent_ingestion,
    )
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
