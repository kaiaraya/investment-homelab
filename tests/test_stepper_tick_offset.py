# -*- coding: utf-8 -*-
"""Unit tests for P.4c Support Stepper (+/-) Price Adjustment & Tick Offset."""
import os
import pytest
from unittest.mock import AsyncMock

from app.core.config import settings
from app.browser.streaming_driver import (
    StreamingDriver,
    PRICE_STEPPER_PLUS_SELECTOR,
    PRICE_STEPPER_MINUS_SELECTOR,
)
from app.brokers.liberator.driver import LiberatorDriver
from scripts.broker_cdp.js_runner import (
    adjust_price_by_ticks,
    calculate_offset_price,
)


def test_adjust_price_by_ticks_set_spreads():
    # Sub-2 THB (tick 0.01)
    assert adjust_price_by_ticks(1.50, 1) == 1.51
    assert adjust_price_by_ticks(1.50, -1) == 1.49
    assert adjust_price_by_ticks(1.99, 1) == 2.00

    # 2.00 - 5.00 (tick 0.02)
    assert adjust_price_by_ticks(2.00, 1) == 2.02
    assert adjust_price_by_ticks(2.00, -1) == 1.99
    assert adjust_price_by_ticks(4.98, 1) == 5.00

    # 5.00 - 10.00 (tick 0.05)
    assert adjust_price_by_ticks(5.00, 1) == 5.05
    assert adjust_price_by_ticks(6.75, 1) == 6.80
    assert adjust_price_by_ticks(6.75, -1) == 6.70

    # 10.00 - 25.00 (tick 0.10)
    assert adjust_price_by_ticks(12.70, 1) == 12.80
    assert adjust_price_by_ticks(12.70, -1) == 12.60

    # 25.00 - 100.00 (tick 0.25)
    assert adjust_price_by_ticks(34.00, 1) == 34.25
    assert adjust_price_by_ticks(34.00, -1) == 33.75
    assert adjust_price_by_ticks(34.00, 2) == 34.50


def test_calculate_offset_price_passive_aggressive():
    quote = {
        "symbol": "PTT",
        "bid_1": 34.00,
        "offer_1": 34.25,
        "last": 34.00,
    }

    # BUY: passive = Bid - 1 tick (33.75)
    buy_pass = calculate_offset_price(quote, side="BUY", offset_mode="passive", ticks=1)
    assert buy_pass == 33.75

    # BUY: aggressive = Ask + 1 tick (34.50)
    buy_agg = calculate_offset_price(quote, side="BUY", offset_mode="aggressive", ticks=1)
    assert buy_agg == 34.50

    # SELL: passive = Ask + 1 tick (34.50)
    sell_pass = calculate_offset_price(quote, side="SELL", offset_mode="passive", ticks=1)
    assert sell_pass == 34.50

    # SELL: aggressive = Bid - 1 tick (33.75)
    sell_agg = calculate_offset_price(quote, side="SELL", offset_mode="aggressive", ticks=1)
    assert sell_agg == 33.75


class FakeLocator:
    def __init__(self, page, selector, visible=True):
        self.page = page
        self.selector = selector
        self._visible = visible

    @property
    def first(self):
        return self

    def filter(self, **kw):
        return FakeLocator(self.page, self.selector, visible=False)

    async def fill(self, value):
        self.page.filled[self.selector] = value

    async def input_value(self):
        return self.page._input_values.get(self.selector, self.page.filled.get(self.selector))

    async def is_visible(self):
        return self._visible

    async def is_enabled(self):
        return True

    async def click(self, **kw):
        self.page.clicks.append(self.selector)

    async def count(self):
        return 1 if self._visible else 0

    async def check(self):
        self.page.clicks.append(f"{self.selector}:check")


class FakePage:
    def __init__(self, input_values=None):
        self.url = "https://webtrade.liberator.co.th/Portfolio"
        self.clicks = []
        self.filled = {}
        self._input_values = input_values or {}

    def is_closed(self):
        return False

    def locator(self, selector):
        return FakeLocator(self, selector)

    def get_by_role(self, role, **kw):
        return FakeLocator(self, f"role:{role}")

    async def wait_for_timeout(self, ms):
        pass


@pytest.mark.asyncio
async def test_liberator_execute_order_stepper_clicks(monkeypatch):
    drv = LiberatorDriver()
    page = FakePage(input_values={"#price": "6.85"})
    drv.page = page
    drv._log_event = AsyncMock()
    monkeypatch.setattr(drv, "connect_cdp", AsyncMock(return_value=True))
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    monkeypatch.setattr(
        drv,
        "scrape_portfolio",
        AsyncMock(return_value={"orders": [{"symbol": "TU", "side": "BUY", "price": 6.85}]}),
    )

    # When bypass_dry_run=True, tick_offset=2
    res = await drv.execute_order(
        symbol="TU",
        side="BUY",
        volume=100,
        price=6.75,
        pin="123456",
        bypass_dry_run=True,
        tick_offset=2,
    )

    assert res["success"] is True
    plus_clicks = [c for c in page.clicks if c == drv.LIB_PRICE_STEPPER_PLUS]
    assert len(plus_clicks) == 2
    assert page.filled["#price"] == "6.75"
