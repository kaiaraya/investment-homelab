import logging
from typing import Any, Dict, List, Optional
from app.ai.agents.base import BaseSubAgent
from app.ai.signal_agent import create_signal_agent
from app.ai.memory import agent_memory
from app.schemas.intelligence import SignalParseResult

logger = logging.getLogger(__name__)


class MarketAnalystAgent(BaseSubAgent):
    """
    Sub-Agent governing Market Intelligence, Signal Ingestion, and Real-Time Price Monitoring (SOP-002).
    """

    def __init__(self, model_override: Optional[Any] = None):
        super().__init__(
            name="MarketAnalystAgent",
            sop_filename="sop_market_signals.md",
            model_override=model_override,
            output_type=SignalParseResult,
        )
        self._signal_extractor = None

    def _get_signal_extractor(self):
        if self._signal_extractor is None:
            try:
                self._signal_extractor = create_signal_agent(model_override=self.model)
            except Exception as exc:
                logger.warning(f"Could not initialize PydanticAI SignalParserAgent: {exc}")
        return self._signal_extractor

    async def ingest_signal(self, text: str) -> Optional[SignalParseResult]:
        """Parses raw Thai/English trading reports into structured SignalParseResult."""
        await self.log_step(
            action_type="INGEST_SIGNAL",
            thought="Extracting actionable orders, watchlist triggers, and hold positions from text.",
            input_context={"text_preview": text[:150]},
        )
        extractor = self._get_signal_extractor()
        if not extractor:
            logger.warning("Signal extractor unavailable.")
            return None

        try:
            result = await extractor.run(text)
            data: SignalParseResult = result.data
            await self.log_step(
                action_type="SIGNAL_PARSED",
                output_result=data.model_dump() if hasattr(data, "model_dump") else str(data),
                is_success=True,
            )
            return data
        except Exception as exc:
            logger.error(f"Failed to parse signal: {exc}")
            await self.log_step(
                action_type="SIGNAL_PARSE_ERROR",
                output_result=str(exc),
                is_success=False,
            )
            return None

    async def register_price_watch(
        self,
        symbol: str,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        side: str = "LONG",
    ) -> Dict[str, Any]:
        """Registers a symbol for real-time Settrade MQTT monitoring."""
        clean_symbol = symbol.strip().upper()
        agent_memory.set_working_key(f"watch_{clean_symbol}", {
            "tp_price": tp_price,
            "sl_price": sl_price,
            "side": side,
        })
        working = agent_memory.get_working_key("active_symbols", set())
        if isinstance(working, set):
            working.add(clean_symbol)
            agent_memory.set_working_key("active_symbols", working)

        result = {
            "symbol": clean_symbol,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "side": side,
            "status": "WATCHING",
        }
        await self.log_step(
            action_type="REGISTER_WATCH",
            thought=f"Registered {clean_symbol} for real-time TP/SL price monitoring.",
            input_context=result,
            output_result=result,
            is_success=True,
        )
        return result

    async def evaluate_tick(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """Evaluates whether current price breaches TP, SL, or abnormal fluctuation levels."""
        clean_symbol = symbol.strip().upper()
        watch_config = agent_memory.get_working_key(f"watch_{clean_symbol}")
        if not watch_config:
            return None

        tp = watch_config.get("tp_price")
        sl = watch_config.get("sl_price")
        side = watch_config.get("side", "LONG")

        trigger_event = None
        if side == "LONG":
            if tp and current_price >= tp:
                trigger_event = {"type": "TAKE_PROFIT", "action": "SELL", "price": current_price, "target": tp}
            elif sl and current_price <= sl:
                trigger_event = {"type": "STOP_LOSS", "action": "SELL", "price": current_price, "target": sl}
        elif side == "SHORT":
            if tp and current_price <= tp:
                trigger_event = {"type": "TAKE_PROFIT", "action": "COVER", "price": current_price, "target": tp}
            elif sl and current_price >= sl:
                trigger_event = {"type": "STOP_LOSS", "action": "COVER", "price": current_price, "target": sl}

        if trigger_event:
            payload = {
                "symbol": clean_symbol,
                "trigger_event": trigger_event,
                "current_price": current_price,
            }
            await self.log_step(
                action_type="PRICE_TRIGGER_BREACHED",
                thought=f"Price threshold breached for {clean_symbol}: {trigger_event['type']}",
                output_result=payload,
                is_success=True,
            )
            return payload
        return None
