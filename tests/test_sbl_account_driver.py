import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock

from app.browser.trademan_driver import trademan_driver
from app.core.config import settings
from app.db.models import SBLBorrowLot, Order, Position
from app.schemas.order import OrderSide
from app.services.eod_service import eod_service
from app.services.trade_dispatcher import trade_dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_scrape_account_summary_dry_run():
    """
    Verifies that scrape_account_summary() returns expected structure and
    numbers in DRY_RUN_MODE when no browser page is attached.

    NB: the 500_000 placeholder is returned only when ``self.page is None``. Real-browser
    tests in this suite persist ``data/session_state.json`` (untracked local artifact), so
    the page must be forced to None here — otherwise the driver restores the live session
    and scrapes real DOM numbers, making this assertion environment-dependent.
    """
    with patch.object(settings, "DRY_RUN_MODE", True):
        with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
            with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=None):
                summary = await trademan_driver.scrape_account_summary()
    assert "excess_equity" in summary
    assert "cash_balance" in summary
    assert "realized_pnl_today" in summary
    assert summary["excess_equity"] == 500_000.0
    assert summary["cash_balance"] == 500_000.0
    assert summary["realized_pnl_today"] == 0.0


@pytest.mark.asyncio
async def test_scrape_account_summary_live_dom():
    """
    Verifies that scrape_account_summary() correctly queries and parses
    DOM text values in Live mode.
    """
    mock_page = AsyncMock()
    
    mock_page.url = "https://trademan.in.th/Portfolio"

    # Mock query selectors for EE, Cash, and Realized PnL
    mock_ee = AsyncMock()
    mock_ee.inner_text.return_value = "฿ 452,150.00"
    
    mock_cash = AsyncMock()
    mock_cash.inner_text.return_value = "฿ 120,500.00"

    mock_pnl = AsyncMock()
    mock_pnl.inner_text.return_value = "+ 3,450.50"

    # RCA-009: the authenticated marker = the account div renders a 7-digit account number.
    mock_acc = AsyncMock()
    mock_acc.inner_text.return_value = "3024959"

    async def mock_query_selector(selector):
        if "dropDownAccountPort" in selector:
            return mock_acc
        if "excess-equity" in selector or "Excess Equity" in selector:
            return mock_ee
        if "cash-balance" in selector or "Cash Balance" in selector or "Line Available" in selector:
            return mock_cash
        if "realized-pnl-today" in selector or "Realized P/L" in selector:
            return mock_pnl
        return None

    mock_page.query_selector.side_effect = mock_query_selector

    with patch.object(settings, "DRY_RUN_MODE", False):
        with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=mock_page):
            with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
                with patch.object(trademan_driver, "switch_tab", new_callable=AsyncMock) as mock_tab:
                    with patch.object(trademan_driver, "_log_event", new_callable=AsyncMock):
                        summary = await trademan_driver.scrape_account_summary()
                        mock_tab.assert_awaited_with("portfolio")
                        assert summary["excess_equity"] == 452150.00
                        assert summary["cash_balance"] == 120500.00
                        assert summary["realized_pnl_today"] == 3450.50
                        assert summary["authenticated"] is True


@pytest.mark.asyncio
async def test_scrape_account_summary_signin_page_returns_none():
    """RCA-009: reading a /SignIn page must return None for every field — never 0.0 (Anti-Mock)."""
    mock_page = AsyncMock()
    mock_page.url = "https://trademan.in.th/SignIn"

    with patch.object(settings, "DRY_RUN_MODE", False):
        with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=mock_page):
            with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
                with patch.object(trademan_driver, "switch_tab", new_callable=AsyncMock):
                    with patch.object(trademan_driver, "_log_event", new_callable=AsyncMock):
                        summary = await trademan_driver.scrape_account_summary()
                        assert summary["authenticated"] is False
                        assert summary["excess_equity"] is None
                        assert summary["cash_balance"] is None
                        assert summary["realized_pnl_today"] is None
                        assert summary["total_equity"] is None


@pytest.mark.asyncio
async def test_scrape_account_summary_missing_selectors_returns_none():
    """RCA-009: an authenticated page whose summary selectors all miss must yield None per
    field. The old body-text regex fallback fabricated values — it is deliberately removed."""
    mock_page = AsyncMock()
    mock_page.url = "https://trademan.in.th/Portfolio"

    mock_acc = AsyncMock()
    mock_acc.inner_text.return_value = "3024952"

    async def mock_query_selector(selector):
        if "dropDownAccountPort" in selector:
            return mock_acc
        return None  # every summary selector misses

    mock_page.query_selector.side_effect = mock_query_selector

    with patch.object(settings, "DRY_RUN_MODE", False):
        with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=mock_page):
            with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
                with patch.object(trademan_driver, "switch_tab", new_callable=AsyncMock):
                    with patch.object(trademan_driver, "_log_event", new_callable=AsyncMock):
                        summary = await trademan_driver.scrape_account_summary()
                        assert summary["authenticated"] is True
                        assert summary["excess_equity"] is None
                        assert summary["cash_balance"] is None
                        assert summary["total_equity"] is None


@pytest.mark.asyncio
async def test_scrape_account_summary_no_page_returns_none_not_zero():
    """RCA-009: no live page (not DRY_RUN) -> None everywhere (never 0.0) so the card can say อ่านไม่ได้."""
    with patch.object(settings, "DRY_RUN_MODE", False):
        with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=None):
            with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
                summary = await trademan_driver.scrape_account_summary()
                assert summary["authenticated"] is False
                assert summary["excess_equity"] is None
                assert summary["cash_balance"] is None


@pytest.mark.asyncio
async def test_execute_sbl_borrow_dry_run_success(db_session: AsyncSession):
    """
    Verifies that execute_sbl_borrow() in DRY_RUN_MODE:
    1. Checks inventory availability.
    2. Simulates borrowing and returns lot_id.
    3. Persists SBLBorrowLot record into SQLite database.
    """
    with patch.object(settings, "DRY_RUN_MODE", True):
        with patch.object(trademan_driver, "scrape_sbl_available_inventory", return_value=50_000):
            res = await trademan_driver.execute_sbl_borrow("BCH", 5000, pin="123456")
            assert res["success"] is True
            assert res["status"] == "SIMULATED_BORROWED"
            assert res["symbol"] == "BCH"
            assert res["borrowed_qty"] == 5000
            assert "SBL-SIM-" in res["lot_id"]

            # Verify saved in DB
            stmt = select(SBLBorrowLot).where(SBLBorrowLot.symbol == "BCH")
            db_res = await db_session.execute(stmt)
            lot = db_res.scalars().first()
            assert lot is not None
            assert lot.borrow_qty == 5000
            assert lot.remaining_qty == 5000
            assert lot.status == "ACTIVE"


@pytest.mark.asyncio
async def test_execute_sbl_borrow_insufficient_stock_rejection(db_session: AsyncSession):
    """
    Verifies strict guardrail: If available SBL pool is less than requested volume,
    or 0, the operation is immediately aborted and rejected.
    """
    with patch.object(trademan_driver, "scrape_sbl_available_inventory", return_value=1_000):
        res = await trademan_driver.execute_sbl_borrow("PR9", 5000, pin="123456")
        assert res["success"] is False
        assert res["status"] == "ABORTED_INSUFFICIENT_SBL"
        assert res["symbol"] == "PR9"
        assert res["requested_volume"] == 5000
        assert res["available_inventory"] == 1000
        assert "มีไม่เพียงพอ" in res["error"]


@pytest.mark.asyncio
async def test_eod_service_incorporates_scraped_account_summary(db_session: AsyncSession):
    """
    Verifies that eod_service integrates live scraped account summary (EE and Cash)
    when trade_dispatcher is in LIVE mode.
    """
    mock_summary = {
        "excess_equity": 680_000.0,
        "cash_balance": 250_000.0,
        "realized_pnl_today": 8_500.0,
        "total_equity": 930_000.0
    }

    with patch.object(type(trade_dispatcher), "is_live", new_callable=PropertyMock, return_value=True):
        with patch.object(trademan_driver, "scrape_account_summary", return_value=mock_summary):
            report = await eod_service.run_eod_summary(db=db_session)
            assert report.excess_equity_thb == 680_000.0
            assert report.cash_balance_thb == 250_000.0
            assert report.realized_pnl_thb == 8_500.0


# ==========================================
# RCA-006a: switch_account — exact dropdown option + post-click verification
# ==========================================

@pytest.fixture(autouse=True)
def _isolate_driver_account_state():
    """switch_account() mutates the driver singleton — restore it after every test here."""
    saved = (trademan_driver.active_account_no, trademan_driver.active_account_type)
    yield
    trademan_driver.active_account_no, trademan_driver.active_account_type = saved

def _make_switch_page(current, option_visible=True, post_click=None, dropdown=True):
    """Build an AsyncMock page emulating #dropDownAccountPort (runbook DOM).

    Structure per learned_workflows/krungsri/trademan_portfolio_dom.md:
    - current account: `#dropDownAccountPort > div.flex.w-full.justify-between > div`
    - option list:     `#dropDownAccountPort div.absolute span:text-is("<acc>")`
    """
    rec = {"current": current, "option_selector": None, "option_clicks": 0}

    header_el = AsyncMock()
    header_el.inner_text.side_effect = lambda: f"Trading A/C {rec['current']}"

    account_btn = AsyncMock()
    option_el = AsyncMock()

    async def _click_option():
        rec["option_clicks"] += 1
        if post_click is not None:
            rec["current"] = post_click

    option_el.click.side_effect = _click_option

    page = AsyncMock()
    # `page.is_closed()` is sync in Playwright. On an AsyncMock it returns a (truthy)
    # coroutine, which would send switch_account() down the "no browser" branch.
    page.is_closed = MagicMock(return_value=False)

    async def _query_selector(selector):
        if selector.startswith("#dropDownAccountPort > div.flex"):
            return header_el
        return None

    async def _wait_for_selector(selector, state=None, timeout=None):
        if selector == "#dropDownAccountPort":
            return account_btn if dropdown else None
        if "div.absolute span:text-is" in selector:
            rec["option_selector"] = selector
            if option_visible:
                return option_el
            raise TimeoutError("option span not visible")
        return None

    page.query_selector.side_effect = _query_selector
    page.wait_for_selector.side_effect = _wait_for_selector
    return page, rec


async def _run_switch(mock_page, account_type):
    """Run switch_account() with login/OTP/popup paths patched out (Invariant 9: no real OTP)."""
    with patch.object(trademan_driver, "ensure_authenticated_trademan", new_callable=AsyncMock, return_value=mock_page):
        with patch.object(trademan_driver, "switch_tab", new_callable=AsyncMock):
            with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new_callable=AsyncMock):
                return await trademan_driver.switch_account(account_type)


@pytest.mark.asyncio
async def test_switch_account_clicks_exact_option_and_verifies():
    """RCA-006a: CASH switch must click the exact runbook span and only then report success."""
    cash_no = settings.TRADEMAN_ACCOUNT_NO_CASH
    margin_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN
    mock_page, rec = _make_switch_page(margin_no, post_click=cash_no)

    res = await _run_switch(mock_page, "CASH")

    assert rec["option_selector"] == f'#dropDownAccountPort div.absolute span:text-is("{cash_no}")'
    assert rec["option_clicks"] == 1
    assert res["success"] is True
    assert res["status"] == "AUTHENTICATED_AND_SWITCHED"
    assert res["account_no"] == cash_no
    assert trademan_driver.active_account_no == cash_no
    assert trademan_driver.active_account_type == "CASH"


@pytest.mark.asyncio
async def test_switch_account_already_on_target_skips_click():
    """RCA-006a: current account already matches -> no option click, still verified as success."""
    cash_no = settings.TRADEMAN_ACCOUNT_NO_CASH
    mock_page, rec = _make_switch_page(cash_no)

    res = await _run_switch(mock_page, "CASH")

    assert rec["option_clicks"] == 0
    assert res["success"] is True
    assert res["account_no"] == cash_no


@pytest.mark.asyncio
async def test_switch_account_missing_option_returns_failure():
    """RCA-006a: target option absent from the dropdown -> ACCOUNT_SWITCH_FAILED (no fake success)."""
    mock_page, rec = _make_switch_page(settings.TRADEMAN_ACCOUNT_NO_MARGIN, option_visible=False)

    res = await _run_switch(mock_page, "CASH")

    assert rec["option_clicks"] == 0
    assert res["success"] is False
    assert res["status"] == "ACCOUNT_SWITCH_FAILED"
    assert "account_no" not in res
    mock_page.keyboard.press.assert_awaited_with("Escape")


@pytest.mark.asyncio
async def test_switch_account_unverified_switch_returns_failure():
    """RCA-006a: click happened but the DOM shows another account -> refuse to report success."""
    mock_page, rec = _make_switch_page("3024959", post_click="9999999")

    res = await _run_switch(mock_page, "CASH")

    assert rec["option_clicks"] == 1
    assert res["success"] is False
    assert res["status"] == "ACCOUNT_SWITCH_FAILED"
    assert res["current_account_no"] == "9999999"
    assert "account_no" not in res


@pytest.mark.asyncio
async def test_switch_account_missing_dropdown_returns_failure():
    """RCA-006a: no #dropDownAccountPort -> ACCOUNT_SWITCH_FAILED (used to be a fake success)."""
    mock_page, _ = _make_switch_page(settings.TRADEMAN_ACCOUNT_NO_MARGIN, dropdown=False)

    res = await _run_switch(mock_page, "MARGIN")

    assert res["success"] is False
    assert res["status"] == "ACCOUNT_SWITCH_FAILED"
    assert "account_no" not in res

