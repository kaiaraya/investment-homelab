#!/usr/bin/env bash
# Investment Homelab Gateway Stop Script
echo "=========================================================="
echo "🛑 Stopping Investment Homelab Services..."
echo "=========================================================="

pkill -f "uvicorn app.main:app"
pkill -f "chrome.*--remote-debugging-port"

echo "✅ All Investment Homelab services and background browsers stopped."
