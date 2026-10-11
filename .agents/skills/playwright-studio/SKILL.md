---
name: playwright-studio
description: Interactive Playwright MCP Studio for TradeMan automation, live UI co-piloting, and continuous workflow learning.
---

# Playwright Studio Skill

This skill guides the AI Agent and User to collaborate interactively in automating TradeMan via the `playwright-homelab` MCP server.

## Overview & The 4-Stage Learning Loop

1. **Stage 1: Interactive Learn (Co-pilot)**
   - Launch visible Google Chrome (`browser_open(headed=true)`).
   - Inspect live DOM structure (`browser_snapshot`).
   - Interact with TradeMan with user watching and commenting (`browser_click`, `browser_type`, `browser_wait_for`).
   - Buffer verified steps (`record_workflow_step`).

2. **Stage 2: Markdown Specification Runbook**
   - Save the buffered steps into a standardized runbook (`save_learned_workflow`).
   - Runbooks live in `learned_workflows/<name>.md`.
   - Markdown documents are version-controlled, human-readable, and easily edited.

3. **Stage 3: Autonomous Execution**
   - Background tasks / schedulers invoke `workflow_run_autonomous(name="<name>")`.
   - Engine reads the markdown table and executes sequentially with headless or headed Chrome.

4. **Stage 4: Anomaly Detection & Re-Learn**
   - If TradeMan updates its DOM, a selector is missing, or unexpected modals appear:
     1. Captures full diagnostic screenshot into `data/screenshots/anomalies/`.
     2. Logs anomaly to SQLite database (`WorkflowAnomaly` model).
     3. Sends immediate alert to LINE notify/push with error details.
     4. Marks status as `NEEDS_RELEARN`.
     5. Prompts the user to re-open IDE co-pilot session to update the `.md` runbook.

---

## MCP Server Tools Reference

### Browser Control Tools
- `browser_open`: Opens visible Chrome or resumes existing session from `data/session_state.json`.
- `browser_navigate`: Navigates to a specific URL (e.g. TradeMan SBL or Portfolio page).
- `browser_screenshot`: Captures high-res verification screenshot.
- `browser_snapshot`: Extracts interactive elements with clean CSS selectors and visible text.
- `browser_click`: Clicks element by selector or text with automatic popup dismiss.
- `browser_type`: Fills input with human-like typing delays.
- `browser_evaluate`: Evaluates arbitrary JavaScript in active page.
- `browser_wait_for`: Waits for element visibility or timeout.

### TradeMan & Learning Loop Tools
- `trademan_check_session`: Checks session cookies, equity, and SET index.
- `record_workflow_step`: Buffers an action (`CLICK`, `TYPE`, `WAIT`, `NAVIGATE`, `CHECK`) into the learning session.
- `save_learned_workflow`: Compiles buffered steps into `learned_workflows/<name>.md`.
- `workflow_run_autonomous`: Runs a workflow spec autonomously from markdown.
- `workflow_list`: Lists all available `.md` workflows.
- `workflow_get_anomalies`: Lists all workflows currently requiring re-learning (`NEEDS_RELEARN`).
