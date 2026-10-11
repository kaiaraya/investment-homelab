#!/usr/bin/env bash
# ============================================================================
# Investment Homelab - MCP stdio server launcher wrapper
# ============================================================================
# PURPOSE (RCA  2026-10-06, Gate D incident):
#   The IDE/Cline MCP client spawns stdio MCP servers with a *sanitized* env,
#   so the children inherited neither DISPLAY nor XAUTHORITY. As a result every
#   headed Playwright step failed with:
#       "Missing X server or $DISPLAY"  /  "Authorization required, but no
#        authorization protocol specified"
#   This wrapper re-injects the desktop display env (DISPLAY=:0 per repo
#   convention in scripts/start_homelab.py Stage 2) and resolves the *current*
#   GNOME/mutter Xwayland auth file, which GNOME regenerates with a random
#   suffix on every login (/run/user/<uid>/.mutter-Xwaylandauth.XXXXXX).
#   Resolving it dynamically keeps headed browser automation working across
#   reboots/logins without any manual config edit (self-healing).
#
#   It ALSO re-injects the *user session D-Bus* (XDG_RUNTIME_DIR +
#   DBUS_SESSION_BUS_ADDRESS) which gdbus / KDE Connect need for SMS-OTP
#   capture (ref KDE-RCA-007). Without it, every `gdbus call --session` fails
#   and the OTP is never captured -> broker login stalls right after Krungsri
#   sends the SMS ("SMS arrived but browser never lands on the post-login page").
#
# USAGE (from cline_mcp_settings.json):
#   "command": ".../scripts/mcp_launch.sh",
#   "args": ["-m", "app.mcp.server"]        # or app.mcp.mcp_server
# ============================================================================
set -uo pipefail

PROJECT_DIR="/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
cd "$PROJECT_DIR" || exit 1

# 1) DISPLAY - keep an explicit value if the client passed one; else repo default.
export DISPLAY="${DISPLAY:-:0}"

# 2) XAUTHORITY - always prefer the *live* GNOME/mutter Xwayland cookie (correct
#    for the current session); fall back to an inherited/stable ~/.Xauthority.
#    NOTE: an inherited XAUTHORITY may be stale (~/.Xauthority carries an old
#    ":10" entry), so we deliberately override it when a mutter cookie exists.
_mutter="$(ls -t /run/user/"$(id -u)"/.mutter-Xwaylandauth.* 2>/dev/null | head -n1 || true)"
if [ -n "${_mutter}" ] && [ -r "${_mutter}" ]; then
  export XAUTHORITY="${_mutter}"
elif [ -z "${XAUTHORITY:-}" ] || [ ! -r "${XAUTHORITY:-/nonexistent}" ]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi

# 3) Ensure a usable HOME (Chrome / Playwright expect it).
export HOME="${HOME:-/home/araya-sawasdichai}"

# 4) XDG_RUNTIME_DIR + DBUS_SESSION_BUS_ADDRESS - the *user* session bus is
#    required by gdbus / KDE Connect for SMS-OTP capture (KDE-RCA-007: without
#    it every `gdbus call --session` fails -> phone reported OFFLINE and the OTP
#    is never captured, so broker login stalls after the SMS is sent). The
#    IDE-spawned env may omit these, so self-heal from the live per-user runtime
#    dir -- same self-healing pattern as the XAUTHORITY cookie above.
_uid="$(id -u)"
if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -d "${XDG_RUNTIME_DIR:-/nonexistent}" ]; then
  [ -d "/run/user/${_uid}" ] && export XDG_RUNTIME_DIR="/run/user/${_uid}"
fi
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "/run/user/${_uid}/bus" ]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${_uid}/bus"
fi

# 5) WAYLAND_DISPLAY - inherit if present; else default when the socket exists.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -S "/run/user/${_uid}/wayland-0" ]; then
  export WAYLAND_DISPLAY="wayland-0"
fi

exec "$PROJECT_DIR/.venv/bin/python" "$@"
