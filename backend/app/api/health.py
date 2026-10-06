"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.services.health import HealthReport, collect_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthReport)
async def health(
    response: Response,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> HealthReport:
    report = await collect_health(settings)
    if report.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
