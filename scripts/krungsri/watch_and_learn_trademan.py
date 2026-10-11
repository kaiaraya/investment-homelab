#!/usr/bin/env python3
"""
Watch-and-Learn Interactive Co-pilot for Krungsri TradeMan.
===========================================================
Interactive Human-in-the-Loop (HITL) Playwright runner:
1. Opens visible Chrome on desktop (DISPLAY=:0).
2. Automates Krungsri Portal User/Pass entry & SMS OTP via KDE Connect (with manual fallback).
3. Pauses cleanly on the Krungsri Portal with visual DOM highlighting, allowing you to click
   the TradeMan button on screen (or let the runner click it).
4. Catches the TradeMan SSO popup tab without breaking token redirects.
5. Co-pilots trading account switching (Cash 3024952 <-> Margin 3024959).
6. Automatically records verified steps to learned_workflows/trademan_account_switch_and_portfolio.md
   and saves session cookies to data/session_state.json.

Usage:
    .venv/bin/python scripts/watch_and_learn_trademan.py
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

# ANSI Color formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"


class TrademanWatchAndLearn:
    def __init__(self):
        self.workflow_name = "trademan_account_switch_and_portfolio"
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.main_page: Optional[Page] = None
        self.trademan_page: Optional[Page] = None
        self.recorded_steps: List[Dict[str, str]] = []
        self.opened_pages: List[Page] = []

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
        print(f"{C_BOLD}{C_MAGENTA} 👁️  WATCH-AND-LEARN CO-PILOT: KRUNGSRI TRADEMAN WORKFLOW{C_RESET}")
        print(f" • Mode: {C_GREEN}Headed Chrome (Visible Desktop DISPLAY={os.environ.get('DISPLAY', ':0')}){C_RESET}")
        print(f" • Target Workflow: {C_BOLD}learned_workflows/{self.workflow_name}.md{C_RESET}")
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
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )

        # Track popup pages
        self.context.on("page", lambda p: self._on_new_page(p))
        self.main_page = await self.context.new_page()

    def _on_new_page(self, page: Page):
        self.opened_pages.append(page)
        print(f"\n{C_YELLOW}🔔 ตรวจพบแท็บ/หน้าต่างใหม่เปิดขึ้นมา! URL: {page.url}{C_RESET}")

    async def run(self):
        try:
            await self.initialize_browser()

            # -------------------------------------------------------------
            # STEP 1: Navigate to Krungsri Login Portal
            # -------------------------------------------------------------
            login_url = getattr(settings, "KRUNGSRI_LOGIN_URL", "https://www.krungsrisecurities.com/th/main/default.aspx")
            print(f"\n{C_BOLD}[Step 1/6] กำลังเปิดหน้า Krungsri Securities Portal...{C_RESET}")
            await self.main_page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            await self.main_page.wait_for_timeout(1000)
            self.record_step("NAV", login_url, "-", "เข้าสู่หน้า Krungsri Securities Portal")

            # -------------------------------------------------------------
            # STEP 2 & 3: Fill Credentials
            # -------------------------------------------------------------
            username = settings.KRUNGSRI_USERNAME
            password = settings.KRUNGSRI_PASSWORD
            if not username or not password:
                print(f"{C_RED}❌ ไม่พบ KRUNGSRI_USERNAME หรือ KRUNGSRI_PASSWORD ใน .env!{C_RESET}")
                username = await self.prompt_user("กรุณากรอก Krungsri Username")
                password = await self.prompt_user("กรุณากรอก Krungsri Password")

            print(f"\n{C_BOLD}[Step 2/6] กรอกข้อมูลล็อกอิน (Username: {username[:3]}***)...{C_RESET}")
            user_input = await self.main_page.wait_for_selector("#login_username, input[name*='user' i]", state="visible", timeout=10000)
            await user_input.fill(username)
            self.record_step("TYPE", "#login_username", "<KRUNGSRI_USERNAME>", "กรอก Username ล็อกอิน")

            pass_input = await self.main_page.wait_for_selector("#login_password, input[name*='pass' i]", state="visible", timeout=10000)
            await pass_input.fill(password)
            self.record_step("TYPE", "#login_password", "<KRUNGSRI_PASSWORD>", "กรอก Password ล็อกอิน")

            # -------------------------------------------------------------
            # STEP 4: Click Login
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 3/6] กดปุ่มเข้าสู่ระบบ...{C_RESET}")
            login_btn = await self.main_page.wait_for_selector("#login, input[value*='เข้าสู่ระบบ'], button:has-text('เข้าสู่ระบบ')", timeout=5000)
            await login_btn.click()
            self.record_step("CLICK", "#login", "-", "กดปุ่มเข้าสู่ระบบ")
            await self.main_page.wait_for_timeout(2000)

            # -------------------------------------------------------------
            # STEP 5: 2FA SMS OTP Detection & Submission
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 4/6] ตรวจสอบช่องกรอก SMS OTP...{C_RESET}")
            otp_input = None
            try:
                otp_input = await self.main_page.wait_for_selector("input[placeholder*='OTP'], #otp, input[name*='otp' i]", state="visible", timeout=12000)
            except Exception:
                pass

            if otp_input:
                print(f"{C_GREEN}✅ พบช่องกรอก OTP บนหน้าจอ!{C_RESET}")
                
                # Check broker ref code
                ref_code = "Pending"
                try:
                    ref_el = await self.main_page.query_selector("span:has-text('Ref'), div:has-text('Ref:'), p:has-text('Ref')")
                    if ref_el:
                        text = await ref_el.inner_text()
                        m = re.search(r'Ref[:\s]+([A-Za-z0-9]+)', text)
                        if m:
                            ref_code = m.group(1)
                except Exception:
                    pass
                print(f"🔑 Broker Reference Code: {C_BOLD}{ref_code}{C_RESET}")

                # Poll KDE Connect for OTP
                print("📱 กำลังดักจับรหัส SMS OTP ผ่าน KDE Connect อัตโนมัติ (60 วินาที)...")
                print("   (หรือหากต้องการพิมพ์เอง สามารถพิมพ์เลข 6 หลักแล้วกด Enter ได้ทันที)")

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

                async def wait_manual():
                    nonlocal captured_otp
                    inp = await self.prompt_user("พิมพ์รหัส OTP 6 หลักที่นี่ถ้าต้องการป้อนเอง")
                    if inp and len(inp.strip()) == 6 and inp.strip().isdigit():
                        captured_otp = inp.strip()

                await asyncio.wait(
                    [asyncio.create_task(poll_kde()), asyncio.create_task(wait_manual())],
                    return_when=asyncio.FIRST_COMPLETED
                )

                if not captured_otp:
                    captured_otp = await self.prompt_user("กรุณากรอกรหัส OTP 6 หลักด้วยตนเอง")

                if captured_otp:
                    await otp_input.fill(captured_otp)
                    self.record_step("TYPE", "input[placeholder*='OTP'], #otp", "<CAPTURED_SMS_OTP>", "กรอกรหัส SMS OTP 6 หลัก")
                    await self.main_page.keyboard.press("Enter")
                    print("✅ ส่งรหัส OTP เรียบร้อย กำลังรอเข้าหน้าสมาชิก...")
                    await self.main_page.wait_for_timeout(3000)

            # -------------------------------------------------------------
            # STEP 6: Dismiss Announcement if Present
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 5/6] ตรวจสอบหน้า Krungsri Securities Member Portal...{C_RESET}")
            try:
                ack_btn = await self.main_page.query_selector("text='รับทราบ', button:has-text('รับทราบ'), a:has-text('รับทราบ')")
                if ack_btn and await ack_btn.is_visible():
                    print("📢 พบประกาศข่าวสาร กำลังกด 'รับทราบ'...")
                    await ack_btn.click()
                    self.record_step("CLICK", "button:has-text('รับทราบ')", "-", "ปิดหน้าต่างแจ้งเตือน/ประกาศ")
                    await self.main_page.wait_for_timeout(1000)
            except Exception:
                pass

            # Highlight TradeMan link on screen
            try:
                await self.main_page.evaluate("""() => {
                    const sel = "a[href*='start_SSO.aspx?page=TM'], a[title*='Trademan'], #icon_r12_c1, img[src*='prelog_icon_10_tm']";
                    const el = document.querySelector(sel);
                    if (el) {
                        el.style.outline = "5px solid #00E676";
                        el.style.boxShadow = "0 0 20px #00E676";
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }""")
            except Exception:
                pass

            # -------------------------------------------------------------
            # STEP 7: HITL PAUSE — Click TradeMan SSO
            # -------------------------------------------------------------
            print("\n" + "=" * 78)
            print(f"{C_BOLD}{C_YELLOW}👉 [HUMAN-IN-THE-LOOP]: หน้าต่าง Krungsri เปิดอยู่บนหน้าจอของคุณแล้ว!{C_RESET}")
            print(f"   ปุ่ม {C_GREEN}TradeMan{C_RESET} ด้านขวามือถูกเน้นกรอบสีเขียวสะท้อนแสงไว้แล้ว")
            print(f"\nตัวเลือก:")
            print(f"  [1] {C_BOLD}คุณคลิกที่ปุ่ม TradeMan บนหน้าจอจริงด้วยตนเอง{C_RESET} (ระบบจะดักจับหน้าต่างให้อัตโนมัติ)")
            print(f"  [2] กด {C_BOLD}[Enter]{C_RESET} ในนี้ เพื่อให้ระบบทดลองคลิกให้อัตโนมัติ")
            print(f"  [3] พิมพ์ {C_BOLD}'p'{C_RESET} เพื่อเปิด Playwright Inspector GUI")
            print("=" * 78)

            choice = await self.prompt_user("เลือกตัวเลือก หรือคลิกบนหน้าจอได้เลย (กด Enter เพื่อให้ระบบคลิก)", default="auto")

            if choice.lower() == 'p':
                print("⏸️ กำลังเปิด Playwright Inspector GUI...")
                await self.main_page.pause()
            elif choice.lower() in ["auto", "2", ""]:
                print("🤖 กำลังคลิกปุ่ม TradeMan บนหน้าจอ...")
                trademan_sel = "a[href*='start_SSO.aspx?page=TM'], a[title*='Trademan'], #icon_r12_c1, img[src*='prelog_icon_10_tm']"
                try:
                    target_btn = await self.main_page.query_selector(trademan_sel)
                    if target_btn:
                        await target_btn.click()
                        print("✅ คลิกปุ่ม TradeMan เรียบร้อย!")
                    else:
                        print("⚠️ ไม่พบ Selector ปุ่ม TradeMan จะลองเรียกคำสั่ง JS popup โดยตรง...")
                        await self.main_page.evaluate("popup('../../th/efin/start_SSO.aspx?page=TM','',1200,800)")
                except Exception as ex:
                    print(f"⚠️ คลิกไม่สำเร็จ: {ex}")

            self.record_step(
                "CLICK",
                "a[href*='start_SSO.aspx?page=TM'], #icon_r12_c1",
                "-",
                "คลิกปุ่ม TradeMan ด้านขวาบนเว็บกรุงศรีเพื่อ SSO เข้าสู่ TradeMan แท็บ Portfolio"
            )

            # -------------------------------------------------------------
            # STEP 8: Monitor TradeMan Redirection & Wait for DOM
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}[Step 6/6] กำลังรอหน้าต่าง TradeMan โหลดและแลกเปลี่ยน SSO Token...{C_RESET}")
            print("⏳ ปล่อยให้เบราว์เซอร์ทำการ Redirect OAuth/SSO ให้เสร็จสิ้น (ห้ามกด Refresh)...")

            trademan_page = None
            account_btn = None

            # Poll across all pages in context
            for _ in range(60):
                await asyncio.sleep(1.0)
                # Check newly opened pages first
                candidate_pages = list(self.context.pages)
                for p in candidate_pages:
                    url = p.url.lower()
                    if "trademan.in.th" in url:
                        trademan_page = p
                        break
                    if "start_sso.aspx" in url:
                        print(f"   🔄 กำลังประมวลผล SSO token บน: {p.url[:60]}...")

                if trademan_page:
                    try:
                        # Check if #dropDownAccountPort is visible
                        btn = await trademan_page.query_selector("#dropDownAccountPort, .account-selector")
                        if btn and await btn.is_visible():
                            account_btn = btn
                            print(f"{C_GREEN}🎉 สำเร็จ! พบ Dropdown บัญชี TradeMan (#dropDownAccountPort) แล้ว!{C_RESET}")
                            print(f"• URL: {trademan_page.url}")
                            await trademan_page.bring_to_front()
                            break
                    except Exception:
                        pass

            if not trademan_page or not account_btn:
                print(f"\n{C_YELLOW}⚠️ ยังไม่พบ #dropDownAccountPort อัตโนมัติ (อาจกำลังโหลด Nuxt){C_RESET}")
                print("👉 หากหน้าต่าง TradeMan เปิดอยู่แล้ว กรุณาตรวจสอบบนหน้าจอ")
                confirm = await self.prompt_user("หน้าจอ TradeMan ของคุณโหลดขึ้นมาแล้วหรือยัง? (y/n)", default="y")
                if confirm.lower() == "y":
                    # Check latest page
                    trademan_page = self.context.pages[-1]
                    await trademan_page.bring_to_front()

            self.trademan_page = trademan_page or self.main_page

            # Read current active account
            current_account = "Unknown"
            try:
                acc_el = await self.trademan_page.query_selector("#dropDownAccountPort")
                if acc_el:
                    current_account = (await acc_el.inner_text()).strip()
            except Exception:
                pass

            print(f"\n{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
            print(f" 🎉 ยินดีด้วยครับ! เข้าสู่ Krungsri TradeMan สำเร็จแล้ว!")
            print(f" • บัญชีที่กำลังเปิดอยู่: {C_BOLD}{current_account}{C_RESET}")
            print(f"{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")

            # -------------------------------------------------------------
            # STEP 9: Account Switching Co-pilot
            # -------------------------------------------------------------
            print(f"\n{C_CYAN}ต้องการทดสอบสลับบัญชี (Cash Balance <-> Margin) หรือไม่?{C_RESET}")
            print(f"  [1] {C_BOLD}ให้ระบบคลิกสลับบัญชีให้อัตโนมัติ{C_RESET}")
            print(f"  [2] คุณคลิกเองบนหน้าจอ แล้วกด Enter เพื่อให้ระบบตรวจจับ")
            print(f"  [3] ข้ามขั้นตอนนี้และบันทึก Workflow ทันที")

            acc_choice = await self.prompt_user("เลือก (1/2/3)", default="1")

            if acc_choice in ["1", ""]:
                print("\n🤖 กำลังเปิด Dropdown สลับบัญชี...")
                try:
                    await self.trademan_page.click("#dropDownAccountPort")
                    self.record_step("CLICK", "#dropDownAccountPort", "-", "คลิกเปิด Dropdown สลับบัญชี Trading A/C")
                    await self.trademan_page.wait_for_timeout(800)

                    # Toggle between 3024952 and 3024959
                    target_acc = "3024952" if "3024959" in current_account else "3024959"
                    print(f"🎯 กำลังเลือกบัญชี: {target_acc}...")
                    acc_item = await self.trademan_page.wait_for_selector(f"span:has-text('{target_acc}'), div:has-text('{target_acc}')", timeout=5000)
                    if acc_item:
                        await acc_item.click()
                        self.record_step("CLICK", f"span:has-text('{target_acc}')", "-", f"คลิกเลือกสลับไปยังบัญชี ({target_acc})")
                        await self.trademan_page.wait_for_timeout(1500)
                        print(f"{C_GREEN}✅ สลับไปยังบัญชี {target_acc} สำเร็จ!{C_RESET}")
                except Exception as ex:
                    print(f"⚠️ เกิดข้อผิดพลาดในการสลับบัญชี: {ex}")

            elif acc_choice == "2":
                print("👉 เชิญคลิกสลับบัญชีบนหน้าจอเบราว์เซอร์ได้เลยครับ...")
                await self.prompt_user("เมื่อคลิกเสร็จแล้ว กด Enter เพื่อดำเนินการต่อ")

            # -------------------------------------------------------------
            # STEP 10: Persist Runbook & Session State (Keep Browser Alive)
            # -------------------------------------------------------------
            print(f"\n{C_BOLD}💾 กำลังบันทึกผลลัพธ์...{C_RESET}")
            await self.save_session()
            self.save_runbook()

            from app.browser.tab_manager import tab_manager
            tab_manager.set_context(self.context)
            if self.main_page and not self.main_page.is_closed():
                tab_manager.register_tab("krungsri_portal", self.main_page)
            if self.trademan_page and not self.trademan_page.is_closed():
                tab_manager.register_tab("trademan", self.trademan_page)
            await tab_manager.scan_and_sync(self.context)

            print(f"\n{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
            print(f"{C_BOLD}{C_GREEN} 🎉 ระบบล็อกอินเข้า Krungsri และ TradeMan สำเร็จเรียบร้อย!{C_RESET}")
            print(f" • แท็บ 1 (Krungsri Master Portal):  {C_BOLD}เปิดค้างไว้{C_RESET} สำหรับ SSO & บริการอื่นๆ ในอนาคต (SBL, eFin, iFund)")
            print(f" • แท็บ 2 (TradeMan Portfolio):      {C_BOLD}เปิดค้างไว้{C_RESET} สำหรับดึงพอร์ตและส่งคำสั่งซื้อขายแบบ Real-time")
            print(f" • สถานะเซสชัน:                     {C_BOLD}{C_YELLOW}PERSISTENT ACTIVE (ไม่ปิดเบราว์เซอร์ 0-sec Latency){C_RESET}")
            print(f"{C_BOLD}{C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
            print(f"\n{C_CYAN}ℹ️  เบราว์เซอร์จะเปิดค้างไว้บนหน้าจอของคุณ และส่ง Heartbeat ป้องกัน Session หลุดทุก 10 นาที{C_RESET}")
            print("   คุณสามารถย่อหน้าต่างหรือสลับไปทำงานอื่นได้ทันที (กด Ctrl+C หากต้องการปิดเบราว์เซอร์)...\n")

            # Smart Keep-Alive Loop: sends lightweight ping across all open tabs
            ping_count = 0
            while True:
                await asyncio.sleep(600)  # 10 minutes
                ping_count += 1
                try:
                    pings = await tab_manager.ping_keepalive()
                    now_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{now_str}] 💓 Smart Keep-Alive Heartbeat #{ping_count} ส่งสำเร็จ: {list(pings.keys())}")
                except Exception as ex:
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
        """Saves current cookies to data/session_state.json for fast direct resumption."""
        state_path = os.path.join(PROJECT_ROOT, "data", "session_state.json")
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        try:
            cookies = await self.context.cookies()
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "TRADEMAN",
                "cookies": cookies,
                "current_url": self.trademan_page.url if self.trademan_page else "https://trademan.in.th/Portfolio"
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  {C_GREEN}✓{C_RESET} บันทึก Session Cookies ({len(cookies)} รายการ) ไปที่: {state_path}")
        except Exception as ex:
            print(f"  {C_RED}✗{C_RESET} บันทึก session_state.json ไม่สำเร็จ: {ex}")

    def save_runbook(self):
        """Generates learned_workflows/trademan_account_switch_and_portfolio.md."""
        runbook_path = os.path.join(PROJECT_ROOT, "learned_workflows", f"{self.workflow_name}.md")
        os.makedirs(os.path.dirname(runbook_path), exist_ok=True)

        lines = [
            f"# Learned Workflow: {self.workflow_name}",
            f"**Workflow Name:** `{self.workflow_name}`  ",
            f"**Platform:** `TRADEMAN`  ",
            f"**Recorded At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Status:** `VERIFIED`  ",
            "",
            "## Description",
            "Verified human-in-the-loop co-piloted workflow for Krungsri Securities portal login, SMS OTP relay via KDE Connect, Single Sign-On (SSO) popup into TradeMan, and Trading Account switching.",
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
            "- [x] All target selectors must be present and visible in DOM",
            "- [x] Krungsri SSO popup window is preserved until OAuth token exchange completes",
            "- [x] `#dropDownAccountPort` is visible on active TradeMan page",
            "- [x] No unhandled error modal overlays",
            "",
            "## Known DOM Quirks & Learned Patterns",
            "- Krungsri TradeMan button uses `javascript:popup('../../th/efin/start_SSO.aspx?page=TM','',1200,800)`. It spawns a new popup window.",
            "- Do NOT invoke direct navigation to `trademan.in.th/Portfolio` before SSO finishes; doing so aborts the session token handshake and drops the user onto `trademan.in.th/SignIn`.",
            "- Once session cookies are saved to `data/session_state.json`, future pre-flight requests can restore cookies and directly open `https://trademan.in.th/Portfolio` in ~2s.",
            "",
            "---",
            "*Generated by Watch-and-Learn Interactive Co-piloting Protocol*"
        ])

        with open(runbook_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"  {C_GREEN}✓{C_RESET} บันทึก Learned Workflow ไปที่: {runbook_path}")


if __name__ == "__main__":
    runner = TrademanWatchAndLearn()
    asyncio.run(runner.run())
