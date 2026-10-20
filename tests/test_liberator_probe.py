# -*- coding: utf-8 -*-
"""Unit tests for Liberator Persistent Session & Probe Toolkit."""
import argparse
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from scripts.liberator.liberator_cdp_client import (
    is_cdp_available,
    resolve_target_tab,
)
from scripts.liberator_probe import cmd_status, cmd_handoff


def test_liberator_is_cdp_available_offline():
    assert not is_cdp_available("http://127.0.0.1:59998", timeout=0.2)


def test_liberator_is_cdp_available_mock_online():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"Browser": "Chrome/120.0", "webSocketDebuggerUrl": "ws://..."}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_cdp_available("http://127.0.0.1:9334")


@pytest.mark.asyncio
async def test_liberator_resolve_target_tab():
    ctx = MagicMock()
    page_portfolio = MagicMock()
    page_portfolio.url = "https://webtrade.liberator.co.th/Portfolio"
    page_portfolio.title = AsyncMock(return_value="Liberator Portfolio")

    page_trade = MagicMock()
    page_trade.url = "https://webtrade.liberator.co.th/Trade"
    page_trade.title = AsyncMock(return_value="Liberator Trade & Order")

    page_market = MagicMock()
    page_market.url = "https://webtrade.liberator.co.th/Market"
    page_market.title = AsyncMock(return_value="Liberator Market Overview")

    ctx.pages = [page_portfolio, page_trade, page_market]

    # Resolve Portfolio
    assert await resolve_target_tab(ctx, "portfolio") == page_portfolio
    # Resolve Trade
    assert await resolve_target_tab(ctx, "trade") == page_trade
    # Resolve Market
    assert await resolve_target_tab(ctx, "market") == page_market


@pytest.mark.asyncio
async def test_liberator_cmd_status_offline():
    args = argparse.Namespace(cdp_url="http://127.0.0.1:59998")
    rc = await cmd_status(args)
    assert rc == 1


@pytest.mark.asyncio
async def test_liberator_cmd_handoff_generation(tmp_path, monkeypatch):
    probes_dir = tmp_path / "probes"
    handoff_dir = tmp_path / "handoff"
    probes_dir.mkdir()
    handoff_dir.mkdir()

    monkeypatch.setattr("scripts.liberator_probe.PROBE_DATA_DIR", str(probes_dir))
    monkeypatch.setattr("scripts.liberator_probe.HANDOFF_DIR", str(handoff_dir))

    # Create dummy Liberator probe json
    dummy_probe = {
        "timestamp": "20261020_174000",
        "broker": "liberator",
        "target": "trade",
        "url": "https://webtrade.liberator.co.th/Trade",
        "title": "Liberator Trade",
        "element_count": 2,
        "elements": [
            {
                "tag": "button",
                "suggested_selector": "#btn-buy",
                "is_visible": True,
                "text": "Buy Stock",
                "role": "button",
            },
            {
                "tag": "input",
                "suggested_selector": "input[name='pin']",
                "is_visible": True,
                "text": "",
                "name": "pin",
            },
        ],
    }
    probe_file = probes_dir / "probe_liberator_trade_20261020_174000.json"
    probe_file.write_text(json.dumps(dummy_probe, ensure_ascii=False))

    args = argparse.Namespace(target="trade", cdp_url="http://127.0.0.1:9334")
    rc = await cmd_handoff(args)
    assert rc == 0

    # Verify generated handoff markdown
    generated = list(handoff_dir.glob("PROBE-LIBERATOR-TRADE-*.md"))
    assert len(generated) == 1
    content = generated[0].read_text(encoding="utf-8")
    assert "# Handoff: DOM Probe Report — LIBERATOR (TRADE)" in content
    assert "#btn-buy" in content
    assert "Buy Stock" in content


def test_liberator_inspect_dom_or_splits_comma_keywords():
    """Comma-separated --focus keywords must be OR'd, not one literal regex."""
    import inspect
    from scripts.liberator.liberator_cdp_client import inspect_dom_elements

    src = inspect.getsource(inspect_dom_elements)
    assert "split(',')" in src
    assert ".join('|')" in src


@pytest.mark.asyncio
async def test_liberator_inspect_dom_passes_focus_through():
    from scripts.liberator.liberator_cdp_client import inspect_dom_elements

    page = MagicMock()
    page.evaluate = AsyncMock(return_value=[])

    result = await inspect_dom_elements(page, keyword_filter="line,cash,balance", max_elements=10)

    assert result == []
    page.evaluate.assert_awaited_once()
    assert page.evaluate.call_args[0][1][1] == "line,cash,balance"
    assert page.evaluate.call_args[0][1][2] == 10
