# PLAN — ให้ `/status` + `/login` อ่าน session จาก CDP (ไม่ใช่ flag ในโปรเซส)

- **เขียน:** 2026-10-26 14:25 · สถานะ: **รออนุมัติ** (ยังไม่เปิดการ์ด)
- **อาการที่ผู้ใช้เจอ:** `/status` ขึ้น KSS/LIB "ยังไม่ login" ทั้งที่ CDP 9333/9334 เปิดอยู่และแท็บ authenticated · กด `/login` แล้วระบบขอ OTP ใหม่
- **สาเหตุ:** ไม่ใช่บั๊กของ CDP — เป็นเพราะ health ทั้งระบบอ่าน **flag ในโปรเซส gateway** ไม่ได้ถาม daemon

## 1. หลักฐาน (อ่านโค้ดจริง)

| ที่ | บรรทัด | อ่านจาก | ผลเมื่อ gateway เพิ่ง restart |
|---|---|---|---|
| `_broker_health()` | `handlers.py:179-192` | `auth_driver.is_authenticated` (kss) · `liberator_plugin.get_health()` (lib) | False ทั้งคู่ → `/status` ขึ้น "ยังไม่ login" |
| `_broker_session_alive()` | `handlers.py:134-141` | เหมือนกัน | False → `/login` ตกไป `session_login_broker()` = ยิง OTP |
| `/logout` guard | `handlers.py:483` | ตัวเดียวกัน | ขึ้น "ไม่ได้เข้าระบบอยู่แล้ว" ทั้งที่ยัง login อยู่ |
| `/port|/cash sync` guard | `handlers.py:857` | ตัวเดียวกัน | ขึ้น "session หลุด — /login ก่อน" ทั้งที่ดึงข้อมูลได้ |
| `/nego` **G3 money guard** | `handlers.py:1120` | ตัวเดียวกัน | **บล็อกคำสั่งซื้อขายจริงทั้งที่ session ยังดี** |
| Pillar-1 `session_get_health()` | `pillar1_session.py:24-56` | flag เดียวกัน + session file | MCP tools ก็รายงานผิดเหมือนกัน |

ซ้ำร้าย: kss อ่าน `app.browser.auth_driver` (**TradeMan**) แต่เส้นทางสดตอนนี้คือ **Settrade Streaming** (`app/browser/streaming_driver.py`) → ต่อให้ TradeMan login ไว้ ก็ไม่เกี่ยวกับแท็บที่ใช้จริง

## 2. ของที่มืออยู่แล้ว (ไม่ต้องสร้างใหม่)

- `scripts/broker_cdp/client.py` — `cdp_url_for()`, `resolve_target_tab()`, `connect_cdp()` (มี port map 9333/9334 + target map ครบ)
- `StreamingDriver.connect_cdp(target="streaming")` (`streaming_driver.py:141`) — attach ไม่ launch ไม่ OTP, เก็บเป็น `page_override`
- `LiberatorDriver.connect_cdp(target="portfolio")` (`liberator/driver.py:220`) — semantics เดียวกัน, เก็บเป็น `self.page`
- `scripts/broker_cdp/brokers.py` — รายชื่อแท็บ/ล็อกอินฮุกต่อ broker
- P.1.11b/P.1.11c ทำ "connect_cdp ก่อน launch" ไว้แล้วในเส้นทาง order/scrape — **แต่ไม่มีใครใช้มันตัดสิน health**

## 3. ดีไซน์: truth ตัวเดียว 3 ชั้น

```
CDP probe (ใหม่, read-only, ไม่ launch/ไม่ login)
  ├─ daemon ตอบไหม (9333/9334)
  ├─ มีแท็บเป้าหมายไหม (target map)
  └─ path ของแท็บ = หน้าเทรดจริง หรือ /login|/otp
        ↓
   session_state ∈ {AUTHENTICATED, LOGIN_PAGE, NO_TARGET_TAB, DAEMON_DOWN, UNKNOWN}
        ↓
  ┌──────────────┬─────────────────────┬──────────────────────────┐
  │ /status      │ /login              │ G3 money guard           │
  │ แสดง 5 สถานะ  │ AUTHENTICATED →     │ รับ AUTHENTICATED        │
  │ + ที่มา       │ attach (zero-OTP)   │ อย่างเดียว (ไม่รับ UNKNOWN)│
  └──────────────┴─────────────────────┴──────────────────────────┘
```

**กฎเหล็ก 4 ข้อ**
1. probe เป็น **read-only**: `Runtime.evaluate` บนแท็บเดิมเท่านั้น ห้าม `goto` ห้าม launch ห้าม login
2. จับด้วย **path** ไม่ใช่ substring (บทเรียนเดิม: `/login` โผล่ใน URL อื่นได้) — และต้อง exclude `/otp`, `/twofa`, หน้า landing
3. `UNKNOWN` = **ไม่ผ่าน** ทุก guard ที่เกี่ยวกับเงิน (fail-closed) แต่ `/status` แสดงว่า UNKNOWN
4. `/login` attach สำเร็จ → set in-process state (`page`, `status=AUTHENTICATED`, heartbeat) เพื่อให้โค้ดเก่าที่ยังอ่าน flag ทำงานต่อได้

## 4. แผนงาน (numbered sub-tasks)

### Wave 0 — สัญญาข้อมูล (ต้องเคาะก่อนเขียนโค้ด)

| # | งาน | ไฟล์ | Tier | Model | Verify | Done when |
|---|---|---|---|---|---|---|
| **0a** | ล็อก path ที่ถือว่า authenticated ต่อ broker (Streaming: หน้า Streaming7 / SBL: `MainSBL.aspx` / Liberator: portfolio+trade) + path ที่ต้องถือว่า login-page | `docs/handoff/TASK-cdp-session-truth.md` (ภาคผนวก), `scripts/broker_cdp/brokers.py` | 🟢 T0 | jules-3.6-flash | ไล่ดู URL จริงจาก daemon 2 ตัว (`curl :9333/json/list`) | ได้ตาราง path ครบ 3 broker + ไม่มี path กำกวม |

### Wave A — ทำให้ `/status` พูดความจริง (ไม่แตะเงิน)

| # | งาน | ไฟล์ | Tier | Model | Verify | Done when |
|---|---|---|---|---|---|---|
| **A.1** | โมดูล `cdp_session_status(broker)` คืน 5 สถานะ + `url_path` + `checked_at` + `reason` (ใช้ client เดิม, read-only) | `app/services/broker_cdp/session_probe.py` (ใหม่) + `tests/test_cdp_session_probe.py` | 🟢 T0 | jules-3.6-flash | unit ครบ 5 สถานะด้วย fake CDP + `GET :9333/json/list` จริงคืน AUTHENTICATED | unit เขียว + probe จริงบนเครื่องนี้ได้ AUTHENTICATED ทั้ง kss และ lib |
| **A.2** | `/status` ใช้ probe · kss ย้ายไปอ่าน **Streaming** (ไม่ใช่ TradeMan) · แสดง 3 บรรทัด: สถานะ / port / ที่มา (CDP vs flag) | `handlers.py:_broker_health` | 🟢 T0 | jules-3.6-flash | ยิง `/status` บน LINE ขณะ gateway ไม่เคย login → ต้องขึ้น 🟢 ทั้งคู่ | `/status` เขียวทั้ง 2 broker โดยไม่ต้อง login ใหม่ |
| **A.3a** | `_broker_session_alive()` ใช้ probe ก่อน แล้ว fallback flag — **เฉพาะ** call site ที่ไม่เกี่ยวกับเงิน (`/logout` 483, sync 857, `/login` 446) | `handlers.py:134` | 🟡 T1 | jules-3.1-pro | unit 4 call site + live: `/logout` ต้องรู้ว่ามี session อยู่จริง | ไม่มี call site ไหนตอบ "session หลุด" ขณะ daemon authenticated |
| **A.3b** | **G3 money guard** (`handlers.py:1120`) รับ `AUTHENTICATED` จาก probe | `handlers.py:1120` | 🔴 T2 | ต้องมี witness | ดูข้อ 6 | รัน `/nego` dry แล้วผ่าน guard โดยไม่ต้อง login ใหม่ **หลัง** witness |

### Wave B — `/login` = attach ก่อน ไม่ใช่ OTP ทันที

| # | งาน | ไฟล์ | Tier | Model | Verify | Done when |
|---|---|---|---|---|---|---|
| **B.1** | `/login <broker>`: ถ้า probe = AUTHENTICATED → `connect_cdp()` → set in-process state → ตอบ "เชื่อมกับแท็บที่เปิดอยู่แล้ว (zero-OTP)" · attach ไม่ได้ค่อยตกไป `session_login_broker()` | `handlers.py:_handle_login` | 🟡 T1 | jules-3.1-pro | unit: fake probe AUTHENTICATED → ไม่เรียก `session_login_broker` เลย · live: `/login kss` ต้องไม่ขึ้น SMS | `/login kss` และ `/login lib` ไม่ขอ OTP ขณะ CDP เปิด |
| **B.2** | `/logout` ต้องไม่ปิดเบราว์เซอร์ของ daemon (disconnect only) + ตอบชัดว่า "หลุดจากโปรเซสนี้ แต่แท็บยังเปิด" | `handlers.py:483`, driver `close()` | 🟢 T0 | jules-3.6-flash | live: `/logout kss` → `:9333/json/list` ยังมีแท็บเดิม | browser ไม่ตายตอน logout |
| **B.3** | `/relogin` (หรือ `/login force`) = ทางเดียวที่ยอมเปิด browser ใหม่ + OTP | `handlers.py` | 🟢 T0 | jules-3.6-flash | unit: `force` เท่านั้นที่เรียก launch | ผู้ใช้มีทางหนีเมื่อ session ตายจริง |

### Wave C — รวม truth ให้ MCP/LINE ตรงกัน

| # | งาน | ไฟล์ | Tier | Model | Verify | Done when |
|---|---|---|---|---|---|---|
| **C.1** | `session_get_health()` เพิ่มฟิลด์ `cdp` ต่อ broker (ใช้ probe ตัวเดิม) — MCP tool กับ LINE รายงานตรงกัน | `app/mcp/pillars/pillar1_session.py` | 🟢 T0 | jules-3.6-flash | unit + เรียก MCP `session_get_health` เทียบกับ `/status` | 2 ช่องทางให้คำตอบเดียวกัน |
| **C.2** | `/status` แนบ `daemon pid` + `last_checked` (debug ได้จากมือถือ) | `handlers.py` | 🟢 T0 | jules-3.6-flash | screenshot | เห็นใน LINE card |

## 5. Risk / guardrail

| ความเสี่ยง | กันอย่างไร |
|---|---|
| probe ไป navigate ทำให้มนุษย์เสียหน้าที่เปิดอยู่ | read-only `Runtime.evaluate`, ห้าม `goto` (unit test assert ว่าไม่มีการเรียก navigate) |
| attach ผิดแท็บ (เช่นแท็บ SBL ตอนสั่ง Streaming) | ใช้ target map ต่อ broker + ตรวจ path ตามระบบ 0a |
| `AUTHENTICATED` จาก probe แต่ driver ยังไม่มี page → ฟังก์ชันล่างพัง | B.1 set `page` ให้ driver ก่อนคืน success; ถ้า attach ไม่ได้ → `UNKNOWN` |
| G3 (เงิน) หลวมขึ้นแบบไม่ตั้งใจ | แยก **A.3b** ออกจาก A.3a และปิดด้วย witness (ข้อ 6) |
| daemon ตอบแต่ Chrome ค้าง | เพิ่ม timeout 2s + `checked_at`; timeout = `DAEMON_DOWN` (fail-closed) |

## 6. ลำดับที่ปลอดภัย (และทำไม)

1. **0a → A.1 → A.2** : ได้ความจริงมาแสดงก่อน — จบอาการ `/status` โกหก ภายในรอบเดียว
2. **B.1 + B.2 + B.3** : `/login` กลายเป็น attach — จบอาการ "กด login ต้อง OTP" (นี่คือสิ่งที่ผู้ใช้ขอ)
3. **A.3a** : `/logout` + sync ใช้ probe (ยังไม่แตะเงิน)
4. **A.3b** : G3 รับ probe — **ต้องมี witness ก่อน** เพราะเป็นด่านที่ปล่อยออเดอร์จริง. แนะนำทำพร้อม **2.7** (value BUY dry) หรือ **2.8** (SBL) ในรอบเปิดตลาดหน้า แล้วค่อยปิด
5. **C.1 + C.2** : ทำให้ MCP/LINE ตรงกัน

## 7. เรื่องที่ต้องตัดสินใจ

- **D1** — `/status` ควรนับ `AUTHENTICATED` เมื่อ **แท็บ Streaming เปิดอยู่** เท่านั้น หรือยอมรับ SBL tab ด้วย?
  → แนะนำ: per-purpose (`streaming` สำหรับ `/buy`, `sbl` สำหรับ `/borrow`) แล้วแสดงเป็น 2 บรรทัดย่อย
- **D2** — `/login` ที่ attach สำเร็จควร **push** ข้อความบอกไหม (ผู้ใช้อาจคิดว่าไม่ได้ทำอะไร)
  → แนะนำ: ใช่ ("🟢 เชื่อมกับแท็บที่เปิดอยู่ (zero-OTP) · 9333")
- **D3** — A.3b จะรอ witness หรือทำเลยแล้วปิดด้วย witness ย้อนหลัง?
  → แนะนำ: รอ — ด่านเงินไม่ควรหลวมก่อนมีหลักฐาน

## 9. ภาคผนวก A — path table วัดจริงจาก daemon (14:26, 2026-10-26)

ยืนยันอาการได้ตรง ๆ: `_broker_health()` ในโปรเซสใหม่ตอบ `kss -> authenticated=False`, `lib -> authenticated=False`
(ทั้งที่ lib มี heartbeat 14:24 ค้างอยู่ — สองฟิลด์ขัดกันเอง) ขณะที่ `curl :9333|:9334/json/list` เห็นแท็บที่ใช้งานได้จริง:

| broker | purpose | port | path ที่ถือว่า AUTHENTICATED | หมายเหตุ |
|---|---|---|---|---|
| kss | streaming | 9333 | `wme2.settrade.com/realtime/streaming7/StreamingPage.jsp` | หน้าซื้อขายสด (เส้นทาง `/buy`, `/nego`) |
| kss | sbl | 9333 | `krungsrisecurities.com/sblweb/MainSBL.aspx` | เส้นทาง `/borrow`, `/short`, `/sbl sync` |
| kss | (member) | 9333 | `krungsrisecurities.com/th/member/*` | อยู่ในพื้นที่สมาชิก = session ยังดี แต่ไม่ใช่หน้าเทรด |
| lib | portfolio | 9334 | `webtrade.liberator.co.th/Portfolio`, `/Market`, `/Trade` | `/Market` = แท็บหลักของ daemon |

**login-page markers (ต้องนับเป็น LOGIN_PAGE ไม่ใช่ AUTHENTICATED):**
`/login`, `/Login.aspx`, `/signin`, `/otp`, `/twofa`, `/member/login`, `/auth/`

→ **0a เสร็จเชิงหลักฐานแล้ว** เหลือแค่ codify ตารางนี้ลง `scripts/broker_cdp/brokers.py` (constants + helper `is_authenticated_path(broker, purpose, url)`) ซึ่งรวมอยู่ใน `CDP-1`

## 8. แผนที่การ์ด (ปิดแล้ว 4/5 — 2026-10-26)

| การ์ด | รวม sub-task | Tier | commit | ผล |
|---|---|---|---|---|
| `CDP-1` `t_033b4521` | 0a + A.1 | 🟢 T0 | `cf99046` | probe 5 สถานะ + path contract · live: kss/streaming, kss/sbl, lib/portfolio = AUTHENTICATED · Chromium 12→12 |
| `CDP-2` `t_2b531977` | A.2 + C.2 | 🟢 T0 | `aaa7a10` | `/status` อ่าน probe · `authenticated=true source=CDP port=9333 pid=59445` |
| `CDP-3` `t_f4b373d4` | B.1 + B.2 + B.3 | 🟡 T1 | `51d927e` | `/login` = attach zero-OTP · `/logout` ไม่ปิดเบราว์เซอร์ · `force` = ทางเดียวที่ขอ OTP |
| `CDP-4` `t_cadae6a7` | A.3a + C.1 | 🟡 T1 | `eacdcff` (+ handlers ใน `51d927e`) | MCP `cdp` block ตรงกับ `/status` · guards ใช้ probe · **G3 ยัง flag-only** |
| `CDP-5` `t_73d6e7e6` | A.3b (G3) | 🔴 T2 | — | **เปลี่ยนวิธี**: env-gate แทน worker+witness แยก |

### CDP-5 เปลี่ยนรูปแบบ (2026-10-26 — ตัดพิธีตามคำขอผู้ใช้)

G3 ไม่ต้องรอ witness เพื่อ "แก้โค้ด" อีก — ผูกกับ setting ใหม่แทน:

```python
if not await _broker_session_alive(broker, allow_cdp=settings.LINE_NEGO_CDP_GATE):   # G3
```

- `LINE_NEGO_CDP_GATE` default **False** → พฤติกรรมเดิมทุกอย่าง (flag-only) ไม่ต้องมี witness ก่อน
- วัน witness: `LINE_NEGO_CDP_GATE=true` ใน `.env` + restart gateway → G3 รับ CDP AUTHENTICATED
- fail-closed คงอยู่: `LOGIN_PAGE` / `NO_TARGET_TAB` / `DAEMON_DOWN` / `UNKNOWN` ไม่ผ่าน G3 แม้เปิด flag (มีเทสต์ล็อก)
- เทสต์ใหม่: `test_nego_g3_accepts_cdp_when_gate_enabled` · `test_nego_g3_still_blocks_login_page_when_gate_enabled` · ของเดิม `test_nego_g3_guard_calls_session_alive_without_cdp` ยังผ่านเพราะ default False
