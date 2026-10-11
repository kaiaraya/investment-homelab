import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.virtual_clock import virtual_clock
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.price_negotiation_service import price_negotiation_service
from app.services.eod_service import eod_service
from app.services.market_monitor_service import market_monitor_service

logger = logging.getLogger(__name__)


class Phase3Scheduler:
    """
    Background Task Scheduler for Phase 3 (8 Market Regimes):
    1. 09:30 - 10:00 (Pre-Market):
       - Browser Session Check & 3.1 Portfolio Overview
    2. 10:00 - 10:30 (Retail Morning Open):
       - Monitor SET Index (%Change, High, Low, Vol, Val), no auto trades
       - 10:30: Report SET Index 1-line to LINE
    3. 10:30 - 12:00 (Auto Trading Window 1):
       - 3 Random Points (spaced >= 15m) executing 3.2 Alerts -> 3.3 Trades -> 3.4 Price Negotiation
    4. 12:00 - 12:30 (Morning Close & Midday Review):
       - 12:00: Lunchtime Action Center Reminder (if pending orders exist)
       - Monitor SET Index, no auto trades
       - 12:30: Report SET Index 1-line to LINE
    5. 14:00 - 14:30 (Retail Afternoon Open):
       - Monitor SET Index, no auto trades
       - 14:30: Report SET Index 1-line to LINE
    6. 14:30 - 16:00 (Auto Trading Window 2):
       - 3 Random Points (spaced >= 15m) executing 3.2 Alerts -> 3.3 Trades -> 3.4 Price Negotiation
    7. 16:00 - 16:30 (Day Close / ATC):
       - Monitor SET Index, no auto trades
       - 16:30: Report SET Index 1-line to LINE
    8. 16:30 - 17:00 (Post-Market):
       - 16:35: 3.5 End-of-Day (EOD) Summary Report & Account Equity
       - Browser safe logout / close

    Supports both real system time and accelerated VirtualClock for time-warp simulations.
    """

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_executed_minute: Optional[str] = None
        self._current_day: Optional[str] = None
        self.morning_random_points: List[str] = ["10:45", "11:15", "11:45"]
        self.afternoon_random_points: List[str] = ["14:45", "15:15", "15:45"]

    @staticmethod
    def generate_random_points(start_str: str, end_str: str, count: int = 3, min_gap_mins: int = 15) -> List[str]:
        """
        Generates N random time points between start_str and end_str with at least min_gap_mins separation.
        """
        def to_mins(t_str: str) -> int:
            h, m = map(int, t_str.split(":"))
            return h * 60 + m

        start_m = to_mins(start_str) + 5
        end_m = to_mins(end_str) - 5
        total_span = end_m - start_m

        for _ in range(100):
            pts = sorted(random.sample(range(start_m, end_m + 1), count))
            if all(pts[i] - pts[i - 1] >= min_gap_mins for i in range(1, len(pts))):
                return [f"{p // 60:02d}:{p % 60:02d}" for p in pts]

        # Fallback to even distribution if random sample took > 100 tries
        step = total_span // (count + 1)
        pts = [start_m + (i + 1) * step for i in range(count)]
        return [f"{p // 60:02d}:{p % 60:02d}" for p in pts]

    def _ensure_daily_random_points(self, now_bkk: datetime) -> None:
        today_str = now_bkk.strftime("%Y-%m-%d")
        if self._current_day != today_str:
            self._current_day = today_str
            self.morning_random_points = self.generate_random_points("10:30", "12:00", count=3, min_gap_mins=15)
            self.afternoon_random_points = self.generate_random_points("14:30", "16:00", count=3, min_gap_mins=15)
            logger.info(
                f"Phase3Scheduler: Generated daily random points for {today_str} -> "
                f"Morning: {self.morning_random_points}, Afternoon: {self.afternoon_random_points}"
            )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"Phase3Scheduler started (checking every {self.check_interval}s)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Phase3Scheduler stopped.")

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                now_bkk = virtual_clock.now()
                current_time_str = now_bkk.strftime("%H:%M")
                weekday = now_bkk.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

                is_simulation = virtual_clock.mode != "REAL_TIME"
                if weekday < 5 or is_simulation:
                    self._ensure_daily_random_points(now_bkk)

                    # 1. 09:30 / 10:15 -> Portfolio Overview
                    overview_times = ["09:30", settings.PORTFOLIO_OVERVIEW_TIME]
                    if current_time_str in overview_times and self._last_executed_minute != f"overview_{current_time_str}":
                        self._last_executed_minute = f"overview_{current_time_str}"
                        logger.info(f"Triggering Portfolio Overview on {current_time_str} (Mode: {virtual_clock.mode})...")
                        asyncio.create_task(self.trigger_portfolio_overview(period_time=current_time_str))

                    # 2. SET Market Observation Reports: 10:30, 12:30, 14:30, 16:30
                    set_report_times = ["10:30", "12:30", "14:30", "16:30"]
                    if current_time_str in set_report_times and self._last_executed_minute != f"set_{current_time_str}":
                        self._last_executed_minute = f"set_{current_time_str}"
                        logger.info(f"Triggering SET Index 1-line Report on {current_time_str}...")
                        asyncio.create_task(market_monitor_service.capture_and_report(period_label=current_time_str))

                    # 3. Random Execution Points (10:30-12:00 & 14:30-16:00)
                    all_random_points = self.morning_random_points + self.afternoon_random_points
                    if current_time_str in all_random_points and self._last_executed_minute != f"random_{current_time_str}":
                        self._last_executed_minute = f"random_{current_time_str}"
                        logger.info(f"Triggering Random Execution Point on {current_time_str} (Mode: {virtual_clock.mode})...")
                        asyncio.create_task(self.trigger_random_execution_point(round_time=current_time_str))

                    # Legacy explicit negotiation rounds support (e.g. 11:00, 15:30)
                    if current_time_str in settings.PRICE_NEGOTIATION_ROUNDS and self._last_executed_minute != f"nego_{current_time_str}":
                        self._last_executed_minute = f"nego_{current_time_str}"
                        logger.info(f"Triggering Scheduled Price Negotiation on {current_time_str}...")
                        asyncio.create_task(self.trigger_price_negotiation(round_name=current_time_str))

                    # 4. 12:00 -> Lunchtime Action Center Reminder
                    if current_time_str == "12:00" and self._last_executed_minute != f"lunch_{current_time_str}":
                        self._last_executed_minute = f"lunch_{current_time_str}"
                        logger.info(f"Triggering 12:00 Lunchtime Action Center Reminder on {current_time_str}...")
                        asyncio.create_task(self.trigger_lunchtime_reminder())

                    # 5. 16:35 -> End-of-Day (EOD) Summary Report
                    if current_time_str == settings.EOD_REPORT_TIME and self._last_executed_minute != f"eod_{current_time_str}":
                        self._last_executed_minute = f"eod_{current_time_str}"
                        logger.info(f"Triggering 16:35 End-of-Day (EOD) Summary on {current_time_str} (Mode: {virtual_clock.mode})...")
                        asyncio.create_task(self.trigger_eod_summary())

                # Sleep interval
                sleep_sec = 1.0 if virtual_clock.mode == "ACCELERATED" and virtual_clock.speed_multiplier >= 10 else self.check_interval
                await asyncio.sleep(sleep_sec)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Phase3Scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

    # -------------------------------------------------------------
    # On-Demand Direct Triggers (Instant testing without waiting)
    # -------------------------------------------------------------

    async def trigger_portfolio_overview(self, period_time: str = "10:15") -> dict:
        """Forces an immediate run of 3.1 Portfolio Overview with 1-line progress reports."""
        logger.info(f"Phase3Scheduler: Manual trigger -> 3.1 Portfolio Overview ({period_time})")
        from app.services.line_service import line_service
        await line_service.push_progress_update(f"⏳ [{period_time}] กำลังเริ่มกวาดข้อมูลพอร์ตและตรวจสอบสิทธิ์ SBL...")
        res = await portfolio_overview_service.run_overview()
        count = len(res.get("portfolio", []))
        await line_service.push_progress_update(f"✅ [{period_time}] กวาดพอร์ตสำเร็จ {count} รายการ (ซิงค์ฐานข้อมูล SQLite เรียบร้อย)")
        return res

    async def trigger_random_execution_point(self, round_time: str = "11:15") -> dict:
        """
        Executes the 3.4 Price Negotiation sequence with human investor step-by-step pacing.
        """
        logger.info(f"Phase3Scheduler: Executing random routine at {round_time}...")
        from app.services.line_service import line_service
        await line_service.push_progress_update(f"⏳ [{round_time}] เริ่มรอบทำงานอัตโนมัติ (3.4 ต่อราคา)...")

        # Human pause between modules
        await asyncio.sleep(2.0)

        # Price Negotiation
        nego_res = await price_negotiation_service.run_negotiation_round(round_name=round_time)

        await line_service.push_progress_update(f"✅ [{round_time}] รอบทำงานอัตโนมัติ 3.4 เสร็จสิ้นเรียบร้อย")
        return {
            "round_time": round_time,
            "negotiation": nego_res
        }

    async def trigger_price_negotiation(self, round_name: str = "11:00") -> dict:
        """Forces an immediate run of 3.4 Price Negotiation Round with 1-line progress reports."""
        logger.info(f"Phase3Scheduler: Manual trigger -> 3.4 Price Negotiation ({round_name})")
        from app.services.line_service import line_service
        await line_service.push_progress_update(f"⏳ [{round_name}] กำลังเริ่มตรวจคำสั่งค้างและคำนวณต่อราคา Bid/Offer...")
        res = await price_negotiation_service.run_negotiation_round(round_name=round_name)
        await line_service.push_progress_update(f"✅ [{round_name}] ตรวจสอบคำสั่งค้างและคำนวณต่อราคาเสร็จสิ้น")
        return res

    async def trigger_lunchtime_reminder(self) -> dict:
        """Sends 12:00 lunchtime reminder if there are pending actions in Action Center."""
        from app.services.action_center_service import action_center_service
        from app.services.line_service import line_service
        count = action_center_service.get_pending_count()
        if count > 0:
            card = action_center_service.build_lunchtime_reminder_card()
            await line_service.push_message(card)
            logger.info(f"Sent 12:00 lunchtime reminder for {count} pending actions")
            return {"sent": True, "pending_count": count}
        else:
            logger.info("12:00 lunchtime check: No pending actions. Skipping reminder.")
            return {"sent": False, "pending_count": 0}

    async def trigger_eod_summary(self) -> dict:
        """Forces an immediate run of 3.5 End-of-Day (EOD) Summary with 1-line progress reports."""
        logger.info("Phase3Scheduler: Manual trigger -> 3.5 EOD Summary")
        from app.services.line_service import line_service
        await line_service.push_progress_update("⏳ [16:35] กำลังเริ่มคำนวณสรุป PnL ปิดตลาดและค่าธรรมเนียม...")
        res = await eod_service.run_eod_summary()
        await line_service.push_progress_update("✅ [16:35] ออกรายงานสรุปการเทรดประจำวันส่งเข้า LINE เรียบร้อย")
        return res

    def get_daily_schedule(self) -> Dict[str, Any]:
        """Returns the full market regimes timeline and today's generated random execution points."""
        return {
            "current_day": self._current_day,
            "regimes": [
                {"period": "09:30 - 10:00", "name": "Pre-Market Login & 3.1 Overview", "status": "AUTOMATED"},
                {"period": "10:00 - 10:30", "name": "Retail Morning Open (SET Monitor only)", "status": "MONITOR_ONLY"},
                {"period": "10:30 - 12:00", "name": "Auto Trading Window 1 (3 Random Points)", "status": "AUTOMATED", "points": self.morning_random_points},
                {"period": "12:00 - 12:30", "name": "Morning Close & Lunchtime Reminder", "status": "MONITOR_ONLY"},
                {"period": "14:00 - 14:30", "name": "Retail Afternoon Open (SET Monitor only)", "status": "MONITOR_ONLY"},
                {"period": "14:30 - 16:00", "name": "Auto Trading Window 2 (3 Random Points)", "status": "AUTOMATED", "points": self.afternoon_random_points},
                {"period": "16:00 - 16:30", "name": "Day Close / ATC (SET Monitor only)", "status": "MONITOR_ONLY"},
                {"period": "16:30 - 17:00", "name": "Post-Market EOD Report & Logout", "status": "AUTOMATED"}
            ]
        }


phase3_scheduler = Phase3Scheduler()
