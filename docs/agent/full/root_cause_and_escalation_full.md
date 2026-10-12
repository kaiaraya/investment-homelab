# Rule: Root Cause First, Anti-Mock Guardrail & KDE Connect Escalation

## Invariant 1: Zero Hallucination & Strict Anti-Mock Guardrail
- Under NO circumstances should an agent, driver, or MCP tool return mock account numbers, fabricated balances, dummy order IDs, or empty arrays masquerading as valid data when a live scraper or automation step fails.
- If data cannot be retrieved or an operation fails, it must be reported honestly with full diagnostic context or routed to a safe maintenance status.

## Invariant 2: Rigorous 3-Point Root Cause Investigation
Before proposing or applying code patches, perform a systematic 3-point Root Cause Analysis:
1. **Session & Context Isolation**: Verify whether browser sessions or contexts collide, or cookies are expired.
2. **DOM & UI Reality**: Inspect live DOM elements via headed browser, screenshots, or Playwright console instead of guessing CSS selectors.
3. **Data Schema & Types**: Compare scraped table structures and column orders with active platform expectations (e.g. Equity vs TFEX column differences).

## Invariant 3: Workflow Self-Annealing (4-Step Self-Healing)
When an automation step fails, apply the 4-step self-annealing sequence before escalating:
1. **Dismiss Obstructive Popups**: Automatically check for and close modals, banners, or overlays.
2. **Try Fallback Selectors**: Test known fallback selectors belonging to the same component family.
3. **Wait for DOM Re-render**: Pause 1–2 seconds for async rendering or hydration.
4. **Escalate**: If all fail, capture an Anomaly Snapshot, log to database, and trigger Admin Escalation.

## Invariant 4: Hardware HITL Escalation via KDE Connect
- When a critical operation fails (e.g. account switching, order execution, SBL transaction, or persistent scraping anomaly):
  - Send an immediate high-priority ping to Admin's Android device via KDE Connect:
    `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ / workflow / รายละเอียด]`
  - Do NOT loop indefinitely, fail silently, or guess.

## Invariant 5: Truthful Remote MCP Communication
- When an MCP tool is invoked while the system is in an uncertain, degraded, or maintenance state:
  - Return JSON-RPC success response containing type-safe payload:
    - `status: "UNDER_MAINTENANCE"`
    - `success: false`
    - `message: "ระบบกำลังปรับปรุง โปรดติดต่อ Admin เนื่องจากข้อมูลยังไม่พร้อม (มีความเสี่ยงสูง)"`
  - Never allow an autonomous remote agent to act on unverified or hallucinated data.

## Invariant 6: Strict Type-Safety & Rigorous Testing
- Use Pydantic models with explicit Enums (`MCPToolStatus`) for all MCP inputs and outputs.
- Every workflow change or bug fix must be covered by unit tests and pass the test suite (`pytest`) before declaring complete.

## Invariant 7: Mandatory Pre-Flight Readiness & Connectivity Gatekeeper
- ก่อนเริ่มการทดสอบ (Unit Test, E2E Test, หรือ Driver Automation) ทุกครั้ง:
  1. ตรวจสอบการเชื่อมต่อ Dependencies ทั้งหมดผ่าน `scripts/preflight_check.py`
  2. หาก Service ใดไม่พร้อม (เช่น Uvicorn ปิดอยู่ หรือ Session คุกกี้ไม่มี) ให้แจ้งเตือนผู้ใช้หรือเตรียม Service ให้พร้อมก่อน ห้ามปล่อยให้คำสั่งไปค้างรอ Timeout
  3. ห้ามไม่ให้ฟังก์ชันเบื้องหลัง (Background Inquiries / Scrapers) สั่ง Full Login ที่กระตุ้น 2FA SMS OTP โดยพลการเด็ดขาด หากไม่มี Session ให้ใช้ Offline / Cached Data

## Invariant 8: Real-time D-Bus Phone Bridge & Non-Destructive Cookies
- การตรวจสอบความพร้อมของสะพานเชื่อมต่อมือถือ (KDE Connect / SMS Relay) ต้องเช็คแบบ Real-time ผ่าน D-Bus property **`isReachable`** และ TCP Port 1716 ห้ามเชื่อค่าแคชจาก `kdeconnect-cli -l`
  - ⚠️ **ห้ามใช้ `iconName` / `statusIconName`** — พิสูจน์สด (2026-10-07) ว่าไม่น่าเชื่อถือ: `iconName` คืน `'smartphonedisconnected'` **แม้โทรศัพท์เชื่อมต่ออยู่จริง** (`isReachable=true` + ping ผ่าน) = false-negative (ดู `KDE-RCA-008` REVISED)
- ห้ามลบไฟล์ `session_state.json` ทิ้งเมื่อเกิด DOM Exception หรือ Timeout ชั่วคราว เพื่อรักษาบัตรผ่าน Zero-OTP ไว้อย่างปลอดภัย
## Invariant 9: OTP Bridge Readiness Gate — Never Fire SMS OTP Unless the Bridge is Live
- ก่อน `auth_driver.login()` (Krungsri) จะ submit credentials / trigger SMS OTP **ทุกครั้ง** ต้องผ่าน `kdeconnect_service.is_device_reachable()` (real-time D-Bus `isReachable == true`) ก่อน
- หาก bridge ไม่พร้อม → ยกเลิก login ด้วย `status=BRIDGE_DOWN` โดย **ไม่ส่ง SMS OTP** (กันเปลือง OTP + กัน account lock) แล้วแจ้ง user ให้เปิดแอป KDE Connect บนมือถือก่อน
- ตรวจ readiness ด้วย property **`isReachable`** เท่านั้น — ห้ามใช้ `iconName` / `statusIconName` (พิสูจน์แล้วว่าไม่น่าเชื่อถือทั้งคู่)
- **ข้อจำกัดที่ยังเหลือ (2026-10-07):** แม้ `isReachable == true` (บริดจ์พร้อมใช้) แต่ SMS relay ยังพังได้ถ้าแอปสองฝั่งคนละเวอร์ชัน — NUC `kdeconnect 23.08.5` vs แอปมือถือรุ่นใหม่ → log `discarding unsupported packet "kdeconnect.notification.request"` → OTP ไม่ถูก relay อัตโนมัติ จนกว่าจะอัปเกรด `kdeconnect` ฝั่ง NUC (ดู `KDE-RCA-008`)

