#!/usr/bin/env bash
# Daily checkpoint commit for InvestmentHomelab.
# Stage the day's changes (secrets/sessions/DBs are gitignored) and commit on the
# CURRENT branch. Never touches `main`/`master` (human-owned — docs/agent/kanban_operating_model.md §5).
#
# Usage:
#   bash scripts/daily_commit_checkpoint.sh            # real commit
#   bash scripts/daily_commit_checkpoint.sh --dry-run  # show what WOULD be committed, no write
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

dry_run=0
[ "${1:-}" = "--dry-run" ] && dry_run=1

# 1. Nothing to do -> clean exit.
if [ -z "$(git status --porcelain)" ]; then
  echo "DAILY-COMMIT: clean tree, nothing to commit"
  exit 0
fi

# 2. Fail-closed: never commit secrets / sessions / DBs (belt-and-suspenders over .gitignore).
if git status --porcelain | grep -E '\.env$|session_state|storage_state|\.db$|\.har$|\.sqlite' >/dev/null; then
  echo "DAILY-COMMIT: ABORT — forbidden file would be committed:" >&2
  git status --porcelain | grep -E '\.env$|session_state|storage_state|\.db$|\.har$|\.sqlite' >&2
  exit 1
fi

# 3. `main`/`master` is human-owned — refuse to commit there.
branch="$(git branch --show-current)"
if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  echo "DAILY-COMMIT: on '$branch' — skipping (main is human-owned)"
  exit 0
fi

# 4. Stage everything (tracked + untracked, honours .gitignore).
if [ "$dry_run" -eq 1 ]; then
  echo "DAILY-COMMIT (dry-run): would commit on '$branch':"
  git add -A --dry-run
  exit 0
fi

git add -A
git commit -m "chore(daily): checkpoint $(date +%F)"

echo "DAILY-COMMIT: committed on '$branch' — $(git rev-parse --short HEAD)"
