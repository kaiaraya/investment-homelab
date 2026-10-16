# Loop Board — Loop <N>

> **แทน Kanban** (ปลดระวาง cline-kanban แล้ว) · เจ้าของบอร์ด: **Argon** (Antigravity)
> 1 board = 1 loop · ทั้ง 3 app (Argon · Antigravity IDE/Flash · Cline plugin) ชี้ **folder เดียวกัน**
> รายละเอียดงานต่อใบ → `docs/handoff/TASK-<slug>.md` (ตัวกลางเดียวของ loop)

- **Loop:** 2
- **Opened:** 2026-10-16
- **Closed:** —
- **Directive:** `directive/master_directive_v2.md` · **Scorecard:** `directive/loop_acceptance_and_tasks.md`

## วิธีใช้
- **Argon** = เจ้าของบอร์ด: ย้ายการ์ดระหว่างคอลัมน์ + เพิ่ม/ลบการ์ด (ดูใน Antigravity)
- **Cline / Flash** = อัปเดตแค่ `Status` ใน handoff md ของตัวเอง → Argon sync ลง board (ไม่ต้องแก้ board ตรงๆ)
- **Human** = gate: อ่านแผน → flip `Status` (gate #1) · squash `task/<slug>` → `main` (gate #2)
- ปิด loop → archive ไฟล์นี้เป็น `docs/board/archive/LOOP-<N>.md` แล้ว reset สำหรับ loop ถัดไป

---

## 🔴 1. Backlog (Argon)
| # | Task | Tier | Owner | Status | Handoff |
|---|------|------|-------|--------|---------|
| 1 | `<slug>` | 🟢T0 | Cline | DRAFT | `docs/handoff/TASK-<slug>.md` |

> หมายเหตุ Loop 2: `loop-redesign-local-handoff` = งาน bootstrap ของ SOP นี้ (ดูคอลัมน์ 4)

## 🟡 2. Ready / Planning (Argon — รอ gate #1)
| # | Task | Tier | Owner | Status | Handoff |
|---|------|------|-------|--------|---------|
| — | — | — | — | — | — |

## 🔵 3. In Progress (Cline T0/T1 · Flash T2)
| # | Task | Tier | Owner | Status | Handoff |
|---|------|------|-------|--------|---------|
| — | — | — | — | — | — |

## 🟢 4. Review / Approval (Flash verify + human witness)
| # | Task | Tier | Owner | Status | Handoff |
|---|------|------|-------|--------|---------|
| 1 | `loop-redesign-local-handoff` | 🟢T0 | Cline | REVIEW | `docs/handoff/TASK-loop-redesign-local-handoff.md` |

## ⚪ 5. Done (human merge แล้ว)
| # | Task | Tier | Owner | Status | Handoff |
|---|------|------|-------|--------|---------|
| — | — | — | — | — | — |

---

## Legend

**Tier (ใครทำ):**
- 🟢 **T0** — code / docs / unit test / headless scrape (ไม่แตะ order/OTP/account) → **Cline plugin** (Act=DeepSeek Flash)
- 🟡 **T1** — logic ที่ไม่แตะ order / OTP / tick size → **Cline plugin** (Plan=DeepSeek Pro · Act=DeepSeek Flash) + diff audit
- 🔴 **T2** — order · OTP · account switch · SBL · live login · live browser · merge `main` → **Antigravity IDE (Flash 3.8)** + human witness

**Status (ใน handoff md):** `DRAFT → READY → IN_PROGRESS → REVIEW → DONE` (↩ `CHANGES_REQUESTED`)

**Owner:** Cline (T0/T1) · Flash (T2/HITL) · Argon (plan + analysis)

**Gate:** gate #1 = human อนุมัติแผน · gate #2 = human merge `main` (T2 ต้องมี witness ตอน STEP 3)
