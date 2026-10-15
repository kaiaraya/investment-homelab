# RCA — Cline Kanban Hub Daemon (card start / session lifecycle)

> RCA ของ **เครื่องมือ `kanban` (Cline) เอง** — ไม่ผูกกับโบรกเกอร์ ไม่ผูกกับ gateway
> (โบรกเกอร์มี RCA แยกตาม `broker_pdca_rca.md` §1)
> เริ่มใช้: **2026-10-15** (เกิดจากการที่การ์ด Kanban start ไม่ได้ทั้งวัน + session ถูก `cancel` กลางเทิร์น)

อ้างอิงภายนอก: `cline/kanban#495`, `cline/kanban#590` (ทั้งคู่ยัง **open**)

---

## KB-RCA-001 (2026-10-15) — การ์ด start ไม่ได้ / session ถูก `cancel`-`interrupted` กลางเทิร์น เพราะ hub daemon spawn ไม่ขึ้น

**Symptom**

1. `kanban task start --task-id <id>` จาก terminal ของ agent: **ค้าง ~30 วิ** แล้วล้ม (บางรอบคืน `Command
   failed: Command timed out after 30000ms`) — ในเว็บ UI ขึ้น *"Task failed to start"*
2. ถ้า start ผ่าน: session ถูกตัดกลางเทิร์นที่ ~38 วิ และ ~49 วิ (ผู้ช่วยเพิ่ง emit `thinking` + 3 ×
   `tool_use`) · การ์ดถูกย้ายเข้า `trash` · transcript เขียน `"status": "cancelled"`,
   `"exit_code": 0`, `"interactive": true`, `totalCost: 0`, `pid: null`
3. `~/.cline/data/logs/hub-daemon.log` = crash loop `MODULE_NOT_FOUND` (นับได้ 8 ครั้ง)

```
Error: Cannot find module '<npm-global>/node_modules/kanban/dist/entry.js'
    at Module._resolveFilename (node:internal/modules/cjs/loader:1564:15)
    ...
    at Module.executeUserEntryPoint [as runMain] (node:internal/modules/run_main:154:5)
  code: 'MODULE_NOT_FOUND',
  requireStack: []
```

**Root Cause Analysis (3 จุด)**

1. **Session & Context**: ไม่ใช่ session ของเราและไม่ใช่ concurrency — เกิดตอนที่ kanban **spawn hub
   daemon ใหม่** (การ์ดใหม่/การ์ดที่ไม่มี daemon ค้างอยู่) · daemon ที่ยังรันอยู่ก่อนหน้าไม่กระทบ
   (`kanban task list` ยังทำงานปกติ) ⇒ อาการจึงดูเหมือน "flaky": บางรอบผ่านเพราะไปเกาะ daemon เก่าได้
2. **DOM & Live Reality (ของจริงอยู่ที่ filesystem/process ไม่ใช่ UI)**: `dist/cli.js` spawn
   `node <pkg>/dist/entry.js` (path sibling ของตัวเอง) แต่ tarball ที่ publish **ไม่มีไฟล์นี้** —
   `dist/` มีแค่ `cli.js`, `index.js`, `*.map`, `web-ui/` · เช็คทุกเวอร์ชัน `0.1.40 → 0.1.70`
   = ไม่มี `dist/entry.js` เลย → **downgrade ไม่ช่วย** · ตัวไฟล์จริงมีอยู่ แต่ซ้อนอยู่ที่
   `node_modules/kanban/node_modules/@clinebot/core/dist/hub/daemon/entry.js` (654 KB,
   resolve ได้ผ่าน `@clinebot/core/hub/daemon-entry`)
3. **Data Schema & Types (bug ที่สองทับซ้อน)**: แม้ใส่ `dist/entry.js` ให้แล้ว daemon ยังตายด้วย
   `ReferenceError: AI is not defined` — บันเดิล core อ้าง global `AI` (Vercel AI SDK namespace) ตอน
   module-evaluation (`C(L,AI)`), ไม่มี `var/let/const AI`, ไม่มี import binding, และ
   `grep -c 'globalThis.AI'` ในไฟล์ = **0** ⇒ bundler ไม่ได้ emit namespace นั้นออกมา
   ⚠️ `export * from "@clinebot/core/hub/daemon-entry"` **ไม่พอ** เพราะ static import ถูก hoist
   ไปประเมิน **ก่อน** body ของ shim → global ยังไม่ถูก set

**Edge Cases ที่พบ**

- **ตัวเลข/schema ของ broker ไม่เกี่ยวเลย** — bug อยู่ที่ packaging ของเครื่องมือ (ไม่เกี่ยวกับออเดอร์
  ราคา OTP หรือข้อมูลการเงิน) ⇒ ไม่ต้องทำ 3-point RCA ฝั่งโบรกเกอร์
- **transcript ของ session ไม่มี error** (มีแค่ warning ของ AI SDK) — หลักฐานเดียวอยู่ใน
  `hub-daemon.log` ⇒ เดิมสรุปผิดว่า "ruled out: hub-daemon" เพราะไปมองแต่ transcript
- **การ์ดที่ถูกย้ายเข้า `trash` start ซ้ำไม่ได้** (`is in trash and can only be started from backlog or
  in_progress`) → ต้อง `kanban task delete` แล้ว `kanban task create` ใหม่ (id เปลี่ยน)
- **`pgrep -f 'kanban task start'` เป็น false negative** — process จริงคือ
  `node <pkg>/dist/cli.js task start …`
- **card start ที่ไม่ผ่าน daemon ใหม่** (เช่น UI ที่ยังเกาะ daemon เดิม) อาจดู "ผ่าน" ทั้งที่บั๊กยังอยู่
- **state ที่เขียนใน `sessions.json` ของ workspace** (`reviewReason: interrupted`) เป็น *ผล* ของ bug
  นี้ ไม่ใช่สาเหตุ ⇒ อย่าไปแก้ที่ไฟล์ state

**Proven Working Solution (พิสูจน์แล้ว 2026-10-15)**

สร้าง shim 1.4 KB ที่ `<npm-global>/kanban/dist/entry.js` (บนเครื่องนี้:
`~/.nvm/versions/node/v24.21.0/lib/node_modules/kanban/dist/entry.js`) — package เป็น ESM
(`"type": "module"`) จึงใช้ top-level `await` ได้:

```js
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

if (typeof globalThis.AI === "undefined") {
  try {
    globalThis.AI = require("ai");        // ai@6.0.303 ที่ติดมากับ @clinebot/core
  } catch {
    globalThis.AI = await import("ai");
  }
}

await import("@clinebot/core/hub/daemon-entry");   // ต้องเป็น dynamic import — ห้าม static export *
```

⚠️ **ต้องใส่ซ้ำทุกครั้งหลัง `npm i -g kanban` / npm upgrade** จนกว่า release > 0.1.70 จะ ship ไฟล์เอง
(หรือมีคนรันเวอร์ชันที่ build จาก `main` ที่มี `2f8764b` / `7ab7909`)

ติดตั้งซ้ำได้ในคำสั่งเดียว (source ของ shim อยู่ในสคริปต์นี้ = single source of truth ·
มีเทสต์ `tests/test_install_entry_shim.py` กันถอยหลัง):

```bash
.venv/bin/python scripts/kanban/install_entry_shim.py --check    # ดูสถานะ ไม่เขียน
.venv/bin/python scripts/kanban/install_entry_shim.py            # ติดตั้ง/ซ่อม (backup ของเดิมไว้)
.venv/bin/python scripts/kanban/install_entry_shim.py --smoke    # + สตาร์ท daemon จริงบนพอร์ตว่าง
```

รันบนเครื่องนี้ 2026-10-15: `--check` → `current -> already-current` (exit 0) ·
`--smoke` → `smoke: OK (port 39377)` (exit 0)

หลักฐาน (เครื่องนี้ · 2026-10-15 21:2x):

| ขั้น | ผล |
|---|---|
| `node --check dist/entry.js` | `SYNTAX OK` |
| `HOME=/tmp/... node dist/entry.js --cwd /tmp/... --port 45999` | log ไม่มี error · `ss -ltn` = **LISTEN 127.0.0.1:45999** |
| `hub-daemon.log` | ไม่โตแล้ว — `MODULE_NOT_FOUND` 8 → **8**, mtime ค้างที่ 13:48 |
| การ์ด smoke `f76e7` (`DONE <sha>`) | ย้ายเข้า `in_progress` · session `status: **completed**` · ข้อความจริง `DONE 9ed1f5a` |
| การ์ด smoke ใบที่ 2 `11c9e` (รันซ้ำ 2026-10-15 22:1x) | session `status: **completed**`, `exit_code: 0`, `interactive: true`, `pid: 1535` · `cwd` = `~/.cline/worktrees/11c9e/InvestmentHomelab` (detached HEAD @ `842c6c5`) · agent ตอบ `PWD /home/araya-sawasdichai/.cline/worktrees/11c9e/InvestmentHomelab` + `DONE 842c6c5` ⇒ **พิสูจน์ว่ารันใน worktree ของการ์ดจริง ไม่ใช่ checkout หลัก และไม่ถูก cancel** |
| `kanban task delete --task-id f76e7` | `worktreeCleanup.removed: true` · board กลับเป็น 0 การ์ดทุกคอลัมน์ |
| `kanban task delete --task-id 11c9e` | `worktreeCleanup[0].removed: true` · `git worktree list` เหลือ main อย่างเดียว · board 0 การ์ดทุกคอลัมน์ · `hub-daemon.log` ยังค้าง 8 / mtime 13:48 |

**User Feedback & Context**: พบ root cause หลังรื้อ `hub-daemon.log` + เทียบ tarball ทุกเวอร์ชัน ·
ผู้ใช้ยืนยันให้ค้นในเน็ตก่อน แล้วเจอ `cline/kanban#495`/`#590` ตรงกับอาการทุกข้อ (รวม ~30 วิ timeout) ·
สรุปค้างไว้ใน `.agents/skills/task-router/SKILL.md` §"Starting a card"

---

## KB-RCA-002 (2026-10-15) — การ์ด start ได้แล้ว แต่ session ตายในเทิร์นแรกด้วย `AI_MissingToolResultsError` (parallel tool calls)

**Symptom**

1. การ์ด start ปกติ (daemon ขึ้น, session มี `pid`, worktree ถูกสร้าง) แต่จบเร็วด้วย
   `status: "failed"`, `exit_code: 1` — transcript มี `user` + `assistant` (thinking + `tool_use` **2 อัน
   ในเทิร์นเดียว**) แล้ว **ไม่มี `tool_result`** ตามมาเลย
2. ใน transcript/session ต่อมาโผล่ `AI_MissingToolResultsError`:
   `Tool results are missing for tool calls: call_00_…, call_01_…` (retry → "6 consecutive mistakes"
   → ตัวช่วยตอบว่าง/มีแค่ `?` กลางเทิร์น)
3. `~/.cline/kanban/workspaces/<workspace>/sessions.json` เก็บ error นี้ซ้ำทุกครั้งที่ start/reply

**Root cause (3 จุด — ตรวจจาก bundle จริง ไม่เดา)**

- **session/context**: ไม่เกี่ยวกับ cookie/session ของโบรกเกอร์และไม่เกี่ยวกับ gateway — อยู่ใน process
  ของ kanban เอง (คนละ bug กับ KB-RCA-001 ที่ daemon spawn ไม่ขึ้น)
- **live bundle**: `@clinebot/agents@0.0.38` (nested ที่ `<npm-global>/kanban/node_modules/@clinebot/agents`
  — ทั้งเครื่องมีสำเนาเดียว และ `@clinebot/core` ทั้ง 3 entry import ตัวนี้ตอนรัน ไม่ได้ inline) ใน
  `Agent.executeToolCalls`:
  ```js
  let i=…; if(this.config.toolExecution==="parallel")
    return Promise.all(i.map(v=>this.executePreparedTool(v)));
  let o=[]; for(let v of i) o.push(await this.executePreparedTool(v)); return o
  ```
  ⇒ เทิร์นที่มี tool call หลายอันจะรันพร้อมกัน (`Promise.all`) แล้วผลไม่ถูกผูกกลับเข้า history ครบ
  → Vercel AI SDK `convertToLanguageModelPrompt` (ใน `streamStep`) โยน `MissingToolResultsError`
- **config/schema**: `maxParallelToolCalls` เป็น zod ใน `kanban/dist/cli.js` = `.number().int().positive()
  .default(8)` และ **ไม่มี config/flag/การ์ด-field ให้ผู้ใช้ตั้ง** (การ์ดมีแค่ `startInPlanMode`,
  `autoReviewEnabled/Mode`, `baseRef`) → resolver `f>=2?"parallel":"sequential"` จึงได้ `"parallel"`
  เสมอ · ขณะที่ default ในตัว agent เองเป็น `"sequential"`

**Upstream**: `cline/kanban#232` — "MissingToolResultsError with parallel tool calls (all providers)",
open, ยังไม่มี fix · ไม่มี release ใหม่ให้อัป (kanban 0.1.70 = latest)

**Proven solution** — patch ให้เหลือเส้นทาง sequential เท่านั้น (สคริปต์เดิมของ KB-RCA-001):
```bash
.venv/bin/python scripts/kanban/install_entry_shim.py --check   # seq-tools: needs-patch | current
.venv/bin/python scripts/kanban/install_entry_shim.py           # apply (backup .bak.<ts> + node --check)
```
ตัด `if(this.config.toolExecution==="parallel")return Promise.all(…);` ออก ฝัง marker
`/*kb-seq-tools*/` ไว้เช็ค idempotency · tool ทุกตัวยังรันครบ เพียง `await` ทีละตัว · ไม่รู้จักรูป
bundle → `failed` + reason (ไม่เดา — Anti-Mock) · ⚠️ re-apply หลัง `npm i -g kanban` ทุกครั้ง

**Edge cases**

- ต้อง **restart kanban/daemon** หลัง patch — process ที่ import โมดูลไปแล้วไม่รับไฟล์ใหม่
- bundle เปลี่ยนรูป (มี `Promise.all` 0/หลายจุด) → สคริปต์ **ไม่เขียนไฟล์** และรายงาน reason
- `node --check` ไม่ผ่าน → ถือว่า fail (ไม่รายงานผ่านเงียบ ๆ)
- patch นี้ *ลด* parallel execution ของ tool = agent ช้าลงเล็กน้อย — ยอมรับได้จนกว่า upstream จะแก้

**Evidence (2026-10-15 22:32 · เครื่องนี้)**

| ขั้น | ผล |
|---|---|
| `--check` (ก่อน) | `seq-tools: needs-patch -> would-patch` · parallel branch 1 จุด · 323199 bytes |
| `install_entry_shim.py` | `seq-tools: needs-patch -> patched` + backup `index.js.bak.1792078350` · `seq syntax: OK` |
| หลัง patch | parallel branch **0** จุด · marker **1** จุด · 323113 bytes (= −102 +16 ตรงเป๊ะ) |
| `node -e "import(...)"` ก่อน/หลัง | `LOAD_OK` เท่ากัน · exports เดิม `Agent,AgentRuntime,createAgent,createAgentRuntime,createTool` |
| `--check` (ซ้ำ) | `seq-tools: current -> already-current` (idempotent) |
| tests | `tests/test_install_entry_shim.py` 38 passed · `verify_changes.py` (2 ไฟล์) PASS |

**Live acceptance test (2026-10-15 22:43 · การ์ด smoke `a9e1a` บน service ที่ restart แล้ว)**

การ์ด smoke สั่งให้ agent ยิง **2 tool calls ในเทิร์นเดียว** (`run_commands` + `read_files`) =
trigger ของเส้นทาง `Promise.all` ตรง ๆ · transcript จริงจาก
`~/.cline/data/sessions/a9e1a-*/a9e1a-*.messages.json`:

```
[1] assistant: thinking | tool_use:run_commands | tool_use:read_files   <<< MULTI-TOOL TURN
[2] user: tool_result
[3] user: tool_result
[4] assistant: thinking | tool_use:run_commands
[5] user: tool_result
[6] assistant: text:SMOKE2_OK d830a01
```

`MissingToolResults occurrences: 0` · session `status: completed` / `exit_code: 0` ·
`cwd = ~/.cline/worktrees/a9e1a/InvestmentHomelab` (isolation เดิม) · journal ไม่มี error
(เทียบ session ก่อน patch `9bcb1-…` = `status: failed`, `exit_code: 1`) · parser ที่ใช้ตรวจอยู่ที่
`/tmp/kb_parse.py` (ไม่ใช่ artifact ถาวร — สร้างใหม่ได้ตามนี้)
💡 smoke #1 (`83692`) ที่ยิง **1 tool call** ผ่านแม้ยังไม่ patch → **ไม่ใช่ acceptance test**
ของ bug นี้ ต้องบังคับ ≥2 tool calls ในเทิร์นเดียวเสมอ

**⚠️ บทเรียนจากการ restart service** — `cline-kanban.service` ไม่มี `--skip-shutdown-cleanup`
⇒ `systemctl --user restart` จะ **ย้าย session ที่ค้าง (รวม `awaiting_review`/`review`) เข้า `trash`
และลบ task worktree** (การ์ด `9bcb1` โดนจริงรอบนี้ · start จาก trash ไม่ได้ตาม edge case ข้อ 5 →
ต้องลากออกจาก trash ใน UI) · ก่อน restart ครั้งถัดไป: ตรวจ `kanban task list` ให้บอร์ดว่าง หรือ
commit/push งานใน worktree ก่อน · restart ที่ถูกต้องคือ
`systemctl --user restart cline-kanban.service` (อย่า kill/nohup เอง — unit มี `Restart=on-failure`)

**User Feedback & Context**: ผู้ใช้ยืนยันให้แก้ต่อหลัง KB-RCA-001 · พบ upstream ตรงอาการเป๊ะ
(`cline/kanban#232`) · ผู้ใช้อนุมัติให้ restart kanban service + รันการ์ดจริงพิสูจน์ (ทำแล้วด้านบน) ·
ต้อง re-apply patch ทุกครั้งหลัง `npm i -g kanban`

