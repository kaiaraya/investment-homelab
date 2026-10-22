# -*- coding: utf-8 -*-
"""Unit tests for the CDP gateway tab manager — routing + per-key lock serialization."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.broker_cdp.manager import _tab_locks, get_tab, lock_for


@pytest.fixture(autouse=True)
def _fresh_locks():
    """Each async test runs on a fresh event loop; an ``asyncio.Lock`` bound to a previous
    loop is unusable, so reset the module-level lock cache around every test."""
    _tab_locks.clear()
    yield
    _tab_locks.clear()


def _make_page(url: str, title: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    return page


def _cdp_stub(pages, pw=None):
    ctx = MagicMock()
    ctx.pages = pages
    pw = pw or MagicMock()
    pw.stop = AsyncMock()
    browser = MagicMock()
    return pw, browser, ctx


# ── lock keying ──────────────────────────────────────────────────────────────


def test_lock_for_same_key_returns_same_lock():
    assert lock_for("kss", "streaming") is lock_for("kss", "streaming")


def test_lock_for_distinct_keys_are_distinct():
    assert lock_for("kss", "streaming") is not lock_for("kss", "sbl")
    assert lock_for("kss", "trade") is not lock_for("liberator", "trade")


def test_lock_key_is_case_and_whitespace_insensitive():
    assert lock_for("KSS", "Streaming") is lock_for(" kss ", " streaming ")


# ── routing ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tab_routes_kss_streaming():
    stream_page = _make_page(
        "https://streaming.settrade.com/realtime/streamingpage.jsp", "Settrade Streaming"
    )
    sso_page = _make_page("https://www.krungsrisecurities.com/member/main.aspx", "KSS Portal")
    pw, browser, ctx = _cdp_stub([sso_page, stream_page])
    fake_connect = AsyncMock(return_value=(pw, browser, ctx))

    with patch("app.services.broker_cdp.manager.connect_cdp", new=fake_connect):
        async with get_tab("kss", "streaming") as page:
            assert page is stream_page

    fake_connect.assert_awaited_once_with("http://127.0.0.1:9333", broker="kss")
    pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_tab_routes_liberator_trade():
    portfolio_page = _make_page("https://webtrade.liberator.co.th/Portfolio", "Liberator Portfolio")
    trade_page = _make_page("https://webtrade.liberator.co.th/Trade", "Liberator Trade & Order")
    pw, browser, ctx = _cdp_stub([portfolio_page, trade_page])
    fake_connect = AsyncMock(return_value=(pw, browser, ctx))

    with patch("app.services.broker_cdp.manager.connect_cdp", new=fake_connect):
        async with get_tab("liberator", "trade") as page:
            assert page is trade_page

    fake_connect.assert_awaited_once_with("http://127.0.0.1:9334", broker="liberator")
    pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_tab_no_tab_found_raises_and_disconnects():
    pw, browser, ctx = _cdp_stub([])
    fake_connect = AsyncMock(return_value=(pw, browser, ctx))

    with patch("app.services.broker_cdp.manager.connect_cdp", new=fake_connect):
        with pytest.raises(RuntimeError):
            async with get_tab("kss", "streaming") as page:  # noqa: F841
                pass

    pw.stop.assert_awaited_once()


# ── serialization ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tab_serializes_concurrent_access_same_key():
    """Two concurrent ``get_tab`` on the same (broker, target) must never overlap."""
    page = _make_page(
        "https://streaming.settrade.com/realtime/streamingpage.jsp", "Settrade Streaming"
    )
    ctx = MagicMock()
    ctx.pages = [page]

    active = 0
    max_active = 0
    calls = 0
    first_entered = asyncio.Event()
    let_first_finish = asyncio.Event()

    async def tracked_connect(cdp_url, broker=""):
        nonlocal active, max_active, calls
        calls += 1
        active += 1
        max_active = max(max_active, active)
        if calls == 1:
            first_entered.set()
            await let_first_finish.wait()  # hold the locked region open for the first caller
        return pw, browser, ctx

    async def tracked_stop():
        nonlocal active
        active -= 1

    pw = MagicMock()
    pw.stop = AsyncMock(side_effect=tracked_stop)
    browser = MagicMock()

    async def body():
        async with get_tab("kss", "streaming") as p:
            assert p is page

    with patch("app.services.broker_cdp.manager.connect_cdp", new=tracked_connect):
        first = asyncio.create_task(body())
        await first_entered.wait()          # first caller is now inside, holding the lock
        second = asyncio.create_task(body())
        await asyncio.sleep(0.05)           # give the second caller a chance to (wrongly) enter
        assert active == 1                  # second caller still blocked on the lock
        let_first_finish.set()
        await asyncio.gather(first, second)

    assert max_active == 1                  # the two callers never overlapped
    assert active == 0


@pytest.mark.asyncio
async def test_get_tab_different_keys_run_concurrently():
    """Different (broker, target) keys hold different locks, so they do not serialize."""
    pages = {
        "streaming": _make_page(
            "https://streaming.settrade.com/realtime/streamingpage.jsp", "Settrade Streaming"
        ),
        "sbl": _make_page("https://www.krungsrisecurities.com/sblweb/MainSBL.aspx", "KSS SBL"),
    }
    ctx = MagicMock()
    ctx.pages = [pages["streaming"], pages["sbl"]]

    entered = 0
    both_entered = asyncio.Event()
    release = asyncio.Event()

    async def tracked_connect(cdp_url, broker=""):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await release.wait()
        return pw, browser, ctx

    pw = MagicMock()
    pw.stop = AsyncMock()
    browser = MagicMock()

    async def body(target):
        async with get_tab("kss", target) as p:
            assert p is pages[target]

    with patch("app.services.broker_cdp.manager.connect_cdp", new=tracked_connect):
        t1 = asyncio.create_task(body("streaming"))
        t2 = asyncio.create_task(body("sbl"))
        await asyncio.wait_for(both_entered.wait(), timeout=1.0)  # both inside their regions
        release.set()
        await asyncio.gather(t1, t2)
