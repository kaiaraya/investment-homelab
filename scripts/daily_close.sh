#!/usr/bin/env bash
# daily_close.sh — one command to close the trading day safely.
#   full suite -> regenerate board mirror -> reconcile (no uncommitted CODE) -> backup.
# Safe by design: never commits, never deletes, never touches git history.
# Usage: scripts/daily_close.sh [--no-tests]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY=".venv/bin/python"
RUN_TESTS=1
for a in "$@"; do [ "$a" = "--no-tests" ] && RUN_TESTS=0; done
fail=0
echo "===== DAILY CLOSE $(date '+%F %T %Z') ====="

# 1) full suite (run once at close, per operating model §4 verify gate)
if [ "$RUN_TESTS" = "1" ]; then
  echo "--- [1/4] full test suite ---"
  if $PY scripts/verify_changes.py --full; then echo "[OK] suite green"; else echo "[FAIL] suite RED"; fail=1; fi
else
  echo "--- [1/4] suite skipped (--no-tests) ---"
fi

# 2) regenerate the readable board mirror
echo "--- [2/4] regenerate board snapshot ---"
if $PY scripts/board_snapshot.py; then echo "[OK] board snapshot"; else echo "[FAIL] board snapshot"; fail=1; fi

# 3) reconcile: CODE must be committed. Board mirror + daily ledger are allowed to be dirty
#    (they are regenerated docs, not card work; this is the exact failure seen 2026-10-30).
echo "--- [3/4] tree reconcile (code must be committed) ---"
dirty=$(git status --porcelain \
  | grep -v '^?? .hermes/' \
  | grep -v 'docs/board/loop_board.md' \
  | grep -v 'docs/handoff/DAILY-' || true)
if [ -n "$dirty" ]; then
  echo "[WARN] uncommitted code / unexpected files:"; echo "$dirty"; fail=1
else
  echo "[OK] no uncommitted code"
fi

# 4) backup tracked patch + untracked files (never destructive)
echo "--- [4/4] backup ---"
BK="$HOME/.hermes/cache/scratch/homelab-backup-$(date +%Y%m%d)"
mkdir -p "$BK"
git diff > "$BK/tracked.patch" 2>/dev/null || true
git ls-files --others --exclude-standard > "$BK/untracked.txt"
tar czf "$BK/untracked.tgz" -T "$BK/untracked.txt" 2>/dev/null || true
echo "[OK] backup -> $BK"

echo "===== DONE fail=$fail $(date '+%F %T %Z') ====="
if [ "$fail" = "0" ]; then echo "STATUS: CLEAN"; else echo "STATUS: REVIEW NEEDED"; fi
exit $fail
