"""Unit tests for the persistent background async runner (infra/async_runner).

RED phase: the production module `infra/async_runner.py` does not exist yet.
These tests describe the expected contract:

- `async_runner.run(coro)` schedules `coro` on a single persistent background
  event loop and blocks until the result is available, returning it.
- The loop is created lazily on first use and reused on subsequent calls.
- The coroutine runs on a background thread distinct from the caller, and the
  same background thread/loop is reused across calls.
- Exceptions raised inside the coroutine propagate to the caller of `run`.
"""

import threading

import pytest

from infra import async_runner


class TestAsyncRunnerResult:

    def test_run__returns_coroutine_result(self):
        async def f():
            return 42

        assert async_runner.run(f()) == 42

    def test_run__two_sequential_calls__return_each_value(self):
        async def f(value):
            return value

        assert async_runner.run(f("first")) == "first"
        assert async_runner.run(f(2)) == 2


class TestAsyncRunnerThreading:

    def test_run__coroutine_runs_on_a_different_thread(self):
        caller_thread_id = threading.get_ident()

        async def capture_thread():
            return threading.get_ident()

        coroutine_thread_id = async_runner.run(capture_thread())

        assert coroutine_thread_id != caller_thread_id

    def test_run__reuses_same_background_thread_across_calls(self):
        async def capture_thread():
            return threading.get_ident()

        first_thread_id = async_runner.run(capture_thread())
        second_thread_id = async_runner.run(capture_thread())

        assert first_thread_id == second_thread_id


class TestAsyncRunnerExceptions:

    def test_run__coroutine_raises__propagates_exception(self):
        async def boom():
            raise ValueError("x")

        with pytest.raises(ValueError):
            async_runner.run(boom())
