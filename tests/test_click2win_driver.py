import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.config import settings
from app.browser.click2win_driver import click2win_driver, Click2WinDriver
from app.browser.click2win_auth_driver import click2win_auth_driver, Click2WinAuthDriver
from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.services.workflow_engine import workflow_engine


def test_detect_account_type_for_symbol():
    """Verifies auto-detection of Equity vs Derivatives accounts from symbol."""
    # Equity stocks
    assert Click2WinDriver.detect_account_type_for_symbol("PTT") == "EQUITY"
    assert Click2WinDriver.detect_account_type_for_symbol("CPALL") == "EQUITY"
    assert Click2WinDriver.detect_account_type_for_symbol("DELTA") == "EQUITY"
    assert Click2WinDriver.detect_account_type_for_symbol("TRUE") == "EQUITY"

    # TFEX derivatives
    assert Click2WinDriver.detect_account_type_for_symbol("S50M24") == "DERIVATIVES"
    assert Click2WinDriver.detect_account_type_for_symbol("S50U24") == "DERIVATIVES"
    assert Click2WinDriver.detect_account_type_for_symbol("GOH24") == "DERIVATIVES"
    assert Click2WinDriver.detect_account_type_for_symbol("USDM24") == "DERIVATIVES"


def test_broker_factory_dispatch():
    """Verifies that BrokerFactory switches between Click2Win and TradeMan drivers cleanly."""
    with patch.object(settings, "TRADING_PLATFORM", "CLICK2WIN"):
        driver = get_broker_driver()
        auth = get_auth_driver()
        assert isinstance(driver, Click2WinDriver)
        assert isinstance(auth, Click2WinAuthDriver)

    with patch.object(settings, "TRADING_PLATFORM", "TRADEMAN"):
        from app.browser.trademan_driver import TradeManDriver
        from app.browser.auth_driver import KrungsriAuthDriver
        driver = get_broker_driver()
        auth = get_auth_driver()
        assert isinstance(driver, TradeManDriver)
        assert isinstance(auth, KrungsriAuthDriver)


@pytest.mark.asyncio
async def test_click2win_scrape_accounts_summary():
    """Verifies account discovery returning both Equity and Derivatives accounts."""
    summary = await click2win_driver.scrape_accounts_summary()
    assert "accounts" in summary
    assert len(summary["accounts"]) >= 2

    types = [a["account_type"] for a in summary["accounts"]]
    assert "EQUITY" in types
    assert "DERIVATIVES" in types

    for acc in summary["accounts"]:
        assert "line_available" in acc
        assert "cash_balance" in acc
        assert "total_equity" in acc
        assert acc["line_available"] > 0


@pytest.mark.asyncio
async def test_click2win_execute_order_equity():
    """Verifies that Click2Win executes and directly submits simulated orders."""
    res = await click2win_driver.execute_order(
        symbol="PTT",
        side="BUY",
        volume=100,
        price=34.00
    )
    assert res["success"] is True
    assert res["status"] == "SUBMITTED"
    assert "broker_order_no" in res
    assert res["broker_order_no"].startswith("C2W-")
    assert res["account_type"] == "EQUITY"


@pytest.mark.asyncio
async def test_click2win_order_validation_rejection():
    """Verifies rejection of invalid board lot."""
    res = await click2win_driver.execute_order(
        symbol="PTT",
        side="BUY",
        volume=99,  # Odd-lot, invalid board lot
        price=34.00
    )
    assert res["success"] is False
    assert res["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_click2win_modify_order():
    """Verifies price adjustment in Click2Win."""
    res = await click2win_driver.modify_order_price(
        broker_order_no="C2W-ORD-1",
        symbol="PTT",
        side="BUY",
        new_price=34.25
    )
    assert res["success"] is True
    assert res["status"] == "MODIFIED"
    assert res["new_price"] == 34.25


def test_workflow_engine_self_annealing():
    """Verifies that WorkflowEngine can self-anneal and update a step's selector in markdown."""
    wf_name = "click2win_order_submit"
    spec = workflow_engine.parse_workflow_spec(wf_name)
    assert spec is not None
    assert len(spec["steps"]) >= 6

    # Test self-annealing step 6 (Submit button)
    new_sel = "button.btn-submit-click2win-new"
    res = workflow_engine.update_workflow_step(
        name=wf_name,
        step_num=6,
        new_selector=new_sel,
        explanation="Settrade UI updated submit button class"
    )
    assert res["success"] is True
    assert res["new_selector"] == new_sel

    # Re-parse to verify persistence
    updated_spec = workflow_engine.parse_workflow_spec(wf_name)
    step6 = next(s for s in updated_spec["steps"] if s["step"] == 6)
    assert step6["selector"] == new_sel
    assert "Self-Annealed" in step6["description"]
