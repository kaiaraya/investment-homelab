# -*- coding: utf-8 -*-
"""Unit tests for KSS Persistent Session & Probe Toolkit (via shared broker_cdp)."""
import argparse
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from scripts.broker_cdp.client import (
    is_cdp_available,
    resolve_target_tab,
)
from scripts.broker_probe import cmd_status, cmd_handoff


def test_is_cdp_available_offline():
    # An unused local port should return False without crashing
    assert not is_cdp_available("http://127.0.0.1:59999", timeout=0.2)


def test_is_cdp_available_mock_online():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"Browser": "Chrome/120.0", "webSocketDebuggerUrl": "ws://..."}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_cdp_available("http://127.0.0.1:9333")


@pytest.mark.asyncio
async def test_resolve_target_tab():
    ctx = MagicMock()
    page_sso = MagicMock()
    page_sso.url = "https://www.krungsrisecurities.com/member/main.aspx"
    page_sso.title = AsyncMock(return_value="Krungsri Securities Portal")

    page_streaming = MagicMock()
    page_streaming.url = "https://streaming.settrade.com/realtime/streamingpage.jsp"
    page_streaming.title = AsyncMock(return_value="Settrade Streaming")

    page_sbl = MagicMock()
    page_sbl.url = "https://www.krungsrisecurities.com/member/sbl_realtime.aspx"
    page_sbl.title = AsyncMock(return_value="KSS SBL Realtime")

    ctx.pages = [page_sso, page_streaming, page_sbl]

    # Resolve Streaming
    assert await resolve_target_tab(ctx, "streaming", "kss") == page_streaming
    # Resolve SSO
    assert await resolve_target_tab(ctx, "sso", "kss") == page_sso
    # Resolve SBL
    assert await resolve_target_tab(ctx, "sbl", "kss") == page_sbl


@pytest.mark.asyncio
async def test_cmd_status_offline():
    args = argparse.Namespace(broker="kss", cdp_url="http://127.0.0.1:59999")
    rc = await cmd_status(args)
    assert rc == 1


@pytest.mark.asyncio
async def test_cmd_handoff_generation(tmp_path, monkeypatch):
    probes_dir = tmp_path / "probes"
    handoff_dir = tmp_path / "handoff"
    probes_dir.mkdir()
    handoff_dir.mkdir()

    monkeypatch.setattr("scripts.broker_probe.PROBE_DATA_DIR", str(probes_dir))
    monkeypatch.setattr("scripts.broker_probe.HANDOFF_DIR", str(handoff_dir))

    # Create dummy probe json with SBL details
    dummy_probe = {
        "timestamp": "20261020_170000",
        "target": "sbl",
        "url": "https://krungsrisecurities.com/sbl",
        "title": "SBL Borrow Market",
        "element_count": 2,
        "elements": [
            {
                "tag": "button",
                "suggested_selector": "#btn-borrow",
                "is_visible": True,
                "text": "Borrow Shares",
                "role": "button",
            },
            {
                "tag": "input",
                "suggested_selector": "input[name='volume']",
                "is_visible": True,
                "text": "",
                "name": "volume",
            },
        ],
        "sbl_details": {
            "is_sbl_app": True,
            "borrow_form": {
                "purchasing_power": "96,885.94",
                "customer_code": "302495",
                "symbol_input_selector": "#ctl00_MainCenter_txtSymbol",
                "symbol_input_exists": True,
                "qty_input_selector": "#ctl00_MainCenter_txtQty",
                "qty_input_exists": True,
                "borrow_button_selector": "#MainCenter_lbBorrow",
                "borrow_button_exists": True,
            },
            "inventory_sample": [
                {"symbol": "ADVANC", "fee": "3.50%", "available_volume": "5,000,000", "im_rate": "50%"}
            ],
            "active_contracts_for_return": [
                {"ref_no": "B494343", "tran_date": "20/10/2026", "symbol": "KBANK", "quantity": "1,000", "has_return_button": True, "return_button_id": "RadReturn_0"}
            ],
        },
    }
    probe_file = probes_dir / "probe_sbl_20261020_170000.json"
    probe_file.write_text(json.dumps(dummy_probe, ensure_ascii=False))

    args = argparse.Namespace(broker="kss", target="sbl", cdp_url="http://127.0.0.1:9333")
    rc = await cmd_handoff(args)
    assert rc == 0

    # Verify generated handoff markdown
    generated = list(handoff_dir.glob("PROBE-SBL-*.md"))
    assert len(generated) == 1
    content = generated[0].read_text(encoding="utf-8")
    assert "# Handoff: DOM Probe Report — SBL" in content
    assert "#btn-borrow" in content
    assert "Borrow Shares" in content
    assert "## 2. SBL Real Time — Borrow Form Contract" in content
    assert "#ctl00_MainCenter_txtSymbol" in content
    assert "ADVANC" in content
    assert "B494343" in content


@pytest.mark.asyncio
async def test_open_target_tabs_skips_when_all_tabs_open():
    from scripts.broker_cdp.brokers import kss_open_tabs

    ctx = MagicMock()
    page_streaming = MagicMock(url="https://wma1.settrade.com/realtime/streaming7/StreamingPage.jsp")
    page_sbl = MagicMock(url="https://www.krungsrisecurities.com/sblweb/MainSBL.aspx")
    ctx.pages = [page_streaming, page_sbl]

    await kss_open_tabs(ctx)

    ctx.new_page.assert_not_called()


@pytest.mark.asyncio
async def test_open_target_tabs_navigates_sso_and_sbl_urls():
    from scripts.broker_cdp.brokers import kss_open_tabs, SSO_STREAMING_URL, SSO_SBL_START_URL

    ctx = MagicMock()
    member_page = MagicMock(url="https://www.krungsrisecurities.com/th/member/main.aspx")
    ctx.pages = [member_page]

    new_page = MagicMock()
    new_page.goto = AsyncMock()
    new_page.wait_for_timeout = AsyncMock()
    new_page.query_selector = AsyncMock(return_value=None)

    stream_page = MagicMock(url="https://wma1.settrade.com/realtime/streaming7/StreamingPage.jsp")
    sbl_page = MagicMock(url="https://www.krungsrisecurities.com/sblweb/MainSBL.aspx")

    async def goto_side_effect(url, *a, **k):
        if "Put_SSO_Settrade" in url:
            ctx.pages.append(stream_page)
        elif "SBL/start" in url:
            ctx.pages.append(sbl_page)

    new_page.goto.side_effect = goto_side_effect
    ctx.new_page = AsyncMock(return_value=new_page)

    with patch("scripts.broker_cdp.brokers.asyncio.sleep", new=AsyncMock(return_value=None)):
        await kss_open_tabs(ctx)

    assert new_page.goto.await_count == 2
    called_urls = [call[0][0] for call in new_page.goto.call_args_list]
    assert SSO_STREAMING_URL in called_urls
    assert SSO_SBL_START_URL in called_urls
    assert stream_page in ctx.pages
    assert sbl_page in ctx.pages
