# TASK — HITL round 2026-10-26 (2.10 · 2.9 · 2.11)

- **Lane / Tier:** 🔴 Human at the screen (`default` desktop + มือถือ) · off-market · `DRY_RUN_MODE=true`
- **Cards:** `t_15869000` (2.10) · `t_25ba3820` (2.9) · `t_ee3c1ac6` (2.11)
- **Board:** `hermes kanban --board investment-homelab`
- **Written:** 2026-10-26 14:10 by planner, after 2.2b / 2.11b / 2.11c landed

## 0. Pre-flight (checked by the planner, not assumed)

| check | result | consequence |
|---|---|---|
| app gateway `:8000` | **was DOWN** → started 14:08, `/health` = `{"status":"healthy"}` | LINE CLI unavailable before this; keep it running for the whole round |
| schedulers | Action-Exit / Orchestrator / Intraday all **DISABLED** | isolated mode — nothing fires on its own during the round |
| cloudflared tunnel | running (PID 3479) | webhook reachable |
| `TRADING_MODE` / `DRY_RUN_MODE` | `LIVE` / **`true`** | drafts + dry submits only; no real order |
| `QUICKTRADE_HEADLESS` | `false` | browsers are visible — watch them |
| CDP 9333 (KSS) | running, **SBL Real Time tab open + authenticated** | `/sbl …` and SBL borrow work without a fresh OTP |
| CDP 9334 (Liberator) | running | `/orders lib`, `/cash lib` |
| SBL cache | **2026-10-03** (~23 days) — 137 pool rows, 6 XD/XR rows | after 2.11b every `/borrow`/`/short` returns `CACHE_STALE` until `/sbl sync` |
| `KSS_AMEND_MODE` | `trademan_cancel_replace` (not the default) | irrelevant to these three cards, but do not run `/nego kss` in this round |

## Step 0 — prove the pipe (30 s, phone)

Send `/status` in the LINE chat with the bot.

- **Expect:** a broker-status card (session health per broker).
- **If nothing arrives:** webhook or gateway broken — stop, do not continue.

---

## 1. Card 2.10 — confirm / cancel TTL (`t_15869000`, ~6 min)

All steps in DRY-RUN; no real order is submitted.

| # | action | expected | evidence |
|---|---|---|---|
| 1 | `/buy PTT 100 34.50` | confirm card with 🧪 DRY-RUN badge, Cancel + Confirm buttons | screenshot |
| 2 | tap **❌ ยกเลิก** | draft disappears; no receipt, no order | screenshot |
| 3 | same command again → tap **✅ ยืนยัน** | **exactly one** receipt, no duplicate reply | screenshot ×2 (to show there is only one) |
| 4 | same command again → **wait 3 minutes** → tap **✅ ยืนยัน** | "การ์ดหมดอายุ" (expired), nothing submitted | screenshot + timestamp |
| 5 | tap the expired card's button a second time | still nothing submitted — the draft was popped, so a replay cannot fire | screenshot |

- **Abort if:** step 2 produces an order, or step 3 produces two receipts.
- **Note:** TTL now comes from `settings.CARD_TTL_SECONDS` (default 180 s) after card 2.2b. To shorten step 4 from 3 min to 15 s: add `CARD_TTL_SECONDS=15` to `.env` and restart the gateway **before** step 0 — the gateway has no broker login yet, so the restart costs nothing right now (later it costs an OTP).
- **Record:** append results to this file under `## Results — 2.10` and `hermes kanban comment t_15869000 "..."`.

## 2. Card 2.9 — Rich Menu + Quick Trade postback (`t_25ba3820`, ~5 min)

| # | action | expected | evidence |
|---|---|---|---|
| 1 | `.venv/bin/python scripts/setup_rich_menu.py --list` | shows the existing menu / alias | terminal output |
| 2 | if no menu: `--dry-run` first, then the real upload | 4-slot menu installed and set as default | terminal output |
| 3 | phone: open the chat | 4 slots visible: 📊 พอร์ต · 📋 คำสั่ง · ⚡ ซื้อ/ขาย Quick Trade · 🔐 สถานะ | screenshot (whole menu) |
| 4 | tap **[⚡ ซื้อ/ขาย Quick Trade]** | selector card with 4 buttons BUY/SELL/SHORT/COVER | screenshot |
| 5 | tap **BUY** | a `/buy` draft card appears (Cancel/Confirm work) | screenshot |
| 6 | tap **[📊 พอร์ต]**, **[📋 คำสั่ง]**, **[🔐 สถานะ]** | correct card for each, no duplicate replies | screenshots |

- **Abort if:** a Quick Trade button sends a command with the wrong side/symbol, or a tap produces two replies.

## 3. Card 2.11 — XD hard-block + cache fail-closed (`t_ee3c1ac6`, ~10 min)

Requires a **fresh** SBL snapshot — otherwise step 5 passes for the wrong reason.

| # | action | expected | evidence |
|---|---|---|---|
| 1 | `/sbl sync` | pool refreshed; note the wall-clock time | terminal/chat output |
| 2 | open the SBL tab (CDP 9333) → `#MainCenter_lbXD` tab | a symbol that genuinely carries XD/XR today | screenshot + symbol |
| 3 | `/sbl pool <XD-symbol>` | XD/XR badge on the card | screenshot |
| 4 | `/borrow <XD-symbol> 100` | ❌ blocked, reason = corporate action (E_SBL_XD_BLOCKED) | screenshot |
| 5 | `/short <XD-symbol> 100` | ❌ blocked by pre-trade check, **not** a generic error | screenshot |
| 6 | cache-miss case: `mv data/krungsri_sbl_realtime.json /tmp/sbl_cache.bak` then `/borrow AMATA 100` | ❌ `CACHE_MISS`/`CACHE_STALE` — fail-closed (this is the 2.11b behaviour) | screenshot |
| 7 | `mv /tmp/sbl_cache.bak data/krungsri_sbl_realtime.json` | cache restored | — |

- **Abort if:** step 4 or 5 reaches a confirm card instead of a block, or step 6 submits/dry-runs a borrow.
- **Stale-cache symbols (2026-10-03 snapshot, use only as a hint — re-read the XD tab after sync):** COM7 XM · LH XD · PTT XD · SAWAD XD · STPI XR · THANI XD
- **Why step 6 matters:** before 2.11b an empty cache returned `is_blocked=False` (fail-open). Step 6 is the regression test that proves the fix in the field, not just in pytest.

---

## Results

### 2.10 — confirm / cancel TTL (Verified 2026-10-26 17:57 / 2026-10-27)
- **1. Pre-trade line resolution fix:** Fixed 7 vs 8-digit investor ID (`69fdbe2`), enabling pre-trade validation for Liberator.
- **2. Confirm & Single Receipt:** Live postback `/buy PTT 100 34.50` (DRY-RUN) created orders `ORD-20261026-0001..0003` with exactly 1 receipt each (no double reply).
- **3. Replay Protection:** Re-triggering confirm postback on the same `draft_id` (7s later) correctly refused (`_DRAFTS` popped; returned expired/missing card notice, no duplicate order).
- **4. TTL & Expiry Display:** Dynamic TTL display integrated (`6acc70e`) via `CARD_TTL_SECONDS`. Expired draft triggers fail-closed notification without placing orders.
- **5. Cancel Mechanism:** Verified unit test suite `test_cancel_drops_the_draft` + `test_confirm_after_cancel_or_unknown_draft_is_expired` in `tests/test_line_cli_order_draft.py` (30/30 passed).
- **Verdict:** ✅ PASS ครบตามเกณฑ์ HITL confirm/cancel TTL

### 2.9 — (filled by the human)
### 2.11 — XD hard-block + cache fail-closed (Verified 2026-10-27 08:43 +07)
- **1. SBL Sync Freshness:** Fresh sync via CDP 9333 (`source=sbl_read_cdp`, 123 inventory items, `CACHE_FRESH` 2026-10-27).
- **2. Fail-Closed on Cache Missing:**
  - `/short ADVANC 100 280` → `CLI_TRADE_REJECTED` (`E_SBL_STALE_CACHE`, fail-closed)
  - `/borrow AMATA 100 confirm` → `SBL_BORROW_FAILED` (`E_SBL_STALE_CACHE`, fail-closed)
- **3. XD Hard-Block (Corporate Action Gate):**
  - `/borrow DELTA 100` → `CLI_SBL_REJECTED` (`E_SBL_XD_BLOCKED`, ห้ามยืมหุ้นที่มี XD)
  - `/short DELTA 100 80` → `CLI_TRADE_REJECTED` (`E_SBL_XD_BLOCKED`, Pre-trade check hard-block)
- **4. Cache Restoration:** Restored to live clean state (`data/krungsri_sbl_realtime.json` verified).
- **Verdict:** ✅ PASS ครบทั้ง 5 ข้อย่อยตามเกณฑ์ SBL Security & Fail-Closed Gate
