#!/usr/bin/env python3
"""STEP 0a probe — LINE webhook / queue / push path (read-only commands only).

Loop-1 discipline: probe the live path before any witness card, write every stage
to disk the moment it is captured.

Stages
  1. signed EMPTY body           -> expect 200 {"note":"verify_ping"}   (tunnel + app alive)
  2. bad signature               -> expect 400                         (signature really enforced)
  3. signed /help text event     -> expect 200, job enqueued, result PUSHED to the admin chat
  4. signed /sbl text event      -> expect 200, job enqueued (DRY_RUN read path)
  5. gateway log tail            -> proves queue worker + push delivery lines

Never sends a trade command. Run with the gateway up and DRY_RUN_MODE=true.
Usage:
    PYTHONPATH=. .venv/bin/python scripts/probe_line_webhook.py \
        --target https://line.a14s.dev/api/v1/webhook/line
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
EVID_DIR = ROOT / "docs" / "handoff" / "evidence" / "loop2"
LOG_CANDIDATES = [Path("/tmp/hermes-gateway-loop2.log")]


def sign(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def text_event(text: str, user_id: str, reply_token: str) -> dict:
    return {
        "destination": "U_probe",
        "events": [
            {
                "type": "message",
                "mode": "active",
                "timestamp": int(time.time() * 1000),
                "source": {"type": "user", "userId": user_id},
                "webhookEventId": f"probe-{int(time.time()*1000)}",
                "deliveryContext": {"isRedelivery": False},
                "replyToken": reply_token,
                "message": {"type": "text", "id": "1", "text": text},
            }
        ],
    }


def log_tail(lines: int = 40) -> str:
    for p in LOG_CANDIDATES:
        if p.exists():
            return "\n".join(p.read_text(errors="replace").splitlines()[-lines:])
    return "(no gateway log found — pass --log <path>)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="http://127.0.0.1:8000/api/v1/webhook/line")
    ap.add_argument("--log", default=None)
    ap.add_argument("--skip-sbl", action="store_true", help="skip stage 4 (SBL read) ")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    secret = os.getenv("LINE_CHANNEL_SECRET") or ""
    admin = os.getenv("LINE_ADMIN_USER_ID") or ""
    if not secret or not admin:
        print("✗ LINE_CHANNEL_SECRET / LINE_ADMIN_USER_ID missing in .env")
        return 2
    if args.log:
        LOG_CANDIDATES.insert(0, Path(args.log))

    EVID_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evid: dict = {
        "probe": "line_webhook",
        "target": args.target,
        "started": stamp,
        "dry_run_mode": os.getenv("DRY_RUN_MODE"),
        "trading_mode": os.getenv("TRADING_MODE"),
        "stages": {},
    }
    path = EVID_DIR / f"line_probe_{stamp}.json"

    def save() -> None:
        path.write_text(json.dumps(evid, ensure_ascii=False, indent=2))
        print(f"  ↳ dump {path}")

    with httpx.Client(timeout=40) as c:
        # --- stage 1: signed empty body -------------------------------------
        body = b""
        r = c.post(args.target, content=body, headers={"X-Line-Signature": sign(secret, body)})
        evid["stages"]["1_verify_ping"] = {"status": r.status_code, "body": r.text[:300]}
        print(f"[1] verify ping -> {r.status_code} {r.text[:120]}")
        save()

        # --- stage 2: bad signature ----------------------------------------
        body = json.dumps(text_event("/help", admin, "probe-bad")).encode()
        r = c.post(args.target, content=body, headers={"X-Line-Signature": "AAAA"})
        evid["stages"]["2_bad_signature"] = {"status": r.status_code, "body": r.text[:300]}
        print(f"[2] bad signature -> {r.status_code} (expect 400)")
        save()

        # --- stage 3: signed /help ------------------------------------------
        body = json.dumps(text_event("/help", admin, "probe-help")).encode()
        t0 = time.monotonic()
        r = c.post(args.target, content=body, headers={"X-Line-Signature": sign(secret, body)})
        elapsed = round(time.monotonic() - t0, 3)
        evid["stages"]["3_help"] = {"status": r.status_code, "elapsed_s": elapsed, "body": r.text[:600]}
        print(f"[3] /help -> {r.status_code} in {elapsed}s :: {r.text[:200]}")
        save()

        time.sleep(4)
        evid["stages"]["3_help_log"] = log_tail(30)
        save()

        # --- stage 4: signed /sbl (read path, DRY_RUN) -----------------------
        if not args.skip_sbl:
            body = json.dumps(text_event("/sbl", admin, "probe-sbl")).encode()
            t0 = time.monotonic()
            r = c.post(args.target, content=body, headers={"X-Line-Signature": sign(secret, body)})
            elapsed = round(time.monotonic() - t0, 3)
            evid["stages"]["4_sbl"] = {"status": r.status_code, "elapsed_s": elapsed, "body": r.text[:600]}
            print(f"[4] /sbl -> {r.status_code} in {elapsed}s :: {r.text[:200]}")
            save()
            time.sleep(6)
            evid["stages"]["4_sbl_log"] = log_tail(60)
            save()

    evid["finished"] = datetime.now().strftime("%Y%m%d_%H%M%S")
    save()
    print(f"\n✔ evidence: {path}")
    print("  NEXT: open the LINE chat — every stage that returned CLI_QUEUED must appear there as a pushed message.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
