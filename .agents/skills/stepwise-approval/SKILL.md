---
name: stepwise-approval
description: Co-pilot execution protocol — decompose work into small AI↔user steps,
  state the expected outcome before each step, capture a screenshot at each stage
  when a headed browser is in use, and require real human interaction at every
  high-risk (T2) step — order/OTP/account/live-login/merge — per the risk-tiered
  gate in `docs/agent/github_handoff.md` §6. Lower-risk work (T0/T1) reports at unit end.
---

# Stepwise-Approval Co-Pilot Skill

This skill governs how the Agent executes multi-step work on InvestmentHomelab so
that the AI and the user **learn the correct workflow faster together**. It applies
to code changes, refactors, bug fixes, and any Playwright-driven browser automation.

---

## 1. Decompose into small steps (risk-tiered check-in)

- Split each task into the smallest independently-verifiable steps
  (one function, one call-site edit, one browser action).
- **Risk-tiered check-in** (see `docs/agent/github_handoff.md` §6) — do NOT hand control
  back at every micro-step, or the user becomes the bottleneck:
  - 🟢 **T0** (code/docs/unit test/headless scrape): execute the whole unit, report at unit end.
  - 🟡 **T1** (logic not touching order/OTP/tick): batch within the unit, report diff + evidence.
  - 🔴 **T2** (order / OTP / account switch / SBL / live login / merge main): **STOP before
    each action** and let the user confirm.
- Never batch **unrelated** changes, and never proceed past a **T2** gate without explicit
  human OK. A unit = one atomic unit from `## Steps / Task Decomposition` in the handoff.

## 2. State what to expect (before each step)

- Before acting, tell the user:
  - **WHAT** you are about to do (the single action), and
  - **WHAT the expected outcome is** (what they should see / the assertion to verify).
- After acting, report the **ACTUAL result** and confirm it matches the expectation.
- If the result differs from the expectation, **stop and escalate** instead of guessing.

## 3. Capture the screen at each stage (headed browser only)

- Whenever Playwright drives a **headed** browser (`headless=False` / `DISPLAY=:0`),
  capture a screenshot after every meaningful stage.
  - Use the browser tool's screenshot capture (e.g. `browser_screenshot`) or
    `await page.screenshot(path=...)` inside driver code.
  - Save to `data/screenshots/` (or the workflow's documented location).
  - Reference the screenshot path in the step report so the user can visually verify.

## 4. Require human interaction when the agent cannot figure it out (Playwright HITL)

- If a selector fails, an unexpected modal appears, or the DOM differs from what was
  learned, **do NOT guess or loop** — escalate to the user (HITL) for interactive
  co-piloting.
- Follow the **4-Tier Self-Annealing** protocol defined in the `watch-and-learn` skill
  (Tier 1 semantic → Tier 2 structural → Tier 3 JS dispatch). At **Tier 4**: capture
  the anomaly screenshot, log it, and prompt the user before proceeding.

---

## 5. Verify with real human interaction at every T2 step (not just unit tests)

- A passing unit test is **NOT** sufficient to declare a hardware/browser step
  verified. Do the real thing and ask the user to confirm the observable result.
- **KDE Connect / mobile bridge**: fire a real ping and ask whether it was seen:
  - `kdeconnect-cli -d <device_id> --ping-msg "Investment Homelab Bridge Active"`
  - then ask the user: **"did you see the ping on your phone?"**
  - If the phone is `paired` but `isReachable=false`, ask the user to unlock it /
    bring the KDE Connect app to the foreground first, then retry the ping.
- **Headed browser**: capture the screenshot (§3) **and** ask the user to confirm
  what they see on screen.
- Apply this at **every T2 step** — never declare "verified" on an automated test alone
  when the step touched real hardware or a visible browser.

---

## 6. Handoff Return Protocol (Cline Verification & Live Acceptance)

When a task card comes back from implementation (`## Cline Report` present in `docs/handoff/TASK-xxx.md`),
**Cline runs Stage A–D itself** with model **DeepSeek Pro** (not a separate reviewer agent):

1. **Stage A: Automated Audit & Code Review**
   - Check all modified/created files in git status / report against the allowed scope.
   - Run targeted verification: `.venv/bin/python scripts/verify_changes.py <changed files>`.
   - Inspect Diff to verify safety invariants (Anti-Mock, Invariant 9 Zero-OTP, Uptick rule).

2. **Stage B: Plan Live Verification Steps**
   - Decompose observable browser/hardware checks into atomic steps.
   - Define exact UI landmarks, tables, or alerts the user should see.

3. **Stage C: Guided Stepwise Headed Check**
   - Execute exactly 1 observable action on `DISPLAY=:0`.
   - Prompt user via `ask_question` with recommended options to confirm observable state before proceeding.

4. **Stage D: Cline Verdict & Task Closeout**
   - Update `## Cline Verification` in `docs/handoff/TASK-xxx.md` to `PASS` or `CHANGES_REQUESTED`.
   - `PASS` → open the result PR → user merges (Human gate #2) → worktree cleanup.

---

## 7. Stepwise Execution Protocol (Cline · DeepSeek Pro for verification)

Verification (Stage A–D) always runs on **DeepSeek Pro** — reasoning-grade accuracy for audit +
stepwise HITL. To get consistent, high-fidelity execution:

1. **One Question at a Time**:
   - Always use the `ask_question` tool for user decisions.
   - Never combine multiple forks into one prompt.

2. **Always Provide `(Recommended)` Options**:
   - The first option must be prefixed with `(Recommended)` and accompanied by a 1-line rationale based on repository invariants.

3. **Strict Single-Step Invariant**:
   - Execute strictly 1 atomic action per model turn. Never batch edits or commands that require separate validation.

4. **Response Style (Token Lean)**:
   - Chat with user: Thai, concise, lead with the direct answer.
   - No conversational filler, no repeating unchanged context.
   - Show only diffs and concrete evidence.

---

## Cross-references

- `docs/agent/github_handoff.md` — PHASE 0–5 loop + §4 Handoff mechanism (PR/Issue) + Risk-Tier (T0/T1/T2) + Human gates.
- `docs/agent/workflow_playbook.md` — Kanban ownership (Argon) + `[Review / Approval]` column = Cline verify.
- `watch-and-learn` — 4-Tier Self-Annealing Playwright protocol + PDCA broker
  knowledge loop.
- `playwright-studio` — MCP tools for headed browser co-piloting and screenshot capture.
- `.agents/rules/root_cause_and_escalation.md` — HITL escalation via KDE Connect.
