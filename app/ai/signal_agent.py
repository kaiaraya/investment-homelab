import os
import asyncio
import logging
from typing import Any, Optional

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from pydantic_ai import Agent
from app.ai.providers import get_deepseek_model, is_deepseek_configured
from app.schemas.intelligence import SignalParseResult
from app.schemas.order import OrderSide

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert Thai stock trading system assistant operating on the Stock Exchange of Thailand (SET).
Your job is to read and analyze trading strategy reports, portfolio summaries, or freeform Thai messages,
and extract actionable trading items into a structured `SignalParseResult` model with 100% type safety.

Extraction Rules:
1. `immediate_orders`:
   - Actions requiring IMMEDIATE execution today (e.g. Cut Loss, Hard Time-Exit, Stop Loss hit, Take Profit now, Sell/Cover/Buy/Short).
   - `symbol`: Clean uppercase stock ticker (e.g. 'AOT', 'DELTA', 'TRUE'). Remove trailing notes like '(ไม้ 2)'.
   - `side`: Must be OrderSide ('BUY', 'SELL', 'SHORT', 'COVER').
   - `volume`: Integer shares (e.g. 600, 2000). If stated as relative (e.g. 'ครึ่งหนึ่ง', 'ปิดทั้งหมด'), set volume to 0 and set `is_relative_volume=True`, `volume_pct=50.0` or `100.0`.
   - `price`: Target or limit execution price as float.
   - `reason`: Short rationale (e.g. 'Stop Loss 2.0%', 'Time-Exit 10 days', 'Climax Take Profit').

2. `watchlist_triggers`:
   - Price-based monitoring trigger conditions.
   - For positions with Trailing Stops: action='SELL' (or 'COVER' if short), condition='PRICE_BELOW', trigger_price=trailing_stop_level.
   - For positions with Dynamic TP: action='SELL' (or 'COVER' if short), condition='PRICE_ABOVE', trigger_price=tp_target_level.
   - `notes`: Description of the trigger level.

3. `hold_positions`:
   - Positions designated to continue holding without immediate action today.
   - Extract `days_held`, `current_return_pct`, `trailing_stop_price`, and any `warning_note` (e.g. 'ถือมาแล้ว 8 วัน ใกล้ Time-Exit').

4. `strategy_summary`:
   - A concise Thai summary (1-2 sentences) of today's key actions.

Be precise, objective, and adhere strictly to the schema. Do not invent symbols that do not appear in the text.
"""


def create_signal_agent(model_override: Optional[Any] = None) -> Agent[None, SignalParseResult]:
    """
    Factory creating a PydanticAI Agent configured to extract SignalParseResult.
    Allows injecting a TestModel or alternative model for testing.
    """
    model = model_override or get_deepseek_model()
    if model is None:
        raise ValueError("Cannot create SignalParserAgent: DeepSeek model could not be initialized.")

    return Agent(
        model,
        output_type=SignalParseResult,
        system_prompt=SYSTEM_PROMPT,
    )


class PydanticAISignalParser:
    """
    High-level service interface for PydanticAI Signal Extraction.
    """
    def __init__(self, agent: Optional[Agent[None, SignalParseResult]] = None):
        self._agent = agent

    def get_agent(self) -> Agent[None, SignalParseResult]:
        if self._agent is None:
            self._agent = create_signal_agent()
        return self._agent

    async def parse_strategy(self, text: str) -> SignalParseResult:
        """
        Executes type-safe parsing via PydanticAI.
        Guarantees that the returned object is a valid `SignalParseResult` instance.
        """
        if not is_deepseek_configured() and self._agent is None:
            raise ValueError("DEEPSEEK_API_KEY is not configured for PydanticAI.")

        agent = self.get_agent()
        logger.info("Executing PydanticAI SignalParserAgent...")

        try:
            run_result = await asyncio.wait_for(agent.run(text), timeout=15.0)
            result: SignalParseResult = run_result.output
        except asyncio.TimeoutError:
            logger.warning("PydanticAI SignalParserAgent timed out after 15s.")
            raise TimeoutError("PydanticAI agent execution timed out after 15s")

        # Post-validation enrichment
        result.source_method = "pydantic_ai_deepseek"
        result.total_parsed = (
            len(result.immediate_orders) +
            len(result.watchlist_triggers) +
            len(result.hold_positions)
        )

        logger.info(
            f"PydanticAI SignalParserAgent parsed successfully: "
            f"{len(result.immediate_orders)} immediate orders, "
            f"{len(result.watchlist_triggers)} triggers, "
            f"{len(result.hold_positions)} hold positions"
        )
        return result


# Default singleton instance
signal_ai_parser = PydanticAISignalParser()
