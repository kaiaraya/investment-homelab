import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from app.browser.auth_driver import auth_driver
from app.browser.popup_manager import popup_manager

async def main():
    page = await auth_driver.launch_browser(resume_state=True)
    await page.goto("https://trademan.in.th/SBL", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    await popup_manager.dismiss_popups(page)

    # 1. Let's inspect page buttons and scroll container
    res = await page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('div.flex.cursor-pointer'));
        const symbols = rows.map(r => {
            const first = r.querySelector('span, div');
            return first ? first.innerText.trim() : '';
        }).filter(Boolean);

        // Look for buttons around or below the table
        const allButtons = Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.innerText.trim(),
            classes: b.className,
            aria: b.getAttribute('aria-label') || ''
        })).filter(b => b.text.length > 0 || b.aria.length > 0);

        const container = document.querySelector('div.overflow-y-auto');

        return {
            initialRowTotal: rows.length,
            sampleSymbols: symbols.slice(0, 15),
            allButtons: allButtons,
            hasScrollContainer: !!container,
            containerScrollHeight: container ? container.scrollHeight : 0,
            containerClientHeight: container ? container.clientHeight : 0
        };
    }""")
    print("Initial SBL Page Info:")
    print(" - Total initial rows:", res["initialRowTotal"])
    print(" - Sample symbols:", res["sampleSymbols"])
    print(" - Scroll container:", res["hasScrollContainer"], "ScrollHeight:", res["containerScrollHeight"], "ClientHeight:", res["containerClientHeight"])
    print(" - All buttons found:")
    # Let's test clicking Page 2 and Next Page
    page2_btn = await page.query_selector("button[aria-label='Go to page 2'], button:has-text('2')")
    if page2_btn:
        print("Clicking Page 2...")
        await page2_btn.click()
        await page.wait_for_timeout(1000)
        
        page2_symbols = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('div.flex.cursor-pointer'));
            return rows.map(r => r.innerText.trim().split('\\n')[0]).filter(Boolean);
        }''')
        print("Page 2 Symbols found:", page2_symbols)

    # Let's test switching to SET100 and checking its pagination
    set100_btn = await page.query_selector("span:has-text('SET100'), div:has-text('SET100')")
    if set100_btn:
        print("\nSwitching to SET100 tab...")
        await set100_btn.click()
        await page.wait_for_timeout(1000)
        
        set100_pages = await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button[aria-label*=\"page\" i], button[aria-label*=\"Page\" i]'))
                .map(b => b.getAttribute('aria-label'));
            const rows = Array.from(document.querySelectorAll('div.flex.cursor-pointer'));
            return {
                pages: btns,
                page1_symbols: rows.map(r => r.innerText.trim().split('\\n')[0]).filter(Boolean)
            };
        }''')
        print("SET100 pagination:", set100_pages["pages"])
        print("SET100 page 1 count:", len(set100_pages["page1_symbols"]), set100_pages["page1_symbols"][:10])

    # Let's test switching to NEWSEC tab
    newsec_btn = await page.query_selector("span:has-text('NEWSEC'), div:has-text('NEWSEC')")
    if newsec_btn:
        print("\nSwitching to NEWSEC tab...")
        await newsec_btn.click()
        await page.wait_for_timeout(1000)
        newsec_info = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('div.flex.cursor-pointer'));
            return rows.map(r => r.innerText.trim().split('\\n')[0]).filter(Boolean);
        }''')
        print("NEWSEC symbols:", len(newsec_info), newsec_info)

    # Let's test switching to XD, XR tab
    xd_btn = await page.query_selector("span:has-text('XD, XR'), div:has-text('XD, XR')")
    if xd_btn:
        print("\nSwitching to XD, XR tab...")
        await xd_btn.click()
        await page.wait_for_timeout(1000)
        xd_info = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('div.flex.cursor-pointer'));
            return rows.map(r => r.innerText.trim().split('\\n')[0]).filter(Boolean);
        }''')
        print("XD, XR symbols:", len(xd_info), xd_info)

if __name__ == "__main__":
    asyncio.run(main())
