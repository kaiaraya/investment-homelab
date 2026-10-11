import asyncio
import os
import sys
import logging
from typing import Any, Callable, Coroutine, Optional, Dict, List
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("PlaywrightGrillHarness")


class GrillController:
    """
    Grill-Me Interactive Playwright Test Harness.
    
    Provides a human-in-the-loop (HITL) direct feedback loop during Playwright testing:
    - Step-by-step inspection and confirmation.
    - Automatic error catching: prevents crashes and engages interactive grilling menu.
    - Live locator testing with visual element highlighting in the browser.
    - Direct hook into Playwright Inspector GUI (page.pause()).
    - On-the-fly JavaScript evaluation and selector overrides.
    """

    def __init__(self, mode: str = "on-failure", auto_highlight: bool = True):
        """
        :param mode: 'step' (pause on every step) or 'on-failure' (pause only when mistakes/errors occur).
        :param auto_highlight: Automatically highlight targeted elements with a glowing border in headed mode.
        """
        self.mode = mode
        self.auto_highlight = auto_highlight
        self.step_counter = 0

    async def highlight_element(self, page: Page, selector: str, color: str = "#f59e0b") -> int:
        """
        Highlights matching elements on the live page with a glowing animated border
        and returns the number of matched elements.
        """
        try:
            js = f"""(sel) => {{
                const els = document.querySelectorAll(sel);
                els.forEach(el => {{
                    el.style.outline = '3px solid {color}';
                    el.style.boxShadow = '0 0 10px {color}';
                    el.style.transition = 'all 0.3s ease';
                }});
                return els.length;
            }}"""
            count = await page.evaluate(js, selector)
            return count
        except Exception as e:
            logger.debug(f"Highlight error for selector '{selector}': {e}")
            return 0

    async def clear_highlights(self, page: Page) -> None:
        """Clears all injected highlight outlines."""
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('*').forEach(el => {
                    if (el.style.outline && el.style.outline.includes('solid')) {
                        el.style.outline = '';
                        el.style.boxShadow = '';
                    }
                });
            }""")
        except Exception:
            pass

    async def probe_locator(self, page: Page, selector: str) -> None:
        """
        Interactive probe: tests a selector against the live page, displays
        count, visibility, text, and highlights it visually.
        """
        print(f"\n🔍 Probing Locator: '{selector}' ...")
        try:
            count = await self.highlight_element(page, selector, color="#10b981")
            locator = page.locator(selector)
            loc_count = await locator.count()
            print(f"   📊 Matched Elements: {loc_count}")

            if loc_count == 0:
                print("   ⚠️  No elements found with this selector.")
                if not selector.startswith("text=") and ":" not in selector:
                    print(f"   💡 Tip: Try text search: text={selector} or :has-text('{selector}')")
            else:
                for idx in range(min(loc_count, 5)):
                    item = locator.nth(idx)
                    is_visible = await item.is_visible()
                    try:
                        text = (await item.inner_text()).strip().replace("\n", " ")
                    except Exception:
                        text = "<no innerText>"
                    try:
                        tag = await item.evaluate("el => el.tagName.toLowerCase()")
                    except Exception:
                        tag = "elem"
                    print(f"   [{idx + 1}] <{tag}> visible={is_visible} | text: {text[:80]}")
                if loc_count > 5:
                    print(f"   ... and {loc_count - 5} more elements.")
        except Exception as e:
            print(f"   ❌ Selector syntax/execution error: {e}")

    async def take_snapshot(self, page: Page, step_name: str, dump_dir: str = "data/diagnostics") -> Dict[str, str]:
        """Saves current screenshot and DOM HTML for inspection."""
        os.makedirs(dump_dir, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_name)[:40]
        ts = int(asyncio.get_event_loop().time() * 1000)
        ss_path = os.path.join(dump_dir, f"{ts}_{safe_name}.png")
        html_path = os.path.join(dump_dir, f"{ts}_{safe_name}.html")

        try:
            await page.screenshot(path=ss_path, full_page=False)
            content = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"   📸 Screenshot saved: {ss_path}")
            print(f"   📄 HTML DOM saved:   {html_path}")
            return {"screenshot": ss_path, "html": html_path}
        except Exception as e:
            print(f"   ⚠️ Failed to take snapshot: {e}")
            return {}

    async def grill_menu(
        self,
        page: Page,
        step_name: str,
        error: Optional[Exception] = None,
        last_selector: Optional[str] = None
    ) -> str:
        """
        Interactive Grill-Me terminal prompt loop.
        Allows the user to inspect, probe, run DevTools/Inspector, eval JS, retry, or skip.
        
        Returns action choice: 'continue', 'retry', 'skip', 'abort', or a new selector string.
        """
        print("\n" + "=" * 70)
        if error:
            print(f" 🔥 [GRILL-ME] MISTAKE / ERROR DETECTED ON STEP #{self.step_counter}")
            print(f"    Step:  {step_name}")
            print(f"    Error: {type(error).__name__}: {error}")
        else:
            print(f" 🎯 [GRILL-ME] CHECKPOINT: STEP #{self.step_counter} - {step_name}")

        try:
            url = page.url
            title = await page.title()
            print(f"    URL:   {url}")
            print(f"    Title: '{title}'")
        except Exception:
            pass

        if last_selector:
            print(f"    Target Selector: {last_selector}")
        print("=" * 70)

        while True:
            print("\nOptions:")
            print("  [Enter] / [c] Continue to next step")
            print("  [p]           Launch Playwright Inspector GUI (page.pause())")
            print("  [i]           Probe / test a selector (live highlighting on screen)")
            print("  [e]           Eval JavaScript in browser console")
            print("  [s]           Take screenshot & dump HTML DOM")
            if error or last_selector:
                print("  [r]           Retry current step")
                print("  [u]           Update selector & retry immediately")
            print("  [k]           Skip this step")
            print("  [q]           Quit / Abort test")

            try:
                choice = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("👉 Select Option: ").strip().lower()
                )
            except (KeyboardInterrupt, EOFError):
                return "abort"

            if choice in ("", "c", "continue"):
                return "continue"
            elif choice == "p":
                print("\n⏸️  Triggering Playwright Inspector GUI (page.pause())...")
                print("   The official Playwright Inspector window will appear.")
                print("   Use its 'Explore' tool or click 'Resume' when done.")
                try:
                    await page.pause()
                except Exception as e:
                    print(f"   ⚠️ Inspector pause ended or failed: {e}")
            elif choice == "i":
                try:
                    sel = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("Enter selector to test (CSS / XPath / text=...): ").strip()
                    )
                    if sel:
                        await self.probe_locator(page, sel)
                except (KeyboardInterrupt, EOFError):
                    pass
            elif choice == "e":
                try:
                    js_code = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("Enter JavaScript expression: ").strip()
                    )
                    if js_code:
                        res = await page.evaluate(js_code)
                        print(f"   💡 Result: {res}")
                except Exception as e:
                    print(f"   ❌ JS Error: {e}")
            elif choice == "s":
                await self.take_snapshot(page, step_name)
            elif choice == "r":
                return "retry"
            elif choice == "u":
                try:
                    new_sel = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("Enter replacement selector to retry with: ").strip()
                    )
                    if new_sel:
                        return f"new_selector:{new_sel}"
                except (KeyboardInterrupt, EOFError):
                    pass
            elif choice == "k":
                print("⏭️  Skipping step.")
                return "skip"
            elif choice == "q":
                print("🛑 Aborting test execution.")
                return "abort"
            else:
                print(f"Unknown command: '{choice}'. Type 'c', 'p', 'i', 'e', 's', 'r', 'k', or 'q'.")

    async def execute_step(
        self,
        page: Page,
        step_name: str,
        action_coro: Callable[..., Coroutine[Any, Any, Any]],
        selector: Optional[str] = None
    ) -> Any:
        """
        Wraps a test step with the Grill-Me feedback loop:
        1. If mode == 'step', prompts user before execution.
        2. Executes action.
        3. If an error occurs, catches it, snapshots the page, and enters the Grill-Me menu
           allowing live debugging, retry, locator modification, or skipping.
        """
        self.step_counter += 1
        current_selector = selector

        if self.mode == "step":
            if current_selector and self.auto_highlight:
                await self.highlight_element(page, current_selector, color="#3b82f6")

            decision = await self.grill_menu(page, step_name, last_selector=current_selector)
            if decision == "abort":
                raise SystemExit("User aborted execution.")
            elif decision == "skip":
                return None
            elif decision.startswith("new_selector:"):
                current_selector = decision.split(":", 1)[1]

        while True:
            try:
                await self.clear_highlights(page)
                if current_selector and self.auto_highlight:
                    await self.highlight_element(page, current_selector, color="#3b82f6")

                print(f"\n▶️  [Step #{self.step_counter}] {step_name} ...")
                if current_selector != selector:
                    try:
                        res = await action_coro(current_selector)
                    except TypeError:
                        res = await action_coro()
                else:
                    res = await action_coro()

                print(f"   ✅ [Step #{self.step_counter}] SUCCESS")
                await self.clear_highlights(page)
                return res

            except Exception as e:
                await self.take_snapshot(page, f"fail_step_{self.step_counter}")
                decision = await self.grill_menu(page, step_name, error=e, last_selector=current_selector)

                if decision == "abort":
                    raise
                elif decision == "skip":
                    print(f"   ⏭️ Skipped step #{self.step_counter}")
                    return None
                elif decision == "retry":
                    print(f"   🔄 Retrying step #{self.step_counter}...")
                    continue
                elif decision.startswith("new_selector:"):
                    current_selector = decision.split(":", 1)[1]
                    print(f"   🔄 Retrying with new selector: '{current_selector}' ...")
                    continue
                elif decision == "continue":
                    return None
