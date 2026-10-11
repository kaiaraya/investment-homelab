import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from playwright.async_api import async_playwright

from app.core.config import settings

SESSION_PATH = "data/session_state.json"
BASE_DIR = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94"

async def execute_action_exit(symbol: str, side: str, volume: int, price: float, pin: str = settings.KRUNGSRI_PIN):
    symbol = symbol.upper()
    side = side.upper()
    side_word = side.capitalize()
    print(f"=== EXECUTING LIVE ACTION EXIT: {side} {volume:,} {symbol} @ {price:.2f} ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True)
        context = await browser.new_context(storage_state=SESSION_PATH, viewport={"width": 1600, "height": 1000})
        page = await context.new_page()

        try:
            await page.goto("https://trademan.in.th/Portfolio", wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("Goto warning, retrying:", e)
            await page.goto("https://trademan.in.th/Portfolio", wait_until="commit", timeout=45000)
        await asyncio.sleep(4)

        # 1. Clear any popups
        await page.evaluate("""() => {
            document.querySelectorAll("input.disable_show, input[type='checkbox']").forEach(cb => {
                if (!cb.checked) cb.click();
            });
            document.querySelectorAll(".v-overlay--active .absolute.top-3.right-3 button, .v-overlay--active button").forEach(btn => {
                btn.click();
            });
        }""")
        await asyncio.sleep(1)

        # 2. Verify Account is 3024959 (Margin)
        acc_text = await page.evaluate("""() => {
            const accEl = document.querySelector("#dropDownAccountPort") || document.querySelector("#dropDownAccount");
            return accEl ? accEl.innerText.trim() : null;
        }""")
        print(f"Current Account: {acc_text}")
        assert "3024959" in (acc_text or ""), f"Account mismatch! Expected 3024959, got {acc_text}"

        # 3. Ensure Buy/Sell panel is open
        if not await page.evaluate("() => !!document.getElementById('send_order__btn')"):
            await page.click("div[title='Buy/Sell']")
            await asyncio.sleep(2)

        # 4. Tier 1 Anti-DW: Click target symbol directly in the Portfolio table
        print(f"Selecting pure stock {symbol} from Portfolio table...")
        clicked_sym = await page.evaluate("""(targetSym) => {
            const allTds = Array.from(document.querySelectorAll("td"));
            const targetTd = allTds.find(td => td.innerText && td.innerText.trim() === targetSym);
            if (targetTd) {
                targetTd.click();
                return true;
            }
            return false;
        }""", symbol)
        assert clicked_sym, f"Could not find {symbol} in portfolio table!"
        await asyncio.sleep(2)

        # 5. Strict Assertions: Check Symbol and On Hand
        verification = await page.evaluate("""() => {
            const symEl = Array.from(document.querySelectorAll("div")).find(d => 
                d.className.includes("bg-[#2B313A]") && d.parentElement && d.parentElement.innerText.includes("Symbol")
            );
            const labels = Array.from(document.querySelectorAll("div"));
            const onHandLabel = labels.find(l => l.innerText && l.innerText.trim() === "On Hand");
            let onHandVal = null;
            if (onHandLabel && onHandLabel.parentElement && onHandLabel.parentElement.nextElementSibling) {
                onHandVal = onHandLabel.parentElement.nextElementSibling.lastElementChild.innerText.trim();
            }
            return {
                symbol: symEl ? symEl.innerText.trim() : null,
                onHand: onHandVal
            };
        }""")
        v_sym = verification.get("symbol")
        v_on_hand = verification.get("onHand")
        print(f"Verified Symbol: {v_sym}, On Hand: {v_on_hand}")
        assert v_sym == symbol, f"CRITICAL: Symbol is {v_sym}, expected {symbol}!"

        # 6. Select Side (SELL, BUY, SHORT, COVER)
        print(f"Selecting {side} side...")
        await page.locator(f"span:text-is('{side}')").first.click()
        await asyncio.sleep(1)

        # 7. Fill Volume and Price
        print(f"Filling Volume: {volume}, Price: {price:.2f}...")
        vol_inp = page.locator("input[id$='-order-volume']").first
        await vol_inp.fill(str(volume))
        await asyncio.sleep(0.5)

        prc_inp = page.locator("input[id$='-order-price']").first
        await prc_inp.fill(f"{price:.2f}")
        await asyncio.sleep(0.5)

        # 8. Capture Pre-Submit Screenshot
        pre_path = f"{BASE_DIR}/trademan_{symbol.lower()}_presubmit.png"
        await page.screenshot(path=pre_path)
        print(f"Saved Pre-Submit Screenshot: {pre_path}")

        # 9. Click Send Button!
        print(">>> CLICKING SEND BUTTON (#send_order__btn) <<<")
        send_btn = page.locator("#send_order__btn").first
        await send_btn.click()
        await asyncio.sleep(2)

        # 10. Check if Confirmation Modal appeared
        modal_info = await page.evaluate("""() => {
            const overlay = document.querySelector(".v-overlay--active");
            if (!overlay) return { hasModal: false };
            const btns = Array.from(overlay.querySelectorAll("button")).map(b => b.innerText.trim());
            return {
                hasModal: overlay.innerText.includes("Order Confirm"),
                text: overlay.innerText.trim(),
                buttons: btns
            };
        }""")
        print(f"Modal info: {json.dumps(modal_info, indent=2, ensure_ascii=False)}")

        # 11. Fill PIN and Click Confirm button
        if modal_info.get("hasModal") and pin:
            print("Modal detected: Entering PIN and confirming...")
            pin_input = page.locator("input#pin, .v-overlay--active input#pin").first
            if await pin_input.is_visible():
                await pin_input.fill("")
                await pin_input.fill(pin)
                await asyncio.sleep(0.5)

            # Save PIN checkbox
            save_pin_cb = page.locator("input#savepin, .v-overlay--active input#savepin").first
            if await save_pin_cb.is_visible():
                try:
                    if not await save_pin_cb.is_checked():
                        await save_pin_cb.click()
                except Exception:
                    pass

            # Click side-specific confirm button
            confirm_btn = page.locator(f".v-overlay--active button:has(span:text-is('{side_word}')), .v-overlay--active button.bg-primaryRed-300, .v-overlay--active button:has-text('{side_word}')").first
            if await confirm_btn.is_visible():
                print(f">>> CLICKING '{side_word}' CONFIRM BUTTON IN MODAL <<<")
                await confirm_btn.click()
                await asyncio.sleep(3)
            else:
                print("Clicking confirm button via JS...")
                await page.evaluate(f"""(word) => {{
                    const overlay = document.querySelector('.v-overlay--active');
                    if (overlay) {{
                        const btn = Array.from(overlay.querySelectorAll('button')).find(b => b.innerText && b.innerText.trim().includes(word));
                        if (btn) btn.click();
                    }}
                }}""", side_word)
                await asyncio.sleep(3)

        post_path = f"{BASE_DIR}/trademan_{symbol.lower()}_submitted.png"
        await page.screenshot(path=post_path)
        print(f"Saved Post-Submit Screenshot: {post_path}")

        # 12. Check Order Transactions table to extract Order No
        await asyncio.sleep(2)
        transactions = await page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll("#order_btn ~ div tr, .order-list tr, div:has(> table) tr, div[class*='order'] tr"));
            return rows.map(r => r.innerText.trim()).filter(t => t.length > 0);
        }""")
        print(f"Order Transactions after submit:")
        for t in transactions[:8]:
            print(" ", t)

        # 13. Extract Order No from toast or transaction
        toast_text = await page.evaluate("""() => {
            const toasts = Array.from(document.querySelectorAll(".v-snackbar, .v-toast, [role=alert], .text-notification, [class*='toast']")).map(t => t.innerText.trim());
            return toasts.join(" | ");
        }""")
        print(f"Toast alerts: {toast_text}")

        # 14. Update SQLite database orders table
        try:
            conn = sqlite3.connect("investment_homelab.db")
            c = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                UPDATE orders 
                SET status = 'OPEN', broker_order_no = 'SUBMITTED-TRADEMAN', updated_at = ?
                WHERE symbol = ? AND side = ? AND status = 'AWAITING_HITL_CONFIRMATION'
            """, (now_str, symbol, side))
            conn.commit()
            conn.close()
            print(f"Updated {symbol} in investment_homelab.db to OPEN")
        except Exception as e:
            print("DB Update Warning:", e)

        # 15. Send Desktop Alert
        try:
            import subprocess
            subprocess.run([
                "notify-send", "-u", "critical", 
                f"Krungsri TradeMan Live: {symbol}",
                f"ส่งคำสั่ง {side} {volume:,} หุ้น {symbol} @ {price:.2f} บาท เรียบร้อยแล้ว!"
            ], timeout=5)
        except Exception as e:
            print("Notification Warning:", e)

        await browser.close()
        print(f"=== COMPLETED LIVE ACTION EXIT FOR {symbol} ===")

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "COCOCO"
    s_side = sys.argv[2] if len(sys.argv) > 2 else "SELL"
    vol = int(sys.argv[3]) if len(sys.argv) > 3 else 8800
    prc = float(sys.argv[4]) if len(sys.argv) > 4 else 5.65
    p_pin = sys.argv[5] if len(sys.argv) > 5 else settings.KRUNGSRI_PIN
    asyncio.run(execute_action_exit(sym, s_side, vol, prc, p_pin))
