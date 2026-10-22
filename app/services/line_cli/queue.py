"""
Async Command Queue for LINE CLI (Loop 2).

Decouples long-running CLI operations (CDP scraping, login/OTP, order execution)
from the incoming LINE Webhook HTTP request lifecycle.
- Webhook receives command -> enqueues job -> immediately returns HTTP 200.
- In-memory asyncio.Queue processed by a single background worker task.
- Per-command timeout guard (e.g. 30s standard, 180s for login).
- On success/failure/timeout: pushes result card/alert directly to the originating chat.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0
LOGIN_TIMEOUT_SECONDS = 180.0
NEGO_TIMEOUT_SECONDS = 45.0


@dataclass
class CommandJob:
    """A unit of work queued for async background execution."""

    job_id: str
    cmd_name: str
    func: Callable[[], Coroutine[Any, Any, Dict[str, Any]]]
    push_target: Optional[str]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    created_at: float = field(default_factory=time.time)


class AsyncCommandQueue:
    """In-memory asyncio.Queue worker with timeout and honest push alerts."""

    def __init__(self, maxsize: int = 50):
        self._maxsize = maxsize
        self._queue: Optional[asyncio.Queue[CommandJob]] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_queue(self) -> asyncio.Queue[CommandJob]:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if self._queue is None or (current_loop is not None and self._bound_loop is not current_loop):
            self._queue = asyncio.Queue(maxsize=self._maxsize)
            self._bound_loop = current_loop
        return self._queue

    @property
    def is_running(self) -> bool:
        return self._running and self._worker_task is not None and not self._worker_task.done()

    @property
    def pending_count(self) -> int:
        if self._queue is None:
            return 0
        return self._queue.qsize()

    def get_status(self) -> Dict[str, Any]:
        """Returns health/diagnostic status of the queue."""
        return {
            "running": self.is_running,
            "pending_count": self.pending_count,
        }

    def start(self):
        """Starts the background worker task."""
        if self.is_running:
            return
        self._get_queue()
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="line_cli_command_worker")
        logger.info("[AsyncCommandQueue] Background worker started.")

    async def stop(self):
        """Stops the background worker gracefully."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._queue = None
        logger.info("[AsyncCommandQueue] Background worker stopped.")

    async def enqueue(
        self,
        cmd_name: str,
        func: Callable[[], Coroutine[Any, Any, Dict[str, Any]]],
        push_target: Optional[str],
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> Optional[str]:
        """Enqueues a job and returns its unique job_id (or None if queue is full)."""
        job_id = uuid.uuid4().hex[:8]
        job = CommandJob(
            job_id=job_id,
            cmd_name=cmd_name,
            func=func,
            push_target=push_target,
            timeout_seconds=timeout_seconds,
        )
        try:
            self._get_queue().put_nowait(job)
        except asyncio.QueueFull:
            logger.warning(
                f"[AsyncCommandQueue] Queue is full ({self._maxsize} jobs). Cannot enqueue {cmd_name}"
            )
            return None

        logger.info(
            f"[AsyncCommandQueue] Enqueued job {job_id} ({cmd_name}) for push_target={push_target} (timeout={timeout_seconds}s)"
        )
        return job_id

    async def _worker_loop(self):
        """Processes jobs from queue one at a time."""
        while self._running:
            try:
                job = await self._get_queue().get()
            except asyncio.CancelledError:
                break

            try:
                await self._process_job(job)
            except Exception as e:
                logger.exception(f"[AsyncCommandQueue] Unhandled error processing job {job.job_id}: {e}")
            finally:
                if self._queue is not None:
                    self._queue.task_done()

    async def _process_job(self, job: CommandJob):
        """Executes a single job with timeout protection."""
        from app.services.line_service import line_service

        logger.info(f"[AsyncCommandQueue] Processing job {job.job_id} ({job.cmd_name})...")
        start_t = time.time()
        try:
            # Enforce timeout guard
            await asyncio.wait_for(job.func(), timeout=job.timeout_seconds)
            elapsed = time.time() - start_t
            logger.info(f"[AsyncCommandQueue] Job {job.job_id} ({job.cmd_name}) completed in {elapsed:.2f}s")
        except asyncio.TimeoutError:
            elapsed = time.time() - start_t
            logger.warning(
                f"[AsyncCommandQueue] Job {job.job_id} ({job.cmd_name}) timed out after {elapsed:.2f}s (limit {job.timeout_seconds}s)"
            )
            target = job.push_target or getattr(settings, "LINE_GROUP_ID", None) or getattr(settings, "LINE_ADMIN_USER_ID", None)
            if target:
                timeout_msg = (
                    f"⚠️ คำสั่ง '{job.cmd_name}' หมดเวลา ({int(job.timeout_seconds)} วินาที)\n"
                    "ระบบได้ยกเลิกคำสั่งและคืนสถานะปลอดภัย เพื่อป้องกันข้อผิดพลาด"
                )
                try:
                    await line_service.push_message(timeout_msg, to_user_id=target)
                except Exception as pe:
                    logger.error(f"[AsyncCommandQueue] Failed to push timeout notice: {pe}")
        except Exception as e:
            elapsed = time.time() - start_t
            logger.exception(f"[AsyncCommandQueue] Job {job.job_id} failed after {elapsed:.2f}s: {e}")
            target = job.push_target or getattr(settings, "LINE_GROUP_ID", None) or getattr(settings, "LINE_ADMIN_USER_ID", None)
            if target:
                err_msg = f"❌ เกิดข้อผิดพลาดในการประมวลผลคำสั่ง '{job.cmd_name}': {type(e).__name__} {str(e)[:100]}"
                try:
                    await line_service.push_message(err_msg, to_user_id=target)
                except Exception as pe:
                    logger.error(f"[AsyncCommandQueue] Failed to push error notice: {pe}")


# Global singleton instance
async_command_queue = AsyncCommandQueue()
