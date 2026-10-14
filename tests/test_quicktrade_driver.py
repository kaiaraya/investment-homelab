"""Unit tests (mock DOM, no browser) for the Krungsri Quick Trade driver (Pillar 6).

Covers the quote scraper, the direct-URL order-detail flow, the price/PIN amendment
fill, and the DRY_RUN gating of Submit. No real navigation is performed.
"""
import pytest

from app.brokers.krungsri.quicktrade_driver import (
    KrungsriQuickTradeDriver,
    ORDER_DETAIL_URL_TMPL,
)


class FakePage:
    def __init__(self, evaluate_result=None):
        self.calls = []
        self.filled = {}
        self.clicks = []
        self.selected = []
        self.waits = []
        self.url = ""
        self._evaluate_result = evaluate_result or {}

    async def fill(self, selector, value):
        self.calls.append(("fill", selector, value))
        self.filled[selector] = value

    async def click(self, selector, **kw):
        self.calls.append(("click", selector))
        self.clicks.append(selector)

    async def select_option(self, selector, **kw):
        self.calls.append(("select_option", selector, kw))
        self.selected.append((selector, kw))

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def goto(self, url, **kw):
        self.url = url
        self.calls.append(("goto", url))

    async def evaluate(self, js):
        self.calls.append(("evaluate", js))
        return self._evaluate_result


class FakeContext:
    def __init__(self):
        self.opened = []

    async def new_page(self):
        p = FakePage()
        self.opened.append(p)
        return p


# --- pure parsers ---------------------------------------------------------

def test_parse_bid_offer_uses_first_row_as_best():
    rows = [["", "29.00", "29.25", ""], ["", "28.75", "29.50", ""]]
    out = KrungsriQuickTradeDriver.parse_bid_offer(rows)
    assert out["best_bid"] == 29.00
    assert out["best_offer"] == 29.25
    assert out["bids"] == [29.00, 28.75]
    assert out["offers"] == [29.25, 29.50]


def test_parse_bid_offer_skips_header_and_blank_rows():
    rows = [["Volume", "Bid", "Offer", "Volume"], ["1,000", "29.00", "29.25", "2,000"], []]
    out = KrungsriQuickTradeDriver.parse_bid_offer(rows)
    assert out["best_bid"] == 29.00
    assert out["best_offer"] == 29.25


def test_parse_market_info_reads_explicit_last():
    out = KrungsriQuickTradeDriver.parse_market_info(
        "High/Low 29.50/28.75 Ceil./Floor 31.25/27.25 Last 29.25 Avg./Close 29.10/29.00")
    assert out["last"] == 29.25


def test_parse_market_info_does_not_guess_last_from_close():
    out = KrungsriQuickTradeDriver.parse_market_info("High/Low 29.50/28.75 Avg./Close 29.10/29.00")
    assert out["last"] is None


def test_parse_order_ledger_header_mapping():
    rows = [
        ["", "Order no", "Symbol", "Date", "Time", "Side", "Price", "Volume", "Matched", "Balance", "Cancelled", "Status"],
        ["", "11008198", "MTC", "14/10/2026", "10:15:00", "Short", "29.25", "1,000", "500", "500", "0", "Open"],
    ]
    orders = KrungsriQuickTradeDriver.parse_order_ledger(rows)
    assert len(orders) == 1
    o = orders[0]
    assert o["order_no"] == "11008198"
    assert o["symbol"] == "MTC"
    assert o["side"] == "SHORT"
    assert o["price"] == 29.25
    assert o["volume"] == 1000
    assert o["balance"] == 500


def test_parse_order_ledger_positional_fallback():
    rows = [["11008198", "MTC", "14/10/2026", "10:15:00", "Short", "29.25", "1,000", "500", "500", "0", "Open"]]
    orders = KrungsriQuickTradeDriver.parse_order_ledger(rows)
    assert orders[0]["order_no"] == "11008198"
    assert orders[0]["side"] == "SHORT"
    assert orders[0]["balance"] == 500


def test_find_order():
    orders = [{"order_no": "1"}, {"order_no": "11008198"}]
    assert KrungsriQuickTradeDriver.find_order(orders, "11008198")["order_no"] == "11008198"
    assert KrungsriQuickTradeDriver.find_order(orders, "999") is None


# --- page primitives (mock DOM) -------------------------------------------

async def test_fetch_quote_fills_symbol_and_reads_tables():
    d = KrungsriQuickTradeDriver()
    page = FakePage(evaluate_result={
        "symbol": "MTC",
        "bid_offer_rows": [["", "29.00", "29.25", ""]],
        "info_text": "Last 29.25",
    })
    out = await d._fetch_quote(page, "mtc")
    assert ("fill", "#eqQuoteSymbol", "MTC") in page.calls
    assert "#btnGetQuotes" in page.clicks
    assert out["symbol"] == "MTC"
    assert out["best_bid"] == 29.00
    assert out["best_offer"] == 29.25
    assert out["last"] == 29.25


async def test_fetch_quote_requires_symbol():
    d = KrungsriQuickTradeDriver()
    with pytest.raises(ValueError):
        await d._fetch_quote(FakePage(), "  ")


async def test_select_account_uses_equity_label():
    d = KrungsriQuickTradeDriver()
    page = FakePage()
    await d._select_account(page, "3024959")
    assert page.selected
    assert page.selected[0][1].get("label") == "3024959 (Equity)"


async def test_open_order_detail_uses_direct_url():
    d = KrungsriQuickTradeDriver()
    ctx = FakeContext()
    page = await d._open_order_detail(ctx, "11008198", "3024959", "2026-10-14")
    assert page.url == ORDER_DETAIL_URL_TMPL.format(
        account_no="3024959", order_no="11008198", trade_date="2026-10-14")
    assert "orderNo=11008198" in page.url
    assert "accountNo=3024959" in page.url
    assert "tradeDate=2026-10-14" in page.url


async def test_fill_amendment_sets_price_and_pin_only():
    d = KrungsriQuickTradeDriver()
    page = FakePage()
    price = await d._fill_amendment(page, 29.5, "1234")
    assert price == "29.50"
    assert (page.filled.get("input[formcontrolname='price']") == "29.50" or
            page.filled.get("input[name='price']") == "29.50")
    assert any("pin" in s.lower() for s in page.filled if "pin" in s.lower())
    assert not any("volume" in s.lower() for s in page.filled)
    assert any("Change Price& Volume" in c for c in page.clicks)


async def test_submit_skipped_when_dry_run():
    d = KrungsriQuickTradeDriver()
    page = FakePage()
    assert await d._submit(page, dry_run=True) is False
    assert page.clicks == []


async def test_submit_clicks_when_live():
    d = KrungsriQuickTradeDriver()
    page = FakePage()
    assert await d._submit(page, dry_run=False) is True
    assert any("Submit" in c for c in page.clicks)


async def test_amend_price_requires_account_no():
    d = KrungsriQuickTradeDriver()
    out = await d.amend_price("11008198", 29.50, account_no="")
    assert out["success"] is False
    assert "account_no" in out["error"]


def test_candidate_accounts_are_deduped_and_ordered():
    from app.brokers.krungsri.quicktrade_driver import quicktrade_driver
    from app.core.config import settings
    accs = quicktrade_driver.candidate_accounts()
    margin = str(settings.TRADEMAN_ACCOUNT_NO_MARGIN).strip()
    cash = str(settings.TRADEMAN_ACCOUNT_NO_CASH).strip()
    assert accs == list(dict.fromkeys([a for a in (margin, cash) if a]))
    assert len(accs) == len(set(accs))


async def test_amend_price_result_always_carries_submitted_and_success_keys():
    """The LINE card / handler read `submitted` off this dict — the key must never disappear."""
    d = KrungsriQuickTradeDriver()
    out = await d.amend_price("11008198", 29.50, account_no="")
    assert out["success"] is False        # no account ⇒ fail closed, and no browser is launched
    assert out["submitted"] is False      # nothing was sent (Anti-Mock)
    assert out["dry_run"] in (True, False)
    assert set(out) >= {"success", "order_no", "new_price", "dry_run", "submitted", "error"}
