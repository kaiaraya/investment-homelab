# TradeMan Session Reconnect & Auto-Healing Runbook

- **Generated At**: 2026-10-03 12:40:50
- **Platform**: Krungsri TradeMan (`https://trademan.in.th/Portfolio`)
- **Protocol**: Watch-and-Learn Interactive Co-pilot Protocol (`/watch-and-learn`, `/playwright-studio`)
- **Strategy**: 4-Tier Full Auto-Healing (Modal Reconnect -> Soft Reload -> LINE/KDE Alert)

> **⚙️ Implementation Status (2026-10-07 / `KSS-RCA-012`):** Tier-1 reconnect logic นี้ถูก **wire เข้า runtime จริงแล้ว**
> ใน `app/browser/popup_manager.py` เป็น **Tier 0** (`PopupManager.RECONNECT_SELECTORS` +
> `PopupManager._reconnect_if_connection_lost()`) และถูกเรียกอัตโนมัติจาก `dismiss_popups()` ทุกครั้งที่
> `switch_account()` / สแครปพอร์ตทำงาน (ไม่ต้องเรียก `heal_trademan_session()` เอง — ไม่มี Gemini dependency).
> ตัวอย่างโค้ดด้านล่างเป็น **reference semantics** เท่านั้น; ของจริง/ตัวที่รันคือ `popup_manager`.
> Regression: `tests/test_popup_manager.py::test_reconnect_if_connection_lost_*`.

## Verified Recovery Steps

| Step | Action | Target / Selector | Description |
| :--- | :--- | :--- | :--- |
| 1 | `NAVIGATE` | `https://trademan.in.th/Portfolio` | Open TradeMan Portfolio |

## Multi-Tier Auto-Healing Implementation
```python
# Production Auto-Healing Strategy for SessionSentinel:
async def heal_trademan_session(page):
    # Tier 1: Check for active Reconnect modal
    reconnect_btn = await page.query_selector("button:has-text('Reconnect'), button:has-text('เชื่อมต่อใหม่')")
    if reconnect_btn and await reconnect_btn.is_visible():
        await reconnect_btn.click()
        await page.wait_for_timeout(3000)
        return True
    
    # Tier 2: Soft Reload
    await page.reload(wait_until='domcontentloaded')
    await page.wait_for_timeout(3000)
    return True
```
