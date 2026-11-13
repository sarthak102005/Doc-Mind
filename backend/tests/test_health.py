"""Health endpoint tests: unit (fake checks) and integration (live docker services)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.services import health as health_mod
from app.services.health import collect_health


async def _ok(_: Settings) -> str:
    return "fine"


async def _boom(_: Settings) -> str:
    raise ConnectionError("refused")


@pytest.mark.unit
async def test_collect_health_all_up() -> None:
    report = await collect_health(get_settings(), {"a": _ok, "b": _ok})
    assert report.status == "ok"
    assert set(report.components) == {"a", "b"}
    assert all(c.status == "up" for c in report.components.values())


@pytest.mark.unit
async def test_collect_health_one_down_is_degraded_and_does_not_raise() -> None:
    report = await collect_health(get_settings(), {"a": _ok, "b": _boom})
    assert report.status == "degraded"
    assert report.components["b"].status == "down"
    assert "ConnectionError" in (report.components["b"].detail or "")


@pytest.mark.unit
def test_health_endpoint_returns_503_when_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_mod, "DEFAULT_CHECKS", {"postgres": _ok, "qdrant": _boom})
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["components"]["qdrant"]["status"] == "down"


@pytest.mark.unit
def test_health_endpoint_lists_the_four_services(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = {name: _ok for name in ("postgres", "qdrant", "redis", "minio")}
    monkeypatch.setattr(health_mod, "DEFAULT_CHECKS", fakes)
    resp = TestClient(create_app()).get("/health")
    assert resp.status_code == 200
    assert set(resp.json()["components"]) == {"postgres", "qdrant", "redis", "minio"}


@pytest.mark.integration
def test_health_live_services_up() -> None:
    """Requires live services. Hits postgres, redis, minio (and qdrant if running)."""
    resp = TestClient(create_app()).get("/health")
    body = resp.json()
    for name in ("postgres", "redis", "minio"):
        assert body["components"][name]["status"] == "up", body
    if body["components"]["qdrant"]["status"] == "down":
        # Qdrant can stay off prior to Phase 3 vector search
        assert body["status"] == "degraded"
        return
    assert resp.status_code == 200, body
    assert body["components"]["qdrant"]["status"] == "up", body
