# TASK-loop2-0 — Directive: ปลด Pillar 4 (SBL manual assist)

**Status:** READY · **Tier:** 🟡 T1 (code/doc-only) · **Model:** Jules 3.1 Pro · **Owner:** Cline (triage)
**Parent:** — (parent-less) · **Children:** 2.4, 2.5

## Goal

แก้ `directive/master_directive_v2.md` เพื่อปลด Pillar 4 (SBL Intelligence) จากสถานะ "Dormant" เป็น
"SBL manual assist ผ่าน LINE CLI" — อ่านอย่างเดียวทันที, `/borrow` `/return` เป็น T2 witness-gated

## Why

แผน Loop 2 เปิดคำสั่ง SBL (`/sbl /borrow /return`) แต่ directive §3 บรรทัด 78 ยังระบุ `pillar4_sbl.py`,
`sbl_intelligence_service.py` = **Dormant** ("ผู้ใช้จัดการยืม-คืนเองไปก่อน") — ขัดกันโดยตรง ต้องปลดก่อน
การ์ด 2.4/2.5 จะผ่าน gate

## Scope (แคบ)

เฉพาะ directive §3 ตาราง "โมดูลที่ปิด" แถว 3 (SBL) — เปลี่ยนสถานะและข้อความให้ตรงกับแผนนี้
**ห้าม** แตะส่วนอื่นของ directive (Phase B scope, Pillar 1–3, Invariants ยังคงเดิม)

## ข้อความใหม่ (ร่าง)

- Pillar 4 SBL → **เปิดเฉพาะ SBL manual assist ผ่าน LINE CLI**: `/sbl` `/sbl sync` `/sbl pool` = read-only
  (อ่าน `sbl_borrow_lots` + CDP inventory), `/borrow` `/return` = live account + PIN = **T2** ต้อง witness
  ก่อนนับว่า done
- ย้ำว่า SBL **ไม่** auto (ไม่มี JIT borrow อัตโนมัติ, ไม่มี scheduler) — ผู้ใช้สั่งผ่าน LINE เองทุกครั้ง
- อ้างอิงการ์ด: `TASK-loop2-line-ux-sbl-plan.md`

## Files

- `directive/master_directive_v2.md` (เฉพาะ §3 แถว SBL)

## Verify

- `grep -n "Dormant\|pillar4_sbl\|sbl_intelligence" directive/master_directive_v2.md` → ไม่เหลือข้อความ
  "ผู้ใช้จัดการยืม-คืนเองไปก่อน" ที่ขัดกับแผน
- doc-only: ไม่มี code change → ไม่ต้อง pytest (แต่ `python -c "import app.main"` ยังผ่านเพื่อยืนยันไม่มี
  side effect)

## Done when

directive §3 ปลด SBL แล้ว ระบุ read-only + borrow/return=T2 ชัดเจน และไม่มีข้อความขัดแย้งหลงเหลือ
