"""Unit tests for the ``execute_order`` 3-Tier Anti-DW symbol selection (TASK-loop1-7).

These pin the KSS-RCA-006 / TASK-loop1-7 guardrail with a mock DOM (no browser):

  * Tier 1 clicks a holdings-row ``<td>`` but the order ticket keeps a STALE symbol
    (the real-world root cause), so the driver must NOT trust Tier 1 alone — it falls
    through to Tier 2 (search modal exact match) and only proceeds once the ticket
    really shows the target symbol.

A ``FakePage`` stands in for the Playwright page: ``page_override`` routes the driver
to it, and ``evaluate()`` is dispatched on the JS body (Tier 1 / Tier 2 / Tier 3 /
send-button probe are distinguishable by a unique substring). The driver runs in
``DRY_RUN_MODE``, so a successful symbol selection finishes as ``SIMULATED_SUCCESS``
(Send omitted) — the cleanest "proceeded without abort" signal.
"""
from unittest.mock import AsyncMock

from app.browser.trademan_driver import trademan_driver
from app.services.validator import validator

TARGET = "BCPG"
STALE = "BBL"


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    async def press(self, key):
        self.pressed.append(key)


class FakeLocator:
    def __init__(self, page, selector, visible=True):
        self.page = page
        self.selector = selector
        self._visible = visible

    @property
    def first(self):
        return self

    async def is_visible(self):
        return self._visible

    async def click(self):
        self.page.clicks.append(self.selector)

    async def fill(self, value):
        self.page.filled[self.selector] = value


class FakePage:
    """Playwright ``Page`` stand-in for ``execute_order``.

    ``evaluate_script`` maps a JS-body substring -> result. A list result is
    consumed one item per call (used to script the two Tier 3 reads).
    """

    def __init__(self, evaluate_script):
        self.url = "https://trademan.in.th/Portfolio"
        self.clicks = []
        self.filled = {}
        self.waits = []
        self.keyboard = FakeKeyboard()
        self._evaluate_script = evaluate_script

    def is_closed(self):
        return False

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def query_selector(self, selector):
        return None

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def evaluate(self, js, arg=None):
        for key, value in self._evaluate_script.items():
            if key in js:
                if callable(value):
                    return value(arg)
                if isinstance(value, list):
                    return value.pop(0)
                return value
        return None


def _patch_driver(monkeypatch, page):
    """Route the driver to ``page`` and neutralise every external side effect."""
    monkeypatch.setattr("app.browser.trademan_driver.settings.DRY_RUN_MODE", True)
    monkeypatch.setattr(trademan_driver, "page_override", page)
    monkeypatch.setattr("app.browser.trademan_driver.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "app.browser.trademan_driver.popup_manager.dismiss_popups",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.browser.trademan_driver.auth_driver.take_diagnostic_snapshot",
        AsyncMock(),
    )
    monkeypatch.setattr(trademan_driver, "_log_event", AsyncMock())
    validator.clear_idempotency_cache()


async def _run(monkeypatch, evaluate_script):
    page = FakePage(evaluate_script)
    _patch_driver(monkeypatch, page)
    result = await trademan_driver.execute_order(TARGET, "COVER", 100, 6.75)
    return page, result


async def test_tier1_stale_symbol_falls_through_to_tier2_and_proceeds(monkeypatch):
    """T1 clicks the td but the ticket stays BBL -> T2 exact-match sets BCPG -> proceed."""
    page, result = await _run(monkeypatch, {
        "send_order__btn": True,
        "targetTd": True,                       # Tier 1 clicked a td
        "v-overlay--active": True,              # Tier 2 exact match found + clicked
        "bg-[#2B313A]": [STALE, TARGET],        # T3 after T1 = BBL, after T2 = BCPG
    })

    assert result["success"] is True
    assert result["status"] == "SIMULATED_SUCCESS"
    # Tier 2 really ran: the search modal was opened and filled with the target.
    assert ".v-overlay--active input" in page.filled
    assert page.filled[".v-overlay--active input"] == TARGET
    assert page.keyboard.pressed == []          # no Escape -> exact match was clicked


async def test_tier2_exact_match_not_found_rejected(monkeypatch):
    """T2 cannot find an exact match -> Escape -> T3 still stale -> REJECTED."""
    page, result = await _run(monkeypatch, {
        "send_order__btn": True,
        "targetTd": True,
        "v-overlay--active": False,             # exact match NOT found
        "bg-[#2B313A]": [STALE, STALE],
    })

    assert result["success"] is False
    assert result["status"] == "REJECTED"
    assert "Anti-DW" in result["error"]
    assert page.keyboard.pressed == ["Escape"]


async def test_tier2_clicked_but_ticket_still_stale_rejected(monkeypatch):
    """T2 clicked the exact match but the ticket is still BBL -> REJECTED (fail-closed)."""
    page, result = await _run(monkeypatch, {
        "send_order__btn": True,
        "targetTd": True,
        "v-overlay--active": True,              # exact match clicked...
        "bg-[#2B313A]": [STALE, STALE],         # ...but the ticket never updated
    })

    assert result["success"] is False
    assert result["status"] == "REJECTED"
    assert "Anti-DW" in result["error"]
    assert page.keyboard.pressed == []          # no Escape (a match was clicked)


async def test_tier1_sets_symbol_correctly_skips_tier2(monkeypatch):
    """Regression: T1 click sets the ticket to BCPG -> Tier 2 never runs -> proceed."""
    page, result = await _run(monkeypatch, {
        "send_order__btn": True,
        "targetTd": True,
        "v-overlay--active": True,              # present but must NOT be reached
        "bg-[#2B313A]": [TARGET],
    })

    assert result["success"] is True
    assert result["status"] == "SIMULATED_SUCCESS"
    # Tier 2 was skipped: the search input was never filled.
    assert ".v-overlay--active input" not in page.filled
