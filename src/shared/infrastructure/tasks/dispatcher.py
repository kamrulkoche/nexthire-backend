"""Running work after the response has been sent.

sp-company-backend queues background work on ARQ (Redis db=1). hgs-backend has
no background work at all and dropped it. NextHire AI has one kind — running a
collection — and no Redis on the development machine, so work is handed to a
small thread pool in this process instead.

Callers depend on ``TaskDispatcher``, never on the pool, so moving to ARQ means
writing one class that enqueues instead of submitting. Tests override
``get_task_dispatcher`` with ``InlineTaskDispatcher``, which runs the work
before the request returns and so makes the outcome assertable.

Each task runs in its own event loop (``asyncio.run``) on a worker thread, and
must open its OWN database session: the request's session is closed by the
time the task runs.
"""

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from ..logging import get_logger

logger = get_logger(__name__)

Task = Callable[[], Awaitable[None]]


class TaskDispatcher(Protocol):
    """Something that runs a task, now or later."""

    async def submit(self, task: Task, *, name: str) -> None:
        """Hand over a task.

        Args:
            task: A zero-argument coroutine function
            name: For the logs
        """
        ...


def _run_isolated(task: Task, name: str) -> None:
    """Run one task on a fresh event loop, logging rather than raising."""
    try:
        asyncio.run(task())  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"Background task '{name}' failed: {e}", exc_info=True)


class ThreadTaskDispatcher:
    """Runs tasks on a small pool of worker threads."""

    def __init__(self, max_workers: int = 2) -> None:
        """Create the pool.

        Args:
            max_workers: Concurrent tasks. Two is plenty: a run is I/O-bound,
                and the source claim stops two workers taking the same source.
        """
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="nexthire-task"
        )

    async def submit(self, task: Task, *, name: str) -> None:
        """Queue the task on the pool and return immediately."""
        logger.info(f"Dispatching background task '{name}'")
        self._pool.submit(_run_isolated, task, name)

    def shutdown(self) -> None:
        """Stop accepting work; let running tasks finish."""
        self._pool.shutdown(wait=False, cancel_futures=True)


class InlineTaskDispatcher:
    """Runs the task before returning. For tests and scripts."""

    async def submit(self, task: Task, *, name: str) -> None:
        """Await the task in the caller's loop."""
        await task()


#: The process-wide dispatcher. Routes reach it through `get_task_dispatcher`
#: so tests can swap it.
task_dispatcher = ThreadTaskDispatcher()


def get_task_dispatcher() -> TaskDispatcher:
    """FastAPI dependency returning the process-wide dispatcher."""
    return task_dispatcher
