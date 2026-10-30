# -*- coding: utf-8 -*-
"""B.6 live order executor (``execute_order_via_cdp``) — unit tests.

No browser is launched: ``manager.get_tab`` is stubbed with a fake page whose selectors
and ledger are canned ("fake DOM"), exactly like ``test_broker_cdp_order_sync.py``. The
tests pin the money-safety contract:

* nothing is ever typed or submitted while ``DRY_RUN_MODE`` is on;
* a refusal happens before any tab work (validator / SBL / quote / kill-switch / PIN);
* an order number is only reported when a NEW matching ledger row proves it — otherwise
  the result is ``UNCONFIRMED`` and no number is invented;
* the ticket is read back before submit (Anti-DW) and the account is asserted;
* a submitted order is written to ``orders`` with ``source='bot_cdp'``.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Order, SBLBorrowLot
from app.services.broker_cdp import order_executor as oe
from app.services.broker_cdp import sync_service

# ── fake DOM ───────────────────────────────────────────────────────────────────
KSS_LEDGER_OLD = ["11009293", "20/10", "10:20:07", "CPF", "Cover", "20.30",
                  "2,400", "2,400", "0", "0", "Matched(M)", "Detail"]

#: Every selector the executor may treat as "the submit button". Live Streaming labels the
#: button with the side name (``button.bg-color-cover-20``), so the fake DOM must answer to
#: both the side-labelled and the generic form.
KSS_SUBMIT_SELECTORS = tuple(oe.KSS_SUBMIT) + tuple(
    f"button.bg-color-{s.lower()}-20" for s in ("BUY", "SELL", "SHORT", "COVER"))
#: Any selector (either broker) that the executor may click to submit.
ALL_SUBMIT_SELECTORS = KSS_SUBMIT_SELECTORS + tuple(oe.LIB_SUBMIT)


def kss_row(bno, symbol, side, price, volume, status="Queuing"):
    return [bno, "21/10", "10:31:00", symbol, side, f"{price:.2f}", f"{volume:,}",
            "0", f"{volume:,}", "0", status, "Detail"]


def lib_row(bno, symbol, side, price, volume, status="Queuing"):
    return [bno, "10:31:00", symbol, side, f"{price:.2f}", str(volume),
            "0", str(volume), "0", status]


class FakeElement:
    def __init__(self, page, selector, value="", visible=True):
        self.page = page
        self.selector = selector
        self.value = value
        self.visible = visible
        self.clicks = 0

    async def is_visible(self):
        return self.visible

    async def input_value(self):
        return self.value

    async def click(self, force=False):
        self.clicks += 1
        self.page.clicked.append(self.selector)
        self.page.on_click(self.selector)

    async def fill(self, text):
        if self.page.ignore_fill == self.selector:
            return                                   # simulate a field that refuses input
        self.value = text
        self.page.filled.append((self.selector, text))


class FakePage:
    """Canned Streaming / WebTrade page.

    ``elements`` maps a selector to ``(value, visible)``. ``ledger`` holds the raw grid
    payload; ``submit_adds_row`` decides whether a matching row appears after Submit.
    """

    def __init__(self, *, elements=None, ledger=None, submit_adds_row=None,
                 ignore_fill=None, account="3024959", row_style="kss", dialog=False):
        self.row_style = row_style
        self.elements = {}
        for sel, spec in (elements or {}).items():
            if isinstance(spec, tuple):
                value, visible = spec
            else:
                value, visible = spec, True
            self.elements[sel] = FakeElement(self, sel, value, visible)
        self.ledger = ledger if ledger is not None else {"account_no": account, "rows": []}
        self.submit_adds_row = submit_adds_row
        self.ignore_fill = ignore_fill
        self.account = account
        self.dialog = dialog
        self.clicked = []
        self.filled = []
        self.evaluated = []
        #: JS alert text emitted on submit (simulates Settrade's "pin suspended" alert).
        self.dialog_on_submit = None
        self.dialog_handlers = []

    # --- playwright event surface (dialog capture) ---------------------------
    def on(self, event, handler):
        if event == "dialog":
            self.dialog_handlers.append(handler)

    def remove_listener(self, event, handler):
        if event == "dialog" and handler in self.dialog_handlers:
            self.dialog_handlers.remove(handler)

    def emit_dialog(self, message):
        class _Dialog:
            def __init__(self, msg):
                self.message = msg

            async def dismiss(self):
                return None

        for handler in list(self.dialog_handlers):
            handler(_Dialog(message))

    # --- playwright surface used by the executor -----------------------------
    async def query_selector(self, selector):
        return self.elements.get(selector)

    async def evaluate(self, js):
        self.evaluated.append(js)
        if js == oe._ACTIVE_ACCOUNT_JS:
            return self.account
        if js == oe._DIALOG_JS:
            return self.dialog
        if js == sync_service._KSS_ORDER_LEDGER_JS:
            return self.ledger
        if js == sync_service._LIBERATOR_ORDER_LEDGER_JS:
            return self.ledger
        return None

    async def wait_for_timeout(self, _ms):
        return None

    # --- DOM simulation -------------------------------------------------------
    def on_click(self, selector):
        if selector in ALL_SUBMIT_SELECTORS and self.submit_adds_row:
            bno, symbol, side, price, volume = self.submit_adds_row
            builder = kss_row if self.row_style == "kss" else lib_row
            self.ledger["rows"].append(builder(bno, symbol, side, price, volume))
        if selector.startswith("li:has-text("):
            self.account = selector.split("'")[1]
        if selector in KSS_SUBMIT_SELECTORS or selector in oe.LIB_SUBMIT:
            self.submitted = True
            if self.dialog_on_submit:
                self.emit_dialog(self.dialog_on_submit)


KSS_TICKET = {
    "input#equity-place-order-buy-radio-button": ("", True),
    "input#equity-place-order-sell-radio-button": ("", True),
    "input#equity-place-order-short-radio-button": ("", True),
    "input#equity-place-order-cover-radio-button": ("", True),
    "input[placeholder='Symbol']": ("", True),
    "input[name='equity-place-order-vol']": ("", True),
    "input[name='price-input']": ("", True),
    "#pin": ("", True),
    "button:has-text('Submit')": ("", True),
    "div.position-relative.cursor-pointer": ("", True),
    "li:has-text('3024959')": ("", True),
}

LIB_TICKET = {
    "button:has-text('Buy')": ("", True),
    "button:has-text('Sell')": ("", True),
    "#SearchSymbolList-setBuySellFooter": ("", True),
    "#volume": ("", True),
    "#price": ("", True),
    "#pin": ("", True),
    "#buttonSubmit": ("", True),
    "button:has-text('Confirm')": ("", True),
}


class _FakeTab:
    def __init__(self, page):
        self._page = page

    async def __aenter__(self):
        return self._page

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fake_tab(monkeypatch):
    """Patch ``order_executor.get_tab``; returns a setter, records whether it was used."""
    calls = {"n": 0}

    def _patch(page):
        def _factory(cdp, target):
            calls["n"] += 1
            calls["last"] = (cdp, target)
            if isinstance(page, Exception):
                raise page
            return _FakeTab(page)
        monkeypatch.setattr(oe, "get_tab", _factory)
        return calls

    return _patch


@pytest.fixture
def no_sync(monkeypatch):
    """Never open a second tab for the post-submit sync."""
    state = {}

    async def _sync(broker, db=None):
        state["broker"] = broker
        return {"broker": broker, "new_manual_count": 0, "scraped": 1}
    monkeypatch.setattr(sync_service, "sync_orders_from_cdp", _sync)
    return state


@pytest.fixture
def live_dry_run(monkeypatch):
    """Turn DRY_RUN_MODE off for the live-path tests without touching .env."""
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    monkeypatch.setattr(settings, "KRUNGSRI_PIN", "123456")
    monkeypatch.setattr(settings, "LIBERATOR_PIN", "654321")


async def _add_sbl(symbol="TU", qty=3100):
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as db:
        db.add(SBLBorrowLot(lot_id=f"SBL-{symbol}-1", symbol=symbol, borrow_qty=qty,
                            remaining_qty=qty, borrow_date=date(2026, 10, 1), status="ACTIVE"))
        await db.commit()


# ── pure helpers ───────────────────────────────────────────────────────────────
def test_normalise_side():
    assert oe.normalise_side("b") == "BUY"
    assert oe.normalise_side("SELL") == "SELL"
    assert oe.normalise_side("H") == "SHORT"
    assert oe.normalise_side("Short-Sell") == "SHORT"
    assert oe.normalise_side("Cover(M)") == "COVER"      # matched marker stripped
    assert oe.normalise_side("buy") == "BUY"
    assert oe.normalise_side("LONG") == "BUY"            # equity aliasing
    assert oe.normalise_side("") is None
    assert oe.normalise_side("XYZ") is None


def test_resolve_broker_and_pin(monkeypatch):
    assert oe.resolve_broker("KSS")["broker"] == "KRUNGSRI"
    assert oe.resolve_broker("liberator")["cdp"] == "liberator"
    assert oe.resolve_broker("nope") is None

    monkeypatch.setattr(settings, "KRUNGSRI_PIN", "123456")
    assert oe.resolve_pin("kss") == "123456"
    assert oe.resolve_pin("kss", pin="000000") == "000000"
    assert oe.resolve_pin("kss", pin="12345") is None     # 5 digits
    monkeypatch.setattr(settings, "KRUNGSRI_PIN", "")
    assert oe.resolve_pin("kss") is None


def test_market_window_warning():
    from datetime import datetime, timedelta, timezone
    bkk = timezone(timedelta(hours=7))
    assert oe.market_window_warning(datetime(2026, 10, 21, 10, 30, tzinfo=bkk)) is None
    assert oe.market_window_warning(datetime(2026, 10, 21, 13, 0, tzinfo=bkk)) is not None
    assert oe.market_window_warning(datetime(2026, 10, 24, 10, 30, tzinfo=bkk)) is not None  # Sat


def test_match_new_order_no():
    orders = [
        {"broker_order_no": "11009293", "symbol": "TU", "side": "Cover", "price": 12.70, "volume": 3100},
        {"broker_order_no": "11010001", "symbol": "TU", "side": "Cover", "price": 12.70, "volume": 3100},
        {"broker_order_no": "11010002", "symbol": "TU", "side": "Buy", "price": 12.70, "volume": 3100},
        {"broker_order_no": "11010003", "symbol": "TU", "side": "Cover", "price": 12.80, "volume": 3100},
    ]
    # only the NEW row that matches on every field
    assert oe.match_new_order_no(orders, symbol="TU", side="COVER", volume=3100, price=12.70,
                                 known=["11009293"]) == "11010001"
    # everything already known -> no proof, never a guess
    assert oe.match_new_order_no(orders, symbol="TU", side="COVER", volume=3100, price=12.70,
                                 known=["11009293", "11010001", "11010002", "11010003"]) is None
    # side mismatch never matches
    assert oe.match_new_order_no(orders, symbol="TU", side="SHORT", volume=3100, price=12.70,
                                 known=[]) is None


# ── refusals before any browser work ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_rejects_unknown_broker(fake_tab):
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    res = await oe.execute_order_via_cdp("bogus", "BUY", "TU", 100, 12.70)
    assert res["success"] is False and res["error_code"] == oe.E_BAD_BROKER
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_rejects_bad_side_and_unsupported_side_for_liberator(fake_tab):
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    bad = await oe.execute_order_via_cdp("kss", "HOLD", "TU", 100, 12.70)
    assert bad["error_code"] == oe.E_BAD_SIDE
    short_lib = await oe.execute_order_via_cdp("lib", "SHORT", "TU", 100, 12.80,
                                              last_trade_price=12.70)
    assert short_lib["error_code"] == oe.E_UNSUPPORTED_SIDE
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_short_requires_quote_for_strict_uptick(fake_tab):
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    res = await oe.execute_order_via_cdp("kss", "SHORT", "TU", 3100, 12.80)
    assert res["error_code"] == oe.E_NO_QUOTE
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_short_uptick_violation_rejected_by_validator(fake_tab):
    await _add_sbl()
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    # short at the last price = zero-plus tick, forbidden under strict G6
    res = await oe.execute_order_via_cdp("kss", "SHORT", "TU", 3100, 12.70, last_trade_price=12.70)
    assert res["error_code"] == oe.E_VALIDATOR
    assert "zero-plus tick" in res["error"] or "Short Sale Rule" in res["error"]
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_odd_lot_rejected(fake_tab):
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 150, 12.70)
    assert res["error_code"] == oe.E_VALIDATOR
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_short_without_sbl_is_refused(fake_tab):
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    res = await oe.execute_order_via_cdp("kss", "SHORT", "TU", 3100, 12.80, last_trade_price=12.70)
    assert res["error_code"] == oe.E_NO_SBL
    assert "SBL" in res["error"]
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_missing_pin_blocks_live_submit(fake_tab, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", False)
    monkeypatch.setattr(settings, "KRUNGSRI_PIN", "")
    calls = fake_tab(FakePage(elements=KSS_TICKET))
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)
    assert res["error_code"] == oe.E_NO_PIN
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_kill_switch_blocks_everything(fake_tab):
    from app.services.kill_switch_service import kill_switch_service
    kill_switch_service._is_active = True
    try:
        calls = fake_tab(FakePage(elements=KSS_TICKET))
        res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)
        assert res["error_code"] == oe.E_KILL_SWITCH
        assert calls["n"] == 0
    finally:
        kill_switch_service._is_active = False


# ── DRY_RUN guard ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dry_run_validates_but_never_touches_the_ticket(fake_tab):
    page = FakePage(elements=KSS_TICKET)
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70, dry_run=True)

    assert res["status"] == "DRY_RUN"
    assert res["submitted"] is False
    assert res["broker_order_no"] is None
    assert res["order_id"] is None
    assert page.filled == []                      # nothing typed into a live ticket
    assert page.clicked == []                     # nothing clicked (no submit!)
    assert res["preflight"]["ok"] is True
    assert res["preflight"]["account_no"] == "3024959"


@pytest.mark.asyncio
async def test_dry_run_defaults_to_settings_flag(fake_tab, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN_MODE", True)
    page = FakePage(elements=KSS_TICKET)
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)
    assert res["status"] == "DRY_RUN" and page.clicked == []


@pytest.mark.asyncio
async def test_dry_run_survives_a_dead_cdp_tab(fake_tab):
    fake_tab(RuntimeError("no tab found"))
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70, dry_run=True)
    assert res["status"] == "DRY_RUN"
    assert res["preflight"]["ok"] is False
    assert "no tab found" in res["preflight"]["error"]


@pytest.mark.asyncio
async def test_dry_run_reports_missing_selectors(fake_tab):
    page = FakePage(elements={"input[placeholder='Symbol']": ("", True)})
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70, dry_run=True)
    assert res["preflight"]["ok"] is False
    assert "submit" in res["preflight"]["missing"]
    assert page.filled == []


# ── live paths ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_live_kss_buy_records_order_and_syncs(fake_tab, no_sync, live_dry_run):
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements=KSS_TICKET,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010077", "TU", "Buy", 12.70, 100))
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["success"] is True
    assert res["status"] == "SUBMITTED"
    assert res["broker_order_no"] == "11010077"
    assert res["order_id"] == "CDP-KRUNGSRI-11010077"
    assert res["account_no"] == "3024959"
    assert "Submit" in " ".join(page.clicked) or any("Submit" in c for c in page.clicked)
    assert no_sync["broker"] == "kss"

    async with TestingSessionLocal() as db:
        rows = (await db.execute(select(Order))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.broker_order_no == "11010077"
        assert row.source == "bot_cdp"
        assert row.status == "SUBMITTED"
        assert row.side == "BUY"
        assert row.broker == "KRUNGSRI"
        assert row.account_no == "3024959"
        assert row.volume == 100 and row.price == pytest.approx(12.70)


@pytest.mark.asyncio
async def test_live_kss_submit_accepts_the_side_labelled_button(fake_tab, no_sync, live_dry_run):
    """Live Streaming renames the submit button to the side name once a side is picked.

    Matching only "Submit" made every real submit die with E_SUBMIT_FAILED (live 2026-10-21),
    so a ticket that offers *only* ``button.bg-color-buy-20`` must still go through.
    """
    elements = {k: v for k, v in KSS_TICKET.items() if k != "button:has-text('Submit')"}
    elements["button.bg-color-buy-20"] = ("", True)
    page = FakePage(elements=elements,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010078", "TU", "Buy", 12.70, 100))
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["status"] == "SUBMITTED"
    assert res["broker_order_no"] == "11010078"
    assert "button.bg-color-buy-20" in page.clicked


@pytest.mark.asyncio
async def test_live_kss_clicks_the_submit_button_of_the_chosen_side(fake_tab, no_sync, live_dry_run):
    """A COVER ticket must click the cover-coloured button, never another side's."""
    elements = {k: v for k, v in KSS_TICKET.items() if k != "button:has-text('Submit')"}
    for side in ("BUY", "SELL", "SHORT", "COVER"):
        elements[f"button.bg-color-{side.lower()}-20"] = ("", True)
    page = FakePage(elements=elements,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010079", "TU", "Cover", 12.60, 3100))
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "COVER", "TU", 3100, 12.60)

    assert res["status"] == "SUBMITTED"
    assert "button.bg-color-cover-20" in page.clicked
    assert "button.bg-color-buy-20" not in page.clicked


@pytest.mark.asyncio
async def test_live_kss_accepts_the_side_labelled_confirm_modal(fake_tab, no_sync, live_dry_run):
    """The Order Confirmation modal's accept button is also named after the side."""
    elements = dict(KSS_TICKET)
    elements["[role=dialog] button:has-text('Cover')"] = ("", True)
    page = FakePage(elements=elements,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010080", "TU", "Cover", 12.60, 3100),
                    dialog=True)
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "COVER", "TU", 3100, 12.60)

    assert res["status"] == "SUBMITTED"
    assert res["broker_order_no"] == "11010080"
    assert res["confirm_modal"] is True
    assert "[role=dialog] button:has-text('Cover')" in page.clicked


@pytest.mark.asyncio
async def test_live_kss_unaccepted_confirm_modal_is_refused_not_read(fake_tab, no_sync, live_dry_run):
    """A modal we cannot accept means the order was NOT sent — never go read a phantom number."""
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements=dict(KSS_TICKET),
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010081", "TU", "Cover", 12.60, 3100),
                    dialog=True)
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "COVER", "TU", 3100, 12.60)

    assert res["error_code"] == oe.E_CONFIRM_FAILED
    assert res["submitted"] is False
    assert res["broker_order_no"] is None
    assert res["order_id"] is None
    async with TestingSessionLocal() as db:
        assert (await db.execute(select(Order))).scalars().all() == []


@pytest.mark.asyncio
async def test_live_kss_unreadable_order_no_is_unconfirmed_never_invented(fake_tab, no_sync, live_dry_run):
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements=KSS_TICKET,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=None)              # ledger never grows
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["success"] is False
    assert res["status"] == "UNCONFIRMED"
    assert res["broker_order_no"] is None
    assert res["error_code"] == oe.E_ORDER_NO_UNREADABLE

    async with TestingSessionLocal() as db:
        rows = (await db.execute(select(Order))).scalars().all()
        assert len(rows) == 1
        assert rows[0].broker_order_no is None
        assert rows[0].status == "UNCONFIRMED"


@pytest.mark.asyncio
async def test_live_anti_dw_blocks_submit_on_symbol_mismatch(fake_tab, no_sync, live_dry_run):
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements=KSS_TICKET,
                    ledger={"account_no": "3024959", "rows": []},
                    ignore_fill="input[placeholder='Symbol']")   # field keeps its old value
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["error_code"] == oe.E_ANTI_DW
    assert res["submitted"] is False
    assert not any("Submit" in c for c in page.clicked)
    async with TestingSessionLocal() as db:
        assert (await db.execute(select(Order))).scalars().all() == []


@pytest.mark.asyncio
async def test_live_ledger_unreadable_aborts_before_submit(fake_tab, no_sync, live_dry_run):
    page = FakePage(elements=KSS_TICKET)
    page.ledger = None                                  # evaluate() returns None
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)
    assert res["error_code"] == oe.E_LEDGER_UNREADABLE
    assert res["submitted"] is False
    assert not any("Submit" in c for c in page.clicked)


@pytest.mark.asyncio
async def test_live_short_switches_to_margin_account(fake_tab, no_sync, live_dry_run):
    await _add_sbl()
    page = FakePage(elements=KSS_TICKET, account="3024952",     # ticket opens on CASH
                    ledger={"account_no": "3024952", "rows": []},
                    submit_adds_row=("11010088", "TU", "Short", 12.80, 3100))
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "SHORT", "TU", 3100, 12.80, last_trade_price=12.70)

    assert res["status"] == "SUBMITTED"
    assert res["account_no"] == "3024959"               # margin, not the default cash acct
    assert "li:has-text('3024959')" in page.clicked
    assert any("equity-place-order-short-radio" in sel for sel in page.clicked)


@pytest.mark.asyncio
async def test_live_short_aborts_when_account_switch_fails(fake_tab, no_sync, live_dry_run):
    await _add_sbl()
    elements = dict(KSS_TICKET)
    del elements["li:has-text('3024959')"]              # dropdown option never renders
    page = FakePage(elements=elements, account="3024952",
                    ledger={"account_no": "3024952", "rows": []})
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "SHORT", "TU", 3100, 12.80, last_trade_price=12.70)

    assert res["error_code"] == oe.E_WRONG_ACCOUNT
    assert res["submitted"] is False
    assert not any("Submit" in c for c in page.clicked)


@pytest.mark.asyncio
async def test_live_liberator_buy_uses_footer_ticket(fake_tab, no_sync, live_dry_run):
    ledger = {"rows": [["9001", "10:20:07", "KBANK", "Buy", "150.00", "100", "0", "100", "0", "Queuing"]]}
    page = FakePage(elements=LIB_TICKET, ledger=ledger,
                    submit_adds_row=("9002", "KBANK", "Buy", 150.00, 100), row_style="lib")
    fake_tab(page)
    res = await oe.execute_order_via_cdp("lib", "BUY", "KBANK", 100, 150.00)

    assert res["status"] == "SUBMITTED"
    assert res["broker_order_no"] == "9002"
    assert res["account_no"] == settings.LIBERATOR_ACCOUNT_NO
    assert "button:has-text('Confirm')" in page.clicked
    assert ("#pin", "654321") in page.filled


@pytest.mark.asyncio
async def test_confirmed_draft_adapter_maps_cmd_to_side(fake_tab, no_sync, live_dry_run):
    page = FakePage(elements=KSS_TICKET, ledger={"account_no": "3024959", "rows": []},
                    submit_adds_row=("11010099", "TU", "Buy", 12.70, 100))
    fake_tab(page)
    # exact payload B.5's trade_draft_confirm postback returns
    res = await oe.execute_confirmed_order({
        "status": "TRADE_DRAFT_CONFIRMED",
        "draft_id": "DRF-123",
        "order": {"cmd": "buy", "symbol": "TU", "volume": 100, "price": 12.70,
                  "broker": "kss", "account": "margin", "account_no": "3024959"},
    })
    assert res["status"] == "SUBMITTED"
    assert res["side"] == "BUY"
    assert res["broker_order_no"] == "11010099"


# ── PIN safety (2026-10-29 lockout) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_pin_rejection_dialog_is_recorded_and_quarantines_the_broker(
        fake_tab, no_sync, live_dry_run):
    """The Settrade alert "pin is suspended" must be read, recorded and stop the next send.

    2026-10-29 regression: the alert was auto-dismissed, nothing was written to ``orders``
    and the next call typed the PIN again until the broker locked account 3024959.
    """
    from app.services import pin_guard
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements=KSS_TICKET,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=None)
    page.dialog_on_submit = ("Place Order: Error : Your pin is suspended. "
                             "The number of incorrect PIN entries exceeds the maximum.")
    fake_tab(page)

    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["success"] is False
    assert res["status"] == "REJECTED"
    assert res["error_code"] == "E_PIN_SUSPENDED"
    assert res["submitted"] is True                      # a submit DID reach the broker
    assert "suspended" in (res["error"] or "").lower()

    # The attempt leaves a row behind instead of vanishing.
    async with TestingSessionLocal() as db:
        rows = (await db.execute(select(Order))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "REJECTED"
        assert rows[0].source == "bot_cdp"
        assert "pin" in (rows[0].error_message or "").lower()

    # And the guard now refuses before anything else is typed.
    assert pin_guard.check("KRUNGSRI")["allowed"] is False

    page2 = FakePage(elements=KSS_TICKET, ledger={"rows": []})
    fake_tab(page2)
    res2 = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)
    assert res2["error_code"] == "E_PIN_GUARD"
    assert res2["submitted"] is False
    assert getattr(page2, "submitted", False) is False      # nothing was typed or clicked
    assert page2.clicked == []


@pytest.mark.asyncio
async def test_pre_submit_refusal_writes_no_order_row(fake_tab, no_sync, live_dry_run):
    """A refusal before submit (nothing typed, nothing sent) must stay out of ``orders``."""
    from tests.conftest import TestingSessionLocal

    page = FakePage(elements={**KSS_TICKET, "input#equity-place-order-buy-radio-button": ("", False)},
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]})
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["success"] is False
    assert res["submitted"] is False
    async with TestingSessionLocal() as db:
        assert (await db.execute(select(Order))).scalars().all() == []


@pytest.mark.asyncio
async def test_successful_submit_clears_an_earlier_pin_quarantine(fake_tab, no_sync, live_dry_run):
    """A broker-accepted order proves the PIN; the guard must not stay closed forever."""
    from app.services import pin_guard

    pin_guard.record_failure("KRUNGSRI", "invalid pin", code="E_PIN_REJECTED")
    pin_guard.reset("KRUNGSRI", reason="operator confirmed the PIN")   # human unlock

    page = FakePage(elements=KSS_TICKET,
                    ledger={"account_no": "3024959", "rows": [KSS_LEDGER_OLD]},
                    submit_adds_row=("11010088", "TU", "Buy", 12.70, 100))
    fake_tab(page)
    res = await oe.execute_order_via_cdp("kss", "BUY", "TU", 100, 12.70)

    assert res["status"] == "SUBMITTED"
    state = pin_guard.status("KRUNGSRI")["state"]
    assert state["failures"] == 0
    assert state["locked_until"] is None
