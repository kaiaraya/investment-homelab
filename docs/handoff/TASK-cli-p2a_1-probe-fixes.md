# TASK-cli-p2a_1-probe-fixes: แก้สคริปต์ probe Account Info ก่อนรันจริง (P2b)

- Created: 2026-10-14 08:00 by Antigravity (review ของ P2a)
- Broker: KSS (TradeMan) เท่านั้น
- Priority: P2a.1 (เล็ก) — **ต้องเสร็จก่อนตลาดเปิด** เพราะ Antigravity จะรัน probe ใน P2b
- Status: DONE (Cline, 2026-10-14 08:08 — F1–F4 fixed, 3/3 unit verifies PASS, probe not run, not committed)

## Context (Antigravity เขียน)
รีวิว `scripts/krungsri/probe_account_info.py` (P2a) แล้วพบ 4 ปัญหา ส่วน pillar2 / handler / driver ของ P2a ผ่านแล้ว **ห้ามแตะ**

| # | ปัญหา | ที่ | ความรุนแรง |
|---|---|---|---|
| F1 | `await page.click("body")` คลิกกลางหน้าจอ อาจโดนปุ่มหรือแถวในตารางพอร์ต ผิดกฎ "คลิกได้แค่ dropdown + chevron" | L148 | สูง |
| F2 | ตัวเลขเงินอาจหลุดลงไฟล์: `_PANEL_JS` เก็บข้อความใน element ล่างสุดเป็น `label` ข้อความเงินอย่าง `123,456.78` จึงกลายเป็น label ได้ แต่ `_redact` จับเฉพาะ `\d{6,}` ที่ติดกัน ตัวเลขที่มี comma คั่นจึงไม่ถูกลบ | `sanitize`, `_redact` | สูง (ผิด D4 ของ P2a) |
| F3 | `selector_path` เป็น `''` ทุกแถว (JS ไม่ได้สร้าง path) ทำให้ probe ไม่ได้คู่ label→selector ซึ่งเป็นเป้าหมายหลัก | `_PANEL_JS` L81-92 | สูง |
| F4 | เช็ก `option.count()` **ก่อน**เปิด dropdown ถ้า option render เฉพาะตอน dropdown เปิด สคริปต์จะไม่เคยสลับบัญชีเลย | L146-153 | กลาง |

## Context map / สิ่งที่ต้องทำ
| # | symbol | ทำ |
|---|---|---|
| F1 | `main()` | ลบ `page.click("body")` แล้วใช้ `await page.keyboard.press("Escape")` แทน (ปิด dropdown โดยไม่คลิก) |
| F2 | `sanitize` (+ helper ใหม่ เช่น `_is_value_like`) | แถวที่ `label` (หลัง strip) เข้าข่ายตัวเลข / ตัวเลขติดลบ / % / มีวงเล็บ เช่น `(1,234.00)` / มี `฿` หรือ `THB` นำหน้าหรือตามหลัง → **ทิ้งแถว** (เป็นค่า ไม่ใช่ label) · `_redact` ให้ลบเลขที่มี comma/จุดด้วย: ตัวเลขยาวตั้งแต่ 4 หลักขึ้นไป หลังตัด `,` ออก → `<num>` (ใช้กับทั้ง label และ selector_path) |
| F3 | `_PANEL_JS` | เพิ่มฟังก์ชัน JS `cssPath(el)`: ไล่ขึ้นไปไม่เกิน 6 ชั้น หยุดเมื่อเจอ `id` (`#id`) · ชั้นอื่นใช้ `tag` + class แรกสูงสุด 2 ตัว (ข้าม class ที่มีตัวเลขหรือ `:`) + `:nth-of-type(n)` เมื่อมี sibling tag เดียวกัน · ใส่ทั้ง `selector_path` (ของ label) และ `value_path` (ของ sibling ถัดไปที่มีข้อความ ถ้ามี) · `sanitize` คืน key `value_path` เพิ่ม (ผ่าน `_redact`) |
| F4 | `main()` loop | ลำดับใหม่: `Escape` → `page.click("#dropDownAccountPort")` → `wait_for_timeout(500)` → หา `option = page.locator(ACCOUNT_OPTION_SELECTOR % acc_no)` → ถ้า `count()` > 0 ให้ `option.first.click()` · ถ้าไม่เจอให้ `Escape` + print เตือน + `_wait_enter("สลับบัญชีเองแล้วกด Enter")` |

## Tests (`tests/test_probe_account_info.py`)
- F2: `sanitize([{label:"123,456.78", ...}])` → `[]`; `"-1,234.50"`, `"12.5%"`, `"(1,000.00)"`, `"฿ 2,000"` → ทิ้ง; label `"Line Available"` อยู่ครบ; `selector_path` ที่มี `12,345` → ได้ `<num>`
- F2 (regression): json.dumps ของผล sanitize ต้องไม่มีตัวเลขยาวตั้งแต่ 4 หลักขึ้นไปหลังตัด comma (assert ด้วย regex)
- F3: `sanitize` คืน key `value_path`; ถ้าไม่มีข้อมูลให้เป็น `""`
- F1/F4 (source guard): source ของ module **ไม่มี** `click("body")` · มี `keyboard.press("Escape")` · ใน source, `click("#dropDownAccountPort")` ต้องมาก่อน `option.count()` (เทียบด้วย `str.index`)
- guard เดิม (ไม่มีการเขียน session, ไม่มี login/order/OTP) ต้องผ่าน

Verify:
- `.venv/bin/python scripts/verify_changes.py scripts/krungsri/probe_account_info.py tests/test_probe_account_info.py`
- ปิดงาน: `--full` **ไม่ต้องรัน** (เปลี่ยนแค่ script + test ที่มี mapping) เว้นแต่ verify ข้างบนแตะไฟล์อื่น

## Scope — ไฟล์ที่อนุญาตให้แก้
- `scripts/krungsri/probe_account_info.py`, `tests/test_probe_account_info.py`
- ส่วน Cline Report ของ handoff นี้

## Out of scope / ห้ามแตะ
- pillar2 / handlers / driver / cards (P2a ผ่านแล้ว)
- `ACCOUNT_INFO_CHEVRON_SELECTOR` (ค่า placeholder ปล่อยไว้ P2b จะแก้)
- ห้ามรัน probe, ห้ามรัน live, ห้ามรีสตาร์ท gateway, ห้าม commit
- ห้ามเพิ่มการคลิกนอกจาก dropdown, option ใน dropdown และ chevron

## Steps (Loop Engineering)
1. F2 + tests → verify
2. F3 + tests → verify
3. F1 + F4 + source guard tests → verify
4. Cline Report

---

## Cline Report (Cline เขียน)
- Files changed:
  - `scripts/krungsri/probe_account_info.py`:
    - F2 — `_ACC_RE` (`\d{6,}`) → `_NUM_RUN_RE` (`\d[\d,]*(?:\.\d+)?`) + `_redact` hides **4+ digits**
      (commas stripped) as `<num>`; new `_is_value_like()` (digit-anchored money/percent/negative/
      parentheses/currency) drops a row whose `label` is really a figure
    - F3 — `_PANEL_JS` gains `cssPath(el)` (≤6 levels, `#id` short-circuit, tag + ≤2 digit/`:`-free
      classes, `:nth-of-type(n)` when needed); each row now carries `selector_path` + `value_path`
    - F1 — `page.click("body")` → `page.keyboard.press("Escape")` (no click at all)
    - F4 — loop order is now `Escape` → `click("#dropDownAccountPort")` → `wait 500` → `locator` →
      `count()` → click, else `Escape` + warn + `_wait_enter("สลับ dropdown …")`
    - docstring `sanitize()` shape + the "only clicks allowed" bullet updated (doc-only consistency)
  - `tests/test_probe_account_info.py` — 6 → 12 tests; `import re`; **one existing assertion had to
    change**: `assert "<redacted>" in blob` → `assert "<num>" in blob` (F2 replaces the token — the old
    one can no longer appear). Not a weakened guard: the zero-digits and `"3024959" not in blob`
    assertions are untouched.
- Summary: every F1–F4 is fixed. A figure can no longer reach the dump as a `label` (dropped) and no
  digit run of 4+ survives anywhere, commas included; the probe now emits a real label→selector mapping
  (`selector_path` + `value_path`), which was the whole point of running it; and it switches accounts by
  opening the dropdown *first* (options only exist while it is open) while never clicking the page body
  — the only clicks left are `#dropDownAccountPort`, an option in it, and the chevron.
- Tests run + result (3 units, verify per unit — all PASS):
  - Unit 1 (F2): `.venv/bin/python scripts/verify_changes.py scripts/krungsri/probe_account_info.py tests/test_probe_account_info.py` → **PASS** (8 passed)
  - Unit 2 (F3): same command → **PASS** (10 passed)
  - Unit 3 (F1+F4): same command → **PASS** (12 passed; `compileall` OK)
  - JS sanity (static, **probe not run**): extracted `_PANEL_JS` and ran `node --check` → **JS SYNTAX OK**
  - `git status`/`stat`: the 2 allowed files are the only ones touched (mtime 08:08). The 3 P2a files
    are untouched (mtime 07:46–07:47, same P2a diff as before).
- Notes from review before starting (both folded in, both covered by a test):
  1. F2 breaks the pre-existing `<redacted>` assertion — updated to `<num>` (see Files changed).
  2. `_is_value_like` is anchored on a digit, so the legitimate label `%MM` is **kept**
     (`test_sanitize_drops_value_like_labels` asserts exactly `["Line Available", "%MM"]`) — a naive
     `"%" in label` check would have silently dropped a target label.
- Open questions:
  - **Stale doc, out of scope (needs a 1-line fix by Antigravity):** `rca/shared/rca_line_cli.md` L127
    (D4 probe row) still says `→ {label, selector_path, value_shape}` · "redacts any 6+ digit run" ·
    "the only clicks are the account option + the chevron" · "tests/test_probe_account_info.py (6 …)".
    Correct now: `{label, selector_path, value_path, value_shape}` · 4+ digit run incl. comma groups →
    `<num>` · clicks = dropdown toggle + an option + the chevron (Escape closes, no body click) ·
    12 tests. `learned_workflows/krungsri/trademan_portfolio_dom.md` L138-142 stays correct as written.
  - `<redacted>` is gone from the probe entirely (single token `<num>`) — the only other uses repo-wide
    are unrelated (`rca_krungsri_trademan.md` PIN, `rca_line_cli.md` SSO `?token=`).
  - `ACCOUNT_INFO_CHEVRON_SELECTOR` untouched (still the P2b placeholder), per scope.
  - Probe was **not** run and nothing was committed, per scope. P2b still owns: run the probe live,
    pin the real Account Info/chevron selectors, then live-test `/cash kss sync`.
  - `test_panel_js_computes_css_paths` greps the JS strings — if P2b rewrites `_PANEL_JS` wording, that
    guard needs the matching update (intentional: it pins the F3 contract).

