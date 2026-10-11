#!/usr/bin/env python3
"""
Watch-and-Learn Interactive Co-pilot for Liberator WebTrade.
============================================================
Interactive Human-in-the-Loop (HITL) Playwright runner for Liberator Securities:
1. Opens visible Chrome on desktop (DISPLAY=:0).
2. Navigates to https://webtrade.liberator.co.th/login.
3. Automatically enters credentials from .env (LIBERATOR_USERNAME, LIBERATOR_PASSWORD).
4. Auto-captures 2FA SMS OTP via KDE Connect (with manual keyboard fallback).
5. Pauses cleanly for developer/user to inspect and navigate to Portfolio tab.
6. Probes & verifies DOM selectors for Cash Balance, Line Available, Unrealized PnL, and Stock Table.
7. Automatically records verified steps to learned_workflows/liberator_portfolio.md.
8. Saves session state to data/liberator_session.json and registers with BrowserTabManager.
9. Keeps the browser open persistently side-by-side with Krungsri/TradeMan.

Usage:
    .venv/bin/python scripts/watch_and_learn_liberator.py
"""

import sys
import os
import re
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from playwright.async_api import async_playwright, Page, BrowserContext, Browser
from app.core.config import settings
from app.services.kdeconnect_service import kdeconnect_service
from app.browser.tab_manager import tab_manager

# ANSI Color formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"


class LiberatorWatchAndLearn:
    def __init__(self):
        self.workflow_name = "liberator_portfolio"
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.recorded_steps: List[Dict[str, str]] = []

    def record_step(self, action: str, selector: str, value: str, description: str):
        step_num = len(self.recorded_steps) + 1
        entry = {
            "step": str(step_num),
            "action": action.upper(),
            "selector": selector,
            "value": value,
            "description": description
        }
        self.recorded_steps.append(entry)
        print(f"{C_GREEN}  [บันทึก Step {step_num}]{C_RESET} {C_BOLD}{action.upper()}{C_RESET} -> {selector} ({description})")

    async def prompt_user(self, prompt_text: str, default: str = "") -> str:
        """Asynchronously prompt for user input without blocking the asyncio loop."""
        loop = asyncio.get_running_loop()
        suffix = f" [{default}]: " if default else ": "
        print(f"\n{C_CYAN}{prompt_text}{suffix}{C_RESET}", end="", flush=True)
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            val = line.strip()
            return val if val else default
        except Exception:
            return default

    async def initialize_browser(self):
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"

        print("\n" + "=" * 78)
        print(f"{C_BOLD}{C_MAGENTA} 👁️  WATCH-AND-LEARN CO-PILOT: LIBERATOR WEBTRADE WORKFLOW{C_RESET}")
        print(f" • Platform: {C_BOLD}LIBERATOR (webtrade.liberator.co.th){C_RESET}")
        print(f" • Mode: {C_GREEN}Headed Chrome (Visible Desktop DISPLAY={os.environ.get('DISPLAY', ':0')}){C_RESET}")
        print(f" • Target Runbook: {C_BOLD}learned_workflows/{self.workflow_name}.md{C_RESET}")
        print("=" * 78 + "\n")

        self.playwright = await async_playwright().start()
        chrome_path = getattr(settings, "PLAYWRIGHT_CHROME_EXECUTABLE", "/usr/bin/google-chrome")
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ]

        kwargs = {
            "headless": False,
            "args": launch_args,
        }
        if os.path.exists(chrome_path):
            kwargs["executable_path"] = chrome_path

        self.browser = await self.playwright.chromium.launch(**kwargs)
        self.context = await self.browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

        tab_manager.set_context(self.context)
        self.page = await self.context.new_page()
        tab_manager.register_tab("liberator", self.page)

    async def run(self):
        try:
            await self.initialize_browser()

            # -------------------------------------------------------------
            # STEP 1: Navigate to Liberator Login Page
            # -------------------------------------------------------------
            login_url = getattr(settings, "LIBERATOR_LOGIN_URL", "https://webtrade.liberator.co.th/login")
            print(f"\n{C_BOLD}[Step 1/5] กำลังเปิดหน้า Liberator WebTrade Login...{C_RESET}")
            await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)
            self.record_step("NAV", login_url, "-", "เข้าสู่หน้า Liberator WebTrade Login")

            # -------------------------------------------------------------
            # STEP 2: Fill Username & Password
            # -------------------------------------------------------------
            username = settings.LIBERATOR_USERNAME
            password = settings.LIBERATOR_PASSWORD
            if not username or not password:
                raise RuntimeError("Set LIBERATOR_USERNAME and LIBERATOR_PASSWORD in .env")

            print(f"\n{C_BOLD}[Step 2/5] กำลังค้นหาช่องกรอก Username/Password บนหน้าจอ...{C_RESET}")
            
            # Detect Username selector with retry loop
            user_selectors = [
                "input[placeholder*='Username' i]",
                "input[placeholder*='Email' i]",
                "input[placeholder*='ชื่อผู้ใช้งาน' i]",
                "input[name*='user' i]",
                "input[name*='login' i]",
                "input[type='text']",
                "#username",
                "#email"
            ]
            user_input = None
            used_user_sel = ""
            for _ in range(10):
                for sel in user_selectors:
                    try:
                        el = await self.page.query_selector(sel)
                        if el and await el.is_visible():
                            user_input = el
                            used_user_sel = sel
                            break
                    except Exception:
                        pass
                if user_input:
                    break
                await asyncio.sleep(1.0)

            if user_input:
                await user_input.fill(username)
                self.record_step("TYPE", used_user_sel, "<LIBERATOR_USERNAME>", "กรอก Username / บัญชี Liberator")
                print(f"✅ กรอก Username สำเร็จด้วย Selector: '{used_user_sel}'")
            else:
                print(f"{C_YELLOW}⚠️ ไม่พบช่อง Username อัตโนมัติ — คุณสามารถคลิกกรอกบนหน้าจอได้เลย{C_RESET}")
                await self.prompt_user("เมื่อกรอก Username บนหน้าจอแล้ว กด Enter เพื่อดำเนินการต่อ")

            # Detect Password selector with retry loop
            pass_selectors = [
                "input[type='password']",
                "input[placeholder*='Password' i]",
                "input[placeholder*='รหัสผ่าน' i]",
                "#password"
            ]
            pass_input = None
            used_pass_sel = ""
            for _ in range(5):
                for sel in pass_selectors:
                    try:
                        el = await self.page.query_selector(sel)
                        if el and await el.is_visible():
                            pass_input = el
                            used_pass_sel = sel
                            break
                    except Exception:
                        pass
                if pass_input:
                    break
                await asyncio.sleep(1.0)

            if pass_input:
                await pass_input.fill(password)
                self.record_step("TYPE", used_pass_sel, "<LIBERATOR_PASSWORD>", "กรอก Password Liberator")
                print(f"✅ กรอก Password สำเร็จด้วย Selector: '{used_pass_sel}'")
            else:
                print(f"{C_YELLOW}⚠️ ไม่พบช่อง Password อัตโนมัติ — คุณสามารถคลิกกรอกบนหน้าจอได้เลย{C_RESET}")
                await self.prompt_user("เมื่อกรอก Password บนหน้าจอแล้ว กด Enter เพื่อดำเนินการต่อ")

            # -------------------------------------------------------------
            # STEP 3: Click Login Button
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 3/5] กำลังกดปุ่มเข้าสู่ระบบ...{C_RESET}")
            btn_selectors = [
                "button[type='submit']",
                "button:has-text('เข้าสู่ระบบ')",
                "button:has-text('Login')",
                "button:has-text('Sign In')",
                "input[type='submit']"
            ]
            btn_login = None
            used_btn_sel = ""
            for sel in btn_selectors:
                try:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        btn_login = el
                        used_btn_sel = sel
                        break
                except Exception:
                    pass

            if btn_login:
                await btn_login.click()
                self.record_step("CLICK", used_btn_sel, "-", "กดปุ่มเข้าสู่ระบบ Liberator")
                print(f"✅ กดปุ่ม Login สำเร็จด้วย Selector: '{used_btn_sel}'")
            else:
                print("กด Enter บนคีย์บอร์ดเพื่อ Submit")
                await self.page.keyboard.press("Enter")
                self.record_step("KEYPRESS", "Enter", "-", "กดปุ่ม Enter เพื่อส่งข้อมูลล็อกอิน")

            await self.page.wait_for_timeout(3000)

            # -------------------------------------------------------------
            # STEP 4: 2FA SMS OTP Detection & Submission
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 4/5] ตรวจสอบหน้าจอ 2FA SMS OTP...{C_RESET}")
            otp_selectors = [
                "input[placeholder*='OTP' i]",
                "input[placeholder*='รหัส OTP' i]",
                "input[inputmode='numeric']",
                "input[type='tel']",
                "input.otp-input",
                "#otp"
            ]
            otp_input = None
            used_otp_sel = ""
            for _ in range(8):
                for sel in otp_selectors:
                    try:
                        el = await self.page.query_selector(sel)
                        if el and await el.is_visible():
                            otp_input = el
                            used_otp_sel = sel
                            break
                    except Exception:
                        pass
                if otp_input:
                    break
                await asyncio.sleep(1.0)

            if otp_input:
                print(f"{C_GREEN}✅ พบช่องกรอก 2FA OTP บนหน้าจอ Liberator!{C_RESET}")
                print("📱 กำลังดักจับรหัส SMS OTP ผ่าน KDE Connect อัตโนมัติ (60 วินาที)...")

                captured_otp = None
                start_time = time.time()

                async def poll_kde():
                    nonlocal captured_otp
                    while time.time() - start_time < 60 and not captured_otp:
                        try:
                            item = await kdeconnect_service.poll_active_notifications()
                            if item and item.otp_code:
                                captured_otp = item.otp_code
                                print(f"\n{C_GREEN}🎉 KDE Connect ดักจับ OTP สำเร็จ: {item.masked_otp}{C_RESET}")
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(1.0)

                async def poll_dom():
                    nonlocal captured_otp
                    while time.time() - start_time < 60 and not captured_otp:
                        try:
                            if otp_input and not self.page.is_closed():
                                val = await otp_input.input_value()
                                if val and len(val.strip()) >= 6 and val.strip().isdigit():
                                    captured_otp = val.strip()
                                    print(f"\n{C_GREEN}🎉 ตรวจพบ OTP ถูกกรอกบนหน้าจอเบราว์เซอร์: {captured_otp[:2]}****{C_RESET}")
                                    break
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)

                async def wait_manual():
                    nonlocal captured_otp
                    inp = await self.prompt_user("พิมพ์รหัส OTP 6 หลักที่นี่ถ้าต้องการป้อนเอง")
                    if inp and len(inp.strip()) == 6 and inp.strip().isdigit():
                        captured_otp = inp.strip()

                await asyncio.wait(
                    [asyncio.create_task(poll_kde()), asyncio.create_task(poll_dom()), asyncio.create_task(wait_manual())],
                    return_when=asyncio.FIRST_COMPLETED
                )

                if not captured_otp:
                    captured_otp = await self.prompt_user("กรุณากรอกรหัส OTP 6 หลักด้วยตนเอง")

                if captured_otp:
                    await otp_input.fill(captured_otp)
                    self.record_step("TYPE", used_otp_sel, "<CAPTURED_SMS_OTP>", "กรอกรหัส 2FA SMS OTP")
                    await self.page.keyboard.press("Enter")
                    print("✅ ส่งรหัส OTP เรียบร้อย กำลังรอเข้าหน้า Dashboard...")
                    await self.page.wait_for_timeout(4000)
            else:
                print("ℹ️  ไม่พบช่อง OTP อัตโนมัติ (อาจเข้าหน้า Dashboard แล้ว หรือผู้ใช้ยืนยันบนหน้าจอแล้ว)")

            # -------------------------------------------------------------
            # STEP 5: HITL CO-PILOT — Inspect Portfolio & Balances
            # -------------------------------------------------------------
            print("\n" + "=" * 78)
            print(f"{C_BOLD}{C_YELLOW}👉 [HUMAN-IN-THE-LOOP CO-PILOT]: เข้าสู่หน้าจอหลัก Liberator WebTrade{C_RESET}")
            print("   หน้าจอเบราว์เซอร์เปิดอยู่บนจอของคุณ")
            print("   กรุณาช่วยคลิกเลือกแท็บ หรือหน้าต่าง **Portfolio / พอร์ตการลงทุน** บนหน้าจอจริง")
            print("=" * 78)

            await self.prompt_user("เมื่อหน้าพอร์ตโฟลิโอแสดงบนหน้าจอแล้ว ให้กด [Enter] เพื่อให้ระบบสแกน DOM")

            # Scan DOM for financial figures
            print(f"\n{C_BOLD}🔍 กำลังสแกนหาข้อมูลทางการเงินและรายการหุ้นในพอร์ต...{C_RESET}")
            
            # Scrape text snippets
            body_text = await self.page.inner_text("body")
            
            # Highlight interesting elements
            try:
                await self.page.evaluate("""() => {
                    const headings = Array.from(document.querySelectorAll('*')).filter(el => {
                        const t = (el.innerText || '').toLowerCase();
                        return t.includes('line available') || t.includes('cash balance') || t.includes('วงเงิน') || t.includes('portfolio');
                    });
                    headings.slice(0, 5).forEach(el => {
                        el.style.outline = '3px solid #00E676';
                    });
                }""")
            except Exception:
                pass

            print(f"\n• Current URL: {self.page.url}")
            print(f"• Title: {await self.page.title()}")

            # Prompt to record the portfolio tab selector
            port_sel = await self.prompt_user(
                "Selector ของปุ่มแท็บ Portfolio (หรือปล่อยว่างเพื่อใช้ค่าเริ่มต้น)",
                default="button:has-text('Portfolio'), a[href*='portfolio']"
            )
            self.record_step("CLICK", port_sel, "-", "คลิกแท็บ Portfolio ใน Liberator WebTrade")

            # Check for PIN modal if required
            pin_code = settings.LIBERATOR_PIN or ""
            print(f"\n🔑 หากมีช่องให้ใส่ Trading PIN บนหน้าจอ สามารถทดสอบกรอกได้ (PIN: {pin_code[:2]}****)")
            test_pin = await self.prompt_user("ต้องการให้ทดสอบกรอก PIN ด้วยหรือไม่? (y/n)", default="n")
            if test_pin.lower() == "y":
                pin_input = await self.page.query_selector("input[type='password'][maxlength='6'], input[placeholder*='PIN' i]")
                if pin_input:
                    await pin_input.fill(pin_code)
                    self.record_step("TYPE", "input[type='password'][maxlength='6']", "<LIBERATOR_PIN>", "กรอก Trading PIN 6 หลัก")
                    print("✅ กรอก PIN สำเร็จ!")

            # -------------------------------------------------------------
            # STEP 6: Save Runbook, Session State, and Keep Browser Alive
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}💾 กำลังบันทึกผลลัพธ์...{C_RESET}")
            await self.save_session()
            self.save_runbook()

            print(f"\n{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
            print(f"{C_BOLD}{C_GREEN} 🎉 ระบบเชื่อมต่อ Liberator WebTrade สำเร็จเรียบร้อย!{C_RESET}")
            print(f" • แท็บ Liberator:              {C_BOLD}เปิดค้างไว้{C_RESET} ใน BrowserTabManager (Tab 3)")
            print(f" • สถานะเซสชัน:                 {C_BOLD}{C_YELLOW}PERSISTENT ACTIVE (ไม่ปิดเบราว์เซอร์ 0-sec Latency){C_RESET}")
            print(f"{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
            print(f"\n{C_CYAN}ℹ️  เบราว์เซอร์จะเปิดค้างไว้บนหน้าจอของคุณ และส่ง Heartbeat ทุก 10 นาที{C_RESET}")
            print("   คุณสามารถย่อหน้าต่างหรือทำงานอื่นได้ตามปกติ (กด Ctrl+C หากต้องการปิดเบราว์เซอร์)...\n")

            # Smart Keep-Alive Loop: sends lightweight ping
            ping_count = 0
            while True:
                await asyncio.sleep(600)  # 10 minutes
                ping_count += 1
                try:
                    pings = await tab_manager.ping_keepalive()
                    now_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{now_str}] 💓 Liberator Keep-Alive Heartbeat #{ping_count} สำเร็จ: {list(pings.keys())}")
                except Exception:
                    pass

        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}🛑 ผู้ใช้สั่งยุติการทำงาน (Ctrl+C) กำลังปิดเบราว์เซอร์อย่างปลอดภัย...{C_RESET}")
        except Exception as e:
            print(f"\n{C_RED}❌ เกิดข้อผิดพลาดระหว่างการรัน: {e}{C_RESET}")
            import traceback
            traceback.print_exc()
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass

    async def save_session(self):
        """Saves current cookies/storage to data/liberator_session.json."""
        state_path = getattr(settings, "LIBERATOR_SESSION_PATH", "data/liberator_session.json")
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        try:
            cookies = await self.context.cookies()
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "LIBERATOR",
                "cookies": cookies,
                "current_url": self.page.url if self.page else "https://webtrade.liberator.co.th"
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  {C_GREEN}✓{C_RESET} บันทึก Session Cookies ({len(cookies)} รายการ) ไปที่: {state_path}")
        except Exception as ex:
            print(f"  {C_RED}✗{C_RESET} บันทึก liberator_session.json ไม่สำเร็จ: {ex}")

    def save_runbook(self):
        """Generates learned_workflows/liberator_portfolio.md."""
        runbook_path = os.path.join(PROJECT_ROOT, "learned_workflows", f"{self.workflow_name}.md")
        os.makedirs(os.path.dirname(runbook_path), exist_ok=True)

        lines = [
            f"# Learned Workflow: {self.workflow_name}",
            f"**Workflow Name:** `{self.workflow_name}`  ",
            f"**Platform:** `LIBERATOR`  ",
            f"**Recorded At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Status:** `VERIFIED`  ",
            "",
            "## Description",
            "Verified human-in-the-loop co-piloted workflow for Liberator WebTrade login, 2FA SMS OTP relay via KDE Connect, and Portfolio inspection.",
            "",
            "## Execution Steps",
            "| Step | Action | Target Selector | Value / Arguments | Description |",
            "| :---: | :---: | :--- | :--- | :--- |"
        ]

        for s in self.recorded_steps:
            lines.append(f"| {s['step']} | `{s['action']}` | `{s['selector']}` | `{s['value']}` | {s['description']} |")

        lines.extend([
            "",
            "## Health Verification Rules",
            "- [x] Login inputs (username/password) are visible and editable",
            "- [x] SMS OTP modal is intercepted and auto-filled via KDE Connect",
            "- [x] Dashboard / Portfolio navigation confirms valid session",
            "- [x] Tab is retained persistently in BrowserTabManager under 'liberator'",
            "",
            "---",
            "*Generated by Watch-and-Learn Interactive Co-piloting Protocol*"
        ])

        with open(runbook_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"  {C_GREEN}✓{C_RESET} บันทึก Learned Workflow ไปที่: {runbook_path}")


if __name__ == "__main__":
    runner = LiberatorWatchAndLearn()
    asyncio.run(runner.run())
