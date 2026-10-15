#!/usr/bin/env python3
"""
Cline Kanban hub-daemon shim installer — machine-local stopgap (KB-RCA-001).
===========================================================================
`kanban@0.1.70` (และ 0.1.40..0.1.70 ทุกตัว) ไม่ ship `dist/entry.js` ที่ `dist/cli.js`
spawn ออกมา (`node <pkg>/dist/entry.js`) → hub daemon start ไม่ขึ้น (`MODULE_NOT_FOUND`
crash-loop ใน `~/.cline/data/logs/hub-daemon.log`) → `kanban task start` ค้าง ~30 วิ
แล้ว session จบเป็น `cancelled` / `interrupted` กลางเทิร์น
ซ้อนกับ bug ตัวที่ 2: `@clinebot/core` daemon entry อ้าง global `AI` (Vercel AI SDK)
ตอน module-evaluation → `ReferenceError: AI is not defined`
Upstream: cline/kanban#495, cline/kanban#590 (ยังไม่ลง release ใด ๆ)
รายละเอียดเต็ม + หลักฐาน: rca/shared/rca_kanban_hub_daemon.md

bug ตัวที่ 3 (KB-RCA-002): แม้ daemon ขึ้นแล้ว การ์ดใหม่ยังตายด้วย
`AI_MissingToolResultsError` ("Tool results are missing for tool calls ...") เพราะ
`@clinebot/agents` รัน tool แบบ `Promise.all` เมื่อ `maxParallelToolCalls >= 2`
(kanban ฝัง default 8, ไม่มี config ให้ผู้ใช้ตั้ง) → patch ให้เป็น sequential
Upstream: cline/kanban#232 (ยัง open) — ดู SEQUENTIAL patch ด้านล่าง

สคริปต์นี้เขียน shim กลับให้อัตโนมัติ — **รันซ้ำทุกครั้งหลัง `npm i -g kanban`
หรือ npm upgrade** จนกว่าจะมี release > 0.1.70 ที่ ship ไฟล์เอง

Usage:
  .venv/bin/python scripts/kanban/install_entry_shim.py --check     # ดูสถานะ ไม่เขียน
  .venv/bin/python scripts/kanban/install_entry_shim.py             # ติดตั้ง/ซ่อม
  .venv/bin/python scripts/kanban/install_entry_shim.py --smoke     # + ลองสตาร์ท daemon จริง
  .venv/bin/python scripts/kanban/install_entry_shim.py --no-sequential-tools
  .venv/bin/python scripts/kanban/install_entry_shim.py --json

Exit code: 0 = ติดตั้งแล้ว/เป็นปัจจุบัน · 1 = ยังต้องแก้ (หรือ syntax/smoke ไม่ผ่าน)

หมายเหตุความปลอดภัย: ทำงานกับไฟล์ในเครื่องเท่านั้น · ไม่แตะ `.env` · ไม่ login ·
ไม่ยิง OTP/SMS · ไม่เรียก broker ใด ๆ ⇒ ปลอดภัยพอจะรันใน background job (Invariant 7/9)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

SHIM_FILENAME = "entry.js"
DEFAULT_SMOKE_PORT = 45999
UPSTREAM_ISSUES = ("cline/kanban#495", "cline/kanban#590")

# Single source of truth ของ shim — ติดตั้งไฟล์นี้ลง <npm-global>/kanban/dist/entry.js
SHIM_JS = """\
// ---------------------------------------------------------------------------
// Local stopgap shim — NOT part of the upstream published package.
//
// Upstream issues: cline/kanban#495 and cline/kanban#590
//   1. kanban@0.1.70 (and 0.1.40..0.1.70) ship dist/ without entry.js, while
//      dist/cli.js spawns `node <pkg>/dist/entry.js` -> MODULE_NOT_FOUND
//      (hub-daemon.log crash-loop).
//   2. @clinebot/core's hub daemon entry references a bare global `AI`
//      (the Vercel AI SDK namespace) at module-evaluation time, and nothing
//      defines it in a standalone `node dist/entry.js` process ->
//      ReferenceError: AI is not defined.
//
// Fix: bootstrap globalThis.AI from the installed `ai` package FIRST, then
// dynamically import the real daemon entry. Order matters: a static
// `export * from` would be hoisted above this body and evaluate the core
// entry before the global exists.
//
// Safe to delete once a published kanban release ships dist/entry.js itself.
// ---------------------------------------------------------------------------
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

if (typeof globalThis.AI === "undefined") {
  try {
    globalThis.AI = require("ai");
  } catch {
    globalThis.AI = await import("ai");
  }
}

await import("@clinebot/core/hub/daemon-entry");
"""


# --------------------------------------------------------------------------- #
# Sequential-tool-execution patch (KB-RCA-002 · cline/kanban#232)
# --------------------------------------------------------------------------- #
# `@clinebot/agents@0.0.38` (dependency ของ @clinebot/core ที่ kanban 0.1.70 ลากมา)
# เลือกเส้นทาง execute tool ใน method `executeToolCalls` แบบนี้ (minified):
#
#   if (this.config.toolExecution === "parallel")
#     return Promise.all(i.map((v) => this.executePreparedTool(v)));
#   let o = []; for (let v of i) o.push(await this.executePreparedTool(v)); return o;
#
# default ในตัว agent เองคือ "sequential" แต่ `dist/cli.js` ของ kanban ฝัง zod
# `maxParallelToolCalls` default = 8 (ไม่มี config/flag ให้ผู้ใช้ตั้ง) → resolver
# `f >= 2 ? "parallel" : "sequential"` → เข้าเส้นทาง Promise.all → พอเทิร์นเดียวมี
# tool call หลายอัน ผลลัพธ์ (`tool_result`) ไม่ถูกผูกกลับเข้า history →
# Vercel AI SDK `convertToLanguageModelPrompt` โยน `AI_MissingToolResultsError`
# ("Tool results are missing for tool calls: ...") → retry → "6 consecutive mistakes"
# → session จบ `status: failed` / `exit_code: 1` โดย transcript ไม่โชว์สาเหตุ
#
# Patch = ตัดเส้นทาง Promise.all ออก (เหลือ sequential ที่ SDK รองรับอยู่แล้ว) แล้วฝัง
# marker ไว้เช็ค idempotency · ปลอดภัย: tool ทุกตัวยังรันครบ เพียง await ทีละตัว
# ต้องรันซ้ำหลัง `npm i -g kanban` ทุกครั้ง (ไฟล์อยู่ใน node_modules)
AGENTS_LOOP_REL = Path("node_modules") / "@clinebot" / "agents" / "dist" / "index.js"
PARALLEL_BRANCH = ('if(this.config.toolExecution==="parallel")'
                   'return Promise.all(i.map((v)=>this.executePreparedTool(v)));')
SEQ_MARKER = "/*kb-seq-tools*/"
SEQ_UPSTREAM_ISSUES = ("cline/kanban#232",)


# --------------------------------------------------------------------------- #
# Locators (pure-ish: filesystem + optional subprocess for `npm root -g`)
# --------------------------------------------------------------------------- #
def npm_global_root(npm_bin: str = "npm", runner: Callable = subprocess.run) -> Optional[Path]:
    """คืน global node_modules root — ลอง `npm root -g` ก่อน แล้ว fallback จาก path ของ node."""
    if shutil.which(npm_bin):
        try:
            proc = runner([npm_bin, "root", "-g"], capture_output=True, text=True, timeout=30)
            out = (proc.stdout or "").strip()
            if proc.returncode == 0 and out:
                return Path(out)
        except Exception:  # noqa: BLE001 - fallback ด้านล่าง
            pass
    node_bin = shutil.which("node")
    if node_bin:
        # <prefix>/bin/node -> <prefix>/lib/node_modules
        return Path(node_bin).resolve().parent.parent / "lib" / "node_modules"
    return None


def kanban_package_dir(root: Path) -> Path:
    return Path(root) / "kanban"


def dist_dir(root: Path) -> Path:
    return kanban_package_dir(root) / "dist"


def shim_path(root: Path) -> Path:
    return dist_dir(root) / SHIM_FILENAME


def core_entry_candidates(root: Path) -> List[Path]:
    """path ที่เป็นไปได้ของ @clinebot/core hub daemon entry (nested หรือ hoisted)."""
    rel = Path("node_modules") / "@clinebot" / "core" / "dist" / "hub" / "daemon" / "entry.js"
    nested = kanban_package_dir(root) / rel
    hoisted = Path(root) / rel
    return [nested, hoisted] if nested != hoisted else [nested]


def core_entry_path(root: Path) -> Optional[Path]:
    for cand in core_entry_candidates(root):
        if cand.is_file():
            return cand
    return None


def ai_package_dir(root: Path) -> Optional[Path]:
    for cand in (kanban_package_dir(root) / "node_modules" / "ai", Path(root) / "ai"):
        if (cand / "package.json").is_file():
            return cand
    return None


def shim_state(root: Path) -> str:
    """'missing' = ไม่มีไฟล์ที่ cli.js เรียก · 'current' = ตรงกับ SHIM_JS · 'stale' = มีแต่คนละเวอร์ชัน."""
    entry = shim_path(root)
    if not entry.is_file():
        return "missing"
    try:
        return "current" if entry.read_text(encoding="utf-8") == SHIM_JS else "stale"
    except OSError:
        return "stale"


def agents_loop_candidates(root: Path) -> List[Path]:
    """path ที่เป็นไปได้ของ @clinebot/agents/dist/index.js (nested หรือ hoisted)."""
    nested = kanban_package_dir(root) / AGENTS_LOOP_REL
    hoisted = Path(root) / AGENTS_LOOP_REL
    return [nested, hoisted] if nested != hoisted else [nested]


def agents_loop_path(root: Path) -> Optional[Path]:
    for cand in agents_loop_candidates(root):
        if cand.is_file():
            return cand
    return None


def sequential_tools_state(root: Path) -> str:
    """'missing' = ไม่มี bundle · 'current' = patch แล้ว · 'needs-patch' = ยัง parallel · 'unknown-shape' = bundle เปลี่ยนรูป."""
    path = agents_loop_path(root)
    if path is None:
        return "missing"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unknown-shape"
    if PARALLEL_BRANCH in text:
        return "needs-patch"
    if SEQ_MARKER in text:
        return "current"
    return "unknown-shape"


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def syntax_check(entry: Path, node_bin: str = "node", runner: Callable = subprocess.run,
                 timeout: int = 60) -> Tuple[bool, str]:
    """`node --check <entry>` → (ok, ข้อความ). ไม่มี node ใน PATH = (False, เหตุผล)."""
    entry = Path(entry)
    if not entry.is_file():
        return False, f"ไม่พบไฟล์ {entry}"
    if not shutil.which(node_bin):
        return False, f"ไม่พบคำสั่ง `{node_bin}` ใน PATH"
    try:
        proc = runner([node_bin, "--check", str(entry)],
                      capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - รายงานเป็นผลลัพธ์ ไม่โยนต่อ
        return False, f"node --check ล้ม: {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return getattr(proc, "returncode", 1) == 0, out or "SYNTAX OK"


def build_smoke_cmd(node_bin: str, entry: Path, port: int, cwd: str) -> List[str]:
    """คำสั่งที่ CLI ของ kanban ใช้ spawn hub daemon (path เดียวกันเป๊ะ)."""
    return [node_bin, str(entry), "--cwd", str(cwd), "--port", str(port)]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    with socket.socket() as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def smoke(entry: Path, node_bin: str = "node", port: Optional[int] = None, timeout: int = 15,
          popen: Callable = subprocess.Popen) -> Dict:
    """
    สตาร์ท daemon จริงด้วยคำสั่งเดียวกับ cli.js ใน HOME/cwd ชั่วคราว (ไม่แตะ session จริง)
    ผ่าน = พอร์ตเปิดก่อน timeout และ process ไม่ตายด้วย MODULE_NOT_FOUND / AI is not defined
    """
    entry = Path(entry)
    if not entry.is_file():
        return {"ok": False, "reason": f"ไม่พบไฟล์ {entry}"}
    if not shutil.which(node_bin):
        return {"ok": False, "reason": f"ไม่พบคำสั่ง `{node_bin}` ใน PATH"}
    use_port = port or free_port()
    with tempfile.TemporaryDirectory(prefix="kb-shim-smoke-") as tmp:
        env = dict(os.environ, HOME=tmp)
        proc = popen(build_smoke_cmd(node_bin, entry, use_port, tmp), cwd=tmp, env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                     start_new_session=True)
        listening = False
        try:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if port_open(use_port):
                    listening = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
        try:
            tail = (proc.stdout.read() or "").strip()[-500:] if proc.stdout else ""
        except Exception:  # noqa: BLE001
            tail = ""
    result: Dict = {"ok": listening, "port": use_port, "exit_code": proc.returncode,
                    "output_tail": tail}
    if not listening:
        result["reason"] = ("daemon ออกก่อนพอร์ตเปิด (ดู output_tail)"
                            if proc.returncode is not None
                            else f"พอร์ต {use_port} ไม่เปิดภายใน {timeout}s")
    return result


# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #
def install(root: Path, *, dry_run: bool = False, node_bin: str = "node",
            verify_syntax: bool = True, runner: Callable = subprocess.run) -> Dict:
    """เขียน shim ลง dist/ ของ kanban (backup ของเดิมถ้ามี) แล้วตรวจ syntax ให้ด้วย."""
    root = Path(root)
    target_dir = dist_dir(root)
    entry = shim_path(root)
    state_before = shim_state(root)
    result: Dict = {
        "dist": str(target_dir),
        "entry": str(entry),
        "state_before": state_before,
        "action": "none",
        "backup": None,
        "syntax_ok": None,
        "syntax": None,
    }
    if not target_dir.is_dir():
        result.update(action="failed", reason=f"ไม่พบ dist ของ kanban: {target_dir}", ok=False)
        return result
    core = core_entry_path(root)
    ai_pkg = ai_package_dir(root)
    result["core_entry"] = str(core) if core else None
    result["ai_package"] = str(ai_pkg) if ai_pkg else None

    if state_before == "current":
        result["action"] = "already-current"
    elif dry_run:
        result["action"] = "would-write"
    else:
        if entry.is_file():
            backup = entry.with_name(f"{entry.name}.bak.{int(time.time())}")
            shutil.copy2(entry, backup)
            result["backup"] = str(backup)
        entry.write_text(SHIM_JS, encoding="utf-8")
        result["action"] = "written" if state_before == "missing" else "replaced"
        result["state_after"] = shim_state(root)

    if verify_syntax and not dry_run:
        ok_syntax, out = syntax_check(entry, node_bin=node_bin, runner=runner)
        result["syntax_ok"], result["syntax"] = ok_syntax, out

    ok_final = result["action"] in {"already-current", "would-write", "written", "replaced"}
    if result.get("syntax_ok") is False:
        ok_final = False
    if not dry_run and shim_state(root) != "current":
        ok_final = False
    result["ok"] = ok_final
    return result


# --------------------------------------------------------------------------- #
# Sequential tool execution (KB-RCA-002)
# --------------------------------------------------------------------------- #
def install_sequential_tools(root: Path, *, dry_run: bool = False, node_bin: str = "node",
                             verify_syntax: bool = True,
                             runner: Callable = subprocess.run) -> Dict:
    """
    บังคับให้ `@clinebot/agents` รัน tool แบบ sequential (ตัดเส้นทาง Promise.all ออก)
    — idempotent · backup ของเดิม · ไม่เดารูปแบบ bundle ที่ไม่รู้จัก (Anti-Mock)
    """
    root = Path(root)
    target = agents_loop_path(root)
    state_before = sequential_tools_state(root)
    result: Dict = {
        "file": str(target) if target else None,
        "state_before": state_before,
        "action": "none",
        "backup": None,
        "syntax_ok": None,
        "syntax": None,
    }
    if target is None:
        result.update(action="failed", ok=False,
                      reason="ไม่พบ @clinebot/agents/dist/index.js — ติดตั้ง kanban ก่อน")
        return result
    if state_before == "unknown-shape":
        result.update(action="failed", ok=False,
                      reason="bundle ของ @clinebot/agents เปลี่ยนรูปแบบ — patch ไม่ได้ (ห้ามเดา, รอ upstream)")
        return result

    if state_before == "current":
        result["action"] = "already-current"
    elif dry_run:
        result["action"] = "would-patch"
    else:
        text = target.read_text(encoding="utf-8")
        hits = text.count(PARALLEL_BRANCH)
        if hits != 1:
            result.update(action="failed", ok=False,
                          reason=f"เจอ parallel branch {hits} จุด (คาด 1) — ไม่เขียนไฟล์")
            return result
        backup = target.with_name(f"{target.name}.bak.{int(time.time())}")
        shutil.copy2(target, backup)
        result["backup"] = str(backup)
        target.write_text(text.replace(PARALLEL_BRANCH, SEQ_MARKER), encoding="utf-8")
        result["action"] = "patched"
        result["state_after"] = sequential_tools_state(root)

    if verify_syntax and not dry_run:
        ok_syntax, out = syntax_check(target, node_bin=node_bin, runner=runner)
        result["syntax_ok"], result["syntax"] = ok_syntax, out

    ok_final = result["action"] in {"already-current", "would-patch", "patched"}
    if result.get("syntax_ok") is False:
        ok_final = False
    if not dry_run and sequential_tools_state(root) != "current":
        ok_final = False
    result["ok"] = ok_final
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run(args) -> Dict:
    root = Path(args.npm_root) if getattr(args, "npm_root", None) else npm_global_root()
    summary: Dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "npm_root": str(root) if root else None,
        "upstream_issues": list(UPSTREAM_ISSUES),
        "sequential_tools_upstream_issues": list(SEQ_UPSTREAM_ISSUES),
        "rca": "rca/shared/rca_kanban_hub_daemon.md (KB-RCA-001, KB-RCA-002)",
    }
    if root is None:
        summary.update(ok=False, reason="หาตำแหน่ง global npm ไม่ได้ — ระบุ --npm-root เอง")
        return summary
    summary["kanban_dist_exists"] = dist_dir(root).is_dir()
    summary["install"] = install(root, dry_run=args.check, node_bin=args.node_bin,
                                 verify_syntax=not args.no_syntax)
    if getattr(args, "sequential_tools", True):
        summary["sequential_tools"] = install_sequential_tools(
            root, dry_run=args.check, node_bin=args.node_bin,
            verify_syntax=not args.no_syntax)
    if args.smoke and not args.check:
        summary["smoke"] = smoke(shim_path(root), node_bin=args.node_bin, port=args.port)
    summary["ok"] = bool(summary["install"].get("ok")) and \
        bool(summary.get("sequential_tools", {}).get("ok", True)) and \
        bool(summary.get("smoke", {}).get("ok", True))
    return summary


def _render(summary: Dict) -> str:
    inst = summary.get("install", {})
    lines = [f"Kanban hub-daemon shim — {summary.get('timestamp')}",
             f"  npm root : {summary.get('npm_root')}",
             f"  entry.js : {inst.get('entry')}",
             f"  state    : {inst.get('state_before')} -> {inst.get('action')}"
             + (f" (backup {inst['backup']})" if inst.get("backup") else "")]
    if inst.get("syntax") is not None:
        lines.append(f"  syntax   : {'OK' if inst.get('syntax_ok') else 'FAIL'} — {inst['syntax']}")
    if inst.get("core_entry") is None:
        lines.append("  WARN     : หา @clinebot/core hub daemon entry ไม่เจอ — shim จะ import ไม่ได้")
    if inst.get("ai_package") is None:
        lines.append("  WARN     : หา package `ai` ไม่เจอ — globalThis.AI จะไม่ถูก set")
    seq = summary.get("sequential_tools")
    if seq is not None:
        lines.append(f"  seq-tools: {seq.get('state_before')} -> {seq.get('action')}"
                     + (f" (backup {seq['backup']})" if seq.get("backup") else ""))
        if seq.get("syntax") is not None:
            lines.append(f"  seq syntax: {'OK' if seq.get('syntax_ok') else 'FAIL'} — {seq['syntax']}")
        if not seq.get("ok"):
            lines.append(f"  WARN     : sequential-tools patch — {seq.get('reason', 'ยังไม่ใช่ current')}")
    if "smoke" in summary:
        lines.append(f"  smoke    : {'OK' if summary['smoke'].get('ok') else 'FAIL'}"
                     f" (port {summary['smoke'].get('port')})")
    if summary.get("ok"):
        lines.append("  VERDICT  : OK (ติดตั้งแล้ว/เป็นปัจจุบัน)")
    else:
        lines.append(f"  VERDICT  : ACTION NEEDED — "
                     + (inst.get("reason") or (seq or {}).get("reason") or summary.get("reason", "")))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ติดตั้ง/ซ่อม Cline Kanban hub-daemon shim (machine-local stopgap, KB-RCA-001)")
    parser.add_argument("--check", action="store_true", help="ดูสถานะเท่านั้น ไม่เขียนไฟล์")
    parser.add_argument("--smoke", action="store_true",
                        help="สตาร์ท daemon จริงบนพอร์ตว่าง (HOME/cwd ชั่วคราว) เพื่อพิสูจน์ว่าไม่ล้ม")
    parser.add_argument("--port", type=int, default=None,
                        help="พอร์ตสำหรับ --smoke (ค่าเริ่มต้น: หาพอร์ตว่างอัตโนมัติ)")
    parser.add_argument("--npm-root", default=None,
                        help="ระบุ global node_modules เอง (ข้าม auto-detect)")
    parser.add_argument("--node-bin", default="node", help="path ของ node ที่จะใช้")
    parser.add_argument("--no-syntax", action="store_true", help="ข้าม node --check")
    parser.add_argument("--no-sequential-tools", dest="sequential_tools",
                        action="store_false", default=True,
                        help="ข้าม patch บังคับ sequential tool execution (KB-RCA-002)")
    parser.add_argument("--print-shim", action="store_true",
                        help="พิมพ์เนื้อหา shim แล้วออก (ไม่เขียนไฟล์)")
    parser.add_argument("--json", action="store_true", help="พิมพ์ผลแบบ JSON")
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    """แยกออกมาเพื่อให้ unit test เรียกได้โดยไม่ต้องรัน process จริง."""
    return build_parser().parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.print_shim:
        print(SHIM_JS)
        return 0
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else _render(summary))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
