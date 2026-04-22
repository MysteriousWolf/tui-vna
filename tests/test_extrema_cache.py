"""Tests for extrema-navigation cache hit and invalidation behavior."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.tina.gui.tabs import tools_logic


class _FakeWidget:
    """Minimal widget stub exposing a mutable value attribute."""

    def __init__(self, value) -> None:
        self.value = value


class _FakeTimer:
    """Minimal timer stub compatible with the tools handler."""

    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        """Record that the timer would have been stopped."""
        self.stopped = True


class _FakeApp:
    """Minimal app stub for exercising extrema navigation cache behavior."""

    def __init__(self, freqs: np.ndarray, data: np.ndarray) -> None:
        self.last_measurement = {
            "freqs": freqs,
            "sparams": {"S21": (data, np.zeros_like(data))},
            "freq_unit": "MHz",
        }
        self.settings = SimpleNamespace(tools_plot_type="magnitude")
        self._tools_input_timer = None
        self._tools_cursor1_hz = None
        self._tools_cursor2_hz = None
        self._delayed_tools_refresh = lambda: None
        self._cursor1_input = _FakeWidget("")
        self._cursor2_input = _FakeWidget("")

    def query_one(self, selector: str, _widget_type=None):
        """Return minimal widget stubs for selectors used by the handler."""
        if selector == "#select_tools_plot_type":
            return _FakeWidget("magnitude")
        if selector == "#tools_radio_s11":
            return _FakeWidget(False)
        if selector == "#tools_radio_s21":
            return _FakeWidget(True)
        if selector == "#tools_radio_s12":
            return _FakeWidget(False)
        if selector == "#tools_radio_s22":
            return _FakeWidget(False)
        if selector == "#input_tools_cursor1":
            return self._cursor1_input
        if selector == "#input_tools_cursor2":
            return self._cursor2_input
        raise AssertionError(f"Unexpected selector: {selector}")

    def set_timer(self, _delay: float, _callback):
        """Return a timer stub so debounce logic can proceed."""
        return _FakeTimer()


@pytest.fixture
def extrema_fixture() -> tuple[np.ndarray, np.ndarray]:
    """Provide a small response with clear extrema candidates."""
    freqs = np.linspace(1.0e9, 1.4e9, 5)
    data = np.array([0.0, 2.0, 0.0, 3.0, 0.0])
    return freqs, data


@pytest.mark.unit
class TestExtremaCache:
    """Cache reuse and invalidation for extrema navigation."""

    def test_repeated_request_with_same_params_hits_cache(
        self, monkeypatch: pytest.MonkeyPatch, extrema_fixture
    ) -> None:
        freqs, data = extrema_fixture
        app = _FakeApp(freqs, data)
        detector_calls: list[tuple[int, bool, bool, int, float]] = []
        candidate_indices = np.array([1, 3], dtype=int)

        def fake_detect(
            detect_data: np.ndarray,
            detect_freqs: np.ndarray,
            minima: bool,
            smoothing: bool,
            *,
            desired_peaks: int,
            prominence_factor: float,
        ) -> np.ndarray:
            detector_calls.append(
                (
                    id(detect_data),
                    smoothing,
                    minima,
                    desired_peaks,
                    prominence_factor,
                )
            )
            np.testing.assert_array_equal(detect_data, data)
            np.testing.assert_array_equal(detect_freqs, freqs)
            return candidate_indices

        monkeypatch.setattr(tools_logic, "_detect_candidates_with_smoothing", fake_detect)

        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=False
        )
        app._tools_cursor1_hz = None
        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=False
        )

        assert detector_calls == [(id(data), False, False, 10, 0.005)]
        assert app._tools_extrema_cache_last_data_id == id(data)
        assert app._tools_extrema_cache == {
            (id(data), False, False, 10, 0.005): candidate_indices
        }

    def test_different_data_object_invalidates_cache(
        self, monkeypatch: pytest.MonkeyPatch, extrema_fixture
    ) -> None:
        freqs, data = extrema_fixture
        app = _FakeApp(freqs, data)
        detector_calls: list[int] = []

        def fake_detect(
            detect_data: np.ndarray,
            _detect_freqs: np.ndarray,
            _minima: bool,
            _smoothing: bool,
            *,
            desired_peaks: int,
            prominence_factor: float,
        ) -> np.ndarray:
            assert desired_peaks == 10
            assert prominence_factor == pytest.approx(0.005)
            detector_calls.append(id(detect_data))
            return np.array([1, 3], dtype=int)

        monkeypatch.setattr(tools_logic, "_detect_candidates_with_smoothing", fake_detect)

        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=False
        )
        first_key = next(iter(app._tools_extrema_cache))

        new_data = data.copy()
        app.last_measurement["sparams"]["S21"] = (new_data, np.zeros_like(new_data))
        app._tools_cursor1_hz = None

        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=False
        )

        assert detector_calls == [id(data), id(new_data)]
        assert len(app._tools_extrema_cache) == 1
        new_key = next(iter(app._tools_extrema_cache))
        assert first_key not in app._tools_extrema_cache
        assert new_key == (id(new_data), False, False, 10, 0.005)
        assert app._tools_extrema_cache_last_data_id == id(new_data)

    def test_different_smoothing_mode_creates_cache_miss(
        self, monkeypatch: pytest.MonkeyPatch, extrema_fixture
    ) -> None:
        freqs, data = extrema_fixture
        app = _FakeApp(freqs, data)
        detector_calls: list[tuple[bool, bool]] = []

        def fake_detect(
            _detect_data: np.ndarray,
            _detect_freqs: np.ndarray,
            minima: bool,
            smoothing: bool,
            *,
            desired_peaks: int,
            prominence_factor: float,
        ) -> np.ndarray:
            assert desired_peaks == 10
            assert prominence_factor == pytest.approx(0.005)
            detector_calls.append((smoothing, minima))
            return np.array([1, 3], dtype=int)

        monkeypatch.setattr(tools_logic, "_detect_candidates_with_smoothing", fake_detect)

        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=False
        )
        app._tools_cursor1_hz = None
        tools_logic.handle_frequency_extrema_navigate(
            app, cursor_index=1, direction=1, minima=False, smoothing=True
        )

        assert detector_calls == [(False, False), (True, False)]
        assert app._tools_extrema_cache_last_data_id == id(data)
        assert len(app._tools_extrema_cache) == 2
        assert (id(data), False, False, 10, 0.005) in app._tools_extrema_cache
        assert (id(data), True, False, 10, 0.005) in app._tools_extrema_cache
