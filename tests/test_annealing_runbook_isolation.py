"""
Regression Suite: annealing flows must never write into the git-tracked runbook tree.

Bug being locked down (F-11 "Self-Annealed ×75", C2W-RCA-021):
``scripts/verify_changes.py --full`` used to overwrite two tracked runbooks
(``learned_workflows/click2win/click2win_order_submit.md`` and
``learned_workflows/shared/test_anneal_wf.md``) on every run, because the annealing tests
called ``WorkflowEngine.save_workflow_spec()`` / ``update_workflow_step()`` while the
module-level ``workflow_engine.WORKFLOWS_DIR`` still pointed at the repo directory
(``test_click2win_driver.py`` even appended a new ``(Self-Annealed: …)`` marker each run).

Fix: the autouse fixture ``isolate_learned_workflow_writes`` in ``tests/conftest.py`` redirects
``WORKFLOWS_DIR`` to a throwaway copy of the tree. The tests here fail loudly if that
protection is ever removed or bypassed.
"""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_engine
from app.services.workflow_engine import WorkflowEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_LEARNED_WORKFLOWS = (REPO_ROOT / "learned_workflows").resolve()


def _snapshot_runbooks() -> dict:
    """path (relative to learned_workflows/) → sha256 digest for every tracked runbook file."""
    return {
        str(p.relative_to(REPO_LEARNED_WORKFLOWS)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(REPO_LEARNED_WORKFLOWS.rglob("*"))
        if p.is_file()
    }


def test_workflow_engine_write_target_is_sandboxed():
    """The test harness must point WorkflowEngine writes at a throwaway sandbox, not the repo."""
    target = Path(workflow_engine.WORKFLOWS_DIR).resolve()
    assert not target.is_relative_to(REPO_LEARNED_WORKFLOWS), (
        f"WorkflowEngine.WORKFLOWS_DIR resolves to the tracked runbook tree ({target}) — "
        "annealing tests would overwrite learned_workflows/*.md (F-11). "
        "Check the autouse fixture isolate_learned_workflow_writes in tests/conftest.py."
    )


@pytest.mark.asyncio
async def test_annealing_flows_never_write_tracked_runbooks():
    """Run the flows that used to pollute runbooks; the repo tree must stay byte-identical."""
    before = _snapshot_runbooks()
    engine = WorkflowEngine()
    sandbox = Path(workflow_engine.WORKFLOWS_DIR).resolve()

    # Flow 1: spec save — used to rewrite learned_workflows/shared/test_anneal_wf.md ("Recorded At")
    engine.save_workflow_spec(
        name="test_anneal_wf",
        title="Test Anneal Workflow",
        description="Test workflow for self-annealing verification",
        steps=[{
            "action": "CLICK",
            "selector": "#non-existent-button",
            "description": "Click target",
        }],
    )

    # Flow 2: self-annealing step update — used to append "(Self-Annealed: …)" to the C2W runbook
    res = engine.update_workflow_step(
        name="click2win_order_submit",
        step_num=6,
        new_selector="button.btn-regression-probe",
        explanation="Regression probe: must stay inside the sandbox",
    )
    assert res["success"] is True
    written = Path(res["filepath"]).resolve()
    assert written.is_relative_to(sandbox), f"runbook write escaped the sandbox: {written}"

    # Flow 3: full 4-step annealing + escalation path (execute_workflow)
    mock_page = MagicMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Selector not found"))
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_page.is_closed = False

    with patch("app.services.workflow_engine.get_broker_driver") as m_bd, \
         patch("app.browser.popup_manager.popup_manager.dismiss_popups", new_callable=AsyncMock), \
         patch("app.services.kdeconnect_service.KdeConnectService.notify_admin_screen_help",
               new_callable=AsyncMock):
        m_bd.return_value = MagicMock(page=mock_page)
        res2 = await engine.execute_workflow("test_anneal_wf")

    # Anti-Mock: a failing step must escalate, never report success
    assert res2["success"] is False
    assert res2["escalated_to_admin"] is True

    after = _snapshot_runbooks()
    changed = sorted(set(before) ^ set(after)) + sorted(
        p for p in set(before) & set(after) if before[p] != after[p]
    )
    assert after == before, f"annealing flows wrote into the tracked runbook tree: {changed}"
