from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

# Keep strong references to in-flight tasks. asyncio only holds a weak reference
# to a task, so without this a fire-and-forget task can be garbage-collected
# mid-run. The done callback drops the reference once it finishes.
_background_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Schedule a coroutine to run in the background, keeping it alive."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
