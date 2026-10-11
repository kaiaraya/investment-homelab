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
    numbers in DRY_RUN_MODE.
    """
    with patch.object(settings, "DRY_RUN_MODE", True):
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
    
    # Mock query selectors for EE, Cash, and Realized PnL
    mock_ee = AsyncMock()
    mock_ee.inner_text.return_value = "฿ 452,150.00"
    
    mock_cash = AsyncMock()
    mock_cash.inner_text.return_value = "฿ 120,500.00"

    mock_pnl = AsyncMock()
    mock_pnl.inner_text.return_value = "+ 3,450.50"

    async def mock_query_selector(selector):
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
            with patch.object(trademan_driver, "switch_tab", new_callable=AsyncMock) as mock_tab:
                summary = await trademan_driver.scrape_account_summary()
                mock_tab.assert_awaited_with("portfolio")
                assert summary["excess_equity"] == 452150.00
                assert summary["cash_balance"] == 120500.00
                assert summary["realized_pnl_today"] == 3450.50


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
