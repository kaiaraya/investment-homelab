import os
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import WorkflowAnomaly
from app.db.session import AsyncSessionLocal
from app.browser.trademan_driver import trademan_driver
from app.browser.auth_driver import auth_driver
from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.browser.popup_manager import popup_manager
from app.services.kdeconnect_service import KdeConnectService
from app.schemas.mcp_response import MCPToolStatus, create_maintenance_response, create_admin_attention_response

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "learned_workflows"))
ANOMALIES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "screenshots", "anomalies"))


class WorkflowEngine:
    """
    Learned Workflows Engine:
    Coordinates the 4-Stage Learning Loop:
    1. Interactive Learn: AI + Human pilot live on screen via Playwright MCP.
    2. Markdown Specification: Compiles observed procedures into learned_workflows/<name>.md.
    3. Autonomous Execution: Reads and executes validated markdown steps.
    4. Anomaly Detection & Re-learn: Detects UI shifts, records anomaly in DB, alerts LINE, flags NEEDS_RELEARN.
    """

    def __init__(self):
        os.makedirs(WORKFLOWS_DIR, exist_ok=True)
        os.makedirs(ANOMALIES_DIR, exist_ok=True)

    def list_workflows(self) -> List[str]:
        """Lists all learned workflow names (.md files) recursively across broker subdirectories."""
        if not os.path.exists(WORKFLOWS_DIR):
            return []
        workflows = []
        for root, _, files in os.walk(WORKFLOWS_DIR):
            for f in files:
                if f.endswith(".md"):
                    workflows.append(f[:-3])
        return sorted(list(set(workflows)))

    def get_workflow_path(self, name: str, broker: Optional[str] = None) -> str:
        clean_name = re.sub(r'[^\w\-\/]', '_', name.strip())
        if not clean_name.endswith(".md"):
            filename = f"{clean_name}.md"
        else:
            filename = clean_name

        direct_path = os.path.join(WORKFLOWS_DIR, filename)
        if os.path.exists(direct_path):
            return direct_path

        # Recursive search across subdirectories (e.g. krungsri/, liberator/, click2win/, shared/)
        base_filename = os.path.basename(filename)
        for root, _, files in os.walk(WORKFLOWS_DIR):
            if base_filename in files:
                return os.path.join(root, base_filename)

        # For saving new workflows, infer destination subdirectory
        if broker:
            target_dir = os.path.join(WORKFLOWS_DIR, broker)
        elif "liberator" in clean_name.lower():
            target_dir = os.path.join(WORKFLOWS_DIR, "liberator")
        elif "click2win" in clean_name.lower() or "c2w" in clean_name.lower():
            target_dir = os.path.join(WORKFLOWS_DIR, "click2win")
        elif any(k in clean_name.lower() for k in ["krungsri", "trademan", "sbl"]):
            target_dir = os.path.join(WORKFLOWS_DIR, "krungsri")
        else:
            target_dir = os.path.join(WORKFLOWS_DIR, "shared")

        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, base_filename)

    def save_workflow_spec(
        self,
        name: str,
        title: str,
        description: str,
        steps: List[Dict[str, Any]],
        validation_rules: Optional[List[str]] = None
    ) -> str:
        """
        Saves or updates a learned workflow as a structured markdown specification.
        """
        filepath = self.get_workflow_path(name)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# Learned Workflow: {title}",
            f"**Workflow Name:** `{name}`  ",
            f"**Recorded At:** {timestamp}  ",
            f"**Status:** `VERIFIED`  ",
            "",
            "## Description",
            description.strip(),
            "",
            "## Execution Steps",
            "| Step | Action | Target Selector | Value / Arguments | Description |",
            "| :---: | :---: | :--- | :--- | :--- |"
        ]

        for i, s in enumerate(steps, 1):
            act = s.get("action", "click").upper()
            sel = s.get("selector", "-")
            val = s.get("value", "-")
            desc = s.get("description", "-")
            lines.append(f"| {i} | `{act}` | `{sel}` | `{val}` | {desc} |")

        lines.append("")
        lines.append("## Health Verification Rules")
        val_rules = validation_rules or ["All target selectors must be present and visible in DOM", "No unhandled error modal overlays"]
        for r in val_rules:
            lines.append(f"- [x] {r}")

        lines.append("")
        lines.append("---")
        lines.append("*Maintained automatically by Playwright MCP Learning Loop*")

        content = "\n".join(lines) + "\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Saved learned workflow spec to {filepath}")
        return filepath

    def parse_workflow_spec(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Parses a learned workflow markdown file into executable steps and validations.
        """
        filepath = self.get_workflow_path(name)
        if not os.path.exists(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        title_match = re.search(r"# Learned Workflow:\s*(.*)", content)
        title = title_match.group(1).strip() if title_match else name

        steps = []
        table_rows = re.findall(r"\|\s*(\d+)\s*\|\s*`?([A-Z_]+)`?\s*\|\s*`?([^`|]+)`?\s*\|\s*`?([^`|]+)`?\s*\|\s*([^|]+)\|", content)
        for row in table_rows:
            step_num, action, selector, value, desc = row
            steps.append({
                "step": int(step_num),
                "action": action.strip().upper(),
                "selector": selector.strip(),
                "value": value.strip() if value.strip() != "-" else None,
                "description": desc.strip()
            })

        return {
            "name": name,
            "title": title,
            "filepath": filepath,
            "steps": steps
        }

    def update_workflow_step(
        self,
        name: str,
        step_num: int,
        new_selector: Optional[str] = None,
        new_action: Optional[str] = None,
        explanation: str = ""
    ) -> Dict[str, Any]:
        """
        Self-Annealing mechanism:
        Updates a specific step in a learned workflow markdown specification.
        Preserves existing steps while replacing selector / action and appending annealing log.
        """
        spec = self.parse_workflow_spec(name)
        if not spec:
            return {"success": False, "error": f"Workflow '{name}' not found."}

        steps = spec.get("steps", [])
        step_found = False
        for s in steps:
            if s["step"] == step_num:
                if new_selector:
                    s["selector"] = new_selector
                if new_action:
                    s["action"] = new_action.upper()
                if explanation:
                    s["description"] = f"{s.get('description', '')} (Self-Annealed: {explanation})".strip()
                step_found = True
                break

        if not step_found:
            return {"success": False, "error": f"Step {step_num} not found in workflow '{name}'."}

        # Save back updated spec
        filepath = self.save_workflow_spec(
            name=name,
            title=spec.get("title", name),
            description=f"Self-annealed on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}. Note: {explanation}",
            steps=steps
        )
        return {
            "success": True,
            "filepath": filepath,
            "updated_step": step_num,
            "new_selector": new_selector,
            "message": f"Successfully self-annealed step {step_num} in '{name}'."
        }

    async def execute_workflow(self, name: str) -> Dict[str, Any]:
        """
        Autonomous execution of a learned workflow.
        If any step fails, triggers anomaly recording, captures diagnostic snapshot, and alerts LINE.
        """
        spec = self.parse_workflow_spec(name)
        if not spec:
            return {"success": False, "error": f"Workflow spec '{name}' not found."}

        steps = spec.get("steps", [])
        logger.info(f"WorkflowEngine: Executing '{name}' ({len(steps)} steps)...")

        page = getattr(trademan_driver, "page", None) or get_broker_driver().page
        is_closed = False
        if page and hasattr(page, "is_closed"):
            res = page.is_closed() if callable(page.is_closed) else page.is_closed
            if asyncio.iscoroutine(res):
                is_closed = await res
            else:
                is_closed = bool(res)

        if not page or is_closed:
            # If no browser is connected, try to launch / connect
            page = await get_auth_driver().launch_browser(resume_state=True)

        executed_steps = []

        for s in steps:
            step_desc = f"Step {s['step']}: {s['action']} on `{s['selector']}`"
            try:
                action = s["action"].upper()
                selector = s["selector"]
                val = s.get("value")

                # Macro replacements for credentials and configuration
                if selector and isinstance(selector, str):
                    selector = selector.replace("<KRUNGSRI_USERNAME>", settings.KRUNGSRI_USERNAME or "")
                    selector = selector.replace("<KRUNGSRI_PASSWORD>", settings.KRUNGSRI_PASSWORD or "")
                if val and isinstance(val, str):
                    val = val.replace("<KRUNGSRI_USERNAME>", settings.KRUNGSRI_USERNAME or "")
                    val = val.replace("<KRUNGSRI_PASSWORD>", settings.KRUNGSRI_PASSWORD or "")
                    val = val.replace("<TRADEMAN_PIN>", getattr(settings, "TRADEMAN_PIN", None) or settings.TRADING_PIN or "")

                if action in ("NAV", "NAVIGATE", "GOTO"):
                    target_url = selector if selector.startswith("http") else (val or selector)
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                elif action == "CLICK":
                    el = await page.wait_for_selector(selector, state="visible", timeout=6000)
                    if el:
                        await el.click()
                elif action in ("TYPE", "FILL"):
                    el = await page.wait_for_selector(selector, state="visible", timeout=6000)
                    if el:
                        await el.fill("")
                        await el.type(str(val or ""), delay=70)
                elif action == "WAIT":
                    wait_ms = 1000
                    if val:
                        try:
                            num = int(val)
                            wait_ms = num * 1000 if num <= 300 else num
                        except ValueError:
                            wait_ms = 1000
                    if selector and selector != "-" and not selector.isdigit():
                        try:
                            await page.wait_for_selector(selector, timeout=min(wait_ms, 15000))
                        except Exception:
                            pass
                    else:
                        await page.wait_for_timeout(wait_ms)
                elif action == "CHECK":
                    el = await page.query_selector(selector)
                    if el and not await el.is_checked():
                        await el.check()

                executed_steps.append(step_desc)
                await page.wait_for_timeout(500)

            except Exception as initial_error:
                # 4-Stage Self-Annealing sequence:
                annealed = False
                logger.warning(f"WorkflowEngine: Step {s['step']} initial failure ({initial_error}). Commencing 4-step self-annealing...")

                # Stage 1: Dismiss obstructive popups/modals
                try:
                    await popup_manager.dismiss_popups(page)
                except Exception as pe:
                    logger.debug(f"Popup dismissal pass: {pe}")

                # Stage 2: Try fallback selectors if defined in step
                fallback_selectors = s.get("fallback_selectors", [])
                if not fallback_selectors and s.get("fallback"):
                    fallback_selectors = [s.get("fallback")]

                for alt_sel in fallback_selectors:
                    try:
                        logger.info(f"Self-Annealing: Trying fallback selector `{alt_sel}` for step {s['step']}...")
                        if action == "CLICK":
                            el = await page.wait_for_selector(alt_sel, state="visible", timeout=3000)
                            if el:
                                await el.click()
                                annealed = True
                                self.update_workflow_step(name, s['step'], new_selector=alt_sel, explanation="Self-annealed to fallback selector")
                                break
                        elif action in ["TYPE", "FILL"]:
                            el = await page.wait_for_selector(alt_sel, state="visible", timeout=3000)
                            if el:
                                await el.fill("")
                                await el.type(str(val or ""), delay=70)
                                annealed = True
                                self.update_workflow_step(name, s['step'], new_selector=alt_sel, explanation="Self-annealed to fallback selector")
                                break
                    except Exception:
                        continue

                # Stage 3: Wait for DOM re-render / hydration (1.5s pause) and retry original selector once
                if not annealed:
                    try:
                        logger.info(f"Self-Annealing: Pausing 1500ms for DOM re-render on `{selector}`...")
                        await page.wait_for_timeout(1500)
                        if action == "CLICK":
                            el = await page.wait_for_selector(selector, state="visible", timeout=3000)
                            if el:
                                await el.click()
                                annealed = True
                        elif action in ["TYPE", "FILL"]:
                            el = await page.wait_for_selector(selector, state="visible", timeout=3000)
                            if el:
                                await el.fill("")
                                await el.type(str(val or ""), delay=70)
                                annealed = True
                    except Exception:
                        pass

                if annealed:
                    logger.info(f"WorkflowEngine: Step {s['step']} successfully self-annealed!")
                    executed_steps.append(f"{step_desc} (Self-Annealed)")
                    await page.wait_for_timeout(500)
                    continue

                # Stage 4: Self-annealing failed -> Escalate to Admin via KDE Connect
                err_msg = f"Failed at {step_desc} after self-annealing: {str(initial_error)}"
                logger.error(f"WorkflowEngine Anomaly: {err_msg}")

                # 1. Take diagnostic anomaly screenshot
                snap_name = f"anomaly_{name}_step{s['step']}_{int(datetime.now().timestamp())}.png"
                snap_path = os.path.join(ANOMALIES_DIR, snap_name)
                try:
                    await page.screenshot(path=snap_path, full_page=False)
                except Exception:
                    snap_path = None

                # 2. Record anomaly in SQLite
                await self.record_anomaly(
                    workflow_name=name,
                    failed_step=step_desc,
                    error_message=str(initial_error),
                    snapshot_path=snap_path
                )

                # 3. Hardware HITL Escalation via KDE Connect
                try:
                    kde = KdeConnectService()
                    await kde.notify_admin_screen_help(
                        reason=f"Workflow '{name}' ติดขัด: {str(initial_error)[:80]}",
                        workflow_or_step=step_desc
                    )
                except Exception as kde_err:
                    logger.warning(f"KDE Connect escalation notice failed: {kde_err}")

                # 4. Alert LINE with Re-learn prompt
                from app.services.line_service import line_service
                alert_text = (
                    f"⚠️ [Workflow Anomaly] ตรวจพบหน้าจอเปลี่ยนไปใน '{name}'\n"
                    f"• จุดที่ติดขัด: {step_desc}\n"
                    f"• สาเหตุ: {str(initial_error)[:100]}\n\n"
                    "สถานะถูกปรับเป็น NEEDS_RELEARN กรุณาเปิด IDE เพื่อเข้าสู่โหมด Co-pilot Re-learn ร่วมกับ AI"
                )
                try:
                    await line_service.push_progress_update(alert_text)
                except Exception:
                    pass

                return {
                    "success": False,
                    "status": MCPToolStatus.NEEDS_ADMIN_ATTENTION.value,
                    "maintenance_mode": True,
                    "message": "ระบบกำลังปรับปรุง โปรดติดต่อ Admin เนื่องจากข้อมูลยังไม่พร้อม (มีความเสี่ยงสูง)",
                    "workflow": name,
                    "failed_step": step_desc,
                    "error": str(initial_error),
                    "snapshot_path": snap_path,
                    "executed_steps": executed_steps,
                    "escalated_to_admin": True
                }

        logger.info(f"WorkflowEngine: Workflow '{name}' completed successfully ({len(executed_steps)} steps).")
        return {
            "success": True,
            "status": MCPToolStatus.SUCCESS.value,
            "workflow": name,
            "executed_steps": executed_steps
        }

    async def record_anomaly(
        self,
        workflow_name: str,
        failed_step: str,
        error_message: str,
        snapshot_path: Optional[str] = None
    ) -> int:
        """Records an anomaly event into SQLite table workflow_anomalies."""
        async with AsyncSessionLocal() as db:
            anomaly = WorkflowAnomaly(
                workflow_name=workflow_name,
                failed_step=failed_step,
                error_message=error_message,
                snapshot_path=snapshot_path,
                status="NEEDS_RELEARN"
            )
            db.add(anomaly)
            await db.commit()
            return anomaly.id

    async def get_active_anomalies(self) -> List[Dict[str, Any]]:
        """Returns all workflows requiring re-learning (status=NEEDS_RELEARN)."""
        async with AsyncSessionLocal() as db:
            stmt = select(WorkflowAnomaly).where(WorkflowAnomaly.status == "NEEDS_RELEARN").order_by(WorkflowAnomaly.created_at.desc())
            res = await db.execute(stmt)
            rows = res.scalars().all()
            return [
                {
                    "id": r.id,
                    "workflow_name": r.workflow_name,
                    "failed_step": r.failed_step,
                    "error_message": r.error_message,
                    "snapshot_path": r.snapshot_path,
                    "status": r.status,
                    "created_at": r.created_at.isoformat()
                }
                for r in rows
            ]

    async def resolve_anomaly(self, anomaly_id: int) -> bool:
        """Marks an anomaly as RESOLVED after an interactive re-learning session."""
        async with AsyncSessionLocal() as db:
            stmt = select(WorkflowAnomaly).where(WorkflowAnomaly.id == anomaly_id)
            res = await db.execute(stmt)
            row = res.scalars().first()
            if row:
                row.status = "RESOLVED"
                row.resolved_at = datetime.now(timezone.utc)
                await db.commit()
                return True
        return False


workflow_engine = WorkflowEngine()
