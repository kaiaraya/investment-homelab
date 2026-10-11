# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: Daily Readiness Orchestration (Shared)
**Component:** `scripts/daily_readiness.py` + `.agents/skills/daily-readiness/SKILL.md`
**Scope:** ชั้น "พิธีกรรมเตรียมความพร้อมรายวัน" ที่ **ใช้ร่วมทุกโบรกเกอร์** (Mobile bridge → Broker sessions → GO/NO-GO)
ไม่ผูกกับโบรกเกอร์ใดโบรกเกอร์หนึ่ง จึงแยกออกจากไฟล์ RCA รายโบรกเกอร์ เพื่อรักษาหลัก **Broker Knowledge Isolation**
**Last Updated:** 2026-10-08
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose)
SSOT ขององค์ความรู้ด้าน **การ orchestrate ความพร้อมรายวัน** (เตรียมสะพาน KDE Connect OTP + session โบรกเกอร์
แล้วตัดสิน GO/NO-GO) บันทึกเฉพาะบั๊ก/edge case ที่เป็นของ "ชั้น orchestration" เท่านั้น
บั๊กที่เกิดจาก DOM/selector/เซสชันของโบรกเกอร์ให้ไปบันทึกใน `rca/krungsri/`, `rca/liberator/`, `rca/click2win/`

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :---: | :---: | :--- | :--- | :---: |
| 2026-10-08 | `READY-RCA-001` | โหมด `--no-login` (report-only) รายงาน **NO-GO ปลอม** — เหตุผล "Krungsri TradeMan ไม่พร้อม (SKIPPED)" ทั้งที่ผู้ใช้ *ตั้งใจ* ข้าม login | verdict ตัดสินจากฟิลด์ `authenticated` (ซึ่งเป็น `None` เมื่อข้าม) แทนที่จะใช้ offline verdict ของ session file | 🟢 FIXED |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `READY-RCA-001`: Report-Only Mode Reported a False NO-GO (Anti-Mock Verdict Bug)
* **วันและเวลา:** 2026-10-08 (~11:03 ระหว่าง VERIFY unit #2)
* **อาการ (Symptom):**
  ```
  $ .venv/bin/python scripts/daily_readiness.py --no-login --json
  ⛔ NO-GO — ยังไม่พร้อม (ต้อง HITL)
     • Krungsri TradeMan ไม่พร้อม (SKIPPED)
  EXIT=1
  ```
  ทั้งที่ผู้ใช้สั่ง `--no-login` = ตั้งใจไม่ login (โหมดตรวจอย่างเดียว) และไฟล์ session ยังไม่ถึงเกณฑ์หมดอายุ
* **การสืบหาต้นตอ (Root Cause Analysis) — 3 จุด:**
  1. **Session & Context Isolation:** ไม่เกี่ยวข้อง (บั๊กอยู่ที่ตรรกะ verdict ล้วน ๆ ไม่ได้เกิดจาก cookie/session ชนกัน)
  2. **DOM & UI Reality:** ไม่เกี่ยวข้อง (โหมด report-only ไม่เปิด browser เลย)
  3. **Data Schema & Types:** **จุดจริง** — `ensure_krungsri()` / `ensure_liberator()` คืน `authenticated = None`
     + `status = "SKIPPED"` เมื่อข้ามโดยเจตนา แต่ตรรกะ verdict เขียนว่า
     `if krungsri.get("authenticated") is not True: reasons.append(...)` → ตีความ `None` เป็นความล้มเหลว
     = **false negative / ขัดหลัก Anti-Mock** (verdict ต้องสะท้อนความจริง ไม่ใช่สะท้อน "เราข้ามเอง")
* **Edge Cases ที่พบ (Edge Cases Identified):**
  * สถานะ `SKIPPED` (ผู้ใช้ข้าม), `BRIDGE_DOWN` (กันไว้ก่อน), `FAILED`/`ERROR` (ลองแล้วไม่สำเร็จ) ให้ผลต่างกัน
    แต่โค้ดเดิมยุบรวมเป็น `authenticated is not True` ทั้งหมด
  * โหมด report-only ต้องใช้ **offline verdict** ของแต่ละโบรกเกอร์ (คนละ semantic — Broker Knowledge Isolation):
    Krungsri = `needs_fresh_login` จาก cookie-storage inspector; Liberator = `exists && !expired` จาก JWT guard
* **วิธีแก้ปัญหาที่พิสูจน์แล้ว (Proven Working Solution):**
  แยกตัวตัดสินต่อโบรกเกอร์ เป็นฟังก์ชันบริสุทธิ์ที่ทดสอบได้ (pure function):
  ```python
  def _krungsri_ready(res: Dict[str, Any]) -> bool:
      st = res.get("status")
      if st == "AUTHENTICATED":
          return True
      if st in ("FAILED", "ERROR", "BRIDGE_DOWN"):
          return False
      if st == "SKIPPED":  # report-only -> ใช้ offline verdict
          return not bool(res.get("needs_fresh_login", True))
      return False

  def _liberator_ready(res: Dict[str, Any]) -> bool:
      st = res.get("status")
      if st == "AUTHENTICATED":
          return True
      if st in ("FAILED", "ERROR", "BRIDGE_DOWN"):
          return False
      if st == "SKIPPED":
          return bool(res.get("exists")) and not bool(res.get("expired", True))
      return False
  ```
  และเรียกใน verdict block:
  ```python
  if not _krungsri_ready(krungsri):
      reasons.append(f"Krungsri TradeMan ไม่พร้อม ({krungsri.get('status')} / verdict={krungsri.get('verdict')})")
  if not args.skip_liberator and not _liberator_ready(liberator):
      reasons.append(f"Liberator ไม่พร้อม ({liberator.get('status')})")
  ```
  **หลักฐานยืนยันผล:** `tests/test_daily_readiness.py` → 16 passed
  (รวม `test_krungsri_ready_matrix`, `test_liberator_ready_matrix`,
  `test_run_report_only_is_go_when_both_sessions_healthy`, `test_run_skips_liberator_when_flagged`)
  และรันจริง:
  ```
  $ .venv/bin/python scripts/daily_readiness.py --no-login --no-ping --json
  "verdict": "NO-GO",
  "reasons": ["Krungsri TradeMan ไม่พร้อม (SKIPPED / verdict=MISSING)"]
  ```
  → ข้อความเหตุผลถูกต้องแล้ว (บอก verdict=MISSING ของไฟล์จริง ไม่ใช่ "เพราะ SKIPPED")
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  * User decision (2026-10-08): **auto re-login ทันทีเมื่อ bridge พร้อม** (ยิง SMS OTP อัตโนมัติผ่าน KDE Connect)
  * กฎที่ต้องคงไว้: ห้ามยิง OTP เมื่อสะพานไม่ live (Invariant 9) → `status=BRIDGE_DOWN` และไม่เรียก `login()`
  * ต่างจาก `scripts/start_homelab.py` Stage 3 ที่ไม่ทำ headed login ให้ Liberator (anti-2FA-SMS policy)
    → daily-readiness ทำ headed login ให้ Liberator **โดยมี gate `is_device_reachable()` + human confirm คั่น**

---

## 🧩 Operational Notes (ไม่ใช่บั๊กของโค้ด)

* **Shell output capture flaky:** ระหว่างพัฒนา คำสั่งที่รันพร้อมกันในเทอร์มิเนลเดียวกันผ่าน tool runner
  อาจไม่คืน output (shell integration ไม่รายงาน completion) → วิธีที่เชื่อถือได้: รันทีละคำสั่ง
  แล้ว redirect ไปไฟล์ (`> /tmp/x.txt`) แล้วอ่านไฟล์
* **สถานะจริงของ environment (2026-10-08):** `data/session_state.json` (Krungsri) **ไม่มี** → verdict `MISSING`
  ต้อง fresh login + SMS OTP จริง (`data/liberator_session.json` ยัง valid ~6234s)
