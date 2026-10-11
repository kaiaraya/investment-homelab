"""
Unit tests for LiberatorDriver.change_order() — in-place order amendment (ต่อราคา).

Pins the selectors proven live on 2026-10-09 against order #11894
(BCH SELL 12.00 x 4,000 in `#OrderTableList`):

  * LIB-RCA-016 — the row must be anchored on the checkbox id, never a \\b-regex over the
                  row text: this table's textContent has NO whitespace between cells
                  ("1189410:03:21BCHSELL12.004,00004,0000Open ...") so \\b never matches.
  * LIB-RCA-017 — `#volume` / `#price` / `#pin` exist TWICE in the DOM (Buy/Sell footer
                  first, amend overlay second) ⇒ the amend fields must be scoped inside
                  `div.overlay`, otherwise the footer form is filled instead.
  * Anti-Mock (Invariant 1) — success is only reported after the order table confirms the
                  new price on the SAME order number.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.brokers.liberator.driver import LiberatorDriver

# Real cell strings captured from the live grid (scripts/liberator/probe_order_change_ui.py)
LIVE_CELLS = [
    "11894", "10:03:21", "BCH", "SELL", "12.00", "4,000",
    "0", "4,000", "0", "Open", "Change Detail Cancel",
]
ORDER_NO = "11894"


class FakeLocator:
    """Minimal Playwright Locator stand-in that records fill()/click() calls."""

    def __init__(self, name="loc", count=1, texts=None, children=None, last=None, log=None):
        self.name = name
        self._count = count
        self._texts = list(texts or [])
        self.children = dict(children or {})
        self._last = last
        self.log = log if log is not None else []
        self.filled = []
        self.clicks = 0

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self._last if self._last is not None else self

    async def count(self):
        return self._count

    async def all_inner_texts(self):
        return list(self._texts)

    async def fill(self, value):
        self.filled.append(value)
        self.log.append((self.name, "fill", value))

    async def click(self):
        self.clicks += 1
        self.log.append((self.name, "click", None))

    def _fallback(self, label):
        return FakeLocator(f"{self.name}>{label}", count=0, log=self.log)

    def locator(self, selector):
        return self.children.get(selector, self._fallback(selector))

    def get_by_text(self, text, exact=False):
        return self.children.get(("text", text), self._fallback(f"text={text}"))

    def filter(self, has_text=None):
        return self.children.get(("filter", has_text), self._fallback(f"filter={has_text}"))


class FakePage:
    """Minimal Page stand-in served with a `selector -> FakeLocator` map."""

    def __init__(self, locators, url="https://webtrade.liberator.co.th/Portfolio"):
        self._locators = dict(locators)
        self.url = url
        self.log = []
        self.waits = []

    def locator(self, selector):
        return self._locators.get(selector, FakeLocator(f"page>{selector}", count=0, log=self.log))

    async def goto(self, url, **kwargs):
        self.url = url
        self.log.append(("goto", url))

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def wait_for_selector(self, selector, timeout=None):
        self.log.append(("wait_for_selector", selector))
        return FakeLocator(selector, log=self.log)

    def is_closed(self):
        return False


def _build_page(cells=None, status="Open", change_available=True, order_present=True):
    """Wires a FakePage that mirrors the live order row + amend overlay structure."""
    log = []
    row_cells = list(cells if cells is not None else LIVE_CELLS)
    if status != row_cells[9]:
        row_cells[9] = status

    overlay = FakeLocator("overlay", count=1, log=log)
    overlay.children = {
        "#volume": FakeLocator("overlay#volume", count=1, log=log),
        "#price": FakeLocator("overlay#price", count=1, log=log),
        "#pin": FakeLocator("overlay#pin", count=1, log=log),
        LiberatorDriver.LIB_CONFIRM_BUTTON: FakeLocator("overlay#confirm", count=1, log=log),
    }

    change_ctrl = FakeLocator("row-change", count=1 if change_available else 0, log=log)
    actions = FakeLocator(
        "row-actions", count=3, log=log,
        children={
            ("text", LiberatorDriver.LIB_AMEND_ACTION): FakeLocator("row-change-text", count=0, log=log),
            "div.cursor-pointer": FakeLocator(
                "row-dpc", count=3, log=log,
                children={("filter", LiberatorDriver.LIB_AMEND_ACTION): change_ctrl},
            ),
        },
    )
    tds = FakeLocator("row-tds", count=11, texts=row_cells, last=actions, log=log)
    row = FakeLocator(
        "order-row", count=1 if order_present else 0, texts=row_cells,
        children={"td": tds}, log=log,
    )

    page = FakePage({
        f"{LiberatorDriver.LIB_ORDER_TABLE} tbody tr:has(input[id='{ORDER_NO}'])": row,
        LiberatorDriver.LIB_AMEND_OVERLAY: overlay,
    })
    page.log = log
    return page, {
        "row": row, "tds": tds, "actions": actions, "change": change_ctrl,
        "overlay": overlay, "volume": overlay.children["#volume"],
        "price": overlay.children["#price"], "pin": overlay.children["#pin"],
        "confirm": overlay.children[LiberatorDriver.LIB_CONFIRM_BUTTON],
    }


def _driver(page, verified_price=11.70, orders=None):
    """Builds a driver wired to the fake page with a stubbed post-amend scrape."""
    drv = LiberatorDriver()
    drv.page = page
    if orders is None:
        orders = [{
            "order_no": ORDER_NO, "time": "10:03:21", "symbol": "BCH", "side": "SELL",
            "price": verified_price, "volume": 4000, "balance": 4000, "status": "Open",
        }]
    drv.scrape_portfolio = AsyncMock(return_value={"orders": orders})
    return drv


@pytest.fixture
def weekday_clock(monkeypatch):
    """Pins the driver's `datetime.now()` to a Friday so the weekend guard is deterministic.

    Without this the whole flow-test set would flip to `MARKET_CLOSED` whenever the suite
    happens to run on a Saturday/Sunday.
    """
    class _Friday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 9, 10, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr("app.brokers.liberator.driver.datetime", _Friday)


# ─── pure guards ─────────────────────────────────────────────────────────────────────

def test_amend_guard_rejects_non_numeric_order_no():
    assert "order number" in LiberatorDriver._amend_guard("BCH-1", 11.7, None)


def test_amend_guard_rejects_non_positive_price():
    assert "must be positive" in LiberatorDriver._amend_guard(ORDER_NO, 0, None)
    assert "must be positive" in LiberatorDriver._amend_guard(ORDER_NO, -1.5, None)


def test_amend_guard_rejects_volume_that_is_not_a_board_lot():
    assert "multiple of 100" in LiberatorDriver._amend_guard(ORDER_NO, 11.7, 150)


def test_amend_guard_accepts_valid_inputs():
    assert LiberatorDriver._amend_guard(ORDER_NO, 11.7, None) is None
    assert LiberatorDriver._amend_guard(ORDER_NO, 11.7, 4000) is None


def test_parse_order_row_cells_matches_live_11894_row():
    """The 11 cells of the live row must map to the documented fields (volume 4,000 kept)."""
    parsed = LiberatorDriver._parse_order_row_cells(LIVE_CELLS)
    assert parsed == {
        "order_no": "11894", "time": "10:03:21", "symbol": "BCH", "side": "SELL",
        "price": 12.0, "volume": 4000, "matched": 0, "balance": 4000,
        "status": "Open", "actions": "Change Detail Cancel",
    }


def test_parse_order_row_cells_tolerates_short_rows():
    """A hidden/extra `<td>` must not raise (returns zeroed fields instead)."""
    parsed = LiberatorDriver._parse_order_row_cells(["11894", "10:03:21", "BCH"])
    assert parsed["symbol"] == "BCH"
    assert parsed["price"] == 0.0
    assert parsed["status"] == ""


# ─── row action resolver ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_order_action_locator_falls_back_when_exact_text_misses():
    """Strategy 1 (get_by_text exact) returns 0 matches -> strategy 2 must win."""
    _, parts = _build_page()
    locator = await LiberatorDriver._order_action_locator(parts["row"], "Change")
    assert locator is parts["change"]


@pytest.mark.asyncio
async def test_order_action_locator_returns_none_for_unknown_label():
    _, parts = _build_page()
    assert await LiberatorDriver._order_action_locator(parts["row"], "Cancel") is None


# ─── change_order flow ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_order_amends_in_place_and_keeps_order_number(weekday_clock):
    page, parts = _build_page()
    drv = _driver(page, verified_price=11.70)

    res = await drv.change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is True
    assert res["action"] == "AMENDED_IN_PLACE"
    assert res["order_no"] == ORDER_NO          # original number retained (no cancel + replace)
    assert res["old_price"] == 12.0
    assert res["new_price"] == 11.70
    assert res["new_volume"] == 4000            # volume untouched
    assert parts["change"].clicks == 1          # pressed the row's native Change control
    assert ("wait_for_selector", LiberatorDriver.LIB_AMEND_OVERLAY) in page.log
    # filled ONLY the overlay's fields (LIB-RCA-017)
    assert parts["price"].filled == ["", "11.70"]
    assert parts["pin"].filled == ["", "123456"]
    assert parts["volume"].filled == []
    assert parts["confirm"].clicks == 1


@pytest.mark.asyncio
async def test_change_order_fills_volume_only_when_requested(weekday_clock):
    page, parts = _build_page()
    drv = _driver(page, verified_price=11.70)

    res = await drv.change_order(ORDER_NO, 11.70, new_volume=2000, pin="123456")

    assert res["new_volume"] == 2000
    assert parts["volume"].filled == ["", "2000"]


@pytest.mark.asyncio
async def test_change_order_reports_unverified_when_price_did_not_change(weekday_clock):
    """Anti-Mock: a click that leaves the old price on the row is NOT a success."""
    page, _ = _build_page()
    drv = _driver(page, verified_price=12.00)

    res = await drv.change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is False
    assert res["action"] == "AMEND_UNVERIFIED"
    assert res["reported_price"] == 12.0
    assert "11.70" in res["error"]


@pytest.mark.asyncio
async def test_change_order_reports_unverified_when_order_vanished(weekday_clock):
    page, _ = _build_page()
    drv = _driver(page, orders=[])

    res = await drv.change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is False
    assert res["action"] == "AMEND_UNVERIFIED"
    assert "no longer in the Orders table" in res["error"]


@pytest.mark.asyncio
async def test_change_order_blocks_non_amendable_status_before_clicking(weekday_clock):
    page, parts = _build_page(status="Matched")
    drv = _driver(page)

    res = await drv.change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is False
    assert "Matched" in res["error"]
    assert parts["change"].clicks == 0          # Change must never be pressed
    assert parts["confirm"].clicks == 0         # and nothing was confirmed


@pytest.mark.asyncio
async def test_change_order_errors_when_order_row_is_missing(weekday_clock):
    page, parts = _build_page(order_present=False)
    drv = _driver(page)

    res = await drv.change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is False
    assert "not found" in res["error"]
    assert parts["change"].clicks == 0


@pytest.mark.asyncio
async def test_change_order_requires_six_digit_pin():
    res = await LiberatorDriver().change_order(ORDER_NO, 11.70, pin="1234")
    assert res["success"] is False
    assert "PIN" in res["error"]


@pytest.mark.asyncio
async def test_change_order_rejects_bad_input_before_touching_the_browser():
    res = await LiberatorDriver().change_order(ORDER_NO, 0, pin="123456")
    assert res["success"] is False
    assert "must be positive" in res["error"]


@pytest.mark.asyncio
async def test_change_order_stages_when_market_is_closed_at_the_weekend(monkeypatch):
    class _Saturday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 10, 10, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr("app.brokers.liberator.driver.datetime", _Saturday)
    res = await LiberatorDriver().change_order(ORDER_NO, 11.70, pin="123456")

    assert res["success"] is False
    assert res["status"] == "MARKET_CLOSED"
    assert res["staged"] is True


# ─── negotiate_price now amends in place (no cancel + re-place) ──────────────────────

def _open_order_row(price):
    return {
        "order_no": ORDER_NO, "time": "10:03:21", "symbol": "BCH", "side": "SELL",
        "price": price, "volume": 4000, "matched": 0, "balance": 4000, "status": "Open",
    }


@pytest.mark.asyncio
async def test_negotiate_price_amends_in_place_and_never_cancels():
    """LIB-RCA-018 / Step 6: the negotiation path must NOT use cancel + re-place anymore."""
    drv = LiberatorDriver()
    drv.scrape_portfolio = AsyncMock(return_value={"orders": [_open_order_row(12.0)]})
    drv.change_order = AsyncMock(return_value={
        "success": True, "action": "AMENDED_IN_PLACE",
        "order_no": ORDER_NO, "old_price": 12.0, "new_price": 11.70,
    })
    drv.cancel_order = AsyncMock(side_effect=AssertionError("cancel_order must never be called"))
    drv.execute_order = AsyncMock(side_effect=AssertionError("execute_order must never be called"))

    res = await drv.negotiate_price(order_no=ORDER_NO, target_price=11.70)

    assert res["success"] is True
    assert res["action"] == "AMENDED_IN_PLACE"
    assert res["order_no"] == ORDER_NO                  # same order number, nothing re-placed
    assert "new_order_no" not in res
    assert "old_order_no" not in res
    drv.change_order.assert_awaited_once()
    drv.cancel_order.assert_not_called()
    drv.execute_order.assert_not_called()


@pytest.mark.asyncio
async def test_negotiate_price_is_noop_when_already_at_target():
    """A same-price amend would be a pointless live submission."""
    drv = LiberatorDriver()
    drv.scrape_portfolio = AsyncMock(return_value={"orders": [_open_order_row(11.70)]})
    drv.change_order = AsyncMock()

    res = await drv.negotiate_price(order_no=ORDER_NO, target_price=11.70)

    assert res["success"] is True
    assert res["action"] == "NONE"
    assert res["order_no"] == ORDER_NO
    drv.change_order.assert_not_called()


@pytest.mark.asyncio
async def test_negotiate_price_propagates_amend_failure():
    drv = LiberatorDriver()
    drv.scrape_portfolio = AsyncMock(return_value={"orders": [_open_order_row(12.0)]})
    drv.change_order = AsyncMock(return_value={
        "success": False, "action": "AMEND_UNVERIFIED", "error": "Amend not confirmed",
    })

    res = await drv.negotiate_price(order_no=ORDER_NO, target_price=11.70)

    assert res["success"] is False
    assert res["action"] == "AMEND_UNVERIFIED"
    assert res["order_no"] == ORDER_NO
    assert "not confirmed" in res["error"]