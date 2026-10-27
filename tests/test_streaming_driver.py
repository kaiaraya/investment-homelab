"""
Unit tests (mock DOM, no browser) for the Settrade Streaming driver (TASK-loop1-8).

Covers:
- execute_order side-radio selection (Buy vs Sell vs Short vs Cover) — SHORT/COVER
  are REAL (Sell/Buy radio + Short/Cover toggle), never simulated as SELL/BUY.
- The Anti-DW symbol assertion (stale ticket -> REJECTED, fail-closed).
- cancel_order (row-scoped cancel + confirm).
- modify_order_price (native in-place change first — SQ-7 PATCH /orders/{orderNo}/change —
  then cancel + replace only when the native path provably sent nothing).
No real navigation / login / order is performed.
"""
import pytest
import re
from unittest.mock import AsyncMock

from app.core.config import settings

from app.browser.streaming_driver import (
    StreamingDriver,
    SYMBOL_INPUT_SELECTOR,
    BUY_RADIO_SELECTORS,
    SELL_RADIO_SELECTORS,
    SHORT_RADIO_SELECTORS,
    COVER_RADIO_SELECTORS,
    PRICE_STEPPER_PLUS_SELECTOR,
    PRICE_STEPPER_MINUS_SELECTOR,
    CANCEL_ACTION_SELECTOR,
    CANCEL_CONFIRM_SELECTOR,
    STREAMING_CHANGE_JS,
    STREAMING_ORDERS_READ_JS,
)

STREAMING_PAGE_URL = "https://wma1.settrade.com/realtime/streaming7/StreamingPage.jsp"


class FakeElement:
    def __init__(self, visible=True, nested=None):
        self._visible = visible
        self._nested = nested or {}
        self.clicked = 0

    async def is_visible(self):
        return self._visible

    async def click(self, **kw):
        self.clicked += 1

    async def query_selector(self, selector):
        return self._nested.get(selector)

    async def inner_text(self):
        return ""


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    async def fill(self, value):
        self.page.filled[self.selector] = value

    async def input_value(self):
        return self.page._input_values.get(self.selector, self.page.filled.get(self.selector))

    async def is_visible(self):
        return True

    async def is_enabled(self):
        return True

    async def click(self, **kw):
        self.page.clicks.append(self.selector)

    async def inner_text(self):
        return ""


class FakePage:
    def __init__(self, elements=None, input_values=None, evaluate_result=None, evaluate_queue=None):
        self.url = STREAMING_PAGE_URL
        self.clicks = []
        self.filled = {}
        self.js_calls = []
        self._elements = elements or {}
        self._input_values = input_values or {}
        self._evaluate_result = evaluate_result
        self._evaluate_queue = list(evaluate_queue or [])

    def is_closed(self):
        return False

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def query_selector(self, selector):
        return self._elements.get(selector)

    async def evaluate(self, js, arg=None):
        self.js_calls.append((js, arg))
        if self._evaluate_queue:
            return self._evaluate_queue.pop(0)
        return self._evaluate_result

    async def wait_for_timeout(self, ms):
        pass

    async def wait_for_load_state(self, *a, **kw):
        pass

    async def goto(self, url, **kw):
        self.url = url


def _driver_with(page):
    d = StreamingDriver()
    d.page_override = page
    d._log_event = AsyncMock()
    return d


def _ticket_page(side, evaluate_result=None, input_values=None):
    """Build a FakePage with buy/sell radios + submit button + canned order row."""
    elements = {
        BUY_RADIO_SELECTORS[0]: FakeElement(),
        SELL_RADIO_SELECTORS[0]: FakeElement(),
        "button.bg-color-dark-blue-60": FakeElement(),
    }
    # Optional Short/Cover radio presence (drives the real SHORT/COVER path).
    if side == "SHORT":
        elements[SHORT_RADIO_SELECTORS[0]] = FakeElement()
    elif side == "COVER":
        elements[COVER_RADIO_SELECTORS[0]] = FakeElement()
    page = FakePage(
        elements=elements,
        input_values=input_values,
        evaluate_result=evaluate_result if evaluate_result is not None else ["11008198", "PTT", "Buy", "100", "34.00"],
    )
    return page


# --- execute_order: side-radio selection ----------------------------------

@pytest.mark.parametrize(
    "side,expected_selector",
    [
        ("BUY", BUY_RADIO_SELECTORS[0]),
        ("SELL", SELL_RADIO_SELECTORS[0]),
        ("SHORT", SHORT_RADIO_SELECTORS[0]),  # real Short radio (not Sell)
        ("COVER", COVER_RADIO_SELECTORS[0]),  # real Cover radio (not Buy)
    ],
)
async def test_execute_order_side_radio_selection(side, expected_selector):
    page = _ticket_page(side)
    d = _driver_with(page)

    res = await d.execute_order(symbol="PTT", side=side, volume=100, price=34.00)

    assert res["success"] is True
    assert res["side"] == side                      # side passes through verbatim
    assert page._elements[expected_selector].clicked == 1
    for other in (BUY_RADIO_SELECTORS[0], SELL_RADIO_SELECTORS[0],
                  SHORT_RADIO_SELECTORS[0], COVER_RADIO_SELECTORS[0]):
        if other != expected_selector and other in page._elements:
            assert page._elements[other].clicked == 0
    # volume / price / symbol were filled
    assert page.filled[SYMBOL_INPUT_SELECTOR] == "PTT"


async def test_execute_order_short_and_cover_use_real_radios():
    # SHORT: clicks the Short radio (NOT the Sell radio).
    page_short = _ticket_page("SHORT")
    d = _driver_with(page_short)
    res = await d.execute_order(symbol="PTT", side="SHORT", volume=100, price=34.00)
    assert res["success"] is True and res["side"] == "SHORT"
    assert page_short._elements[SHORT_RADIO_SELECTORS[0]].clicked == 1
    assert page_short._elements[SELL_RADIO_SELECTORS[0]].clicked == 0

    # COVER: clicks the Cover radio (NOT the Buy radio).
    page_cover = _ticket_page("COVER")
    d = _driver_with(page_cover)
    res = await d.execute_order(symbol="PTT", side="COVER", volume=100, price=34.00)
    assert res["success"] is True and res["side"] == "COVER"
    assert page_cover._elements[COVER_RADIO_SELECTORS[0]].clicked == 1
    assert page_cover._elements[BUY_RADIO_SELECTORS[0]].clicked == 0


async def test_execute_order_rejects_invalid_board_lot():
    d = _driver_with(_ticket_page("BUY"))
    res = await d.execute_order(symbol="PTT", side="BUY", volume=99, price=34.00)
    assert res["success"] is False
    assert res["status"] == "REJECTED"


# --- Anti-DW symbol assertion ---------------------------------------------

async def test_execute_order_anti_dw_assert_aborts_on_stale_ticket():
    """A stale order-ticket symbol must abort BEFORE submit (fail-closed)."""
    page = _ticket_page(
        "BUY",
        input_values={SYMBOL_INPUT_SELECTOR: "BBL"},  # ticket keeps a stale symbol
    )
    d = _driver_with(page)

    res = await d.execute_order(symbol="PTT", side="BUY", volume=100, price=34.00)

    assert res["success"] is False
    assert res["status"] == "REJECTED"
    assert "Anti-DW" in res["error"]
    assert "PTT" in res["error"] and "BBL" in res["error"]
    # Submit button must NOT have been clicked.
    assert page._elements["button.bg-color-dark-blue-60"].clicked == 0


async def test_execute_order_fails_closed_without_browser():
    d = StreamingDriver()
    d.page_override = None
    d._log_event = AsyncMock()
    res = await d.execute_order(symbol="PTT", side="BUY", volume=100, price=34.00)
    assert res["success"] is False
    assert res["status"] == "FAILED"


# --- cancel_order ----------------------------------------------------------

async def test_cancel_order_clicks_row_cancel_and_confirm(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)  # force LIVE cancel path (ignore .env)
    row = FakeElement(nested={CANCEL_ACTION_SELECTOR: FakeElement()})
    page = FakePage(elements={
        "tr:has-text('11008198')": row,
        CANCEL_CONFIRM_SELECTOR: FakeElement(),
    })
    d = _driver_with(page)

    res = await d.cancel_order(broker_order_no="11008198")

    assert res["success"] is True
    assert res["status"] == "CANCELLED"
    assert row._nested[CANCEL_ACTION_SELECTOR].clicked == 1
    assert page._elements[CANCEL_CONFIRM_SELECTOR].clicked == 1


async def test_cancel_order_fails_closed_when_row_missing(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)  # force LIVE cancel path so fail-closed fires
    page = FakePage(elements={})
    d = _driver_with(page)

    res = await d.cancel_order(broker_order_no="99999999")

    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert "not found" in res["error"]


# --- DRY_RUN_MODE guard (live-money safety) --------------------------------

async def test_execute_order_dry_run_skips_submit(monkeypatch):
    """DRY_RUN_MODE=True must stop before the irreversible Send click."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", True)
    page = _ticket_page("BUY")
    d = _driver_with(page)

    res = await d.execute_order(symbol="PTT", side="BUY", volume=100, price=34.00)

    assert res["success"] is True
    assert res["status"] == "SIMULATED_SUCCESS"
    # Submit button must NOT have been clicked.
    assert page._elements["button.bg-color-dark-blue-60"].clicked == 0


async def test_cancel_order_dry_run_skips_cancel(monkeypatch):
    """DRY_RUN_MODE=True must never fire a cancel (irreversible)."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", True)
    row = FakeElement(nested={CANCEL_ACTION_SELECTOR: FakeElement()})
    page = FakePage(elements={"tr:has-text('11008198')": row})
    d = _driver_with(page)

    res = await d.cancel_order(broker_order_no="11008198")

    assert res["success"] is True
    assert res["status"] == "SIMULATED_SUCCESS"
    assert row._nested[CANCEL_ACTION_SELECTOR].clicked == 0


# --- modify_order_price (cancel + replace) ---------------------------------

async def test_modify_order_price_cancel_and_replace(monkeypatch):
    d = StreamingDriver()
    cancel_mock = AsyncMock(return_value={
        "success": True, "status": "CANCELLED", "broker_order_no": "11008198",
    })
    execute_mock = AsyncMock(return_value={
        "success": True, "status": "SUBMITTED", "broker_order_no": "11009999",
    })
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)
    monkeypatch.setattr(d, "_log_event", AsyncMock())

    res = await d.modify_order_price(
        broker_order_no="11008198", symbol="PTT", side="BUY",
        new_price=34.25, remaining_volume=100,
    )

    assert res["success"] is True
    assert res["status"] == "MODIFIED"
    assert res["broker_order_no"] == "11009999"
    assert res["old_order_no"] == "11008198"
    assert res["new_price"] == 34.25

    cancel_mock.assert_awaited_once_with(broker_order_no="11008198", symbol="PTT", bypass_dry_run=False)
    execute_mock.assert_awaited_once_with(symbol="PTT", side="BUY", volume=100, price=34.25, pin=None, bypass_dry_run=False)


async def test_modify_order_price_only_cancels_when_no_new_price(monkeypatch):
    d = StreamingDriver()
    cancel_mock = AsyncMock(return_value={
        "success": True, "status": "CANCELLED", "broker_order_no": "11008198",
    })
    execute_mock = AsyncMock()
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)
    monkeypatch.setattr(d, "_log_event", AsyncMock())

    res = await d.modify_order_price(broker_order_no="11008198", symbol="PTT", new_price=0.0)

    assert res["status"] == "CANCELLED"
    execute_mock.assert_not_awaited()


async def test_execute_order_stepper_offset_clicks():
    page = _ticket_page("BUY", input_values={"input[name='price-input'], input[placeholder='Price']": "34.50"})
    d = _driver_with(page)

    res = await d.execute_order(symbol="PTT", side="BUY", volume=100, price=34.00, tick_offset=2)
    assert res["success"] is True
    plus_clicks = [c for c in page.clicks if c == PRICE_STEPPER_PLUS_SELECTOR]
    assert len(plus_clicks) == 2
    assert res["price"] == 34.50


async def test_execute_order_stepper_offset_minus():
    page = _ticket_page("SELL", input_values={"input[name='price-input'], input[placeholder='Price']": "33.75"})
    d = _driver_with(page)

    res = await d.execute_order(symbol="PTT", side="SELL", volume=100, price=34.00, tick_offset=-1)
    assert res["success"] is True
    minus_clicks = [c for c in page.clicks if c == PRICE_STEPPER_MINUS_SELECTOR]
    assert len(minus_clicks) == 1
    assert res["price"] == 33.75


# --- SQ-7 native change (PATCH /orders/{orderNo}/change) -------------------
# Contract source: data/har/kss_change_all.har (live capture 2026-10-26 11:50).
# The PATCH answers 200 with an EMPTY body, so success may only be claimed after
# an Anti-Mock re-read of the SAME orderNo shows the new price.

PATCH_OK = {"ok": True, "account": "3024959", "httpStatus": 200, "body": ""}


def _order_row(order_no="11014863", price=6.70, vol=100, status="O", show="Queuing(O)"):
    return {
        "accountNo": "3024959", "orderNo": order_no, "symbol": "BCPG", "side": "Buy",
        "price": price, "vol": vol, "balance": vol, "status": status,
        "showOrderStatus": show, "rejectCode": 0,
    }


async def test_streaming_change_js_contract_matches_har():
    """The embedded JS must keep the captured endpoint/method/headers/payload shape."""
    assert "orders/${encodeURIComponent(arg.orderNo)}/change" in STREAMING_CHANGE_JS
    assert "method: 'PATCH'" in STREAMING_CHANGE_JS
    assert "credentials: 'include'" in STREAMING_CHANGE_JS   # SSO cookie auth, no CSRF
    assert "'terminal': 'streaming'" in STREAMING_CHANGE_JS
    for field in ("bypassWarning", "newVolume", "pin", "tradeDate", "newPrice"):
        assert field in STREAMING_CHANGE_JS
    assert "/orders`" in STREAMING_ORDERS_READ_JS


async def test_change_order_native_happy_path_keeps_same_order_no(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, [_order_row()]])
    d = _driver_with(page)

    res = await d.change_order_native(
        broker_order_no="11014863", new_price=6.70, new_volume=100,
        pin="515286", symbol="BCPG", side="BUY",
    )

    assert res["success"] is True
    assert res["status"] == "MODIFIED_IN_PLACE"
    assert res["stage"] == "verified"
    assert res["verified"] is True
    assert res["broker_order_no"] == "11014863"   # SAME orderNo — no new order created
    assert res["old_order_no"] == "11014863"
    assert res["native_change"] is True
    assert res["observed_price"] == 6.70

    # Exactly two JS hops: PATCH, then the Anti-Mock re-read.
    assert len(page.js_calls) == 2
    patch_js, patch_arg = page.js_calls[0]
    assert patch_js == STREAMING_CHANGE_JS
    assert patch_arg["orderNo"] == "11014863"
    assert patch_arg["newPrice"] == 6.70
    assert patch_arg["newVolume"] == 100
    assert patch_arg["pin"] == "515286"
    assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", patch_arg["tradeDate"])
    assert page.js_calls[1][0] == STREAMING_ORDERS_READ_JS


async def test_modify_order_price_prefers_native_and_never_cancels(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, [_order_row()]])
    d = _driver_with(page)
    cancel_mock = AsyncMock()
    execute_mock = AsyncMock()
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)

    res = await d.modify_order_price(
        broker_order_no="11014863", symbol="BCPG", side="BUY",
        new_price=6.70, remaining_volume=100, pin="515286",
    )

    assert res["success"] is True and res["status"] == "MODIFIED_IN_PLACE"
    assert res["broker_order_no"] == "11014863"
    cancel_mock.assert_not_awaited()   # no queue position lost
    execute_mock.assert_not_awaited()


async def test_modify_order_price_falls_back_when_patch_fails(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[
        {"ok": False, "account": "3024959", "httpStatus": 500, "body": '{"errorCode":"99"}'},
    ])
    d = _driver_with(page)
    cancel_mock = AsyncMock(return_value={"success": True, "status": "CANCELLED", "broker_order_no": "11014863"})
    execute_mock = AsyncMock(return_value={"success": True, "status": "SUBMITTED", "broker_order_no": "11019999"})
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)

    res = await d.modify_order_price(
        broker_order_no="11014863", symbol="BCPG", side="BUY",
        new_price=6.70, remaining_volume=100, pin="515286",
    )

    assert res["success"] is True
    assert res["status"] == "MODIFIED"
    assert res["broker_order_no"] == "11019999"
    assert res["native_change"] is False
    cancel_mock.assert_awaited_once_with(broker_order_no="11014863", symbol="BCPG", bypass_dry_run=False)
    execute_mock.assert_awaited_once_with(
        symbol="BCPG", side="BUY", volume=100, price=6.70, pin="515286", bypass_dry_run=False
    )
    assert len(page.js_calls) == 1   # failed PATCH -> no re-read attempted


async def test_modify_order_price_falls_back_when_no_browser(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    d = StreamingDriver()
    d._log_event = AsyncMock()
    monkeypatch.setattr(d, "_ensure_streaming_page", AsyncMock(return_value=None))
    cancel_mock = AsyncMock(return_value={"success": True, "status": "CANCELLED", "broker_order_no": "11014863"})
    execute_mock = AsyncMock(return_value={"success": True, "status": "SUBMITTED", "broker_order_no": "11019999"})
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)

    res = await d.modify_order_price(
        broker_order_no="11014863", symbol="BCPG", new_price=6.70, remaining_volume=100, pin="515286",
    )

    assert res["status"] == "MODIFIED" and res["native_change"] is False
    cancel_mock.assert_awaited_once()


async def test_change_order_native_fails_closed_on_price_mismatch(monkeypatch):
    """PATCH 200 (empty body) but the re-read still shows the OLD price => FAILED."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, [_order_row(price=6.75)]])
    d = _driver_with(page)

    res = await d.change_order_native(
        broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286",
    )

    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert res["stage"] == "verify"
    assert res["fallback_ok"] is False
    assert "Anti-Mock" in res["error"]
    assert res["observed_price"] == 6.75


async def test_modify_order_price_never_cancels_after_verify_failure(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, [_order_row(price=6.75)]])
    d = _driver_with(page)
    cancel_mock = AsyncMock()
    execute_mock = AsyncMock()
    monkeypatch.setattr(d, "cancel_order", cancel_mock)
    monkeypatch.setattr(d, "execute_order", execute_mock)

    res = await d.modify_order_price(
        broker_order_no="11014863", symbol="BCPG", new_price=6.70, remaining_volume=100, pin="515286",
    )

    assert res["success"] is False and res["stage"] == "verify"
    cancel_mock.assert_not_awaited()   # the PATCH may have landed — cancel would double-trade
    execute_mock.assert_not_awaited()


async def test_change_order_native_fails_closed_when_order_missing_after_patch(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, []])
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286")

    assert res["success"] is False and res["stage"] == "verify"
    assert "not found" in res["error"]
    assert res["fallback_ok"] is False


async def test_change_order_native_fails_closed_when_orders_unreadable(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, None])
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286")

    assert res["success"] is False and res["stage"] == "verify"
    assert res["fallback_ok"] is False


async def test_change_order_native_fails_closed_on_volume_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[PATCH_OK, [_order_row(price=6.70, vol=300)]])
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286")

    assert res["success"] is False and res["stage"] == "verify"
    assert res["observed_volume"] == 300


async def test_change_order_native_dry_run_never_patches(monkeypatch):
    """DRY_RUN_MODE=True must not touch the broker (and must not cancel either)."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", True)
    page = FakePage()
    d = _driver_with(page)
    cancel_mock = AsyncMock()
    monkeypatch.setattr(d, "cancel_order", cancel_mock)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286")

    assert res["success"] is True
    assert res["status"] == "SIMULATED_SUCCESS"
    assert res["stage"] == "dry_run"
    assert page.js_calls == []

    res2 = await d.modify_order_price(
        broker_order_no="11014863", symbol="BCPG", new_price=6.70, remaining_volume=100, pin="515286",
    )
    assert res2["status"] == "SIMULATED_SUCCESS"
    cancel_mock.assert_not_awaited()


async def test_change_order_native_reads_remaining_volume_when_unknown(monkeypatch):
    """Callers that don't know the volume (e.g. MCP) get it read from the live order."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[[_order_row()], PATCH_OK, [_order_row()]])
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=0, pin="515286")

    assert res["success"] is True and res["stage"] == "verified"
    assert page.js_calls[1][0] == STREAMING_CHANGE_JS
    assert page.js_calls[1][1]["newVolume"] == 100   # from the live order, not guessed
    assert res["volume"] == 100


async def test_change_order_native_rejects_unknown_volume_without_ordering(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    page = FakePage(evaluate_queue=[None])   # orders read unavailable -> no volume known
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=0, pin="515286")

    assert res["status"] == "REJECTED" and "INVALID_VOLUME" in res["error"]
    assert res["fallback_ok"] is True
    assert all(js != STREAMING_CHANGE_JS for js, _ in page.js_calls)   # never PATCHed


async def test_change_order_native_requires_volume_and_pin(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    monkeypatch.setattr(settings, "KRUNGSRI_PIN", "")
    page = FakePage()
    d = _driver_with(page)

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=0, pin="515286")
    assert res["status"] == "REJECTED"
    assert "INVALID_VOLUME" in res["error"]
    assert res["fallback_ok"] is True     # nothing was sent -> cancel+replace is safe

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin=None)
    assert res["status"] == "REJECTED"
    assert res["error"] == "NO_PIN"
    assert res["fallback_ok"] is False    # cancel+replace would need the same PIN
    assert all(js != STREAMING_CHANGE_JS for js, _ in page.js_calls)


async def test_change_order_native_fails_closed_without_browser(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    d = StreamingDriver()
    d._log_event = AsyncMock()
    monkeypatch.setattr(d, "_ensure_streaming_page", AsyncMock(return_value=None))

    res = await d.change_order_native(broker_order_no="11014863", new_price=6.70, new_volume=100, pin="515286")

    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert res["stage"] == "no_page"
    assert res["fallback_ok"] is True


# --- plugin wiring (app/brokers/streaming/plugin.py) -----------------------

async def test_plugin_modify_order_price_passes_native_path(monkeypatch):
    from app.brokers.streaming import plugin as plugin_mod

    captured = {}

    async def fake_modify(**kw):
        captured.update(kw)
        return {
            "success": True, "status": "MODIFIED_IN_PLACE", "native_change": True,
            "broker_order_no": kw["broker_order_no"], "message": "changed in place",
        }

    monkeypatch.setattr(plugin_mod.streaming_driver, "modify_order_price", fake_modify)

    res = await plugin_mod.streaming_plugin.modify_order_price(
        "11014863", 6.70, symbol="BCPG", remaining_volume=100, pin="515286",
    )

    assert res.success is True
    assert res.order_id == "11014863"          # same orderNo survives into the OrderResult
    assert res.raw_response["status"] == "MODIFIED_IN_PLACE"
    assert captured["prefer_native"] is True   # native path requested by default
    assert captured["remaining_volume"] == 100
    assert captured["pin"] == "515286"

