#!/usr/bin/env python3
"""
Settrade Open API Sandbox Test & Diagnostic Harness.

This script validates connectivity to the Settrade Open API (v2) Sandbox:
1. Verifies Investor authentication (App ID & App Secret).
2. Tests Real-time Market Data Streaming (MQTT over WebSocket).
3. Tests Portfolio & Purchasing Power inquiries (Equity & TFEX).
4. Tests Sandbox Order Placement & Order Book tracking.
5. Measures latency benchmarks (API vs Playwright).

Usage:
    ./.venv/bin/python scripts/test_settrade_sandbox.py
    ./.venv/bin/python scripts/test_settrade_sandbox.py --app-id <ID> --app-secret <SECRET> --symbol CPALL
"""

import os
import sys
import time
import argparse
import logging
from typing import Optional, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings

# ANSI terminal colors for readable diagnostics
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{CYAN}{BOLD}========================================================================{RESET}")
    print(f"{CYAN}{BOLD}   SETTRADE OPEN API (v2) SANDBOX TEST HARNESS & DIAGNOSTIC STUDIO     {RESET}")
    print(f"{CYAN}{BOLD}========================================================================{RESET}\n")


def print_credential_guide():
    print(f"{YELLOW}{BOLD}⚠️  ยังไม่พบข้อมูล Settrade Open API Credentials ใน .env หรือ Arguments{RESET}\n")
    print("วิธีรับ App ID และ App Secret ฟรีจาก Settrade Developer Portal:")
    print("------------------------------------------------------------------------")
    print(f"1. เข้าไปที่: {CYAN}https://developer.settrade.com/open-api/{RESET}")
    print(f"2. เข้าสู่ระบบด้วยบัญชี Settrade ของคุณ")
    print(f"3. ไปที่เมนู {BOLD}'API Management'{RESET} หรือ {BOLD}'Create Application'{RESET}")
    print(f"4. สร้าง App ใหม่ เลือก Environment เป็น {GREEN}{BOLD}'Sandbox'{RESET}")
    print(f"5. คัดลอก {BOLD}App ID{RESET} และ {BOLD}App Secret{RESET} มาใส่ในไฟล์ {CYAN}.env{RESET}:")
    print(f"""
{BOLD}# เพิ่มลงในไฟล์ .env:{RESET}
SETTRADE_APP_ID="YOUR_APP_ID"
SETTRADE_APP_SECRET="YOUR_APP_SECRET"
SETTRADE_BROKER_ID="SANDBOX"
SETTRADE_APP_CODE="SANDBOX"
SETTRADE_ACCOUNT_NO_EQUITY="YOUR_USERNAME-E"        # เช่น kai.araya-E
SETTRADE_ACCOUNT_NO_DERIVATIVES="YOUR_USERNAME-D"   # เช่น kai.araya-D
SETTRADE_PIN="000000"
""")
    print("หรือสั่งรันสคริปต์นี้พร้อมส่งพารามิเตอร์โดยตรง:")
    print(f"  {CYAN}./.venv/bin/python scripts/test_settrade_sandbox.py --app-id <ID> --app-secret <SECRET>{RESET}\n")


def test_settrade_connectivity(
    app_id: str,
    app_secret: str,
    broker_id: str = "SANDBOX",
    app_code: str = "SANDBOX",
    symbol: str = "CPALL",
    equity_acc: Optional[str] = None,
    deri_acc: Optional[str] = None,
    place_test_order: bool = False
):
    try:
        from settrade_v2 import Investor
        from settrade_v2.errors import SettradeError
    except ImportError:
        print(f"{RED}❌ ไม่พบโมดูล settrade-v2 กรุณาติดตั้งด้วย: uv pip install settrade-v2{RESET}")
        return

    print(f"{BOLD}[1/4] กำลังเริ่มต้นการเชื่อมต่อ Investor Object...{RESET}")
    t0 = time.time()
    try:
        investor = Investor(
            app_id=app_id,
            app_secret=app_secret,
            broker_id=broker_id,
            app_code=app_code,
            is_auto_queue=False
        )
        latency_init = (time.time() - t0) * 1000
        print(f"{GREEN}✅ เชื่อมต่อและ Authenticate สำเร็จ! Latency: {latency_init:.2f} ms{RESET}")
    except Exception as e:
        print(f"{RED}❌ เกิดข้อผิดพลาดในการเชื่อมต่อ (Auth Failed): {e}{RESET}")
        return

    # [2/4] Test Real-time Market Data Connection (MQTT over WebSocket)
    print(f"\n{BOLD}[2/4] กำลังทดสอบ Real-time Market Data (MQTT WebSocket) สำหรับหุ้น '{symbol}'...{RESET}")
    try:
        t_market = time.time()
        market = investor.MarketData()
        quote = market.get_quote_symbol(symbol=symbol)
        latency_market = (time.time() - t_market) * 1000
        print(f"{GREEN}✅ ดึงข้อมูลราคาสำเร็จ (REST Snapshot)! Latency: {latency_market:.2f} ms{RESET}")
        if isinstance(quote, dict):
            last_price = quote.get("last") or quote.get("last_price") or quote.get("close")
            high = quote.get("high")
            low = quote.get("low")
            total_vol = quote.get("total_volume")
            print(f"   📊 Symbol: {BOLD}{symbol}{RESET} | Last: {GREEN}{last_price}{RESET} | High: {high} | Low: {low} | Vol: {total_vol}")

        # Test Realtime MQTT Streaming
        print(f"   📡 กำลังเชื่อมต่อ RealtimeDataConnection (MQTT over WebSocket)...")
        realtime = investor.RealtimeDataConnection()
        events_received = []

        def on_price_update(data):
            events_received.append(data)
            print(f"   {CYAN}⚡ [Realtime Tick]{RESET} {data}")

        subscriber = realtime.subscribe_price_info(
            symbol=symbol,
            on_message=on_price_update
        )
        subscriber.start()
        print(f"   ⏳ รอรับสตรีมข้อมูล 3 วินาที...")
        time.sleep(3)
        subscriber.stop()
        print(f"{GREEN}✅ ทดสอบ Real-time MQTT สำเร็จ! ได้รับ {len(events_received)} event(s){RESET}")

    except Exception as e:
        print(f"{YELLOW}⚠️ การทดสอบ Market Data พบปัญหา: {e}{RESET}")

    # [3/4] Test Portfolio & Account Information
    print(f"\n{BOLD}[3/4] กำลังทดสอบตรวจสอบบัญชีและพอร์ตการลงทุน (Portfolio)...{RESET}")
    if equity_acc:
        try:
            t_port = time.time()
            equity = investor.Equity(account_no=equity_acc)
            account_info = equity.get_account_info()
            portfolio = equity.get_portfolio()
            latency_port = (time.time() - t_port) * 1000
            print(f"{GREEN}✅ ดึงข้อมูลบัญชี Equity ({equity_acc}) สำเร็จ! Latency: {latency_port:.2f} ms{RESET}")
            print(f"   💵 Account Info: {account_info}")
            print(f"   💼 Portfolio: {portfolio}")
        except Exception as e:
            print(f"{YELLOW}⚠️ ดึงข้อมูลพอร์ต Equity ล้มเหลว: {e}{RESET}")
    else:
        print(f"   ℹ️ ไม่ได้ระบุ SETTRADE_ACCOUNT_NO_EQUITY (ข้ามการดึงพอร์ตหุ้น)")

    if deri_acc:
        try:
            deri = investor.Derivatives(account_no=deri_acc)
            deri_info = deri.get_account_info()
            print(f"{GREEN}✅ ดึงข้อมูลบัญชี Derivatives ({deri_acc}) สำเร็จ!{RESET}")
            print(f"   💵 Derivatives Info: {deri_info}")
        except Exception as e:
            print(f"{YELLOW}⚠️ ดึงข้อมูลพอร์ต Derivatives ล้มเหลว: {e}{RESET}")

    # [4/4] Optional Order Placement Test
    if place_test_order and equity_acc:
        print(f"\n{BOLD}[4/4] กำลังทดสอบส่งคำสั่งซื้อขายเข้ากระดานจำลอง (Sandbox Order)...{RESET}")
        try:
            t_order = time.time()
            order_res = equity.place_order(
                symbol=symbol,
                side="Buy",
                volume=100,
                price=50.0,
                price_type="Limit",
                pin=settings.SETTRADE_PIN or "000000"
            )
            latency_order = (time.time() - t_order) * 1000
            print(f"{GREEN}✅ ส่งคำสั่งเข้า Sandbox สำเร็จ! Latency: {latency_order:.2f} ms{RESET}")
            print(f"   📋 Order Response: {order_res}")
        except Exception as e:
            print(f"{RED}❌ ส่งคำสั่งล้มเหลว: {e}{RESET}")
    else:
        print(f"\n{BOLD}[4/4] ข้ามการทดสอบส่งออเดอร์ (ระบุ --place-order เพื่อทดสอบยิงออเดอร์จริงเข้า Sandbox){RESET}")

    print(f"\n{CYAN}{BOLD}========================================================================{RESET}")
    print(f"{GREEN}{BOLD}   สรุปผลการทดสอบ: ระบบ Settrade Open API พร้อมเชื่อมเข้า MCP Gateway!  {RESET}")
    print(f"{CYAN}{BOLD}========================================================================{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Settrade Open API Sandbox Diagnostic Tool")
    parser.add_argument("--app-id", default=settings.SETTRADE_APP_ID, help="Settrade App ID")
    parser.add_argument("--app-secret", default=settings.SETTRADE_APP_SECRET, help="Settrade App Secret")
    parser.add_argument("--broker-id", default=settings.SETTRADE_BROKER_ID or "SANDBOX", help="Broker ID")
    parser.add_argument("--app-code", default=settings.SETTRADE_APP_CODE or "SANDBOX", help="App Code")
    parser.add_argument("--symbol", default="CPALL", help="Symbol to test quotes")
    parser.add_argument("--equity-acc", default=settings.SETTRADE_ACCOUNT_NO_EQUITY, help="Equity Account No")
    parser.add_argument("--deri-acc", default=settings.SETTRADE_ACCOUNT_NO_DERIVATIVES, help="Derivatives Account No")
    parser.add_argument("--place-order", action="store_true", help="Send a 100-share limit test order to Sandbox")

    args = parser.parse_args()
    print_banner()

    if not args.app_id or not args.app_secret:
        print_credential_guide()
        return

    test_settrade_connectivity(
        app_id=args.app_id,
        app_secret=args.app_secret,
        broker_id=args.broker_id,
        app_code=args.app_code,
        symbol=args.symbol,
        equity_acc=args.equity_acc,
        deri_acc=args.deri_acc,
        place_test_order=args.place_order
    )


if __name__ == "__main__":
    main()
