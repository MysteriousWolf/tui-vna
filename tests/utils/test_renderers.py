"""Unit tests for create_smith_chart renderer."""

from __future__ import annotations

import numpy as np
import pytest

from tina.gui.plotting.renderers import create_smith_chart


@pytest.fixture
def simple_sparams():
    """Single-trace sparams fixture with consistent array lengths."""
    n = 51
    freqs = np.linspace(10e6, 1000e6, n)
    mag_db = np.full(n, -20.0)
    phase_deg = np.linspace(-90.0, 90.0, n)
    return freqs, {"S11": (mag_db, phase_deg)}


class TestCreateSmithChart:
    @pytest.mark.unit
    def test_successful_render_creates_file(self, simple_sparams, tmp_path):
        """create_smith_chart writes a non-empty PNG when given valid inputs."""
        freqs, sparams = simple_sparams
        output = tmp_path / "smith.png"

        create_smith_chart(
            freqs,
            sparams,
            ["S11"],
            output,
            dpi=72,
            transparent=True,
        )

        assert output.exists()
        assert output.stat().st_size > 0

    @pytest.mark.unit
    def test_empty_freqs_raises_value_error(self, tmp_path):
        """create_smith_chart raises ValueError when freqs array is empty."""
        freqs = np.array([])
        sparams = {"S11": (np.array([]), np.array([]))}

        with pytest.raises(ValueError, match="[Ee]mpty"):
            create_smith_chart(freqs, sparams, ["S11"], tmp_path / "out.png")

    @pytest.mark.unit
    def test_mismatched_array_lengths_raises_value_error(self, tmp_path):
        """create_smith_chart raises ValueError when sparams arrays don't match freqs length."""
        freqs = np.linspace(10e6, 1000e6, 51)
        sparams = {"S11": (np.full(10, -20.0), np.zeros(10))}

        with pytest.raises(ValueError, match="[Mm]ismatched"):
            create_smith_chart(freqs, sparams, ["S11"], tmp_path / "out.png")
