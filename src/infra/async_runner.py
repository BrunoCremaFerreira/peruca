"""Persistent background event loop for running coroutines from sync code.

Graph nodes are synchronous but call async services. Spinning up a fresh event
loop per call (``asyncio.run``) tears down and recreates the loop every time,
which prevents reuse of long-lived async resources such as aiohttp connection
pools. This module keeps a single event loop alive on a dedicated daemon thread
and reuses it across calls, so connections can be pooled and per-call loop
setup/teardown overhead is avoided.
"""

import asyncio
import threading
from typing import Any, Coroutine

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is not None:
        return _loop
    with _lock:
        if _loop is None:
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever,
                name="async-runner",
                daemon=True,
            )
            thread.start()
            _loop = loop
    return _loop


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run ``coro`` on the persistent background loop and block for its result.

    Exceptions raised inside the coroutine propagate to the caller.
    """
    loop = _ensure_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()
