#!/usr/bin/env bash
# Investment Homelab Gateway Launcher Script
PROJECT_DIR="/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
cd "$PROJECT_DIR" || exit 1

echo "=========================================================="
echo "⚡ Starting Investment Homelab Sequential Orchestrator..."
echo "📍 Stage 1: KDE Connect Hardware Bridge Probe (Mi 10T) — mandatory OTP gate (offline → degrade + skip broker logins)"
echo "📍 Stage 2: Krungsri TradeMan Session Gate (Zero-OTP / 2FA)"
echo "📍 Stage 3: Liberator WebTrade Session Gate (cached session, optional)"
echo "📍 Stage 4: Launch FastAPI Gateway & Web Cockpit (/console)"
echo "=========================================================="

# Execute Sequential 4-Stage Startup & Readiness Orchestrator
# Stage 1: KDE Connect Hardware Bridge Probe (mandatory SMS-OTP-readiness gate; offline → degrade + skip broker logins)
# Stage 2: Krungsri TradeMan Session Gate (Zero-OTP or Headed Login, LINE escalation on failure)
# Stage 3: Liberator WebTrade Session Gate (cached session only, no headed login)
# Stage 4: Launch FastAPI Server & Open /console Cockpit
exec "$PROJECT_DIR/.venv/bin/python3" "$PROJECT_DIR/scripts/start_homelab.py" "$@"

