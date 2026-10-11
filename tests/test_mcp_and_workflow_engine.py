import os
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import WorkflowAnomaly
from app.db.session import AsyncSessionLocal
from app.services.workflow_engine import workflow_engine, WorkflowEngine
from app.mcp.mcp_server import TOOLS, handle_tool_call, RECORDED_BUFFER


@pytest.mark.asyncio
async def test_tools_schema():
    """Verify that all MCP tools adhere to the standard schema."""
    assert len(TOOLS) >= 12
    tool_names = [t["name"] for t in TOOLS]
    assert "browser_open" in tool_names
    assert "browser_click" in tool_names
    assert "browser_type" in tool_names
    assert "browser_screenshot" in tool_names
    assert "browser_snapshot" in tool_names
    assert "record_workflow_step" in tool_names
    assert "save_learned_workflow" in tool_names
    assert "workflow_run_autonomous" in tool_names
    assert "workflow_get_anomalies" in tool_names

    for t in TOOLS:
        assert "name" in t
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"].get("type") == "object"


@pytest.mark.asyncio
async def test_workflow_engine_spec_save_and_parse(tmp_path):
    """Verify markdown runbook generation and parsing."""
    test_engine = WorkflowEngine()
    test_engine.get_workflow_path = lambda name: os.path.join(tmp_path, f"{name}.md")

    steps = [
        {"action": "CLICK", "selector": "#btn-test", "value": "-", "description": "Click test button"},
        {"action": "TYPE", "selector": "input#query", "value": "PTT", "description": "Type stock symbol"},
        {"action": "WAIT", "selector": "-", "value": "500", "description": "Wait for results"}
    ]

    saved_path = test_engine.save_workflow_spec(
        name="test_search_flow",
        title="Test Search Stock Flow",
        description="A verified procedure to search for a stock symbol in TradeMan.",
        steps=steps,
        validation_rules=["Table row must appear"]
    )

    assert os.path.exists(saved_path)
    with open(saved_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "# Learned Workflow: Test Search Stock Flow" in content
    assert "`test_search_flow`" in content
    assert "| 1 | `CLICK` | `#btn-test` | `-` | Click test button |" in content
    assert "| 2 | `TYPE` | `input#query` | `PTT` | Type stock symbol |" in content

    # Test parsing
    spec = test_engine.parse_workflow_spec("test_search_flow")
    assert spec is not None
    assert spec["name"] == "test_search_flow"
    assert spec["title"] == "Test Search Stock Flow"
    assert len(spec["steps"]) == 3
    assert spec["steps"][0]["action"] == "CLICK"
    assert spec["steps"][0]["selector"] == "#btn-test"
    assert spec["steps"][1]["action"] == "TYPE"
    assert spec["steps"][1]["value"] == "PTT"


@pytest.mark.asyncio
async def test_mcp_handle_tool_call_buffered_recording():
    """Test recording interactive steps and compiling into markdown runbook."""
    RECORDED_BUFFER.clear()

    # Step 1: record step 1
    res1 = await handle_tool_call("record_workflow_step", {
        "workflow_name": "tmp_test_workflow",
        "action": "CLICK",
        "selector": "#menu-btn",
        "description": "Click Main Menu"
    })
    assert "Buffered step 1" in res1

    # Step 2: record step 2
    res2 = await handle_tool_call("record_workflow_step", {
        "workflow_name": "tmp_test_workflow",
        "action": "TYPE",
        "selector": "input#search",
        "value": "CPALL",
        "description": "Enter CPALL symbol"
    })
    assert "Buffered step 2" in res2

    # Step 3: save learned workflow
    res3 = await handle_tool_call("save_learned_workflow", {
        "name": "tmp_test_workflow",
        "title": "Search CPALL Workflow",
        "description": "Interactive workflow for CPALL lookup."
    })
    assert "Successfully compiled and saved" in res3

    # Verify listing
    res_list = await handle_tool_call("workflow_list", {})
    assert "tmp_test_workflow.md" in res_list

    # Clean up
    path = workflow_engine.get_workflow_path("tmp_test_workflow")
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_mcp_json_rpc_stdio_subprocess():
    """End-to-end integration test of MCP server over standard input/output pipes."""
    import sys
    import subprocess

    cmd = [sys.executable, "-m", "app.mcp.mcp_server"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # 1. initialize
    req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    proc.stdin.write(req1.encode())
    await proc.stdin.drain()

    line1 = await proc.stdout.readline()
    resp1 = json.loads(line1.decode().strip())
    assert resp1["id"] == 1
    assert resp1["result"]["serverInfo"]["name"] == "playwright-homelab"

    # 2. tools/list
    req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
    proc.stdin.write(req2.encode())
    await proc.stdin.drain()

    line2 = await proc.stdout.readline()
    resp2 = json.loads(line2.decode().strip())
    assert resp2["id"] == 2
    tool_names = [t["name"] for t in resp2["result"]["tools"]]
    assert "browser_open" in tool_names
    assert "workflow_run_autonomous" in tool_names

    # 3. tools/call (workflow_list)
    req3 = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "workflow_list", "arguments": {}}
    }) + "\n"
    proc.stdin.write(req3.encode())
    await proc.stdin.drain()

    line3 = await proc.stdout.readline()
    resp3 = json.loads(line3.decode().strip())
    assert resp3["id"] == 3
    assert "learned_workflows" in resp3["result"]["content"][0]["text"]

    # 4. ping
    req4 = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}}) + "\n"
    proc.stdin.write(req4.encode())
    await proc.stdin.drain()

    line4 = await proc.stdout.readline()
    resp4 = json.loads(line4.decode().strip())
    assert resp4["id"] == 4

    # Terminate process cleanly
    proc.terminate()
    await proc.wait()

