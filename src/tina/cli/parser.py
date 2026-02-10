"""Command-line argument parser for tina."""

import argparse

from ..config.settings import AppSettings


def create_cli_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="tina - Terminal UI Network Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick measurement with last settings
  tina --now

  # Quick measurement with custom output
  tina -n --output-folder ./data --filename-prefix test_run

  # Custom measurement parameters
  tina --host 192.168.1.100 --start-freq 10 --stop-freq 1000 --points 201

  # GUI mode (default)
  tina
        """,
    )

    # Quick measurement option
    parser.add_argument(
        "--now",
        "-n",
        action="store_true",
        help="Quick measurement: use last settings to connect, measure, and save to s2p + png files",
    )

    # Connection parameters
    conn_group = parser.add_argument_group("connection settings")
    conn_group.add_argument("--host", help="VNA IP address (e.g., 192.168.1.100)")
    conn_group.add_argument(
        "--port", default="inst0", help="VISA port (default: inst0)"
    )
    conn_group.add_argument(
        "--timeout",
        type=int,
        help="Connection timeout in milliseconds (default: 60000)",
    )

    # Frequency parameters
    freq_group = parser.add_argument_group("frequency settings")
    freq_group.add_argument(
        "--start-freq", type=float, help="Start frequency in MHz (default: 1.0)"
    )
    freq_group.add_argument(
        "--stop-freq", type=float, help="Stop frequency in MHz (default: 1100.0)"
    )
    freq_group.add_argument(
        "--freq-unit",
        choices=["Hz", "kHz", "MHz", "GHz"],
        help="Frequency unit for output files (default: MHz)",
    )

    # Measurement parameters
    meas_group = parser.add_argument_group("measurement settings")
    meas_group.add_argument(
        "--points", type=int, help="Number of sweep points (default: 601)"
    )
    meas_group.add_argument("--averaging", action="store_true", help="Enable averaging")
    meas_group.add_argument(
        "--avg-count", type=int, help="Averaging count (default: 16)"
    )

    # Override flags
    override_group = parser.add_argument_group("override settings")
    override_group.add_argument(
        "--set-freq-range", action="store_true", help="Override VNA frequency range"
    )
    override_group.add_argument(
        "--set-sweep-points",
        action="store_true",
        help="Override VNA sweep points (default: true)",
    )
    override_group.add_argument(
        "--set-avg-count", action="store_true", help="Override VNA averaging count"
    )

    # Output parameters
    output_group = parser.add_argument_group("output settings")
    output_group.add_argument(
        "--output-folder", help="Output folder path (default: measurement)"
    )
    output_group.add_argument(
        "--filename-prefix", help="Filename prefix (default: measurement)"
    )
    output_group.add_argument(
        "--custom-filename", help="Use custom filename instead of auto-generated"
    )

    # S-parameter selection
    sparam_group = parser.add_argument_group("S-parameter selection")
    sparam_group.add_argument("--s11", action="store_true", help="Export S11 parameter")
    sparam_group.add_argument("--s21", action="store_true", help="Export S21 parameter")
    sparam_group.add_argument("--s12", action="store_true", help="Export S12 parameter")
    sparam_group.add_argument("--s22", action="store_true", help="Export S22 parameter")
    sparam_group.add_argument(
        "--all-sparams",
        action="store_true",
        help="Export all S-parameters (S11, S21, S12, S22)",
    )

    # Plot parameters
    plot_group = parser.add_argument_group("plot settings")
    plot_group.add_argument(
        "--plot-s11", action="store_true", help="Include S11 in plots"
    )
    plot_group.add_argument(
        "--plot-s21", action="store_true", help="Include S21 in plots"
    )
    plot_group.add_argument(
        "--plot-s12", action="store_true", help="Include S12 in plots"
    )
    plot_group.add_argument(
        "--plot-s22", action="store_true", help="Include S22 in plots"
    )
    plot_group.add_argument(
        "--plot-all", action="store_true", help="Include all S-parameters in plots"
    )
    plot_group.add_argument(
        "--no-plots", action="store_true", help="Skip plot generation"
    )

    return parser


def apply_cli_settings(args: argparse.Namespace, settings: AppSettings) -> AppSettings:
    """Apply CLI arguments to settings object."""
    # Connection settings
    if args.host:
        settings.last_host = args.host
    if args.port:
        settings.last_port = args.port
    if args.timeout:
        # Convert to VNA config format if needed
        pass

    # Frequency settings
    if args.start_freq is not None:
        settings.start_freq_mhz = args.start_freq
    if args.stop_freq is not None:
        settings.stop_freq_mhz = args.stop_freq
    if args.freq_unit:
        settings.freq_unit = args.freq_unit

    # Measurement settings
    if args.points is not None:
        settings.sweep_points = args.points
    if args.averaging:
        settings.enable_averaging = True
    if args.avg_count is not None:
        settings.averaging_count = args.avg_count

    # Override flags
    if args.set_freq_range:
        settings.set_freq_range = True
    if args.set_sweep_points:
        settings.set_sweep_points = True
    if args.set_avg_count:
        settings.set_averaging_count = True

    # Output settings
    if args.output_folder:
        settings.output_folder = args.output_folder
    if args.filename_prefix:
        settings.filename_prefix = args.filename_prefix
    if args.custom_filename:
        settings.custom_filename = args.custom_filename
        settings.use_custom_filename = True

    # S-parameter selection
    if args.all_sparams:
        settings.export_s11 = True
        settings.export_s21 = True
        settings.export_s12 = True
        settings.export_s22 = True
    else:
        if args.s11:
            settings.export_s11 = True
        if args.s21:
            settings.export_s21 = True
        if args.s12:
            settings.export_s12 = True
        if args.s22:
            settings.export_s22 = True

    # Plot settings
    if args.plot_all:
        settings.plot_s11 = True
        settings.plot_s21 = True
        settings.plot_s12 = True
        settings.plot_s22 = True
    else:
        if args.plot_s11:
            settings.plot_s11 = True
        if args.plot_s21:
            settings.plot_s21 = True
        if args.plot_s12:
            settings.plot_s12 = True
        if args.plot_s22:
            settings.plot_s22 = True

    return settings
