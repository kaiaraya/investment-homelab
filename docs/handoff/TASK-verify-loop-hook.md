# TASK-verify-loop-hook: Verify Hook ต่อ unit (`scripts/verify_changes.py`) + rule §3

- Created: 2026-10-08 by Cline (Act mode) — ต่อจากคำสั่งผู้ใช้ในแชท:
  _"ผมเคยบอกแล้ว ว่าไม่ควรใช้เวลา และ token เยอะในแต่ละรอบ — ทำเป็น hook ดีไหม?"_ → ผู้ใช้ยืนยันว่า
  หมายถึง **rules / hook / skill / workflow ของ Cline**
- Broker: N/A (infra / Loop Engineering — ไม่แตะ broker logic)
- Status: DONE (ยกเว้น full-suite gate ที่ติด suite hang — ดู Open questions)

## Context

**Symptom (process ไม่ใช่ product):** งาน Gate C/D (2026-10-08) ใช้เวลา/token ต่อ loop สูงผิดปกติ เพราะ
1. รัน full suite **3 รอบ** ในงานเดียว
2. รัน bundle 11 ไฟล์ทุก loop แทนที่จะรันเฉพาะ test ที่แมปกับ unit
3. รัน pytest 2 ตัวพร้อมกัน → `test_homelab.db` (SQLite ตัวเดียว) เกิด lock/deadlock + ค้าง 20+ นาที

**Root cause:** ไม่มี entrypoint เดียวสำหรับ "verify 1 unit" → agent ต้องตัดสินใจเองทุก loop
ว่า test ตัวไหนเกี่ยวข้อง → มีแนวโน้มเลือก "รันเยอะไว้ก่อน" (Big-Bang verify)

**Solution (user-approved):** rule + hook ตาม `.agents/rules/loop_engineering.md` §3 —
**"หนึ่ง unit = หนึ่งคำสั่ง verify"** ผ่าน `scripts/verify_changes.py`
(compileall + เฉพาะ test ที่แมป + pytest single-writer gate + `--full` ครั้งเดียวตอนปิดงาน)

## Scope — ไฟล์ที่อนุญาตให้แก้
- `scripts/verify_changes.py` (ไฟล์ใหม่)
- `tests/test_verify_changes.py` (ไฟล์ใหม่)
- `.agents/rules/loop_engineering.md` (§3 + Cross-references)
- `AGENTS.md` (Project §Tests → verify hook)
- handoff นี้

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify | Status |
|---|----------------------------|------------------|--------|--------|
| 1 | สร้าง `scripts/verify_changes.py`: `MODULE_TEST_MAP` + `resolve_tests()` + `compile_changed()` + `_pytest_already_running()` guard + `main()` (exit 0/1/2) | 1 คำสั่ง verify 1 unit จบด้วย exit code | `py_compile` + `--dry-run` 3 เคส | ✅ |
| 2 | `--dry-run` ต้องไม่ถูก guard กั้น (ตรวจแผนได้แม้มี pytest รันอยู่) | dry-run ทำงานตอน suite รันอยู่ | CASE A/B พิมพ์แผนได้, exit 0 | ✅ |
| 3 | UNMAPPED / docs-only ต้องไม่แตะ guard (ไม่เดา test) | unmapped → 2, docs → 0 | CASE C + unit test | ✅ |
| 4 | เขียน `tests/test_verify_changes.py` (pure — ไม่มี browser/DB/subprocess) | 17 tests ครอบ mapping/exit-code/guard | `scripts/verify_changes.py scripts/verify_changes.py tests/test_verify_changes.py` → **17 passed** | ✅ |
| 5 | แก้ `.agents/rules/loop_engineering.md` §3: บังคับ hook, ห้าม full suite ต่อ loop, single-writer, UNMAPPED ห้ามเดา | rule ไม่ขัดกับสคริปต์จริง | อ่านเทียบโค้ด (Zero-Contradiction) | ✅ |
| 6 | `AGENTS.md`: ชี้ hook ที่ Project §Tests + Cross-references | agent หาเจอเองโดยไม่ต้องถาม | อ่านเทียบโค้ด | ✅ |
| 7 | ดึงผล full suite (final gate) | pass/fail จริง | `scripts/verify_changes.py --full` | ⚠️ suite ค้างก่อนจบ (ดู Open questions #1) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py scripts/verify_changes.py tests/test_verify_changes.py` → exit `0`
- `.venv/bin/python scripts/verify_changes.py --dry-run app/services/line_service.py` → พิมพ์ targeted tests (ไม่รัน)

## Out of scope / ห้ามแตะ
- Order placement / tick size / price-volume validation
- ไม่แก้ test เดิม และไม่แก้ fixture ใน `tests/conftest.py`

---

## Cline Report (2026-10-08, Act mode)

### Files changed (path เต็ม)

**ไฟล์ใหม่**
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/verify_changes.py`
  — verify hook: `MODULE_TEST_MAP` (module → targeted tests, **SSOT เดียว**), `resolve_tests()`,
  `compile_changed()`, `_py_files()`, `_pytest_already_running()`, `_guard_blocked()`, `main()`
  (exit `0`=PASS · `1`=FAIL · `2`=BLOCKED/UNMAPPED/usage)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_verify_changes.py` — 17 unit tests (pure: ไม่เปิด browser/DB/subprocess)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-verify-loop-hook.md` — handoff นี้

**แก้ไข**
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/rules/loop_engineering.md`
  — §3 Verification Rules เขียนใหม่ (บังคับ hook · ห้าม full suite ต่อ loop · pytest single-writer · UNMAPPED ห้ามเดา) + Cross-references +1 บรรทัด
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/AGENTS.md` — Project §Tests → เพิ่ม verify hook + 2 ข้อห้าม (แทนบรรทัด `Tests:` เดิม)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/skills/loop-engineer/SKILL.md`
  — ข้อ 3 (VERIFY) ชี้คำสั่ง hook ตรง ๆ (`verify_changes.py` → exit 0 = PASS; `--full` ครั้งเดียวตอนปิดงาน)

### Summary
1. **"หนึ่ง unit = หนึ่งคำสั่ง verify"** — `scripts/verify_changes.py <ไฟล์ที่แก้>` = `compileall` ไฟล์ที่แก้
   + รัน **เฉพาะ** test ที่แมปกับไฟล์นั้น แล้วจบด้วย exit code → agent ไมต้องตัดสินใจเองทุก loop
2. **Single-writer gate ในตัวสคริปต์** — สแกน `/proc/*/cmdline` ถ้าเจอ pytest อื่นรันอยู่ → `BLOCKED` (exit 2)
   กัน SQLite deadlock ช้ำ (ต้นเหตุจริงที่ทำให้งานก่อนค้าง 20+ นาที)
3. **Anti-Mock ในตัว hook** — ไฟล์ `.py` ที่ไม่มี mapping → `UNMAPPED` (exit 2) **ไม่เดา test** ;
   ไฟล์ docs → `report-only` (ไม่มี test, verify = อ่านเทียบโค้ด) ; `drift guard`: test ที่แมปทุกตัวต้องมีอยู่จริงบนดิสก์
4. **`--dry-run` ไม่ถูก gate** — ตรวจแผนได้แม้มี pytest รันอยู่ (ถูกที่สุด: 0 วินาที)
5. **rule + AGENTS.md** ชี้ hook → ทั้ง Antigravity และ Cline เห็นกฎเดียวกันโดยไม่ต้องถาม

### Tests run + result
```bash
# syntax
.venv/bin/python -m py_compile scripts/verify_changes.py tests/test_verify_changes.py      # OK

# hook ตรวจ unit ตัวเอง (end-to-end proof)
.venv/bin/python scripts/verify_changes.py scripts/verify_changes.py tests/test_verify_changes.py \
    .agents/rules/loop_engineering.md AGENTS.md
#   → compileall: OK · 17 passed in 6.47s · PASS (targeted) in 11.5s · exit 0

# dry-run กับไฟล์จริงของงาน Gate C/D
.venv/bin/python scripts/verify_changes.py --dry-run app/services/otp_relay_registry.py \
    app/services/line_service.py app/schemas/auth.py app/browser/auth_driver.py \
    app/brokers/liberator/driver.py AGENTS.md docs/handoff/TASK-otp-channel-authoritative.md
#   → 11 targeted tests + compileall 5 ไฟล์ + report-only 2 · exit 0

# ไฟล์นอก mapping
.venv/bin/python scripts/verify_changes.py app/core/config.py                              # → UNMAPPED, exit 2
```
**เทียบต้นทุนต่อ loop:** เดิม = full suite (ค้าง ไม่จบ) + bundle 11 ไฟล์ ≈ 45–60s · ใหม่ = **11.5s** และได้ exit code เดียว

### Open questions / สิ่งที่ไม่แน่ใจ
1. **full suite ของ repo ค้างก่อนจบ (~87%) — ยังไม่ถูกแก้ (นอก scope ของ task นี้)** หลักฐาน:
   - run #1 (pid 44608) ค้าง 20+ นาที → ต้อง kill ; run #2 (`--full`, pid 47742) ค้างจุดเดิม
   - `--collect-only -q` = 335 tests (ตอนรัน = 320 ก่อนมี test ใหม่) ; ค้างหลัง dot #279 (279/320 = 87%)
   - dot #280 ในลำดับ collection = `tests/test_time_warp_scenarios.py::test_scenario_1_normal`
     **แต่** รันไฟล์นั้นเดี่ยว ๆ = `6 passed in 2.84s` → **ไม่ใช่ test เดี่ยวที่ช้า แต่เป็น order-dependent / state leakage**
   - **วินิจฉัยแล้ว** ด้วย `-o faulthandler_timeout=90` (built-in; venv ไม่มี pytest-timeout plugin) → `/tmp/vc_hang.log`:
     - `Timeout (0:01:30)!` ยิงหลัง dot #279 (87%) → **main thread ว่างอยู่ใน event loop**
       (`selectors.select` ← `asyncio.run_until_complete` ← `pytest_asyncio/plugin.py:905`)
       ขณะที่ **4 thread ค้างที่ `aiosqlite/core.py:59` (`_connection_worker_thread`)**
     - → **ไม่ใช่ test เดี่ยวที่ช้า แต่เป็น SQLite lock / await-deadlock บน `test_homelab.db` ตัวกลาง**
       (state สะสมข้าม test — ไฟล์ที่ค้างผ่านเดี่ยว 2.84s) ยืนยันซ้ำได้ 2/2 run ที่จุดเดียวกัน
     - **ยังไม่แก้ (นอก scope)** แนวทางที่ควรทำต่อ: per-test DB isolation / ปิด connection ใน fixture /
       `PRAGMA busy_timeout` + ใส่ `faulthandler_timeout = 90` ใน `[tool.pytest.ini_options]`
       (`pyproject.toml:18-21`) เพื่อให้คราวหน้าค้างแล้วรายงานตัวเองแทนค้างเงียบ
     - ต้นทุนที่เสียไปก่อนหน้านี้ (ค้าง 20+ นาที × 2) เกิดจากข้อนี้ — ไม่ใช่จาก hook/rule ที่เพิ่งทำ
   - **run #3 (2026-10-09, `--full`, pid 71787)** — ค้างจุดเดิมซ้ำอีกครั้ง: ผ่าน 80% แล้วได้อีก 11 dots
     (dot #291/347 ≈ 83%) แล้วหยุดนิ่ง **561.9s** → `kill -9` (exit `-9`)
     · หลักฐาน ณ ตอนค้าง: fd เปิดค้างบน `test_homelab.db` (2 descriptors) + `wchan = ep_poll`
     (async event loop รอ ไม่มี CPU burn) → ยืนยัน diagnosis เดิมว่าเป็น **SQLite lock / await-deadlock บน `test_homelab.db`**
     ไม่ใช่ test เดี่ยวที่ช้า · ระหว่างทาง targeted mode (`verify_changes.py <files>`) ทำงานปกติ (PASS, exit 0)
2. **`MODULE_TEST_MAP` ยังเป็น manual** — ไฟล์ใหม่ที่ยังไม่มี mapping จะได้ `UNMAPPED` (ตั้งใจ: กันเดา)
   แต่ต้องมีวินัยเพิ่มบรรทัดในสคริปต์เมื่อแตะ module ใหม่
3. **ยังไม่ verified แบบ live ในงานนี้**: `scripts/verify_changes.py --full` จะจบจริงได้ต่อเมื่อแก้ hang ข้อ 1
4. **D2 ของ `TASK-otp-channel-authoritative.md` ยังค้าง** — ต้องรอผู้ใช้พิมพ์ OTP 6 หลัก (ไม่ mock)

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
