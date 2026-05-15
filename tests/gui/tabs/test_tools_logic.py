"""Unit tests for tools_logic async cancellation semantics."""

from __future__ import annotations

import asyncio

import pytest

from tina.gui.tabs.tools_logic import delayed_tools_refresh


@pytest.mark.unit
class TestDelayedToolsRefreshCancellation:
    """Verify CancelledError propagation in delayed_tools_refresh."""

    @pytest.mark.asyncio
    async def test_parent_cancellation_propagates(self) -> None:
        """Cancelling the enclosing task must re-raise CancelledError."""
        long_running = asyncio.Event()

        async def _slow() -> None:
            await long_running.wait()

        app = _make_app(_slow, _slow)

        task = asyncio.create_task(delayed_tools_refresh(app))
        await asyncio.sleep(0)  # let gather start
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_inner_cancelled_error_propagates(self) -> None:
        """CancelledError raised inside a gathered coroutine must propagate out."""

        async def _raises_cancelled() -> None:
            raise asyncio.CancelledError

        async def _noop() -> None:
            return

        app = _make_app(_raises_cancelled, _noop)

        with pytest.raises(asyncio.CancelledError):
            await delayed_tools_refresh(app)


def _make_app(computation_coro_factory, plot_coro_factory):
    """Return a minimal app stub whose async methods call the given factories."""

    class _App:
        def _is_tools_tab_active(self) -> bool:
            return True

        async def _run_tools_computation_async(self) -> None:
            await computation_coro_factory()

        async def _refresh_tools_plot(self) -> None:
            await plot_coro_factory()

    return _App()
