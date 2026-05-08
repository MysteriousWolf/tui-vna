"""Tests for distortion-result cache reuse and invalidation behavior."""

from __future__ import annotations

import numpy as np
import pytest

from tina.gui.tabs import tools_logic
from tina.tools.base import ToolResult


class _FakeApp:
    """Minimal app stub for exercising distortion cache behavior."""

    def __init__(self) -> None:
        self._tools_distortion_cache: dict[tuple, ToolResult] = {}
        self._tools_distortion_cache_last_data_key: tuple | None = None


@pytest.fixture
def distortion_fixture() -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Provide a small but valid response for distortion fitting."""
    freqs = np.linspace(1.0e9, 1.6e9, 9)
    mag = np.linspace(-1.0, 1.0, freqs.size)
    phase = np.linspace(-20.0, 20.0, freqs.size)
    return freqs, {"S21": (mag, phase)}


@pytest.mark.unit
class TestDistortionCache:
    """Cache reuse and invalidation for distortion computations."""

    def test_same_inputs_reuse_cached_result_for_overlay_and_results(
        self, monkeypatch: pytest.MonkeyPatch, distortion_fixture
    ) -> None:
        """Identical inputs should return the cached result and call compute only once."""
        freqs, sparams = distortion_fixture
        app = _FakeApp()
        compute_calls: list[tuple[str, str, float | None, float | None]] = []
        expected = ToolResult(
            tool_name="distortion",
            unit_label="dB",
            extra={"coeffs": [0.0] * 6, "delta_y": [0.0] * 6},
        )

        def fake_compute(
            self,
            compute_freqs: np.ndarray,
            compute_sparams: dict,
            trace: str,
            plot_type: str,
            cursor1_hz: float | None,
            cursor2_hz: float | None,
        ) -> ToolResult:
            np.testing.assert_array_equal(compute_freqs, freqs)
            assert compute_sparams is sparams
            compute_calls.append((trace, plot_type, cursor1_hz, cursor2_hz))
            return expected

        monkeypatch.setattr(tools_logic.DistortionTool, "compute", fake_compute)

        overlay_result = tools_logic._get_cached_distortion_result(
            app,
            freqs,
            sparams,
            "S21",
            "magnitude",
            float(freqs[1]),
            float(freqs[-2]),
        )
        table_result = tools_logic._get_cached_distortion_result(
            app,
            freqs,
            sparams,
            "S21",
            "magnitude",
            float(freqs[1]),
            float(freqs[-2]),
        )

        assert overlay_result is expected
        assert table_result is expected
        assert compute_calls == [
            ("S21", "magnitude", float(freqs[1]), float(freqs[-2]))
        ]
        assert len(app._tools_distortion_cache) == 1

    def test_parameter_change_causes_cache_miss(
        self, monkeypatch: pytest.MonkeyPatch, distortion_fixture
    ) -> None:
        """Changing a cursor parameter should invalidate the cache and trigger recomputation."""
        freqs, sparams = distortion_fixture
        app = _FakeApp()
        compute_calls: list[tuple[float | None, float | None]] = []

        def fake_compute(
            self,
            _compute_freqs: np.ndarray,
            _compute_sparams: dict,
            _trace: str,
            _plot_type: str,
            cursor1_hz: float | None,
            cursor2_hz: float | None,
        ) -> ToolResult:
            compute_calls.append((cursor1_hz, cursor2_hz))
            return ToolResult(tool_name="distortion", unit_label="dB", extra={})

        monkeypatch.setattr(tools_logic.DistortionTool, "compute", fake_compute)

        tools_logic._get_cached_distortion_result(
            app,
            freqs,
            sparams,
            "S21",
            "magnitude",
            float(freqs[1]),
            float(freqs[-2]),
        )
        tools_logic._get_cached_distortion_result(
            app,
            freqs,
            sparams,
            "S21",
            "magnitude",
            float(freqs[2]),
            float(freqs[-2]),
        )

        assert compute_calls == [
            (float(freqs[1]), float(freqs[-2])),
            (float(freqs[2]), float(freqs[-2])),
        ]
        assert len(app._tools_distortion_cache) == 2

    def test_new_data_object_invalidates_existing_cache(
        self, monkeypatch: pytest.MonkeyPatch, distortion_fixture
    ) -> None:
        """Replacing sparams with a new array object should clear the old cache entry."""
        freqs, sparams = distortion_fixture
        app = _FakeApp()
        compute_calls: list[tuple[int, int, int]] = []

        def fake_compute(
            self,
            compute_freqs: np.ndarray,
            compute_sparams: dict,
            trace: str,
            _plot_type: str,
            _cursor1_hz: float | None,
            _cursor2_hz: float | None,
        ) -> ToolResult:
            mag, phase = compute_sparams[trace]
            compute_calls.append((id(compute_freqs), id(mag), id(phase)))
            return ToolResult(tool_name="distortion", unit_label="dB", extra={})

        monkeypatch.setattr(tools_logic.DistortionTool, "compute", fake_compute)

        tools_logic._get_cached_distortion_result(
            app,
            freqs,
            sparams,
            "S21",
            "magnitude",
            float(freqs[1]),
            float(freqs[-2]),
        )
        first_key = next(iter(app._tools_distortion_cache))

        new_mag = sparams["S21"][0].copy()
        new_phase = sparams["S21"][1].copy()
        new_sparams = {"S21": (new_mag, new_phase)}

        tools_logic._get_cached_distortion_result(
            app,
            freqs,
            new_sparams,
            "S21",
            "magnitude",
            float(freqs[1]),
            float(freqs[-2]),
        )

        assert compute_calls == [
            (id(freqs), id(sparams["S21"][0]), id(sparams["S21"][1])),
            (id(freqs), id(new_mag), id(new_phase)),
        ]
        assert len(app._tools_distortion_cache) == 1
        new_key = next(iter(app._tools_distortion_cache))
        assert first_key not in app._tools_distortion_cache
        assert new_key[0] == (id(freqs), id(new_mag), id(new_phase))
        assert app._tools_distortion_cache_last_data_key == (
            id(freqs),
            id(new_mag),
            id(new_phase),
        )
