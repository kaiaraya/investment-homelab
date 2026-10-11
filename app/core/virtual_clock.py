"""
Virtual Clock & Time Acceleration Engine.
Provides a controllable virtual clock for Phase 3 Trading Homelab Simulation.
Supports:
1. REAL_TIME: Follows actual system time (UTC+7 Bangkok).
2. ACCELERATED: Multiplies time flow (e.g. 10x, 60x where 1 real second = 1 virtual minute).
3. FAST_FORWARD: Advances instantly to specific trading milestone hours.
4. PAUSED: Freezes time when waiting for interactive HITL (Human-in-the-Loop) responses.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)

BKK_TZ = timezone(timedelta(hours=7))


class VirtualClock:
    def __init__(self):
        self._mode: str = "REAL_TIME"  # REAL_TIME, ACCELERATED, FAST_FORWARD, PAUSED
        self._speed_multiplier: float = 1.0
        self._simulated_time: Optional[datetime] = None
        self._last_real_anchor: Optional[datetime] = None
        self._pause_anchor: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._listeners: List[Callable[[datetime], None]] = []

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def speed_multiplier(self) -> float:
        return self._speed_multiplier

    def now(self) -> datetime:
        """Returns the current effective time (either real Bangkok time or virtual simulated time)."""
        if self._mode == "REAL_TIME" or self._simulated_time is None:
            return datetime.now(BKK_TZ)

        if self._mode == "PAUSED":
            return self._simulated_time

        if self._mode == "ACCELERATED":
            # Calculate elapsed real time multiplied by speed
            real_now = datetime.now(BKK_TZ)
            if self._last_real_anchor:
                elapsed_real = (real_now - self._last_real_anchor).total_seconds()
                simulated_advance = elapsed_real * self._speed_multiplier
                return self._simulated_time + timedelta(seconds=simulated_advance)
            return self._simulated_time

        # FAST_FORWARD / MANUAL
        return self._simulated_time

    def set_real_time_mode(self) -> None:
        """Restores real system time."""
        self._mode = "REAL_TIME"
        self._simulated_time = None
        self._last_real_anchor = None
        self._speed_multiplier = 1.0
        logger.info("VirtualClock: Switched to REAL_TIME mode.")

    def set_accelerated_mode(self, speed_multiplier: float = 60.0, start_time_str: str = "09:30") -> datetime:
        """
        Starts accelerated time from a given start time (default 09:30 AM today).
        speed_multiplier=60 means 1 real second = 1 virtual minute.
        """
        today_bkk = datetime.now(BKK_TZ).date()
        hour, minute = map(int, start_time_str.split(":"))
        start_dt = datetime(today_bkk.year, today_bkk.month, today_bkk.day, hour, minute, 0, tzinfo=BKK_TZ)

        self._mode = "ACCELERATED"
        self._speed_multiplier = speed_multiplier
        self._simulated_time = start_dt
        self._last_real_anchor = datetime.now(BKK_TZ)
        logger.info(f"VirtualClock: ACCELERATED mode active at {speed_multiplier}x speed from {start_time_str}")
        return self.now()

    def advance_to(self, time_str: str) -> datetime:
        """
        Fast-forwards virtual clock directly to a target time of the current day (e.g. '10:15', '11:00', '16:35').
        """
        current = self.now()
        hour, minute = map(int, time_str.split(":"))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        self._simulated_time = target
        self._last_real_anchor = datetime.now(BKK_TZ)
        self._mode = "FAST_FORWARD"
        logger.info(f"VirtualClock: Fast-forwarded to {time_str}")
        return target

    def advance_minutes(self, minutes: int) -> datetime:
        """Advances virtual time forward by N minutes."""
        current = self.now()
        target = current + timedelta(minutes=minutes)
        self._simulated_time = target
        self._last_real_anchor = datetime.now(BKK_TZ)
        return target

    def pause(self) -> datetime:
        """Pauses the virtual clock (e.g. while awaiting human decision)."""
        current = self.now()
        self._simulated_time = current
        self._mode = "PAUSED"
        logger.info(f"VirtualClock: Clock PAUSED at {current.strftime('%H:%M:%S')}")
        return current

    def resume(self) -> datetime:
        """Resumes clock from paused state."""
        if self._mode == "PAUSED":
            self._mode = "ACCELERATED" if self._speed_multiplier > 1.0 else "FAST_FORWARD"
            self._last_real_anchor = datetime.now(BKK_TZ)
            logger.info(f"VirtualClock: Clock RESUMED at {self.now().strftime('%H:%M:%S')}")
        return self.now()

    def format_status(self) -> dict:
        """Returns diagnostic status of the virtual clock."""
        curr = self.now()
        return {
            "mode": self._mode,
            "speed_multiplier": f"{self._speed_multiplier}x",
            "current_virtual_time": curr.strftime("%Y-%m-%d %H:%M:%S"),
            "current_time_str": curr.strftime("%H:%M"),
            "is_market_open": "10:00" <= curr.strftime("%H:%M") <= "16:35",
            "next_milestone": self._get_next_milestone(curr.strftime("%H:%M"))
        }

    def _get_next_milestone(self, time_str: str) -> str:
        milestones = [
            ("09:30", "Morning Login Prep"),
            ("10:00", "Market Open / Trade Center"),
            ("10:15", "Portfolio Overview & Missing TP/SL Check"),
            ("11:00", "Price Negotiation Round 1 (Morning Unmatched)"),
            ("15:30", "Price Negotiation Round 2 (Afternoon Unmatched)"),
            ("16:35", "Market Close / EOD Reconciliation")
        ]
        for m_time, label in milestones:
            if time_str < m_time:
                return f"{m_time} - {label}"
        return "Market Closed (EOD Complete)"


# Global singleton instance
virtual_clock = VirtualClock()
