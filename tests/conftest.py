import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app as fastapi_app
from app.db.models import Base
from app.db.session import get_db
from app.core.config import settings

TEST_DB_PATH = "./test_homelab.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

import app.db.session
import app.browser.trademan_driver
import app.browser.session_sentinel
import app.browser.auth_driver
import app.services.eod_service
import app.services.trade_dispatcher
import app.services.portfolio_overview_service
import app.services.trade_center_service
import app.services.price_negotiation_service
import app.services.market_monitor_service
import app.services.daily_scenario_runner

app.db.session.AsyncSessionLocal = TestingSessionLocal
app.browser.trademan_driver.AsyncSessionLocal = TestingSessionLocal
app.browser.session_sentinel.AsyncSessionLocal = TestingSessionLocal
app.browser.auth_driver.AsyncSessionLocal = TestingSessionLocal
app.services.eod_service.AsyncSessionLocal = TestingSessionLocal
app.services.trade_dispatcher.AsyncSessionLocal = TestingSessionLocal
app.services.portfolio_overview_service.AsyncSessionLocal = TestingSessionLocal
app.services.trade_center_service.AsyncSessionLocal = TestingSessionLocal
app.services.price_negotiation_service.AsyncSessionLocal = TestingSessionLocal
app.services.market_monitor_service.AsyncSessionLocal = TestingSessionLocal
app.services.daily_scenario_runner.AsyncSessionLocal = TestingSessionLocal


@pytest_asyncio.fixture(autouse=True)
async def prepare_test_db():
    """Initializes tables before each test and cleans them up after."""
    from app.services.validator import validator
    from app.browser.auth_driver import auth_driver
    from app.services.action_center_service import action_center_service

    validator.clear_idempotency_cache()
    auth_driver.status = "DISCONNECTED"
    auth_driver.current_ref = None
    auth_driver.last_login_attempt = None
    auth_driver.page = None
    action_center_service.clear_all()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    auth_driver.status = "DISCONNECTED"
    auth_driver.current_ref = None
    auth_driver.last_login_attempt = None
    auth_driver.page = None
    action_center_service.clear_all()


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


fastapi_app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session



@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    return {"X-Homelab-Key": settings.HOMELAB_SECRET_KEY}


@pytest.fixture(autouse=True)
def isolate_external_side_effects(monkeypatch, tmp_path):
    """
    Safety net for ALL tests:
    - LINE runs in simulation mode (no real push to the phone/chat).
    - The KDE Connect singleton never pings the real Mi 10T.
    Individual tests may still patch these objects further.
    """
    from unittest.mock import AsyncMock
    from app.services.kdeconnect_service import kdeconnect_service

    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", True)
    monkeypatch.setattr(kdeconnect_service, "send_critical_alert", AsyncMock(return_value=True))
    yield
