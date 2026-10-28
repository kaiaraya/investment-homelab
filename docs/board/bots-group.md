# Bots Group — Homelab War Room

> เป้าหมายร่วมของทุกบอท = **Kanban board `investment-homelab` ใบเดียว** (Single Source of Truth)
> กลไกสองชั้น: **Kanban dispatcher** ทำงานหนัก (เขียน/รัน/review) · **Group Chat** เป็นห้อง steering + จุดที่มนุษย์ตัดสินใจ

สร้างเมื่อ 2026-10-27 · profile: default · board: `investment-homelab`

---

## 1. แนวคิดหลัก

| กลไก | Kanban dispatcher | Group Chat (War Room) |
|---|---|---|
| ธรรมชาติ | worker แยกเดี่ยว อ่านแค่ body การ์ดตัวเอง | คุยกัน 3 รอบ/ครั้ง, 10 msg/ครั้ง, เห็น transcript ร่วม |
| เหมาะกับ | เขียนโค้ด / รัน test / review diff (งานหนัก) | ตัดสินใจ / ถาม-ตอบ / แจ้งสถานะ / เสนอแผน |
| ความคงทน | การ์ดอยู่รอด restart | transcript อยู่ แต่เป็น "บทสนทนา" |

**กติกาข้อเดียว:** โค้ดทุกบรรทัดยังเขียน/รันผ่าน Kanban เหมือนเดิม → Group Chat คือห้อง steering ที่ทุกบอทมาโผล่หน้าให้มนุษย์เห็น คุยกัน โชว์ความคืบหน้า ยกเรื่องสำคัญมาให้มนุษย์ตัดสิน ทั้งคู่ชี้ไปที่ board เดียวกัน

## 2. Roster (4 bot + มนุษย์)

| สมาชิก | โปรไฟล์ | บทบาท | Model |
|---|---|---|---|
| 🤖 `@hermes` | `default` | **Architect** — สลายงานเป็นการ์ด, ดูแล board, เสนอ loop/แผนปรับปรุง | gemini-4-argon (planning lane) |
| 🤖 `@builder` | `homelab-build` | **Code Execution** — แก้ repo, targeted test, `## Worker Report` | gemini-3.8-flash (T0) / 3.1-pro (T1) |
| 🤖 `@reviewer` | `homelab-review` | **Review + HITL** — audit diff, `verify_changes.py`, ตอบคำถาม, ชี้จุดให้มนุษย์ชี้ขาด | gemini-3.1-pro |
| 🤖 `@watcher` | `homelab-watcher` | **เวลา + Token** — อ่าน state.db + kanban.db, alert threshold (read-only) | gemini-3.8-flash |
| 🧑 `@user` | มนุษย์ | **ตัดสินใจเรื่องสำคัญจริง ๆ** — T2 witness, OTP, live money, merge main | — |

## 3. Scope of Works (ใครทำ / ห้ามทำ)

| Bot | รับผิดชอบ | ห้ามเด็ดขาด |
|---|---|---|
| `@builder` | แก้ไฟล์ตามการ์ด, targeted test, ไม่ commit (มนุษย์ squash) | full suite, แก้ `DRY_RUN_MODE`/`TRADING_MODE`, สร้าง/แก้/ยกเลิกออเดอร์จริง |
| `@reviewer` | diff + `verify_changes.py`, อนุมัติ/reject, ตอบคำถาม, ชี้จุด HITL | merge main, แก้โค้ดเอง (สั่งกลับ), แตะ broker/live screen |
| `@watcher` | อ่าน token/time จาก state.db + kanban.db, เตือน threshold | แก้โค้ด, เปลี่ยนสถานะการ์ด (ได้แค่ comment) |
| `@architect` | decompose งาน, สร้าง/ลิงก์/ปิดการ์ด, judge done, เสนอแผน | witness, รัน live path |
| มนุษย์ | เงิน/สิทธิ์/OTP/witness/live order/merge | — (กติกาเดียวที่ทุกบอทฟัง) |

## 4. ทำงานร่วมกัน (วงจร)

```
@architect สลายเป้าหมาย → สร้างการ์ดบน board (tier/model/parents)
        ↓ dispatcher spawn
@builder ลงมือ → ## Worker Report → kanban_request_review
        ↓ review_dispatch (อัตโนมัติ)
@reviewer audit → ผ่าน(done) / สั่งแก้(request_changes) / ยกให้ @user
        ↓ ระหว่างทาง
@watcher (cron 9:00,16:00) โพสต์รายงาน token/time + เตือน threshold
        ↓ ทุก loop
@architect อ่าน board + ข้อมูล watcher → เสนอ loop/ปรับปรุงถัดไป
        ↓
มนุษย์ (@user) ตัดสินจุดสำคัญในห้อง — badge "needs you"
```

ทุกบอทโพสต์**เฉพาะสรุป**เข้าห้อง ไม่โพสต์โค้ด/ล็อกเต็ม (โค้ดอยู่ในการ์ด, session_logs อยู่ใน repo)

## 5. Handoff งานกันอย่างไร

**A. Machine handoff (durable) — ผ่าน board:**
- builder → reviewer: `kanban_request_review` + `## Worker Report`
- reviewer → builder: `kanban_request_changes` + `## Review Report` (ระบุต้องแก้อะไร)
- ทุก handoff ฝังใน body การ์ด → worker ถัดไปอ่านได้แม้ไม่เคยคุยกัน

**B. Human-facing handoff (มองเห็น) — ผ่านห้อง:**
- bot ส่งงานต่อ: `@builder ช่วยดู X ต่อจากนี้…`
- bot ยกเรื่องให้มนุษย์: `@user …` → ห้องติด badge **needs you**
- bot ไม่มีอะไรพูด: ส่ง `[SILENT]` (เงียบ)

กฎเหล็ก: หนึ่งการ์ด = หนึ่งงาน; body ต้อง self-contained (`goal · files · verify · done-when · tier`) เพราะ worker อ่านแค่ body ไม่เห็นบทสนทนา

## 6. Kanban board เดียวกัน (สิทธิ์)

| Bot | สิทธิ์บน board |
|---|---|
| `@architect` | `create / link / list / complete` (เต็ม) |
| `@builder` | `show / complete / request_review / comment` |
| `@reviewer` | `request_changes / request_review / comment` |
| `@watcher` | `list / comment` (อ่านอย่างเดียว) |
| มนุษย์ | ทุกอย่าง + unblock / witness / approve |

## 7. สิ่งที่สร้างแล้ว (2026-10-27)

| รายการ | สถานะ |
|---|---|
| `homelab-watcher` profile (clone จาก homelab-build, gemini-3.8-flash) | ✅ |
| `SOUL.md` ของ builder / reviewer / watcher (บทบาท + กติกา) | ✅ |
| `ui_meta: {hermes-bots: {}}` marker ทั้ง 3 bot profile (เปิด bot-mode messaging) | ✅ |
| script `~/.hermes/profiles/homelab-watcher/scripts/homelab_watch.py` (token+time, read-only) | ✅ |
| cron `[bot:homelab-watcher] token + time watch` — `0 9,16 * * *`, no-agent | ✅ |
| Group Chat "Homelab War Room" | ⏳ รอสร้างใน desktop (ไม่มี CLI) |
| cron deliver → bot-chat (โพสต์เข้ากลุ่ม) | ⏳ หลังสร้างห้อง |

### watcher threshold (แก้ใน script)
- การ์ด `running` > 2 ชม. → alert
- การ์ด `blocked` > 24 ชม. → alert
- การ์ด `triage` ค้าง > 48 ชม. → alert
- (เพิ่มเกณฑ์ token spike >3x ได้ในอนาคต)

## 8. ขั้นตอนที่เหลือ (ทำใน desktop ~2 นาที)

1. เปิด **Bots tab** ใน Hermes Desktop
2. กด **+** → **New Group Chat**
3. ชื่อ: `Homelab War Room` (ใส่รูปก็ได้)
4. เลือกสมาชิก 4 ตัว: `hermes` (default), `homelab-build`, `homelab-review`, `homelab-watcher`
5. สร้าง → เปิดห้อง → วาง "กติกาห้อง" ด้านล่างเป็นข้อความแรก (แล้ว pin)

### กติกาห้อง (วางเป็นข้อความแรก)

```
🏗️ Homelab War Room — กติกา

เป้าหมายร่วม: Kanban board `investment-homelab` คือ Single Source of Truth — ทุกงานจบที่การ์ด

สมาชิก: @hermes=architect(สลายงาน/ดูแล board/เสนอแผน) · @builder=เขียนโค้ด+test ผ่านการ์ด ·
@reviewer=audit+HITL gate · @watcher=token/time รายวัน (read-only)

1. โค้ดเขียน/รันผ่าน Kanban เท่านั้น — ห้องนี้เอาไว้ steering/ตัดสินใจ ไม่ใช่รันงานยาว
2. ส่งงานต่อ: @mention · ยกเรื่องให้คน: @user · ไม่มีอะไรพูด: [SILENT]
3. เงิน/สิทธิ์/OTP/live order/merge main = มนุษย์ตัดสินเท่านั้น bot ไม่มีสิทธิ์
4. ทุก handoff เขียนลง body การ์ด (goal·files·verify·done-when) — worker อ่านแค่ body
```

## 9. Follow-up หลังสร้างห้อง

```bash
# 1. เปลี่ยน deliver ของ watcher cron ให้โพสต์เข้า bot chat (แล้ว room จะดึงขึ้นเอง)
hermes -p homelab-watcher cron list            # ดู job id
hermes -p homelab-watcher cron edit <id> --deliver bot-chat:homelab-watcher

# 2. ทดลอง @watcher ในห้อง → ควรตอบด้วยรายงาน token/time ล่าสุด
```

## 10. ข้อควรระวัง (บทเรียนที่บันทึกไว้)

1. **อย่าให้บอทคุยเรื่องเงินแทน witness** — การ unblock การ์ด T2 = re-dispatch worker headless; การอนุมัติต้องมาจากมนุษย์อยู่หน้าเครื่องเท่านั้น
2. **Group มี cap 3 รอบ/ครั้ง** — งานโค้ดที่ใช้เวลานานต้องไปใน Kanban ไม่งั้นห้องค้าง
3. **อย่ารัน full suite** — builder/routine review ต้อง targeted เท่านั้น
4. `message_agent` ต้องมี `ui_meta: {hermes-bots: {}}` (ทำแล้ว) + canonical "Bot Chat" (desktop สร้างให้ตอนใช้กลุ่ม)
