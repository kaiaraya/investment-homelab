import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.trademan_driver import trademan_driver
from app.db.models import MarketSnapshot
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class MarketMonitorService:
    """
    Market Monitor Service for SET Index Tracking:
    Active during market observation windows:
    1. 10:00 - 10:30 (Retail Morning Open) -> Report at 10:30
    2. 12:00 - 12:30 (Morning Close & Lunchtime) -> Report at 12:30
    3. 14:00 - 14:30 (Retail Afternoon Open) -> Report at 14:30
    4. 16:00 - 16:30 (Day Close / ATC) -> Report at 16:30

    Features:
    - Scrapes SET %Change, Current Index, High, Low, Volume(K), Value(M)
    - Records snapshots in SQLite DB (MarketSnapshot)
    - Pushes concise 1-line progress update to LINE
    """

    async def capture_and_report(self, period_label: str = "10:30") -> Dict[str, Any]:
        """
        Scrapes the current SET index, persists to database, and sends a 1-line summary to LINE.
        """
        logger.info(f"MarketMonitor: Capturing SET snapshot for period {period_label}...")
        snapshot_data = await trademan_driver.scrape_set_index_summary()

        # Persist to SQLite
        try:
            async with AsyncSessionLocal() as db:
                snapshot = MarketSnapshot(
                    index_name=snapshot_data.get("index_name", "SET"),
                    current_index=float(snapshot_data.get("current_index", 0.0)),
                    change_value=float(snapshot_data.get("change_value", 0.0)),
                    pct_change=float(snapshot_data.get("pct_change", 0.0)),
                    high=float(snapshot_data.get("high", 0.0)),
                    low=float(snapshot_data.get("low", 0.0)),
                    volume_k=float(snapshot_data.get("volume_k", 0.0)),
                    value_mb=float(snapshot_data.get("value_mb", 0.0)),
                    period_name=period_label
                )
                db.add(snapshot)
                await db.commit()
                logger.info(f"MarketMonitor: Snapshot saved to DB (id={snapshot.id})")
        except Exception as e:
            logger.error(f"MarketMonitor: Failed to save snapshot to DB: {e}")

        # Send concise 1-line progress notification to LINE
        summary_text = self.format_1line_summary(snapshot_data, period_label)
        from app.services.line_service import line_service
        try:
            await line_service.push_progress_update(summary_text)
        except Exception as e:
            logger.warning(f"MarketMonitor: Failed to push 1-line to LINE: {e}")

        return {
            "period": period_label,
            "snapshot": snapshot_data,
            "summary_text": summary_text
        }

    def format_1line_summary(self, data: Dict[str, Any], period_label: str) -> str:
        idx = data.get("current_index", 0.0)
        pct = data.get("pct_change", 0.0)
        high = data.get("high", 0.0)
        low = data.get("low", 0.0)
        val = data.get("value_mb", 0.0)
        sign = "+" if pct > 0 else ""
        return f"📊 [{period_label}] SET: {idx:,.2f} ({sign}{pct:.2f}%) High: {high:,.2f} Low: {low:,.2f} Val: {val:,.0f}MB"

    async def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest recorded market snapshot from the database."""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(MarketSnapshot).order_by(desc(MarketSnapshot.created_at)).limit(1)
                res = await db.execute(stmt)
                row = res.scalars().first()
                if row:
                    return {
                        "index_name": row.index_name,
                        "current_index": row.current_index,
                        "change_value": row.change_value,
                        "pct_change": row.pct_change,
                        "high": row.high,
                        "low": row.low,
                        "volume_k": row.volume_k,
                        "value_mb": row.value_mb,
                        "period_name": row.period_name,
                        "created_at": row.created_at.isoformat()
                    }
        except Exception as e:
            logger.error(f"Error fetching latest snapshot: {e}")
        return None


market_monitor_service = MarketMonitorService()
