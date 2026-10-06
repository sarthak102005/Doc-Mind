"""Worker entry point: processes ingestion queue jobs (Phase 1 lifecycle)."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.services.redis_client import pop_ingestion_job
from app.worker.tasks import process_document_stub

logger = logging.getLogger("docmind.worker")


async def run_worker() -> None:
    settings = get_settings()
    logger.info(
        "Worker started (storage=%s, redis=%s, postgres=%s:%s)",
        settings.storage_backend,
        settings.redis_backend,
        settings.postgres_host,
        settings.postgres_port,
    )
    while True:
        try:
            job = await pop_ingestion_job(timeout=1)
            if job:
                doc_id = job.get("document_id")
                if doc_id:
                    logger.info("Worker picked up ingestion job for document %s", doc_id)
                    # Run worker task in threadpool so async loop isn't blocked
                    await asyncio.to_thread(process_document_stub, doc_id)
            else:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in worker job processing: %s", exc)
            await asyncio.sleep(1.0)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker process stopped by KeyboardInterrupt")


if __name__ == "__main__":
    main()
