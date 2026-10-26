# Kanban Operating Model — InvestmentHomelab Development Loop

> **Canonical SOP** (replaces `workflow_playbook.md`, `local_handoff.md`, `handoff_protocol.md`,
> `token_workflow.md` — those are now 3-line redirects). Project rules: `.hermes.md`.
> Migration card: `docs/handoff/TASK-hermes-only-migration.md`.

## 1. Lanes, models, and who writes what

| Lane | Assignee (Hermes profile) | Model | Writes |
|---|---|---|---|
| **P** plan / verdict | `default` | `gemini-4-argon` | `directive/*.md`, card body, `## Planner Analysis`, board state |
| **0a** probe (read-only) | `default` desktop, headed | `gemini-3.8-flash` | `## DOM / API Contract` |
| **B** build (T0/T1) | `homelab-build` | T0 `gemini-3.8-flash` · T1 `gemini-3.1-pro` | code (`app/**`, `tests/**`), `## Worker Report` |
| **R** review | `homelab-review` | `gemini-3.1-pro` | `## Review Report`, verdict |
| **H** human witness (T2) | `default` desktop, headed | `gemini-3.8-flash` | `## Verification & Stepwise Approval`, `### Live Evidence`, squash `main` |
| **C** Colab | `homelab-colab` | `gemini-3.8-flash` | notebook/artifact on Drive, `## Colab Report` |
| **T** triage | specifier (aux `deepseek-pro`) | per aux config | card body from an idea |

Model selection rule of thumb: **money/logic errors are expensive ⇒ T1 and review run `gemini-3.1-pro`;
volume work (code T0, DOM scraping, pipelines) runs `gemini-3.8-flash`; planning runs `gemini-4-argon`.**
Per-card override: `hermes kanban --board investment-homelab set-model <id> <model>` (applies at next dispatch).

## 2. Card lifecycle

```
create --triage ──► specifier fills body ──► todo ──► ready ──► running ──► review ──► done
        (idea)                                   ▲          (plan)      (build)   (review)  (human)
                                                 └── blocked ◄── T2 / needs-probe / needs-human
```

| STEP | Who | Action | Status |
|---|---|---|---|
| 0 | P | Write the card: goal · files · verify command · done-when · tier · `Probe:` · `Lane:` | `triage`/`todo` |
| 0a | human + P | If the card touches broker DOM/XHR: read-only headed probe → `## DOM / API Contract` | `blocked` → `ready` |
| 1 | human | gate #1: approve the card (plan + probe evidence) | `ready` |
| 2a | B | implement + unit test + `## Worker Report` | `running` |
| 2b | R | audit `git diff`, re-run `verify_changes.py`, `## Review Report` + verdict | `review` |
| 3 | human + P | T2 only: live witness → `## Verification & Stepwise Approval` + `### Live Evidence` | `review` |
| 4 | human | gate #2: squash/merge to `main` | `done` |
| 5 | P | `## Planner Analysis` → next cards / triage for leftovers | → STEP 0 |

Commands: `hermes kanban --board investment-homelab {list,show,create,edit,comment,block,unblock,claim,complete,set-model,dispatch}`.
`--board` goes **before** the verb. `create` takes the title positionally (`--title` is rejected).

## 3. Card body contract (minimum a worker can act on)

```markdown
- Lane: homelab-build | homelab-review | homelab-colab | default
- Tier: 🟢 T0 | 🟡 T1 | 🔴 T2
- Probe: NONE | PROBE_NEEDED | PROBE_DONE
- Verify: .venv/bin/python scripts/verify_changes.py <files>
- Done when: <observable outcome>
## Scope — files allowed to change
## Context map (file · symbol/lines · why)
## Steps (atomic, one action each, each with its own verify)
## Out of scope
```

Full template: `docs/handoff/_TEMPLATE.md`. A worker reads **only its card body**, so the body must be
self-contained — never "see the planning chat".

## 4. Gates

1. **Probe gate** — `Probe: PROBE_DONE` + `## DOM / API Contract` before any card that touches broker
   DOM/XHR leaves `blocked`. Read-only, headed, human confirms the account/landing.
2. **Live-money gate (T2)** — dispatch only when `DRY_RUN_MODE=false` for that run, browser headed, and
   the human is watching and said "go". Card carries `## Witness Session` (date · who · side/symbol/vol/price
   · go-ahead). Otherwise keep `blocked`. Never flip `DRY_RUN_MODE` to make a test pass.
3. **Verify gate** — `verify_changes.py` PASS is the entry condition for `review`; `--full` once at close.
4. **Merge gate** — only the human merges `main` (gate #2). Workers never touch `main`.

`scripts/preflight_card.py` mechanically checks 1, 2, and the secrets-in-index rule before dispatch.

## 5. Git conventions

- Work on a card branch or a worktree: `--workspace worktree:<path> --branch wt/<card-id>`.
- Commit format: `TASK-<slug>: <type>(<scope>): <summary>`.
- Stage only that card's files — the tree routinely carries other workstreams; never `git add -A`.
- Before any push/merge: no `.env`, `*session*.json`, `*.db`, `data/screenshots/*.png` in the index.
- `main` is human-owned; workers leave a clean uncommitted diff or a card branch.

## 6. Tooling quick reference

| Need | Command |
|---|---|
| Board ops | `hermes kanban --board investment-homelab …` |
| Pre-dispatch check | `.venv/bin/python scripts/preflight_card.py --card docs/handoff/TASK-<slug>.md` |
| Verify changed files | `.venv/bin/python scripts/verify_changes.py <files>` (`--dry-run`, `--full`) |
| Read-only live state | `.venv/bin/python scripts/mcp_probe.py <tool> '<json>'` (gateway must be up) |
| Persistent CDP probe | `.venv/bin/python scripts/broker_probe.py --broker kss|liberator {start-session,status,probe,handoff}` |
| Daily readiness | `.venv/bin/python scripts/daily_readiness.py` (0=GO, 1=NO-GO) |
| Gateway | `hermes gateway status` · restart the app: uvicorn `app.main:app` (never `--reload`) |
| Colab | `colab new|install|exec|drivemount|download|log` (skill: `colab-offload`) |
| Token report | `.venv/bin/python scripts/token_report.py --since <date>` |

## 7. Vision (known limitation)

`auxiliary.vision` is configured (`gemini-3.8-flash`) but the `antigravity-subscription-directsdk` plugin
flattens message content to a string (`prompt.py:44`), so images never reach a model; the bare `agy` CLI
returns 429 (separate credit pool). **Vision works only after adding `GEMINI_API_KEY` and setting
`auxiliary.vision.provider=gemini` + `model=gemini-2.5-flash`.** Until then: read DOM text, store screenshot
paths as evidence, and never claim an image was inspected.

## 8. Token discipline (kept from the retired SOP)

- Ranged reads only; grep the CODEMAP instead of opening it; trim output (`pytest -q --tb=line`, `| tail -40`).
- One card = one session. Context > 60K → compact, then continue in a new session.
- `token_guard` hooks (`.cline/hooks`, `.agents/hooks.json`) are retired; Hermes' own loop guardrails and
  compression apply. `scripts/hooks/token_guard.py` is kept only for its unit test.

## 9. History

The retired 4-agent hybrid loop (Argon / Flash 3.8 / Jules Cloud VM / Cline plugin), its STEP 0–5 tables,
`jules_bridge.py` workflow, and the branch handoff mechanics are preserved verbatim in
`docs/agent/full/` and `scripts/legacy/`. Read them only to explain history — never to run work.
