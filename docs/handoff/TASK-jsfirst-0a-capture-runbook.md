# TASK-jsfirst-0a-capture-runbook — HAR Capture (Streaming + SBL Realtime + Liberator)

**Status:** READY (รอ human capture) · **Tier:** 🔍 0a probe (Human + Flash 3.8) · **Owner:** Human (+ Flash)
**Parent:** — · **Children:** P.1, P.4, P.5 · **Priority:** HIGH

## Goal
จับ HAR (XHR / Fetch / Form PostBack) ของทุก action บน 3 surface เพื่อเขียน endpoint map → JS snippet library (read ก่อน, order ตามมา)

---

## ก่อนเริ่ม (สำคัญมาก)

- ทำบน browser ที่ล็อกอินอยู่แล้ว — **Session A** = Krungsri SSO (CDP 9333) มี 2 แท็บ: Streaming `[0]` + SBL Realtime `[2]` · **Session B** = Liberator WebTrade (CDP 9334)
- DevTools (F12) → tab **Network** → ติ๊ก **Preserve log** → กด **Clear (⊘)** ก่อนเริ่มแต่ละ session
- **อย่ากรอง filter** — เปิดทุก type (All / Fetch/XHR / Doc / Form) เพราะ SBL ใช้ WebForms PostBack
- หุ้นทดสอบ: **BCPG** (฿~6.8 × 100 ≈ ฿680) · ตั้งราคา passive ให้ค้างไม่ match แล้วยกเลิกท้ายสุด (ไม่เสียเงินจริง)
- PIN: ตอน capture ใช้ PIN จริงของคุณ (KRUNGSRI_PIN / LIBERATOR_PIN) — ระบบจะใส่ให้เองตอนรันจริง

---

## Session A1 — Settrade Streaming (order entry)

**0. สลับ account ไป Margin** (Short/Cover ต้อง Margin): คลิก `div.position-relative.cursor-pointer` (span แสดง `3024952 (Equity)`) → dropdown `ul.p-0.m-0` → คลิก `li:has-text("3024959")`

**1. Quote (read):** ใส่ `BCPG` ใน `input[placeholder="Symbol"]` → รอ quote โหลด → **จับ XHR ราคา bid/offer**

**2. Place BUY (passive — ค้างไม่ match):**
- side = Buy → คลิก `#equity-place-order-buy-radio-button`
- symbol `BCPG`, volume `input[name="equity-place-order-vol"]` = `100`, price `input[name="price-input"]` = **Best Bid − 1 tick** (เช่น bid 6.75 → ใส่ 6.70)
- PIN `#pin` → คลิก `button:has-text("Submit")`
- **จด order number** ที่โผล่ในตารางออเดอร์ → **จับ XHR (POST submit)**

**3. Change (native in-place):** บนแถว order นั้น คลิก Change (`li.css-phnjeo` + ขีดเส้นใต้, scoped ตาม order no) → เปลี่ยน price (เช่น 6.65) → PIN → confirm → **จับ XHR (POST change)**

**4. Cancel:** คลิก Cancel บนแถวเดิม → ยืนยัน → PIN → **จับ XHR (POST cancel)**

**5. (optional ถ้ามี SBL stock)** Place SHORT: คลิก `#equity-place-order-short-radio-button`, price = **Best Offer + 1 tick** → submit → change → cancel (จับ XHR เหมือนข้อ 2–4)

---

## Session A2 — SBL Realtime (แท็บ `[2]` ใน browser เดียวกัน)

**1. เปิด SBL:** ไป `/sblweb/MainSBL.aspx` (หรือ `/th/SBL/start.aspx`)

**2. Read (ไม่มีค่าใช้จ่าย):** จับ XHR ตอนโหลด inventory SET50/100 + ค่า **PP** (regex `PP = ([0-9,.]+)`) + คลิก `#MainCenter_lbXD` ดูตาราง XD/XR

**3. Borrow (minimal — ไม่กี่สตางค์):** เลือกหุ้นที่เห็น `Volume > 0` ในตาราง → fill `#ctl00_MainCenter_txtSymbol` + `#ctl00_MainCenter_txtQty` = `100` → คลิก `#MainCenter_lbBorrow` → **จับ PostBack POST** (`__doPostBack('ctl00$MainCenter$lbBorrow','')`)

**4. Return (คืนทันที):** คลิก `a[id*='RadReturn']` บนแถวที่เพิ่ง borrow → **จับ POST return** → คืนทันทีไม่ค้างข้ามคืน

> ⚠️ borrow สร้าง lot จริง (fee ~3.5%/yr ≈ ไม่กี่สตางค์ถ้าคืนทันที) — **ข้ามข้อ 3–4 ได้** ถ้าไม่อยากแตะเงิน (แต่จะไม่ได้ request ของ submit borrow/return)

---

## Session B — Liberator WebTrade (CDP 9334)

**1. Read:** เปิด Portfolio → **จับ XHR balance/orders**

**2. Place BUY (passive):** footer ticket → toggle `:text('Buy')` → `#SearchSymbolList-setBuySellFooter` = `BCPG`, `#volume` = `100`, `#price` = **Best Bid − 1 tick** → `input#pin` → `#buttonSubmit` → `button:has-text('Confirm')` → **จับ XHR**

**3. Change (in-place):** แก้ราคา order นั้น → **จับ XHR**

**4. Cancel:** ยกเลิก → **จับ XHR**

---

## ส่งออก

- Session A → `data/har/kss_all.har` (Streaming + SBL)
- Session B → `data/har/liberator_all.har`

## Output (Flash/Jules เขียนต่อ)
`docs/handoff/TASK-jsfirst-0a-endpoint-map.md` — ตาราง action → URL/method/payload/response + ช่อง "replayable? (nonce/sign/CSRF?)"
