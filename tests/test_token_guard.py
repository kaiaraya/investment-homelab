"""Tests for scripts/hooks/token_guard.py (Antigravity + Cline PreToolUse token guard)."""
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(REPO, "scripts", "hooks", "token_guard.py")
CLINE_HOOK = os.path.join(REPO, ".cline", "hooks", "PreToolUse")


def run(payload, agent="cline", raw=None, cmd=None):
    data = raw if raw is not None else json.dumps(payload)
    env = dict(os.environ, TOKEN_GUARD_LOG=os.path.join(os.environ.get("TMPDIR", "/tmp"), "token_guard_test.log"))
    proc = subprocess.run(cmd or [sys.executable, GUARD, "--agent", agent], input=data,
                          capture_output=True, text=True, timeout=20, env=env)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture
def big_file(tmp_path):
    p = tmp_path / "big.py"
    p.write_text("x = 1\n" * 900)
    return str(p)


@pytest.fixture
def small_file(tmp_path):
    p = tmp_path / "small.py"
    p.write_text("x = 1\n" * 50)
    return str(p)


def cline_read(files):
    return {"hookName": "tool_call", "preToolUse": {"toolName": "read_files", "parameters": {"files": files}}}


def cline_search(queries):
    return {"hookName": "tool_call", "preToolUse": {"toolName": "search_codebase", "parameters": {"queries": queries}}}


# ---- Cline: read_files
def test_cline_blocks_image():
    out = run(cline_read([{"path": "/x/data/screenshots/a.png"}]))
    assert out["cancel"] is True and "base64" in out["errorMessage"]


def test_cline_blocks_binary():
    assert run(cline_read([{"path": "/x/investment_homelab.db"}]))["cancel"] is True


def test_cline_blocks_big_file_without_range(big_file):
    out = run(cline_read([{"path": big_file}]))
    assert out["cancel"] is True and "900" in out["errorMessage"]


def test_cline_allows_big_file_with_range(big_file):
    assert run(cline_read([{"path": big_file, "start_line": 100, "end_line": 220}]))["cancel"] is False


def test_cline_blocks_too_wide_range(big_file):
    assert run(cline_read([{"path": big_file, "start_line": 1, "end_line": 800}]))["cancel"] is True


def test_cline_allows_small_file(small_file):
    assert run(cline_read([{"path": small_file}]))["cancel"] is False


def test_cline_parameters_as_json_string(big_file):
    payload = {"preToolUse": {"toolName": "read_files", "parameters": {"files": json.dumps([{"path": big_file}])}}}
    assert run(payload)["cancel"] is True


def test_cline_tool_call_shape(big_file):
    payload = {"hookName": "tool_call", "tool_call": {"id": "1", "name": "read_files", "input": {"files": [{"path": big_file}]}}}
    assert run(payload)["cancel"] is True


# ---- Cline: search_codebase
def test_cline_blocks_generic_queries():
    assert run(cline_search(["approve", "KILL"]))["cancel"] is True


def test_cline_blocks_short_alternation():
    assert run(cline_search(["B3|B4|B5|Gate B"]))["cancel"] is True


def test_cline_blocks_too_many_queries():
    assert run(cline_search(["_handle_text_message", "_handle_postback", "dispatch_order", "prepare_order_approval"]))["cancel"] is True


def test_cline_allows_specific_queries():
    assert run(cline_search(["_handle_text_message", "otp_relay_readiness"]))["cancel"] is False


def test_cline_other_tools_allowed():
    assert run({"preToolUse": {"toolName": "run_commands", "parameters": {"commands": ["ls"]}}})["cancel"] is False


# ---- Antigravity: view_file
def ag_view(path, start=None, end=None):
    args = {"AbsolutePath": path}
    if start is not None:
        args.update(StartLine=start, EndLine=end)
    return {"toolCall": {"name": "view_file", "args": args}, "stepIdx": 1}


def test_antigravity_allows_image():
    assert run(ag_view("/x/a.png"), agent="antigravity")["decision"] == "allow"


def test_antigravity_blocks_binary():
    assert run(ag_view("/x/a.db"), agent="antigravity")["decision"] == "deny"


def test_antigravity_blocks_big_file_without_range(big_file):
    assert run(ag_view(big_file), agent="antigravity")["decision"] == "deny"


def test_antigravity_allows_range(big_file):
    assert run(ag_view(big_file, 10, 120), agent="antigravity")["decision"] == "allow"


def test_antigravity_ignores_other_tools():
    assert run({"toolCall": {"name": "grep_search", "args": {"Query": "x"}}}, agent="antigravity")["decision"] == "allow"


# ---- fail-open + wrapper
def test_fail_open_on_bad_json():
    assert run(None, raw="{not json")["cancel"] is False
    assert run(None, agent="antigravity", raw="")["decision"] == "allow"


def test_missing_file_allowed():
    assert run(cline_read([{"path": "/nonexistent/file.py"}]))["cancel"] is False


def test_cline_hook_wrapper_executes(big_file):
    assert os.access(CLINE_HOOK, os.X_OK), "PreToolUse must be executable"
    out = run(cline_read([{"path": big_file}]), cmd=[CLINE_HOOK])
    assert out["cancel"] is True
