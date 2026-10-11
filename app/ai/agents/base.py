import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic_ai import Agent
from app.ai.providers import get_gemini_model
from app.ai.memory import agent_memory

logger = logging.getLogger(__name__)

# Base path for SOP directives
DIRECTIVES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "directives" / "sops"


class BaseSubAgent:
    """
    Base class for all specialized DOE Sub-Agents.
    Automatically loads its directive Standard Operating Procedure (SOP) Markdown file,
    configures PydanticAI / Gemini provider, and records decisions in DualStoreMemory.
    """

    def __init__(
        self,
        name: str,
        sop_filename: str,
        model_override: Optional[Any] = None,
        output_type: Optional[type] = None,
    ):
        self.name = name
        self.sop_filename = sop_filename
        self.sop_path = DIRECTIVES_DIR / sop_filename
        self.sop_content = self._load_sop()
        self.model = model_override or get_gemini_model()
        self.output_type = output_type

        # Initialize internal PydanticAI Agent if model is available
        self._agent: Optional[Agent] = None
        if self.model:
            try:
                self._agent = Agent(
                    model=self.model,
                    system_prompt=self.sop_content,
                    output_type=output_type or str,
                )
            except Exception as exc:
                logger.warning(f"Could not build PydanticAI Agent for [{self.name}]: {exc}")

    def _load_sop(self) -> str:
        """Reads the Markdown SOP from disk. Falls back to a default prompt if missing."""
        if self.sop_path.exists():
            try:
                content = self.sop_path.read_text(encoding="utf-8")
                logger.debug(f"Loaded SOP directive for [{self.name}] from {self.sop_path}")
                return content
            except Exception as exc:
                logger.error(f"Error reading SOP file {self.sop_path}: {exc}")

        logger.warning(f"SOP file {self.sop_path} not found. Using fallback directive prompt.")
        return f"You are {self.name}, an autonomous financial sub-agent adhering strictly to risk guardrails."

    async def log_step(
        self,
        action_type: str,
        thought: Optional[str] = None,
        input_context: Optional[Any] = None,
        output_result: Optional[Any] = None,
        is_success: bool = True,
        regime: Optional[str] = None,
    ) -> int:
        """Convenience wrapper to commit an action to the DualStoreMemory persistent audit trail."""
        return await agent_memory.log_decision(
            agent_name=self.name,
            action_type=action_type,
            regime=regime,
            thought=thought,
            input_context=input_context,
            output_result=output_result,
            is_success=is_success,
        )

    async def run_prompt(self, user_prompt: str, message_history: Optional[list] = None) -> Any:
        """Executes a prompt against the underlying LLM agent with audit logging."""
        if not self._agent:
            msg = f"Agent [{self.name}] LLM is not initialized (missing API key or model)."
            logger.warning(msg)
            await self.log_step(action_type="LLM_RUN_FAILED", thought=msg, is_success=False)
            return None

        try:
            result = await self._agent.run(user_prompt, message_history=message_history)
            data = result.data
            await self.log_step(
                action_type="LLM_RUN_SUCCESS",
                input_context={"prompt": user_prompt},
                output_result=data if isinstance(data, (dict, list, str, int, float)) else str(data),
                is_success=True,
            )
            return data
        except Exception as exc:
            logger.error(f"Agent [{self.name}] run failed: {exc}")
            await self.log_step(
                action_type="LLM_RUN_ERROR",
                input_context={"prompt": user_prompt},
                output_result=str(exc),
                is_success=False,
            )
            raise
