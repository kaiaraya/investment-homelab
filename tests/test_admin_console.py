"""
Tests for the Admin Console control endpoints (/api/v1/admin/*)
==============================================================
Covers:
  * Pillar × Broker feature matrix (SSOT: app.core.feature_matrix)
  * Component toggle registry (live values + restart policy)
  * Toggle -> atomic .env write + live in-process settings update
  * Real reload endpoint (os.execv is PATCHED — never replaces the pytest process)
  * 404 for an unknown component key

Anti-Mock note: the real `.env` and the real process image must never be touched by
these tests, so `_write_env_key` and `_exec_reload` are patched and `settings` is restored.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_feature_matrix_endpoint():
    async with _client() as client:
        res = await client.get("/api/v1/admin/feature-matrix")
    assert res.status_code == 200
    data = res.json()
    assert [b["key"] for b in data["brokers"]] == [
        "KRUNGSRI", "LIBERATOR", "CLICK2WIN", "SETTRADE_OPENAPI",
    ]
    pillar_keys = [p["key"] for p in data["pillars"]]
    assert "P1_SESSION" in pillar_keys
    assert "P7_AGENTIC" in pillar_keys
    # Every cell must reference a known status token (keeps UI + payload in sync)
    for pillar in data["pillars"]:
        for broker in data["brokers"]:
            assert pillar["cells"][broker["key"]] in data["status_meta"]
    assert data["status_meta"]["live"]["icon"] == "🟢"


@pytest.mark.asyncio
async def test_components_endpoint_lists_toggles_with_restart_policy():
    async with _client() as client:
        res = await client.get("/api/v1/admin/components")
    assert res.status_code == 200
    data = res.json()
    by_key = {c["key"]: c for c in data["components"]}
    assert {"intraday_scheduler", "dry_run_mode", "line_simulation_mode"} <= set(by_key)
    # Daemons are read at boot -> need reload; safety/LINE flags are per-request -> immediate
    assert by_key["intraday_scheduler"]["restart_required"] is True
    assert by_key["action_exit_dispatcher"]["restart_required"] is True
    assert by_key["dry_run_mode"]["restart_required"] is False
    assert by_key["line_simulation_mode"]["restart_required"] is False
    assert data["trading_mode"] in ("TEST", "LIVE")
    assert {g["key"] for g in data["groups"]} == {"daemons", "safety", "line"}


@pytest.mark.asyncio
async def test_toggle_component_writes_env_and_updates_live_settings():
    original = settings.ENABLE_PROGRESS_NOTIFICATIONS
    written = {}

    def fake_write(key: str, value: str) -> None:
        written[key] = value

    try:
        with patch("app.api.v1.endpoints.admin._write_env_key", side_effect=fake_write):
            async with _client() as client:
                res = await client.post(
                    "/api/v1/admin/components/progress_notifications",
                    json={"enabled": True},
                )
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["restart_required"] is False
        assert written["ENABLE_PROGRESS_NOTIFICATIONS"] == "true"
        # live in-process settings were updated
        assert settings.ENABLE_PROGRESS_NOTIFICATIONS is True
        assert body["component"]["enabled"] is True
    finally:
        settings.ENABLE_PROGRESS_NOTIFICATIONS = original


@pytest.mark.asyncio
async def test_toggle_unknown_component_returns_404():
    async with _client() as client:
        res = await client.post(
            "/api/v1/admin/components/this_key_does_not_exist",
            json={"enabled": True},
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_reload_endpoint_schedules_execv_without_replacing_process():
    with patch("app.api.v1.endpoints.admin._exec_reload") as m_exec:
        async with _client() as client:
            res = await client.post("/api/v1/admin/reload")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["action"] == "RELOAD_SCHEDULED"
    assert body["command"].endswith("--port %d" % body["port"])
    assert "uvicorn" in body["command"]
    assert "app.main:app" in body["command"]
    assert "--reload" not in body["command"]
    # Background task should have invoked the (patched) exec
    assert m_exec.called
