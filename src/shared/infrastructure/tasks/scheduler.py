"""The collection scheduler.

APScheduler's ``BackgroundScheduler`` in the API process, ticking every
``SCHEDULER_TICK_SECONDS``. The scheduler decides only WHEN to look; which
sources are due, and claiming them so no two processes run the same one, is the
collection module's job (``RunDueCollectionsUseCase``). That keeps this file
free of business rules, and means a second API replica with the scheduler left
on would still never double-run a source — the claim is a database row update,
not an in-memory lock.

Turn it off with ``SCHEDULER_ENABLED=false`` (tests, scripts, extra replicas).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from ...utils.config import settings
from ..logging import get_logger

logger = get_logger(__name__)

Tick = Callable[[], Awaitable[None]]

_scheduler: Optional[BackgroundScheduler] = None


def _run_tick(tick: Tick) -> None:
    """Run one tick on a fresh event loop. Never lets an error kill the job."""
    try:
        asyncio.run(tick())  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"Scheduler tick failed: {e}", exc_info=True)


def start_scheduler(tick: Tick) -> None:
    """Start ticking, unless disabled or already started.

    Args:
        tick: The coroutine function to run on every tick
    """
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("Collection scheduler is disabled (SCHEDULER_ENABLED=false)")
        return
    if _scheduler is not None:
        return

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_tick,
        "interval",
        args=[tick],
        seconds=settings.scheduler_tick_seconds,
        id="collection-tick",
        # One tick at a time: a slow tick is skipped over, not stacked.
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        f"Collection scheduler started (tick every {settings.scheduler_tick_seconds}s)"
    )


def shutdown_scheduler() -> None:
    """Stop the scheduler if it is running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Collection scheduler stopped")
