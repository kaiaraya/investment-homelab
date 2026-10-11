import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.browser.auth_driver import KrungsriAuthDriver, auth_driver
from app.browser.session_sentinel import SessionSentinel
from app.core.events import event_bus


@pytest.mark.asyncio
async def test_session_status_endpoint():
    """Tests GET /api/v1/session/status returns correct initial structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/session/status")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "is_authenticated" in data
        assert "session_file_exists" in data
        assert "otp_queue_size" in data


@pytest.mark.asyncio
async def test_session_submit_otp_endpoint():
    """Tests POST /api/v1/session/submit-otp publishes OTP to event queue."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid format (not 6 digits)
        bad_res = await client.post("/api/v1/session/submit-otp", json={"otp": "123"})
        assert bad_res.status_code == 422 or bad_res.status_code == 400

        # Valid 6 digits
        res = await client.post("/api/v1/session/submit-otp", json={"otp": "987654", "ref": "TEST99"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

        # Check queue
        item = await event_bus.otp_queue.get()
        assert item["data"]["otp"] == "987654"
        assert item["data"]["ref"] == "TEST99"


@pytest.mark.asyncio
async def test_session_login_missing_credentials():
    """Tests POST /api/v1/session/login rejects if credentials are empty."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # If env has no credentials and none provided in request
        original_user = settings.KRUNGSRI_USERNAME
        original_pass = settings.KRUNGSRI_PASSWORD
        settings.KRUNGSRI_USERNAME = ""
        settings.KRUNGSRI_PASSWORD = ""
        try:
            res = await client.post("/api/v1/session/login", json={})
            assert res.status_code == 400
            assert "credentials missing" in res.json()["detail"].lower()
        finally:
            settings.KRUNGSRI_USERNAME = original_user
            settings.KRUNGSRI_PASSWORD = original_pass


@pytest.mark.asyncio
async def test_session_logout_endpoint():
    """Tests POST /api/v1/session/logout closes session and resets status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/session/logout")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["status"] == "DISCONNECTED"


@pytest.mark.asyncio
async def test_driver_initial_state():
    """Tests KrungsriAuthDriver default attributes and initial state."""
    driver = KrungsriAuthDriver()
    assert driver.status == "DISCONNECTED"
    assert driver.is_authenticated is False
    assert driver.current_url is None
    assert driver.current_ref is None
