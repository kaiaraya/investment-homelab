---
name: stepwise-approval
description: Co-pilot execution protocol — decompose work into small AI↔user steps,
  state the expected outcome before each step, capture a screenshot at each stage
  when a headed browser is in use, verify with real human interaction at every step
  (e.g. ping the phone and ask), and require human interaction whenever the agent
  cannot confidently proceed.
---

# Stepwise-Approval Co-Pilot Skill

This skill governs how the Agent executes multi-step work on InvestmentHomelab so
that the AI and the user **learn the correct workflow faster together**. It applies
to code changes, refactors, bug fixes, and any Playwright-driven browser automation.

---

## 1. Decompose into small steps (AI ↔ user, every step)

- Split each task into the smallest independently-verifiable steps
  (one function, one call-site edit, one browser action).
- Execute **EXACTLY one step**, then **STOP** and hand control back to the user.
- **Check in between every step.** Never batch unrelated changes and report only
  at the end — the user is involved between each step.

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

## 5. Verify with real human interaction at every step (not just unit tests)

- A passing unit test is **NOT** sufficient to declare a hardware/browser step
  verified. Do the real thing and ask the user to confirm the observable result.
- **KDE Connect / mobile bridge**: fire a real ping and ask whether it was seen:
  - `kdeconnect-cli -d <device_id> --ping-msg "Investment Homelab Bridge Active"`
  - then ask the user: **"did you see the ping on your phone?"**
  - If the phone is `paired` but `isReachable=false`, ask the user to unlock it /
    bring the KDE Connect app to the foreground first, then retry the ping.
- **Headed browser**: capture the screenshot (§3) **and** ask the user to confirm
  what they see on screen.
- Apply this at **every** step — never declare "verified" on an automated test alone
  when the step touched real hardware or a visible browser.

---

## Cross-references

- `watch-and-learn` — 4-Tier Self-Annealing Playwright protocol + PDCA broker
  knowledge loop.
- `playwright-studio` — MCP tools for headed browser co-piloting and screenshot capture.
- `.agents/rules/root_cause_and_escalation.md` — HITL escalation via KDE Connect.
