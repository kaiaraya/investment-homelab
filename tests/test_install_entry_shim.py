"""
Unit tests for scripts.kanban.install_entry_shim (KB-RCA-001).

Fix ที่ทดสอบ: `kanban@0.1.70` (ทุกเวอร์ชันที่ publish) ไม่ ship `dist/entry.js` ที่
`dist/cli.js` เรียกออกมา → hub daemon spawn ไม่ขึ้น (`MODULE_NOT_FOUND`) → `kanban task start`
ค้าง ~30 วิ แล้ว session จบ `cancelled`/`interrupted` · ซ้อนกับ `@clinebot/core` ที่อ้าง
global `AI` ตอน module-evaluation (`ReferenceError: AI is not defined`)

Assertion สำคัญ (กันถอยหลัง):
  * shim ต้อง set `globalThis.AI` **ก่อน** ประเมิน core entry (dynamic import เท่านั้น —
    `export * from` ถูก hoist แล้วจะพังกลับ)
  * `install()` ต้อง idempotent + backup ของเดิมไว้ + ไม่เขียนเลยเมื่อ `--check`
  * ตรวจ syntax/smoke ต้อง "รายงานตามจริง" (ไม่มี node = fail ไม่ใช่ผ่านเงียบ ๆ — Anti-Mock)
"""

import json
import shutil
from pathlib import Path

import pytest

import scripts.kanban.install_entry_shim as shim


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _fake_npm_root(tmp_path: Path, *, with_core: bool = True, with_ai: bool = True) -> Path:
    """สร้างโครง <root>/kanban/dist + (optional) @clinebot/core + ai ให้เหมือนเครื่องจริง."""
    root = tmp_path / "node_modules"
    (root / "kanban" / "dist").mkdir(parents=True)
    if with_core:
        core = (root / "kanban" / "node_modules" / "@clinebot" / "core" / "dist" / "hub"
                / "daemon" / "entry.js")
        core.parent.mkdir(parents=True)
        core.write_text("// real daemon entry\n", encoding="utf-8")
    if with_ai:
        pkg = root / "kanban" / "node_modules" / "ai"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text('{"name": "ai"}', encoding="utf-8")
    return root


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _recording_runner(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """แทน subprocess.run: เก็บคำสั่งที่ถูกเรียกและคืนผลตามที่กำหนด."""
    calls = []

    def runner(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return _Proc(returncode, stdout, stderr)

    runner.calls = calls
    return runner


# --------------------------------------------------------------------------- #
# Shim source contract (bug 1 + bug 2 ที่ต้องไม่กลับมา)
# --------------------------------------------------------------------------- #
def test_shim_sets_global_ai_before_dynamic_import():
    src = shim.SHIM_JS
    assert "globalThis.AI" in src
    assert 'await import("@clinebot/core/hub/daemon-entry")' in src
    assert src.index("globalThis.AI") < src.index(
        'await import("@clinebot/core/hub/daemon-entry")'
    ), "ต้อง set globalThis.AI ก่อนประเมิน core entry"


def test_shim_must_not_statically_reexport_core_entry():
    # static `export * from` / `import * from` ถูก hoist ไปประเมินก่อน body -> globalThis.AI
    # ยังไม่มี = พังกลับ (คอมเมนต์อธิบายได้ แต่โค้ดจริงต้องเป็น dynamic import เท่านั้น)
    code = "\n".join(line for line in shim.SHIM_JS.splitlines()
                     if not line.strip().startswith("//"))
    assert "export * from" not in code
    assert "import * from" not in code
    assert 'await import("@clinebot/core/hub/daemon-entry")' in code


def test_shim_source_references_both_upstream_issues():
    for issue in shim.UPSTREAM_ISSUES:
        assert issue in shim.SHIM_JS
        assert issue in shim.__doc__


# --------------------------------------------------------------------------- #
# Locators & state
# --------------------------------------------------------------------------- #
def test_shim_state_missing_current_and_stale(tmp_path):
    root = _fake_npm_root(tmp_path)
    assert shim.shim_state(root) == "missing"
    shim.install(root, verify_syntax=False)
    assert shim.shim_state(root) == "current"
    shim.shim_path(root).write_text("// a different file\n", encoding="utf-8")
    assert shim.shim_state(root) == "stale"


def test_locators_find_core_entry_and_ai_package(tmp_path):
    root = _fake_npm_root(tmp_path)
    assert shim.core_entry_path(root) is not None
    assert shim.ai_package_dir(root) is not None
    bare = _fake_npm_root(tmp_path / "bare", with_core=False, with_ai=False)
    assert shim.core_entry_path(bare) is None
    assert shim.ai_package_dir(bare) is None


def test_shim_path_is_sibling_of_cli_and_web_ui(tmp_path):
    root = _fake_npm_root(tmp_path)
    assert shim.shim_path(root).parent == shim.dist_dir(root)
    assert shim.shim_path(root).name == "entry.js"


# --------------------------------------------------------------------------- #
# install()
# --------------------------------------------------------------------------- #
def test_install_writes_shim_and_reports_ok(tmp_path):
    root = _fake_npm_root(tmp_path)
    res = shim.install(root, verify_syntax=False)
    assert res["ok"] is True
    assert res["action"] == "written" and res["state_before"] == "missing"
    assert shim.shim_path(root).read_text(encoding="utf-8") == shim.SHIM_JS


def test_install_is_idempotent(tmp_path):
    root = _fake_npm_root(tmp_path)
    shim.install(root, verify_syntax=False)
    again = shim.install(root, verify_syntax=False)
    assert again["action"] == "already-current"
    assert again["backup"] is None and again["ok"] is True


def test_install_backs_up_stale_file_before_replacing(tmp_path):
    root = _fake_npm_root(tmp_path)
    entry = shim.shim_path(root)
    entry.write_text("// what an npm upgrade left behind\n", encoding="utf-8")
    res = shim.install(root, verify_syntax=False)
    assert res["action"] == "replaced"
    assert Path(res["backup"]).read_text(encoding="utf-8") == "// what an npm upgrade left behind\n"
    assert shim.shim_state(root) == "current"


def test_dry_run_never_touches_filesystem(tmp_path):
    root = _fake_npm_root(tmp_path)
    res = shim.install(root, dry_run=True, verify_syntax=False)
    assert res["action"] == "would-write" and res["ok"] is True
    assert not shim.shim_path(root).exists()


def test_install_fails_honestly_when_kanban_absent(tmp_path):
    root = tmp_path / "node_modules"
    (root / "kanban").mkdir(parents=True)
    res = shim.install(root, verify_syntax=False)
    assert res["ok"] is False and res["action"] == "failed"
    assert "dist" in res["reason"]


def test_install_reports_node_check_failure(tmp_path, monkeypatch):
    root = _fake_npm_root(tmp_path)
    monkeypatch.setattr(shim.shutil, "which", lambda _bin: "/usr/bin/node")
    res = shim.install(root, runner=_recording_runner(1, "", "SyntaxError: Unexpected token"))
    assert res["ok"] is False and res["syntax_ok"] is False
    assert "SyntaxError" in res["syntax"]


# --------------------------------------------------------------------------- #
# syntax_check / smoke
# --------------------------------------------------------------------------- #
def test_syntax_check_reports_missing_file(tmp_path):
    ok, msg = shim.syntax_check(tmp_path / "nope.js")
    assert ok is False and "ไม่พบไฟล์" in msg


def test_syntax_check_reports_missing_node_instead_of_passing(tmp_path, monkeypatch):
    target = tmp_path / "entry.js"
    target.write_text(shim.SHIM_JS, encoding="utf-8")
    monkeypatch.setattr(shim.shutil, "which", lambda _bin: None)
    ok, msg = shim.syntax_check(target)
    assert ok is False and "PATH" in msg


def test_syntax_check_invokes_node_check(tmp_path, monkeypatch):
    target = tmp_path / "entry.js"
    target.write_text(shim.SHIM_JS, encoding="utf-8")
    monkeypatch.setattr(shim.shutil, "which", lambda _bin: "/usr/bin/node")
    runner = _recording_runner(0)
    ok, out = shim.syntax_check(target, runner=runner)
    assert ok is True and out == "SYNTAX OK"
    assert runner.calls[0][0] == ["node", "--check", str(target)]


def test_build_smoke_cmd_matches_cli_contract():
    cmd = shim.build_smoke_cmd("node", Path("/p/dist/entry.js"), 45999, "/tmp/scratch")
    assert cmd == ["node", "/p/dist/entry.js", "--cwd", "/tmp/scratch", "--port", "45999"]


def test_smoke_fails_fast_without_node(tmp_path, monkeypatch):
    entry = tmp_path / "entry.js"
    entry.write_text(shim.SHIM_JS, encoding="utf-8")
    monkeypatch.setattr(shim.shutil, "which", lambda _bin: None)
    res = shim.smoke(entry)
    assert res["ok"] is False and "PATH" in res["reason"]


def test_smoke_fails_fast_when_entry_missing(tmp_path):
    res = shim.smoke(tmp_path / "nope.js")
    assert res["ok"] is False and "ไม่พบไฟล์" in res["reason"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node ไม่มีในเครื่องนี้")
def test_shim_source_is_valid_node_syntax_in_reality(tmp_path):
    """ตรวจ SHIM_JS ด้วย `node --check` จริง (ไม่ต้องมี kanban ติดตั้งในเครื่อง)."""
    target = tmp_path / "entry.js"
    target.write_text(shim.SHIM_JS, encoding="utf-8")
    ok, msg = shim.syntax_check(target)
    assert ok, msg


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_check_mode_is_read_only_and_reports_status(tmp_path, capsys):
    root = _fake_npm_root(tmp_path)
    assert shim.main(["--check", "--npm-root", str(root), "--no-syntax"]) == 0
    out = capsys.readouterr().out
    assert "would-write" in out and "OK" in out
    assert not shim.shim_path(root).exists()


def test_main_reports_action_needed_when_npm_root_missing(monkeypatch, capsys):
    monkeypatch.setattr(shim, "npm_global_root", lambda *a, **k: None)
    assert shim.main([]) == 1
    assert "ACTION NEEDED" in capsys.readouterr().out


def test_json_output_is_machine_readable(tmp_path, capsys):
    root = _fake_npm_root(tmp_path)
    shim.install(root, verify_syntax=False)
    assert shim.main(["--npm-root", str(root), "--no-syntax", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["install"]["state_before"] == "current"
    assert "cline/kanban#495" in payload["upstream_issues"]
    assert "rca_kanban_hub_daemon.md" in payload["rca"]


def test_print_shim_dumps_source(capsys):
    assert shim.main(["--print-shim"]) == 0
    assert "globalThis.AI" in capsys.readouterr().out


def test_parser_defaults():
    args = shim.parse_args([])
    assert args.check is False and args.smoke is False and args.print_shim is False
    assert args.node_bin == "node" and args.port is None and args.json is False
