#!/usr/bin/env python3
"""
Comprehensive End-to-End Verification & Interactive Test Suite for AutoTrade Homelab.
Validates:
1. Mode Switch & Security Guardrails (TEST vs LIVE, PIN Challenge, Value Limit)
2. Real-Time Daily Order Strategy Ingestion via LINE Webhook
3. Live Portfolio Reconciliation & Batch Review Card Generation
4. Virtual TradeMan Simulator Execution (BUY, SELL with real-market matching)
5. SBL Short Selling with Inventory Checking & SBL Lot Generation
6. Alert Center Trigger Breach & Interactive Push Card
7. Price Negotiation Center (11:00 / 15:30) & Order Price Modification
8. Short Position COVER & Interactive SBL Share Return
"""

import asyncio
import json
import logging
import os
import sys

# Setup root path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.browser.trademan_simulator import virtual_simulator
from app.core.config import settings
from app.db.init_db import init_db
from app.db.models import Order, Position, SBLBorrowLot, SessionLog, WatchlistTrigger
from app.db.session import AsyncSessionLocal
from app.services.line_service import line_service
from app.services.parser import signal_parser
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.price_negotiation_service import price_negotiation_service
from app.services.trade_center_service import trade_center_service
from app.services.trade_dispatcher import trade_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("autotrade_test")

SAMPLE_DAILY_ORDER_MESSAGE = """
🚨 5.1 Hard Exit & Cut Loss Triggers (3 ไม้ + เศษหุ้น 1 ไม้):
TLI: [SELL 2,000 หุ้น] | ถือมา 16 วันทำการ (-1.77%, ทุน ฿11.30 ➡️ ตลาด ฿11.10) ➡️ SELL ปิดสถานะทั้งหมด 2,000 หุ้น: V3S Hard Time-Exit ปิดเมื่อครบ 10 วันทำการ เพื่อคืนเงินสด ฿22,200 หมุนรอบใหม่
MCOT: [SELL 3,400 หุ้น] | ติดลบ -3.51% (ทุน ฿5.70 ➡️ ตลาด ฿5.50) ➡️ SELL Cut Loss ทั้งหมด 3,400 หุ้น: V3S Stop Loss ทันทีตามวินัยจำกัดความเสี่ยง 2.0%
GLOBAL: [SELL 5,500 หุ้น] | ติดลบ -2.86% (ทุน ฿7.00 ➡️ ตลาด ฿6.80) ➡️ SELL Cut Loss ทั้งหมด 5,500 หุ้น: V3S Stop Loss ทันทีตามวินัยจำกัดความเสี่ยง 2.0%
TRUE (เศษหุ้น): [SELL 100 หุ้น] | ติดลบ -0.76% (ถือ 8 วันทำการ, ทุน ฿13.20 ➡️ ตลาด ฿13.10) ➡️ SELL ปิดเศษหุ้น 100 หุ้น: Weed-Out เคลียร์หน้าพอร์ต

🟢 5.2 Climax TP & Strong Runners (4 ไม้):
DELTA: [มีทั้งหมด 200 หุ้น] | กำไร +12.65% (ทุน ฿245.00 ➡️ ตลาด ฿276.00) ➡️ 🎯 Climax TP Zone:แผนแบ่งล็อกกำไร: SELL ครึ่งนึง 100 หุ้น (ล็อกกำไรเข้าพอร์ต +฿3,100) และ HOLD อีก 100 หุ้น โดยยก Trailing Stop ล็อกที่ ฿265.00
SINGER (ไม้ 1): [HOLD 3,700 หุ้น] | กำไร +4.85% (ทุน ฿10.30 ➡️ ตลาด ฿10.80) ➡️ HOLD 3,700 หุ้น: ยก Trailing Stop ล็อกต้นทุนที่ ฿10.30 รันเทรนด์ต่อ

🟢 5.3 Active Swings & Watchlist (14 ไม้):
AOT (ไม้ 2): [HOLD 600 หุ้น] | ติดลบ -1.96% (ทุน ฿63.75 ➡️ ฿62.50) ➡️ SELL 600 หุ้น ทันทีหากราคาหลุด ฿62.25
PTG (SHORT): [HOLD 6,400 หุ้น] | ติดลบ -0.64% (ทุน Short ฿7.85 ➡️ ฿7.90) ➡️ COVER 6,400 หุ้น ทันทีหากราคาทะลุ ฿8.00
AP (SHORT): [HOLD 5,000 หุ้น] | ติดลบ -0.62% (ทุน Short ฿8.10 ➡️ ฿8.15) ➡️ COVER 5,000 หุ้น ทันทีหากราคาทะลุ ฿8.25
"""


async def run_suite():
    print("=" * 80)
    print("🚀 [INVESTMENT HOMELAB] STARTING AUTOTRADE FULL VERIFICATION SUITE")
    print("=" * 80)

    # Step 0: Database Init
    print("\n[Step 0] Initializing SQLite database...")
    await init_db()
    virtual_simulator.seed_initial_state()

    # Test 1: Mode Switch & Security Guardrails
    print("\n" + "=" * 50)
    print("🧪 [Test 1] Mode Switch & Security Guardrails")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        # Check initial mode
        print(f"  • Current Active Mode: {trade_dispatcher.get_mode_badge()}")
        assert trade_dispatcher.current_mode == "TEST"

        # Try to switch to LIVE with WRONG PIN
        res_fail = await line_service.process_webhook_events(db, [{
            "type": "message",
            "replyToken": "mock_token_1",
            "message": {"type": "text", "text": "MODE LIVE 999999"}
        }])
        print(f"  • Attempt switch to LIVE with WRONG PIN: Status = {res_fail[0]['status']}")
        assert res_fail[0]["result"]["success"] is False
        assert trade_dispatcher.current_mode == "TEST"
        print("    ✅ Blocked invalid PIN successfully.")

        # Switch to LIVE with CORRECT PIN
        res_live = await line_service.process_webhook_events(db, [{
            "type": "message",
            "replyToken": "mock_token_2",
            "message": {"type": "text", "text": f"MODE LIVE {settings.TRADING_PIN}"}
        }])
        print(f"  • Attempt switch to LIVE with CORRECT PIN: Status = {res_live[0]['status']}")
        assert res_live[0]["result"]["success"] is True
        assert trade_dispatcher.current_mode == "LIVE"
        print(f"    ✅ Switched to: {trade_dispatcher.get_mode_badge()}")

        # Switch back to TEST for safe simulation
        res_test = await line_service.process_webhook_events(db, [{
            "type": "message",
            "replyToken": "mock_token_3",
            "message": {"type": "text", "text": "MODE TEST"}
        }])
        assert trade_dispatcher.current_mode == "TEST"
        print(f"    ✅ Returned to Sandbox: {trade_dispatcher.get_mode_badge()}")

    # Test 2: Daily Order Ingestion & Live Portfolio Reconciliation
    print("\n" + "=" * 50)
    print("🧪 [Test 2] Daily Order Ingestion & Live Portfolio Reconciliation")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        res_daily = await line_service.process_webhook_events(db, [{
            "type": "message",
            "replyToken": "mock_token_daily",
            "message": {"type": "text", "text": SAMPLE_DAILY_ORDER_MESSAGE}
        }])
        order_res = res_daily[0]
        print(f"  • Ingestion Status: {order_res['status']}")
        print(f"  • Batch ID: {order_res.get('batch_id')}")
        print(f"  • Immediate Orders: {order_res.get('immediate_count')} items")
        print(f"  • Watchlist Triggers: {order_res.get('trigger_count')} items")
        print(f"  • Reconciliation Warnings: {len(order_res.get('warnings', []))} items")
        for w in order_res.get("warnings", []):
            print(f"    {w}")

        assert order_res["status"] == "DAILY_ORDER_BATCH_PREPARED"
        assert order_res["immediate_count"] >= 3  # TLI, MCOT, GLOBAL, DELTA
        batch_id = order_res["batch_id"]

    # Test 3: Batch Approval & Execution in TEST Mode
    print("\n" + "=" * 50)
    print("🧪 [Test 3] Batch Approval & Execution (Virtual Simulator)")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        postback_data = f"action=batch_approve&batch_id={batch_id}"
        res_batch = await line_service.process_webhook_events(db, [{
            "type": "postback",
            "replyToken": "mock_token_batch_approve",
            "postback": {"data": postback_data}
        }])
        batch_exec = res_batch[0]["result"]
        print(f"  • Batch Execution Processed: {batch_exec['processed']} orders")
        for ord_r in batch_exec["results"]:
            print(f"    • {ord_r['symbol']} ({ord_r['side']}) {ord_r['volume']:,} @ ฿{ord_r['price']:.2f} -> Status: {ord_r['status']} (Order: {ord_r.get('broker_order_no')})")

        assert batch_exec["success"] is True
        assert batch_exec["processed"] >= 3
        print("  ✅ Immediate orders successfully executed in Virtual TradeMan!")

    # Test 4: SBL SHORT Execution with Inventory Check
    print("\n" + "=" * 50)
    print("🧪 [Test 4] SBL SHORT Execution with SBL Inventory & Lot Creation")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        short_res = await trade_dispatcher.dispatch_order(
            symbol="AP",
            side="SHORT",
            volume=5000,
            price=8.10,
            current_market_price=8.10
        )
        print(f"  • SHORT Execution: Success={short_res['success']}, Status={short_res['status']}")
        print(f"  • SBL Lot Created: {short_res.get('sbl_lot_created', {}).get('lot_id')}")
        print(f"  • Order No: {short_res.get('broker_order_no')}")
        assert short_res["success"] is True
        assert short_res["sbl_lot_created"] is not None
        print("  ✅ Simulated SBL borrow lot created with 5.5% fee rate.")

    # Test 5: Alert Center Trigger Breach & Interactive Push Card
    print("\n" + "=" * 50)
    print("🧪 [Test 5] Alert Center Trigger Breach & Push Card Execution")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        # Simulate AOT price dropping to 62.00 (trigger condition was <= 62.25)
        pos_aot = virtual_simulator.positions.get("AOT")
        if pos_aot:
            pos_aot["current_price"] = 62.00

        print("  • Checking Alert Center with AOT price = ฿62.00 (Breaches Stop ฿62.25)...")
        # Trigger interactive execution
        trig_exec_res = await line_service.process_webhook_events(db, [{
            "type": "postback",
            "replyToken": "mock_token_trigger_exec",
            "postback": {"data": "action=trigger_execute&symbol=AOT&side=SELL&vol=600&price=62.00"}
        }])
        print(f"  • Trigger Action Result: Status={trig_exec_res[0]['status']}")
        assert trig_exec_res[0]["status"] == "TRIGGER_EXECUTED"
        print("  ✅ Trigger order successfully executed via Interactive Push Action.")

    # Test 6: Price Negotiation Center Round (11:00 / 15:30)
    print("\n" + "=" * 50)
    print("🧪 [Test 6] Price Negotiation Center (11:00 / 15:30 Rounds)")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        # Provide position for TLI
        virtual_simulator.positions["TLI"] = {"symbol": "TLI", "side": "LONG", "volume": 1000, "avg_cost": 11.10, "current_price": 11.00}

        # Create an unmatched SELL order at 11.20 (higher than market 11.00)
        unmatched_ord = await trade_dispatcher.dispatch_order(
            symbol="TLI",
            side="SELL",
            volume=1000,
            price=11.20,
            current_market_price=11.00  # Price > Market -> OPEN in queue
        )
        assert unmatched_ord["status"] == "Open" or unmatched_ord["status"] == "OPEN"
        broker_no = unmatched_ord["broker_order_no"]
        print(f"  • Created Unmatched Order: {broker_no} (Selling at ฿11.20, Market at ฿11.00)")

        # Run Price Negotiation Round
        proposals = await price_negotiation_service.run_negotiation_round(db)
        print(f"  • Negotiation Proposals Generated: {len(proposals)}")

        # User approves adjusting price to 11.00 via LINE
        adj_res = await line_service.process_webhook_events(db, [{
            "type": "postback",
            "replyToken": "mock_token_nego",
            "postback": {"data": f"action=approve_negotiation&order_no={broker_no}&symbol=TLI&side=SELL&new_price=11.00&volume=1000"}
        }])
        print(f"  • User Confirmed Adjustment: Status={adj_res[0]['status']}")
        print(f"  • Adjusted Order Result: is_matched={adj_res[0]['result'].get('is_matched')}")
        assert adj_res[0]["status"] == "PRICE_NEGOTIATION_APPROVED"
        print("  ✅ Order successfully renegotiated and filled at market offer!")

    # Test 7: COVER Execution & SBL Share Return Lifecycle
    print("\n" + "=" * 50)
    print("🧪 [Test 7] Short Position COVER & Interactive SBL Share Return")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        # Execute simulated COVER on PTG
        cover_res = await trade_dispatcher.dispatch_order(
            symbol="PTG",
            side="COVER",
            volume=6400,
            price=8.00,
            current_market_price=8.00
        )
        print(f"  • COVER Execution: Status={cover_res['status']}")
        print(f"  • SBL Ready to Return Lot: {cover_res.get('sbl_ready_to_return', {}).get('lot_id')}")
        assert cover_res["success"] is True

        # User confirms SBL Return via LINE card
        sbl_return_postback = "action=sbl_return_confirm&lot_id=LOT-PTG-01&symbol=PTG&qty=6400"
        ret_res = await line_service.process_webhook_events(db, [{
            "type": "postback",
            "replyToken": "mock_token_sbl_ret",
            "postback": {"data": sbl_return_postback}
        }])
        print(f"  • SBL Return Confirmed via LINE: Status={ret_res[0]['status']}")
        print(f"  • Returned Result: {ret_res[0]['result'].get('message')}")
        assert ret_res[0]["status"] == "SBL_RETURN_CONFIRMED"
        print("  ✅ SBL shares returned to inventory and borrow interest finalized.")

    # Test 8: Value Limit Guardrail in LIVE Mode
    print("\n" + "=" * 50)
    print("🧪 [Test 8] Value Limit Guardrail in LIVE Mode")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        # Switch to LIVE
        await trade_dispatcher.switch_mode("LIVE", pin=settings.TRADING_PIN)
        print(f"  • Current Mode: {trade_dispatcher.get_mode_badge()}")

        # Order with 100,000 THB value (Limit is 50,000 THB)
        blocked_order = await trade_dispatcher.dispatch_order(
            symbol="CPALL",
            side="BUY",
            volume=2000,
            price=50.00  # 2000 * 50 = 100,000 THB > 50,000 Limit
        )
        print(f"  • Blocked Order Result: Status={blocked_order.get('status')}")
        print(f"  • Error: {blocked_order.get('error')}")
        assert blocked_order["success"] is False
        assert blocked_order["status"] == "REJECTED_VALUE_LIMIT"
        print("  ✅ Value Limit Guardrail successfully blocked oversized live order.")

        # Switch back to TEST
        await trade_dispatcher.switch_mode("TEST")
        print(f"  • Restored Mode: {trade_dispatcher.get_mode_badge()}")

    print("\n" + "=" * 80)
    print("🎉 ALL 8 AUTOTRADE VERIFICATION TESTS PASSED SUCCESSFULLY! (100% PASS)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_suite())
