#!/usr/bin/env bash
# ==============================================================================
# Google Jules Cloud VM — Environment Setup Script (InvestmentHomelab)
# Paste or invoke `bash scripts/jules_setup.sh` in Jules Environment Setup.
# Safe by design: runs inside an isolated Cloud VM with dummy .env values only
# (never touches live broker sessions, OTP, or production SQLite).
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

echo "[jules_setup] Preparing Python virtual environment (.venv)..."
if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip setuptools wheel -q
.venv/bin/python -m pip install -r requirements.txt -q

if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
    echo "[jules_setup] Created safe dummy .env from .env.example (Cloud VM test mode)."
fi

mkdir -p data/logs data/screenshots

echo "[jules_setup] Running dry-run verification sanity check..."
.venv/bin/python scripts/verify_changes.py --dry-run app/main.py
echo "[jules_setup] READY — Jules Cloud VM environment is configured."
