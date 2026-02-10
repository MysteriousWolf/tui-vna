"""Tests for CLI argument parser."""

import argparse

from tina.cli.parser import apply_cli_settings, create_cli_parser
from tina.config.settings import AppSettings


class TestCliParser:
    """Test CLI argument parser creation."""

    def test_create_cli_parser_returns_parser(self):
        """Test that create_cli_parser returns an ArgumentParser."""
        parser = create_cli_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parser_accepts_now_flag(self):
        """Test that parser accepts --now flag."""
        parser = create_cli_parser()
        args = parser.parse_args(["--now"])
        assert args.now is True

    def test_parser_accepts_short_now_flag(self):
        """Test that parser accepts -n flag."""
        parser = create_cli_parser()
        args = parser.parse_args(["-n"])
        assert args.now is True

    def test_parser_default_now_is_false(self):
        """Test that default --now is False."""
        parser = create_cli_parser()
        args = parser.parse_args([])
        assert args.now is False

    def test_parser_accepts_host(self):
        """Test that parser accepts --host."""
        parser = create_cli_parser()
        args = parser.parse_args(["--host", "192.168.1.100"])
        assert args.host == "192.168.1.100"

    def test_parser_accepts_port(self):
        """Test that parser accepts --port."""
        parser = create_cli_parser()
        args = parser.parse_args(["--port", "inst1"])
        assert args.port == "inst1"

    def test_parser_default_port(self):
        """Test that default port is inst0."""
        parser = create_cli_parser()
        args = parser.parse_args([])
        assert args.port == "inst0"

    def test_parser_accepts_frequency_params(self):
        """Test that parser accepts frequency parameters."""
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--start-freq", "10", "--stop-freq", "1000", "--freq-unit", "MHz"]
        )
        assert args.start_freq == 10.0
        assert args.stop_freq == 1000.0
        assert args.freq_unit == "MHz"

    def test_parser_accepts_measurement_params(self):
        """Test that parser accepts measurement parameters."""
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--points", "201", "--averaging", "--avg-count", "32"]
        )
        assert args.points == 201
        assert args.averaging is True
        assert args.avg_count == 32

    def test_parser_accepts_override_flags(self):
        """Test that parser accepts override flags."""
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--set-freq-range", "--set-sweep-points", "--set-avg-count"]
        )
        assert args.set_freq_range is True
        assert args.set_sweep_points is True
        assert args.set_avg_count is True

    def test_parser_accepts_output_params(self):
        """Test that parser accepts output parameters."""
        parser = create_cli_parser()
        args = parser.parse_args(
            [
                "--output-folder",
                "./data",
                "--filename-prefix",
                "test",
                "--custom-filename",
                "custom.s2p",
            ]
        )
        assert args.output_folder == "./data"
        assert args.filename_prefix == "test"
        assert args.custom_filename == "custom.s2p"

    def test_parser_accepts_sparam_flags(self):
        """Test that parser accepts S-parameter flags."""
        parser = create_cli_parser()
        args = parser.parse_args(["--s11", "--s21", "--s12", "--s22"])
        assert args.s11 is True
        assert args.s21 is True
        assert args.s12 is True
        assert args.s22 is True

    def test_parser_accepts_all_sparams(self):
        """Test that parser accepts --all-sparams flag."""
        parser = create_cli_parser()
        args = parser.parse_args(["--all-sparams"])
        assert args.all_sparams is True

    def test_parser_accepts_plot_flags(self):
        """Test that parser accepts plot flags."""
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--plot-s11", "--plot-s21", "--plot-s12", "--plot-s22", "--plot-all"]
        )
        assert args.plot_s11 is True
        assert args.plot_s21 is True
        assert args.plot_s12 is True
        assert args.plot_s22 is True
        assert args.plot_all is True

    def test_parser_accepts_no_plots(self):
        """Test that parser accepts --no-plots flag."""
        parser = create_cli_parser()
        args = parser.parse_args(["--no-plots"])
        assert args.no_plots is True


class TestApplyCliSettings:
    """Test applying CLI arguments to settings."""

    def test_apply_host_setting(self):
        """Test applying host setting."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--host", "192.168.1.100"])

        updated = apply_cli_settings(args, settings)
        assert updated.last_host == "192.168.1.100"

    def test_apply_port_setting(self):
        """Test applying port setting."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--port", "inst1"])

        updated = apply_cli_settings(args, settings)
        assert updated.last_port == "inst1"

    def test_apply_frequency_settings(self):
        """Test applying frequency settings."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--start-freq", "10", "--stop-freq", "1000", "--freq-unit", "GHz"]
        )

        updated = apply_cli_settings(args, settings)
        assert updated.start_freq_mhz == 10.0
        assert updated.stop_freq_mhz == 1000.0
        assert updated.freq_unit == "GHz"

    def test_apply_measurement_settings(self):
        """Test applying measurement settings."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--points", "401", "--averaging", "--avg-count", "64"]
        )

        updated = apply_cli_settings(args, settings)
        assert updated.sweep_points == 401
        assert updated.enable_averaging is True
        assert updated.averaging_count == 64

    def test_apply_override_flags(self):
        """Test applying override flags."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(
            ["--set-freq-range", "--set-sweep-points", "--set-avg-count"]
        )

        updated = apply_cli_settings(args, settings)
        assert updated.set_freq_range is True
        assert updated.set_sweep_points is True
        assert updated.set_averaging_count is True

    def test_apply_output_settings(self):
        """Test applying output settings."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(
            [
                "--output-folder",
                "./data",
                "--filename-prefix",
                "test",
                "--custom-filename",
                "custom.s2p",
            ]
        )

        updated = apply_cli_settings(args, settings)
        assert updated.output_folder == "./data"
        assert updated.filename_prefix == "test"
        assert updated.custom_filename == "custom.s2p"
        assert updated.use_custom_filename is True

    def test_apply_sparam_export_flags(self):
        """Test applying S-parameter export flags."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--s11", "--s21"])

        updated = apply_cli_settings(args, settings)
        assert updated.export_s11 is True
        assert updated.export_s21 is True

    def test_apply_all_sparams_flag(self):
        """Test applying --all-sparams flag."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--all-sparams"])

        updated = apply_cli_settings(args, settings)
        assert updated.export_s11 is True
        assert updated.export_s21 is True
        assert updated.export_s12 is True
        assert updated.export_s22 is True

    def test_apply_plot_flags(self):
        """Test applying plot flags."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--plot-s11", "--plot-s21"])

        updated = apply_cli_settings(args, settings)
        assert updated.plot_s11 is True
        assert updated.plot_s21 is True

    def test_apply_plot_all_flag(self):
        """Test applying --plot-all flag."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(["--plot-all"])

        updated = apply_cli_settings(args, settings)
        assert updated.plot_s11 is True
        assert updated.plot_s21 is True
        assert updated.plot_s12 is True
        assert updated.plot_s22 is True

    def test_unspecified_settings_remain_default(self):
        """Test that unspecified settings retain their defaults."""
        settings = AppSettings(last_host="original.host")
        parser = create_cli_parser()
        args = parser.parse_args(["--port", "inst1"])

        updated = apply_cli_settings(args, settings)
        # Host should remain unchanged
        assert updated.last_host == "original.host"
        # Port should be updated
        assert updated.last_port == "inst1"

    def test_combined_flags(self):
        """Test combining multiple flags."""
        settings = AppSettings()
        parser = create_cli_parser()
        args = parser.parse_args(
            [
                "--now",
                "--host",
                "192.168.1.100",
                "--start-freq",
                "100",
                "--stop-freq",
                "2000",
                "--points",
                "1001",
                "--all-sparams",
                "--plot-all",
                "--no-plots",
            ]
        )

        updated = apply_cli_settings(args, settings)
        assert updated.last_host == "192.168.1.100"
        assert updated.start_freq_mhz == 100.0
        assert updated.stop_freq_mhz == 2000.0
        assert updated.sweep_points == 1001
        assert updated.export_s11 is True
        assert updated.export_s21 is True
        assert updated.export_s12 is True
        assert updated.export_s22 is True
        assert updated.plot_s11 is True
        assert updated.plot_s21 is True
        assert updated.plot_s12 is True
        assert updated.plot_s22 is True
