"""Unit tests for CLI plotting export utilities."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from tina.cli.plotting import export_plots_cli
from tina.config.settings import AppSettings


@pytest.fixture
def sparams():
    freqs = np.linspace(10e6, 1000e6, 51)
    mag = np.full(51, -20.0)
    phase = np.zeros(51)
    return freqs, {"S11": (mag, phase), "S21": (mag, phase)}


class TestExportPlotsCli:
    """Tests for the export_plots_cli helper."""

    @pytest.mark.unit
    def test_all_exports_succeed(self, sparams, tmp_path):
        """No exception when create_matplotlib_plot succeeds for both plot types."""
        freqs, sp = sparams
        settings = AppSettings(plot_s11=True, plot_s21=True, plot_s12=False, plot_s22=False)

        with patch("tina.cli.plotting.create_matplotlib_plot") as mock_plot:
            mock_plot.return_value = None
            export_plots_cli(freqs, sp, settings, str(tmp_path), "test")
            assert mock_plot.call_count == 2

    @pytest.mark.unit
    def test_partial_failure_raises_runtime_error(self, sparams, tmp_path):
        """RuntimeError raised when at least one plot export fails."""
        freqs, sp = sparams
        settings = AppSettings(plot_s11=True, plot_s21=True, plot_s12=False, plot_s22=False)

        call_count = 0

        def fail_second(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated failure")

        with patch("tina.cli.plotting.create_matplotlib_plot", side_effect=fail_second):
            with pytest.raises(RuntimeError, match="One or more plot exports failed"):
                export_plots_cli(freqs, sp, settings, str(tmp_path), "test")

    @pytest.mark.unit
    def test_no_selected_params_returns_early(self, sparams, tmp_path):
        """No plots generated when no S-params are selected in settings."""
        freqs, sp = sparams
        settings = AppSettings(plot_s11=False, plot_s21=False)

        with patch("tina.cli.plotting.create_matplotlib_plot") as mock_plot:
            export_plots_cli(freqs, sp, settings, str(tmp_path), "test")
            mock_plot.assert_not_called()
