# Plan — Complete remaining Settrade Streaming probes & finish Loop-1 nego

## Goal

Probe every remaining Settrade Streaming DOM selector needed to finish Loop-1 nego (SHORT/COVER + native change + cancel), fix the KSS daemon's Streaming-tab bug, and consolidate probe tooling — everything doable now in one pass, with the live-order-dependent probes clearly gated on market open.

## Current context / assumptions

- **Market CLOSED now** (SET: 09:55–12:30 / 14:25–16:30 +07). Probes that need a live *queuing* order (Change dialog, Cancel dialog, Submit confirmation, live bid/offer depth) **cannot run now**. They need the next trading session.
- Repo: `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab` (branch `main`, last commit `0ce8d38`).
- The KSS probe system already exists (built by Jules) but is **uncommitted**: `scripts/kss_probe.py`, `scripts/kss/cdp_client.py`, `scripts/kss/kss_session_daemon.py`, `tests/test_kss_probe.py` (5/5 pass). CLI verified working (`kss_probe.py status` correctly reports "CDP not running" when no daemon).
- **Known bug**: `scripts/kss/kss_session_daemon.py` → `open_target_tabs()` cannot open the Streaming tab — it clicks `a:has-text('โปรแกรม Streaming')` which lives in a *hidden* dropdown (never visible), then falls back to `sso_page.evaluate("popup(...)")` which throws `ReferenceError: popup is not defined`. Net result: Streaming never opens.
- **Confirmed working selectors** (do NOT re-probe these):
  - Direct SSO URL: `https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming` → `app.settrade.com/oauth/...` → `wma1.settrade.com/realtime/streaming7/StreamingPage.jsp`
  - Account dropdown: `span.outline-none:has-text('Equity')` → option `li:has-text('3024959')` (margin)
  - Side radios (`name="placeOrderRadio"`): Buy `#equity-place-order-buy-radio-button` (B), Sell `#equity-place-order-sell-radio-button` (S), Short `#equity-place-order-short-radio-button` (H), Cover `#equity-place-order-cover-radio-button` (C)
  - Order row action cell: `li:has-text('Change')` (class `…text-decoration-underline…css-phnjeo…`, React handler, no inline `onclick`)
- Ad-hoc scripts I wrote earlier overlap with `kss_probe.py` and must be retired: `scripts/streaming/streaming_keepalive.py`, `_reuse.py`, `_finish_setup.py`, `_dump_change_cell.py`, `_dump_links.py`, `probe_change_cells.py`.

## Architecture / proposed approach

Keep `scripts/kss_probe.py` as the **single official** probe CLI (persistent CDP daemon on port 9333, profile `data/kss_chrome_profile`). Fix its one blocking bug (Streaming-tab open), delete the redundant ad-hoc scripts, and verify the whole loop end-to-end with one OTP. Then enumerate the remaining dialogs (Change/Cancel/Submit/SBL) and mark which are blocked on market open.

## Step-by-step tasks

### Phase A — now (no market needed)

**A1. Fix `open_target_tabs()` to use the direct SSO URL.**

File: `scripts/kss/kss_session_daemon.py`. Replace the body of `open_target_tabs` (currently lines ~132–164) with:

```python
SSO_STREAMING_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming"


async def open_target_tabs(ctx: BrowserContext):
    """Open the Settrade Streaming tab via the direct SSO endpoint (reliable;
    the 'โปรแกรม Streaming' link sits in a hidden dropdown and popup() is undefined)."""
    if any("streamingpage" in p.url.lower() for p in ctx.pages):
        logger.info("Streaming tab already open.")
        return
    logger.info("Opening Settrade Streaming tab via direct SSO URL...")
    page = await ctx.new_page()
    try:
        await page.goto(SSO_STREAMING_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        logger.warning(f"SSO navigation error: {e}")
    for _ in range(30):
        await asyncio.sleep(2)
        for p in ctx.pages:
            if "streamingpage" in p.url.lower():
                logger.info(f"Streaming tab opened: {p.url}")
                return
    logger.warning("Streaming tab did not appear after SSO navigation.")
```

Keep the module-level `SSO_STREAMING_URL` constant. Verification: `python -c "import ast; ast.parse(open('scripts/kss/kss_session_daemon.py').read())"` exits 0 (no syntax error); no `popup(` string remains in the file (`grep -n popup scripts/kss/kss_session_daemon.py` → only a comment mention if any).

**A2. Retire the ad-hoc streaming scripts.**

```bash
cd ~/Documents/antigravity/InvestmentHomelab
git rm scripts/streaming/streaming_keepalive.py scripts/streaming/_reuse.py \
       scripts/streaming/_finish_setup.py scripts/streaming/_dump_change_cell.py \
       scripts/streaming/_dump_links.py scripts/streaming/probe_change_cells.py
```
Keep the probe-result JSONs under `data/probes/` (historical evidence). Verification: `ls scripts/streaming/` shows only the original Phase-0 probes (`probe_streaming*.py`, `dump_*.py`, `probe_krungsri_sso.py`, `probe_autologin.py`, `probe_sbl_v2.py`, `probe_sbl_margin_change.py`, `dump_side_radios.py`).

**A3. Add a regression test for the daemon's direct-SSO open (TDD).**

File: `tests/test_kss_probe.py` — add one test asserting `open_target_tabs` navigates the SSO URL when no Streaming tab exists (fake context). Follow the existing fake-object style in that file. Then:
```bash
.venv/bin/python -m pytest tests/test_kss_probe.py -q   # expect: 6 passed
```

**A4. Verify the full kss_probe loop end-to-end (one OTP, user types it).**

```bash
cd ~/Documents/antigravity/InvestmentHomelab
.venv/bin/python scripts/kss_probe.py start-session    # user enters OTP once; daemon stays running
.venv/bin/python scripts/kss_probe.py status           # expect: >=1 tab tagged STREAMING + KRUNGSRI-SSO
.venv/bin/python scripts/kss_probe.py probe --target streaming --focus "account,order,change"
.venv/bin/python scripts/kss_probe.py handoff --target streaming
```
Expected outputs:
- `status` → `✅ CDP is running and responsive.` + a `[STREAMING]` row pointing at `…/StreamingPage.jsp`.
- `probe` → `💾 Probe results saved to: data/probes/probe_streaming_<ts>.json` and ≥1 match for `change`.
- `handoff` → `📋 Handoff document generated successfully: docs/handoff/PROBE-STREAMING-<ts>.md`.

**A5. Resolve the "SBL tab" question (probe now — static UI).**

```bash
.venv/bin/python scripts/kss_probe.py probe --target streaming --focus "sbl,short,cover,borrow,ยืม"
```
Decision rule:
- If results show **only** the 4 radios (Short/Cover/Buy/Sell) and no distinct SBL tab → record: *"SBL is not a separate tab; Short/Cover are direct side radios on the margin account"* (this matches my earlier Phase-0 finding). No SBL-specific scraper needed.
- If a distinct SBL tab/section IS found → capture its selector and add a follow-up task to scrape borrowable-stock inventory (for shortability checks).

**A6. Commit Phase A.**

```bash
git add -A && git commit -m "kss: fix Streaming-tab SSO open, retire ad-hoc probe scripts, verify kss_probe loop"
```

### Phase B — market open only (next session, with human witness)

These are **blocked on a live queuing order**. Do them in one headed session after login, on a small real order (e.g. SHORT BCPG 100 @6.80, or COVER) with the user watching.

**B1. Probe the Change dialog.** With an active queuing order on screen:
```bash
.venv/bin/python scripts/kss_probe.py probe --target streaming --focus "change,price,confirm,pin,แก้"
```
plus a one-off headed script that clicks `li:has-text('Change')` on the target row and dumps the resulting modal (price input, confirm button, PIN field, cancel). Record exact selectors.

**B2. Probe the Cancel dialog.** Click `li:has-text('Cancel')` on the row → dump the confirmation modal (confirm button, PIN, "yes/no").

**B3. Probe Submit confirmation.** Fill the order form (side radio + symbol + volume + price + PIN) → click Submit → dump the confirmation/result modal. (This is the last unknown for `execute_order`.)

**B4. Implement native modify (TDD).** In `app/browser/streaming_driver.py`, rewrite `modify_order_price` to use the **Change** flow (click Change cell → fill new price in the Change dialog → confirm) instead of the current cancel+replace. Add failing tests first (FakePage for the Change dialog), implement, `pytest tests/test_streaming_driver.py -q` → all green.

**B5. Witness full nego.** Login once, headed: place SHORT → Change price → Cancel, watching each step. Update `docs/handoff/TASK-loop1-8-streaming-primary.md` with the confirmed dialog selectors.

## Risks, tradeoffs, open questions

- **Krungsri SSO expires server-side (~45 min)** — the 5-min heartbeat keeps market-data alive but does NOT stop auth expiry. Every new trading session needs one fresh login+OTP at session start. Plan accounts for this (login once at session start, do everything in that one browser).
- **Port 9333 collision**: the user's own Chrome (pid 5543) already holds port 9222, so 9333 was chosen. If the daemon later fails to bind 9333, re-check `ss -tlnp | grep 9333`.
- **Open question — SBL**: is there a real SBL tab, or are Short/Cover just the direct radios? Resolved in A5.
- **Open question — Change dialog PIN**: does changing a price require re-entering PIN? Unknown until B1; the driver must not assume — it must read the actual modal.
- Phase B cannot be done "now" by definition (no live order possible after close). If the user wants to force it, the only route is placing an ATO/pre-open order for next session — a live-money action that needs explicit user go + witness.

## Deliverable / done-when

- Phase A: `kss_probe.py` loop works end-to-end (status→probe→handoff) with one OTP; daemon opens Streaming correctly; ad-hoc scripts removed; SBL question answered in `docs/handoff/PROBE-STREAMING-*.md`; everything committed.
- Phase B (separate session): Change/Cancel/Submit dialog selectors captured; `modify_order_price` uses native Change with tests green; witness confirms the full nego path.
