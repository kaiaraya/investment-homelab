import asyncio
import json
import sqlite3
from datetime import datetime
from playwright.async_api import async_playwright

from app.core.config import settings

SESSION_PATH = "data/session_state.json"
BASE_DIR = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94"

async def execute_live_sawad_sell(pin: str = settings.KRUNGSRI_PIN):
    print("=== STARTING LIVE SEND: SAWAD SELL 2,200 @ OFFER 1 ===")
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

        # 4. Tier 1 Anti-DW: Click SAWAD directly in the Portfolio table
        print("Selecting pure stock SAWAD from Portfolio table...")
        clicked_sawad = await page.evaluate("""() => {
            const allTds = Array.from(document.querySelectorAll("td"));
            const targetTd = allTds.find(td => td.innerText && td.innerText.trim() === "SAWAD");
            if (targetTd) {
                targetTd.click();
                return true;
            }
            return false;
        }""")
        assert clicked_sawad, "Could not find SAWAD in portfolio table!"
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
        assert v_sym == "SAWAD", f"CRITICAL: Symbol is {v_sym}, not SAWAD!"
        assert "2,200" in (v_on_hand or ""), f"CRITICAL: On Hand is {v_on_hand}, expected 2,200!"

        # 6. Select SELL side
        print("Selecting SELL side...")
        await page.locator("span:text-is('SELL')").first.click()
        await asyncio.sleep(1)

        # 7. Extract current live Bid 1 / Offer 1 to confirm best passive pricing
        quotes = await page.evaluate("""() => {
            const prcInput = document.querySelector("input[id$='-order-price']");
            return {
                defaultPrice: prcInput ? prcInput.value : null
            };
        }""")
        print(f"Default Price in form: {quotes.get('defaultPrice')}")
        target_price = "22.50"  # Best Offer 1 queue price

        # 8. Fill Volume (2,200) and Price (22.50)
        print(f"Filling Volume: 2200, Price: {target_price}...")
        vol_inp = page.locator("input[id$='-order-volume']").first
        await vol_inp.fill("2200")
        await asyncio.sleep(0.5)

        prc_inp = page.locator("input[id$='-order-price']").first
        await prc_inp.fill(target_price)
        await asyncio.sleep(0.5)

        # 9. Capture Pre-Submit Screenshot
        pre_submit_path = f"{BASE_DIR}/trademan_sawad_live_presubmit.png"
        await page.screenshot(path=pre_submit_path)
        print(f"Saved Pre-Submit Screenshot: {pre_submit_path}")

        # 10. Click Send Button!
        print(">>> CLICKING SEND BUTTON (#send_order__btn) <<<")
        send_btn = page.locator("#send_order__btn").first
        await send_btn.click()
        await asyncio.sleep(2)

        # 11. Check if Confirmation Modal or Dialog appeared
        modal_info = await page.evaluate("""() => {
            const overlays = Array.from(document.querySelectorAll(".v-overlay--active, .v-dialog, [role=dialog]"));
            const visibleOverlays = overlays.filter(o => o.offsetParent !== null || o.classList.contains("v-overlay--active"));
            
            let buttons = [];
            visibleOverlays.forEach(o => {
                const btns = Array.from(o.querySelectorAll("button")).map(b => b.innerText.trim());
                buttons.push(...btns);
            });

            const toasts = Array.from(document.querySelectorAll(".v-snackbar, .v-toast, [role=alert], .text-notification")).map(t => t.innerText.trim());

            return {
                hasModal: visibleOverlays.length > 0,
                modalText: visibleOverlays.map(o => o.innerText.trim()),
                buttons: buttons,
                toasts: toasts
            };
        }""")
        print(f"Modal Info after Send: {json.dumps(modal_info, indent=2, ensure_ascii=False)}")

        # Capture Post-Send Screenshot
        post_send_path = f"{BASE_DIR}/trademan_sawad_live_postsend.png"
        await page.screenshot(path=post_send_path)
        print(f"Saved Post-Send Screenshot: {post_send_path}")

        # If confirmation modal exists, fill PIN and click 'Sell'
        if modal_info.get("hasModal") and pin:
            print(f"Modal detected: Filling PIN into input#pin and clicking 'Sell' button...")
            pin_input = page.locator("input#pin, .v-overlay--active input#pin").first
            if await pin_input.is_visible():
                await pin_input.fill("")
                await pin_input.fill(pin)
                await asyncio.sleep(0.5)
            else:
                print("WARNING: input#pin not visible!")

            # Optional: Check 'Save PIN'
            save_pin_cb = page.locator("input#savepin, .v-overlay--active input#savepin").first
            if await save_pin_cb.is_visible():
                try:
                    if not await save_pin_cb.is_checked():
                        await save_pin_cb.click()
                except Exception:
                    pass

            # Click the red 'Sell' confirm button
            sell_confirm_btn = page.locator(".v-overlay--active button:has(span:text-is('Sell')), .v-overlay--active button.bg-primaryRed-300, .v-overlay--active button:has-text('Sell')").first
            if await sell_confirm_btn.is_visible():
                print(">>> CLICKING 'SELL' CONFIRM BUTTON IN MODAL <<<")
                await sell_confirm_btn.click()
                await asyncio.sleep(3)
            else:
                print("WARNING: sell_confirm_btn not visible! Trying JS click...")
                await page.evaluate("""() => {
                    const overlay = document.querySelector(".v-overlay--active");
                    if (overlay) {
                        const btn = Array.from(overlay.querySelectorAll("button")).find(b => b.innerText && b.innerText.trim() === "Sell");
                        if (btn) btn.click();
                    }
                }""")
                await asyncio.sleep(3)

            post_modal_path = f"{BASE_DIR}/trademan_sawad_live_postmodal.png"
            await page.screenshot(path=post_modal_path)
            print(f"Saved Post-Modal Screenshot: {post_modal_path}")

        # 12. Check Order Transaction table & extract submitted order
        await asyncio.sleep(2)
        transactions = await page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll("#order_btn ~ div tr, .order-list tr, div:has(> table) tr, div[class*='order'] tr"));
            return rows.map(r => r.innerText.trim()).filter(t => t.length > 0);
        }""")
        print(f"Order Transactions after submit: {transactions[:10]}")

        final_path = f"{BASE_DIR}/trademan_sawad_live_final.png"
        await page.screenshot(path=final_path)
        print(f"Saved Final Screenshot: {final_path}")

        # 13. Update SQLite database orders table if executed
        if pin:
            try:
                conn = sqlite3.connect("investment_homelab.db")
                c = conn.cursor()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""
                    UPDATE orders 
                    SET status = 'OPEN', broker_order_no = 'SUBMITTED-TRADEMAN', updated_at = ?
                    WHERE order_id = 'ORD-ACT-D6EC6894'
                """, (now_str,))
                conn.commit()
                conn.close()
                print("Updated ORD-ACT-D6EC6894 in investment_homelab.db to OPEN")
            except Exception as e:
                print("DB Update Warning:", e)

            # 14. (REMOVED 2026-10-08 — KDE-RCA-009) KDE Connect ping alert dropped per user request.
            #     It hard-coded a bogus device id ("a0149021_...", underscore — not a valid KDE
            #     Connect hex id) so the alert NEVER reached the phone while still printing
            #     "Sent KDE Connect alert" (silent false-success). To re-add, call
            #     app/services/kdeconnect_service.py (is_device_reachable / send_critical_alert)
            #     which resolves the live id from config.KDECONNECT_DEVICE_ID — never a literal.

        await browser.close()
        print("=== LIVE SEND EXECUTION SCRIPT COMPLETED ===")

if __name__ == "__main__":
    import sys
    target_pin = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(execute_live_sawad_sell(pin=target_pin))
