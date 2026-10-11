import asyncio
import re
import json
import logging
from typing import List, Dict, Any, Optional
import httpx

from app.core.config import settings
from app.schemas.order import OrderSide
from app.schemas.intelligence import (
    SignalParseResult,
    ExtractedOrder,
    ExtractedWatchlistTrigger,
    ExtractedHoldPosition,
    ExtractedTPSL,
    TPSLParseResult
)
from app.services.validator import validator

logger = logging.getLogger(__name__)


class SignalIntelligenceParser:
    """
    Intelligent Signal & Strategy Text Parser.
    Extracts actionable trade orders, trailing stops, and watchlist trigger conditions
    from freeform Thai natural language or rich markdown portfolio strategy reports.
    Uses Google Gemini 3.6 Flash when GEMINI_API_KEY is available, with high-precision Regex Fallback.
    """

    async def parse_strategy_with_ai(self, text: str) -> SignalParseResult:
        """
        Primary entrypoint: Ingests strategy report using Type-Safe PydanticAI Agent with Gemini 3.6 Flash.
        Features Dual-Engine Resilience: Automatically falls back to deterministic rule parser
        if API is unavailable or quota is exceeded.
        """
        try:
            from app.ai.signal_agent import signal_ai_parser
            logger.info("Executing Type-Safe PydanticAI SignalParserAgent...")
            result = await signal_ai_parser.parse_strategy(text)
            if result and (result.immediate_orders or result.watchlist_triggers or result.hold_positions):
                return result
        except Exception as e:
            logger.warning(
                f"PydanticAI agent execution failed or quota unavailable ({e}). "
                f"Activating Dual-Engine Deterministic Fallback..."
            )

        # Dual-Engine Fallback: Deterministic Regex/Keyword Parser
        fallback_res = self.parse_text(text)
        fallback_res.source_method = "deterministic_fallback"
        logger.info(
            f"Dual-Engine Fallback completed: {len(fallback_res.immediate_orders)} immediate orders, "
            f"{len(fallback_res.watchlist_triggers)} triggers, {len(fallback_res.hold_positions)} hold positions"
        )
        return fallback_res

    async def _call_gemini_for_strategy(self, text: str) -> Optional[SignalParseResult]:
        """
        Calls Gemini 3.6 Flash REST API with strict Structured JSON Output and 45s timeout.
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}"
        
        system_prompt = (
            "You are an expert Thai stock trading system assistant operating on the Stock Exchange of Thailand (SET).\n"
            "Analyze the given strategy text or user message (which may be freeform Thai conversation or Markdown report).\n"
            "Extract the following categories strictly into JSON:\n\n"
            "1. 'immediate_orders': Actions requiring immediate execution today (e.g. Cut Loss, Hard Time-Exit, Stop Loss, Take Profit now, Sell/Cover/Buy/Short).\n"
            "   Each item must have:\n"
            "   - 'symbol': Clean uppercase stock ticker (2-8 chars, e.g. 'TRUE', 'TIDLOR', 'AOT', 'TFM'). Do NOT include notes like '(ไม้ 2)' or '(เศษหุ้น)'.\n"
            "   - 'side': One of 'BUY', 'SELL', 'SHORT', 'COVER'.\n"
            "   - 'volume': Integer number of shares if explicitly stated (e.g. 600, 2000). If relative (e.g. 'ครึ่งหนึ่ง', 'ปิดทั้งหมด'), set volume to 0.\n"
            "   - 'volume_pct': Float percentage if relative quantity (e.g. 50.0 for half, 100.0 for all/close position, 30.0 for 30%), or null if explicit volume given.\n"
            "   - 'is_relative_volume': Boolean (true if stated as fraction/all/half/percentage, false if exact number of shares).\n"
            "   - 'price': Target or market price (float, e.g. 62.25). If current price is given, use it.\n"
            "   - 'reason': Short explanation (e.g. 'Stop Loss 2.0%', 'Time-Exit 10 days', 'Take profit').\n\n"
            "2. 'watchlist_triggers': Price-based monitoring triggers.\n"
            "   IMPORTANT: For Dynamic Runners with both Trailing Stop (e.g. breakeven cost) and Dynamic TP target (+5%):\n"
            "   - Create ONE trigger for the Trailing Stop: action='SELL' (or 'COVER' if short), condition='PRICE_BELOW' (or 'PRICE_ABOVE' if short), trigger_price=trailing_stop_price, notes='Trailing Stop Breakeven'.\n"
            "   - Create ONE trigger for the Dynamic TP: action='SELL' (or 'COVER' if short), condition='PRICE_ABOVE' (or 'PRICE_BELOW' if short), trigger_price=tp_target_price, notes='Dynamic TP Target +5%'.\n"
            "   - For Weed-out Watchlist positions (e.g. PR9) where a Stop Loss is specified, create a trigger for the stop loss level.\n"
            "   Each item must have: 'symbol', 'action', 'volume', 'condition' ('PRICE_ABOVE' or 'PRICE_BELOW'), 'trigger_price', 'notes'.\n\n"
            "3. 'hold_positions': Positions advised to HOLD (including Active Swings and Weed-Out Watchlist positions).\n"
            "   Each item must have:\n"
            "   - 'symbol': Clean uppercase stock ticker.\n"
            "   - 'volume': Integer volume.\n"
            "   - 'position_type': 'LONG' or 'SHORT'.\n"
            "   - 'cost_price': Float cost price if provided, else null.\n"
            "   - 'current_price': Float current market price if provided, else null.\n"
            "   - 'current_return_pct': Float profit/loss percentage if provided, else null.\n"
            "   - 'days_held': Integer days held if provided, else null.\n"
            "   - 'group_type': 'ACTIVE_SWING' for normal swing cycle, or 'WEED_OUT' for weed-out watchlist queue.\n"
            "   - 'warning_note': Key warning if any (e.g. 'Time-Exit วันที่ 9/10', 'ปริ่ม Stop 2.0%'), else null.\n"
            "   - 'trailing_stop_price': Float price if trailing stop mentioned, else null.\n"
            "   - 'note': Notes on holding.\n\n"
            "4. 'strategy_summary': 1-2 concise sentences summarizing the overall strategy, model parameters (Win rate, Stop Loss %, Dynamic TP %, Time-Exit days) in Thai.\n\n"
            "Output ONLY valid JSON adhering strictly to this schema."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": system_prompt},
                    {"text": f"Input Text to Parse:\n{text}"}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_json = json.loads(raw_text)

                immediate_orders: List[ExtractedOrder] = []
                for item in parsed_json.get("immediate_orders", []):
                    clean_sym = self._clean_symbol(item.get("symbol", ""))
                    if not clean_sym:
                        continue
                    
                    side_str = item.get("side", "SELL").upper()
                    try:
                        side_enum = OrderSide(side_str)
                    except ValueError:
                        side_enum = OrderSide.SELL

                    vol_raw = item.get("volume")
                    vol = int(vol_raw) if vol_raw is not None else 0
                    vol_pct_raw = item.get("volume_pct")
                    vol_pct = float(vol_pct_raw) if vol_pct_raw is not None else None
                    is_rel = bool(item.get("is_relative_volume", False)) or (vol == 0 and vol_pct is not None)
                    px_raw = item.get("price")
                    px = float(px_raw) if px_raw is not None else 0.0
                    reason = str(item.get("reason", ""))

                    is_valid_lot = (vol % 100 == 0) if not is_rel and vol > 0 else True

                    immediate_orders.append(ExtractedOrder(
                        symbol=clean_sym,
                        side=side_enum,
                        volume=vol,
                        price=px,
                        reason=reason,
                        section="AI Ingested",
                        is_valid_lot=is_valid_lot,
                        volume_pct=vol_pct if vol_pct is not None else (100.0 if is_rel else None),
                        is_relative_volume=is_rel
                    ))

                watchlist_triggers: List[ExtractedWatchlistTrigger] = []
                for item in parsed_json.get("watchlist_triggers", []):
                    clean_sym = self._clean_symbol(item.get("symbol", ""))
                    if not clean_sym:
                        continue
                    w_vol_raw = item.get("volume")
                    w_vol = int(w_vol_raw) if w_vol_raw is not None else 0
                    w_px_raw = item.get("trigger_price")
                    w_px = float(w_px_raw) if w_px_raw is not None else 0.0
                    watchlist_triggers.append(ExtractedWatchlistTrigger(
                        symbol=clean_sym,
                        action=str(item.get("action", "SELL")).upper(),
                        volume=w_vol,
                        condition=str(item.get("condition", "PRICE_ABOVE")).upper(),
                        trigger_price=w_px,
                        notes=str(item.get("notes", "")),
                        section="AI Ingested Watchlist"
                    ))

                hold_positions: List[ExtractedHoldPosition] = []
                for item in parsed_json.get("hold_positions", []):
                    clean_sym = self._clean_symbol(item.get("symbol", ""))
                    if not clean_sym:
                        continue

                    p_type = str(item.get("position_type", "LONG")).upper()
                    if p_type not in ["LONG", "SHORT"]:
                        p_type = "LONG"

                    g_type = str(item.get("group_type", "ACTIVE_SWING")).upper()
                    if g_type not in ["ACTIVE_SWING", "WEED_OUT"]:
                        g_type = "ACTIVE_SWING"

                    h_vol_raw = item.get("volume")
                    h_vol = int(h_vol_raw) if h_vol_raw is not None else 0

                    hold_positions.append(ExtractedHoldPosition(
                        symbol=clean_sym,
                        volume=h_vol,
                        position_type=p_type,
                        current_return_pct=float(item["current_return_pct"]) if item.get("current_return_pct") is not None else None,
                        trailing_stop_price=float(item["trailing_stop_price"]) if item.get("trailing_stop_price") is not None else None,
                        cost_price=float(item["cost_price"]) if item.get("cost_price") is not None else None,
                        current_price=float(item["current_price"]) if item.get("current_price") is not None else None,
                        days_held=int(item["days_held"]) if item.get("days_held") is not None else None,
                        group_type=g_type,
                        warning_note=str(item.get("warning_note", "")) if item.get("warning_note") else None,
                        note=str(item.get("note", ""))
                    ))

                summary = parsed_json.get("strategy_summary", "")

                return SignalParseResult(
                    total_parsed=len(immediate_orders) + len(watchlist_triggers) + len(hold_positions),
                    immediate_orders=immediate_orders,
                    watchlist_triggers=watchlist_triggers,
                    hold_positions=hold_positions,
                    raw_sections_found=["AI Ingestion (Gemini 3.6 Flash)"],
                    queued_order_ids=[],
                    strategy_summary=summary,
                    source_method="gemini_3.6_flash"
                )
            else:
                err_msg = f"Gemini API returned status {resp.status_code}: {resp.text}"
                logger.error(err_msg)
                raise RuntimeError(err_msg)

    def _clean_symbol(self, raw_symbol: str) -> str:
        """Removes parentheses, notes, odd-lot tags, whitespace from stock ticker."""
        cleaned = re.sub(r'\(.*?\)', '', raw_symbol).strip()
        cleaned = re.sub(r'[^A-Z0-9]', '', cleaned.upper())
        return cleaned

    def parse_text(self, text: str) -> SignalParseResult:
        """
        Deterministic Regex & Keyword Strategy Parser.
        Operates without internet or API keys.
        """
        immediate_orders: List[ExtractedOrder] = []
        watchlist_triggers: List[ExtractedWatchlistTrigger] = []
        hold_positions: List[ExtractedHoldPosition] = []
        sections_found: List[str] = []

        clean_text = text.strip()
        lines = clean_text.splitlines()

        # 1. Check for single simple signal (e.g. "BUY TRUE @ 13.20 Vol: 3800" or "BUY ADVANC @ 250.00 Vol: 200")
        simple_pattern = re.search(
            r'^\s*(BUY|SELL|SHORT|COVER)\s+([A-Z0-9]{2,8})\s*(?:@|at)?\s*([0-9.]+)\s*(?:Vol:\s*|\s+)?([0-9,]+)\s*$',
            clean_text,
            re.IGNORECASE
        )
        if simple_pattern:
            side_str, sym_raw, px_str, vol_str = simple_pattern.groups()
            sym = self._clean_symbol(sym_raw)
            vol = int(vol_str.replace(",", ""))
            px = float(px_str)
            side_enum = OrderSide(side_str.upper())
            is_valid, err = validator.validate_all(sym, side_enum.value, vol, px, record_idempotency=False)
            immediate_orders.append(ExtractedOrder(
                symbol=sym,
                side=side_enum,
                volume=vol,
                price=px,
                reason="Direct Signal Ingest",
                section="Single Signal",
                is_valid_lot=is_valid,
                validation_error=err,
                is_relative_volume=False
            ))
            return SignalParseResult(
                total_parsed=1,
                immediate_orders=immediate_orders,
                watchlist_triggers=[],
                hold_positions=[],
                raw_sections_found=["Single Signal"],
                queued_order_ids=[],
                strategy_summary="Deterministic Regex Parsed Strategy",
                source_method="regex"
            )

        # Pre-process: merge continuation lines (e.g. lines starting with ➡️)
        processed_lines = []
        for l in text.splitlines():
            s = l.strip()
            if s.startswith("➡️") and processed_lines:
                processed_lines[-1] = processed_lines[-1] + " " + s
            elif s:
                processed_lines.append(s)

        current_section = "General"

        for line in processed_lines:
            # Detect Section Headers
            is_header = line.startswith(("🚨", "🟢", "🎯", "📋", "🟡", "#", "==")) or bool(re.match(r'^[0-9]+\.[0-9]+', line))
            if is_header and ("5.1" in line or "Hard Exit" in line):
                current_section = "5.1 Hard Exit & Cut Loss"
                sections_found.append(current_section)
                continue
            elif is_header and ("5.2" in line or "Climax TP" in line or "Dynamic TP" in line):
                current_section = "5.2 Dynamic TP & Strong Runners"
                sections_found.append(current_section)
                continue
            elif is_header and ("5.3" in line or "Active Swings" in line or "Watchlist" in line or "สถานะคงค้าง" in line):
                current_section = "5.3 Active Swings & Watchlist"
                sections_found.append(current_section)
                continue

            # Stock Symbol prefix match: e.g. "TLI: [SELL 2,000 หุ้น]...", "DELTA: ...", "AOT (ไม้ 2): ...", "AOT (ไม้ 2) (LONG | ...)"
            stock_match = re.match(r'^([A-Z0-9]{2,8})(?:\s*\([^)]*\))*\s*(?::|\s*\(|➡️|\s+)', line)
            if not stock_match:
                continue

            raw_sym = stock_match.group(1)
            if raw_sym.upper() in ["IMPORTANT", "ROLLING", "ADAPTIVE", "DYNAMIC", "SWING"]:
                continue
            sym = self._clean_symbol(raw_sym)

            # Extract market price if present in line:
            curr_px_match = re.search(r'ราคาปัจจุบัน\s*[฿]?([0-9.]+)', line)
            px: float = 0.0
            if curr_px_match:
                px = float(curr_px_match.group(1))
            else:
                px_match = re.search(r'(?:ตลาด|@|ราคา)\s*[฿]?([0-9.]+)', line)
                if px_match:
                    px = float(px_match.group(1))

            # 1. Section 5.1 Hard Exit & Cut Loss -> Immediate Orders
            if "5.1" in current_section:
                sell_m = re.search(r'SELL\s+(?:ปิดสถานะทั้งหมด|Cut\s*Loss\s*ทั้งหมด|ปิดเศษหุ้น|ทันที)?\s*([0-9,]+)\s*หุ้น(?:\s*:\s*(.*))?', line, re.IGNORECASE)
                if not sell_m:
                    sell_m = re.search(r'\[SELL\s+([0-9,]+)\s*หุ้น\]', line)
                
                vol = 0
                reason = "Hard Exit / Cut Loss"
                if sell_m:
                    vol = int(sell_m.group(1).replace(",", ""))
                    if sell_m.lastindex and sell_m.lastindex >= 2 and sell_m.group(2):
                        reason = sell_m.group(2).strip()

                is_valid, err = validator.validate_all(sym, "SELL", vol, px, record_idempotency=False)
                immediate_orders.append(ExtractedOrder(
                    symbol=sym,
                    side=OrderSide.SELL,
                    volume=vol,
                    price=px,
                    reason=reason,
                    section=current_section,
                    is_valid_lot=is_valid,
                    validation_error=err,
                    is_relative_volume=False
                ))
                continue

            # 2. Section 5.2 Climax TP & Strong Runners
            if "5.2" in current_section:
                vol_m = re.search(r'HOLD\s+([0-9,]+)\s*หุ้น', line, re.IGNORECASE)
                vol = int(vol_m.group(1).replace(",", "")) if vol_m else 0

                ts_m = re.search(r'Trailing\s*Stop.*?([0-9]+\.[0-9]+)', line, re.IGNORECASE)
                if ts_m:
                    ts_px = float(ts_m.group(1))
                    watchlist_triggers.append(ExtractedWatchlistTrigger(
                        symbol=sym,
                        action="SELL",
                        volume=vol,
                        condition="PRICE_BELOW",
                        trigger_price=ts_px,
                        notes="Trailing Stop Breakeven"
                    ))

                tp_m = re.search(r'(?:เป้า|\+5%).*?([0-9]+\.[0-9]+)', line, re.IGNORECASE)
                if tp_m:
                    tp_px = float(tp_m.group(1))
                    watchlist_triggers.append(ExtractedWatchlistTrigger(
                        symbol=sym,
                        action="SELL",
                        volume=vol,
                        condition="PRICE_ABOVE",
                        trigger_price=tp_px,
                        notes="Dynamic TP Target +5%"
                    ))
                continue

            # 3. Section 5.3 Active Swings & Watchlist
            if "5.3" in current_section:
                vol_m = re.search(r'HOLD\s+([0-9,]+)\s*หุ้น', line, re.IGNORECASE)
                vol = int(vol_m.group(1).replace(",", "")) if vol_m else 0

                days_m = re.search(r'(?:ถือ|ถือครอง)\s*([0-9]+)\s*วัน', line)
                days = int(days_m.group(1)) if days_m else None

                p_type = "SHORT" if "SHORT" in line.upper() else "LONG"
                g_type = "WEED_OUT" if ("Weed-Out" in line or "Watchlist" in line or "คิว" in line) else "ACTIVE_SWING"

                warn_m = re.search(r'\(([^)]*(?:Time-Exit|Stop|เฝ้าระวัง|ใกล้ครบ)[^)]*)\)', line)
                warn_note = warn_m.group(1) if warn_m else None

                hold_positions.append(ExtractedHoldPosition(
                    symbol=sym,
                    volume=vol,
                    position_type=p_type,
                    days_held=days,
                    group_type=g_type,
                    warning_note=warn_note
                ))
                continue

        return SignalParseResult(
            total_parsed=len(immediate_orders) + len(watchlist_triggers) + len(hold_positions),
            immediate_orders=immediate_orders,
            watchlist_triggers=watchlist_triggers,
            hold_positions=hold_positions,
            raw_sections_found=list(set(sections_found)),
            queued_order_ids=[],
            strategy_summary="Deterministic Regex Parsed Strategy",
            source_method="regex"
        )

    async def parse_multi_stock_tpsl(self, text: str) -> TPSLParseResult:
        """
        Extracts multi-stock TP and SL for Long and Short positions from Thai messages.
        Uses Gemini 3.6 Flash when configured, otherwise regex fallback.
        """
        if settings.GEMINI_API_KEY:
            try:
                res = await self._call_gemini_for_tpsl(text)
                if res and res.items:
                    return res
            except Exception as e:
                logger.warning(f"Gemini TP/SL parse failed, falling back to regex: {e}")
        
        return self._parse_tpsl_regex_fallback(text)

    async def _call_gemini_for_tpsl(self, text: str) -> Optional[TPSLParseResult]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={settings.GEMINI_API_KEY}"
        system_prompt = (
            "You are an expert Thai stock trading assistant. Extract stock symbols, position sides (LONG or SHORT), "
            "Take Profit (TP) prices, and Stop Loss (SL) prices from the user's Thai message. "
            "Output JSON format: [{\"symbol\": \"...\", \"side\": \"LONG\"|\"SHORT\", \"take_profit\": 0.0, \"stop_loss\": 0.0, \"notes\": \"...\"}]. "
            "Output ONLY valid JSON."
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": system_prompt},
                    {"text": f"User message: {text}"}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                items_data = json.loads(raw_text)
                if isinstance(items_data, dict) and "items" in items_data:
                    items_data = items_data["items"]
                items = [ExtractedTPSL(**item) for item in items_data]
                return TPSLParseResult(items=items, confidence=0.98, source_method="gemini_3.6_flash")
        return None

    def _parse_tpsl_regex_fallback(self, text: str) -> TPSLParseResult:
        items: List[ExtractedTPSL] = []
        chunks = re.split(r'(?:[\n,;]|ส่วน|แล้วก็|และ|กับ)', text, flags=re.IGNORECASE)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            sym_match = re.search(r'\b([A-Z0-9]{2,8})\b', chunk)
            if not sym_match:
                continue

            symbol = sym_match.group(1).upper()
            if symbol in ["TP", "SL", "BUY", "SELL", "HOLD", "SHORT", "COVER"]:
                symbols = re.findall(r'\b([A-Z]{2,8})\b', chunk)
                valid_syms = [s for s in symbols if s not in ["TP", "SL", "BUY", "SELL", "HOLD", "SHORT", "COVER"]]
                if not valid_syms:
                    continue
                symbol = valid_syms[0].upper()

            side = "SHORT" if re.search(r'(?:short|ชอร์ต|ยืม|sbl)', chunk, re.IGNORECASE) else "LONG"

            tp: Optional[float] = None
            tp_match = re.search(
                r'(?:TP|เป้า(?:หมาย)?|ขายทำกำไร|take\s*profit)\s*(?:ที่|คือ|เท่ากับ|:|=)?\s*([0-9]+(?:\.[0-9]+)?)',
                chunk,
                re.IGNORECASE
            )
            if tp_match:
                tp = float(tp_match.group(1))

            sl: Optional[float] = None
            sl_match = re.search(
                r'(?:SL|คัท(?:ลอส)?|ตัดขาดทุน|stop\s*loss)\s*(?:ที่|คือ|เท่ากับ|:|=)?\s*([0-9]+(?:\.[0-9]+)?)',
                chunk,
                re.IGNORECASE
            )
            if sl_match:
                sl = float(sl_match.group(1))

            if tp is not None or sl is not None:
                items.append(ExtractedTPSL(
                    symbol=symbol,
                    side=side,
                    take_profit=tp,
                    stop_loss=sl,
                    notes=chunk[:60]
                ))

        return TPSLParseResult(
            items=items,
            confidence=0.85 if items else 0.0,
            source_method="regex_fallback"
        )


signal_parser = SignalIntelligenceParser()
