# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: Playwright Headed-Browser / MCP Environment (Shared)
**Component:** `app.mcp.mcp_server` (playwright-homelab MCP transport) + Playwright/Chromium launch environment
**Scope:** สภาพแวดล้อมการรัน **headed (มีหน้าจอ) browser automation** ที่ **ใช้ร่วมกันทั้ง Krungsri TradeMan, Settrade Click2Win และ Liberator WebTrade**
**Last Updated:** 2026-10-05
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose)
ไฟล์นี้เป็น SSOT ขององค์ความรู้ด้าน **สภาพแวดล้อมการรันเบราว์เซอร์แบบ headed** ซึ่งเป็น Dependency ร่วม
(ไม่ผูกกับโบรกเกอร์ใดโบรกเกอร์หนึ่ง) การแก้ไขในชั้นนี้มีผลกับทุกโบรกเกอร์ จึงต้องแยกออกจากไฟล์ RCA รายโบรกเกอร์
เพื่อรักษาหลัก **Broker Knowledge Isolation**

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :---: | :---: | :--- | :--- | :---: |
| 2026-10-05 | `PWENV-RCA-001` | MCP tools ฝั่ง headed (`browser_open`, `browser_screenshot`, `trademan_check_session`) ล้มเหลวทุกครั้งด้วย `Missing X server or $DISPLAY` ทั้งที่จอ `:0` ทำงานปกติ | โปรเซสของ MCP server ไม่มีตัวแปรสภาพแวดล้อม `DISPLAY` (ไม่ได้ถูก export ตอน launch) จึงสืบทอด env ที่ไม่มี DISPLAY → Chromium ยกเลิกการเริ่มต้น | 🟡 LOGGED (รอแก้ — นอก scope ปัจจุบัน) |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `PWENV-RCA-001`: MCP Server Process Missing `DISPLAY` → All Headed MCP Tools Fail
* **วันและเวลา:** 2026-10-05 (ระหว่างทดสอบ Stage 2 headed login)
* **อาการ (Symptom):**
  เรียก `playwright-homelab` MCP tool แบบ headed (เช่น `trademan_check_session`, `browser_screenshot`) แล้วได้:
  ```
  BrowserType.launch: Target page, context or browser has been closed
  ║ Looks like you launched a headed browser without having a XServer running. ║
  [pid] ERROR:ui/ozone/platform/x11/ozone_platform_x11.cc:257] Missing X server or $DISPLAY
  [pid] ERROR:ui/aura/env.cc:246] The platform failed to initialize.  Exiting.
  ```
  **ในขณะเดียวกัน** การรัน headed login ผ่าน `scripts/start_homelab.py` (Stage 2) **สำเร็จปกติ**
  บนจอเดียวกัน → เป็นการชี้ว่าเป็นปัญหาสภาพแวดล้อมของ "โปรเซส" ไม่ใช่ของเครื่อง
* **การสืบหาต้นตอ (Root Cause Analysis):**
  - เครื่องนี้มี X server และใช้งานได้จริง: `DISPLAY=:0`, มี socket `/tmp/.X11-unix/X0`, `xdpyinfo -display :0` ผ่าน,
    `XDG_SESSION_TYPE=wayland` (มี XWayland), graphical session active บน `tty2`
  - Shell ที่รันสคริปต์มี `DISPLAY=:0` และ `scripts/start_homelab.py` **ตั้ง `os.environ["DISPLAY"]=":0"` เอง** (L373-374)
    ก่อนเรียก `auth_driver.login(...)` จึงสำเร็จ
  - แต่ **โปรเซส MCP server** (playwright-homelab) ถูก launch ในบริบทที่ **ไม่มี `DISPLAY`** → Chromium ที่มัน spawn
    ไม่มี X server ให้ต่อ → ตายทันทีที่ `ozone_platform_x11` (ไม่ใช่ปัญหา selector/DOM)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - "headed" ของ MCP ≠ "headed" ของสคริปต์: ต้องดูว่า **โปรเซสไหน** ถือ `DISPLAY`
  - อาการ `Target page, context or browser has been closed` ที่พ่วงมากับ failure นี้ **หลอกตา** ให้คิดว่า browser ถูกปิด
    ทั้งที่จริงคือ launch ไม่ผ่านตั้งแต่แรก
  - `browser_open` มี fallback ไป Chromium headless ได้ในบางกรณี → อาจได้ผลลัพธ์ที่ไม่ใช่ headed จริง (ห้ามสรุปว่า verified)
  - เดิมมี `trademan_check_session` และ `browser_screenshot` ล้มพร้อมกันหมด — เป็นสัญญาณว่าเป็น env ไม่ใช่ UI
* **วิธีแก้ปัญหาที่พิสูจน์แล้ว / แนวทาง (Proven Working Path & Recommended Fix):**
  - **Workaround ที่ใช้ได้ทันที (พิสูจน์แล้ว):** รัน headed ผ่านสคริปต์/driver ตรง ๆ โดยกำหนด `DISPLAY=:0`
    (เช่น runner ที่ `os.environ["DISPLAY"]=":0"` แล้วเรียก `stage2_verify_krungsri_session()`)
    → สำเร็จ `STAGE2_RESULT=True` ใน 30.4s, ผู้ใช้เห็นหน้าต่าง Chrome จริงบนจอ
  - **Recommended Fix (นอก scope ของงานปัจจุบัน):** export `DISPLAY=:0` (หรือ `XAUTHORITY` ที่ถูกต้อง) ใน launch env
    ของระบบที่สตาร์ท MCP server (systemd unit / สคริปต์/ตัวห่อที่รัน `python -m app.mcp.mcp_server`) แล้ว restart service
  - **ข้อควรระวัง Anti-Mock:** ห้ามตีความ headless fallback ว่าเป็น "headed verified" ต้องมีหลักฐานหน้าจอ + คำยืนยันจากผู้ใช้ (stepwise-approval §5)
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้สั่งให้ทดสอบ Login Stage 2 แบบ **headed browser** เพื่อยืนยันกับสายตาจริง
  - ผู้ใช้ยืนยันเห็นหน้าต่าง Chrome เด้งและล็อกอินจบที่หน้า Portfolio ✅ (ทำให้แยกได้ชัดว่า env ของสคริปต์ดี แต่ env ของ MCP ไม่ดี)
