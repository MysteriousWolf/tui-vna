"""CLI measurement runner for tina."""

import argparse
import os

from ..config.settings import AppSettings, SettingsManager
from ..drivers import HPE5071B as VNA
from ..drivers import VNAConfig
from ..utils import TouchstoneExporter
from .parser import apply_cli_settings
from .plotting import export_plots_cli


def create_vna_config(settings: AppSettings) -> VNAConfig:
    """Create VNA config from settings."""
    return VNAConfig(
        host=settings.last_host,
        port=settings.last_port,
        start_freq_hz=settings.start_freq_mhz * 1e6,
        stop_freq_hz=settings.stop_freq_mhz * 1e6,
        sweep_points=settings.sweep_points,
        set_freq_range=settings.set_freq_range,
        set_sweep_points=settings.set_sweep_points,
        enable_averaging=settings.enable_averaging,
        averaging_count=settings.averaging_count,
        set_averaging_count=settings.set_averaging_count,
    )


def run_cli_measurement(args: argparse.Namespace) -> int:
    """Run measurement in CLI mode."""
    try:
        # Load settings
        settings_manager = SettingsManager()
        settings = settings_manager.load()

        # Apply CLI arguments to settings
        settings = apply_cli_settings(args, settings)

        # Validate required settings
        if not settings.last_host:
            print("Error: No host IP configured. Use --host option or run GUI first.")
            return 1

        print(f"Connecting to VNA at {settings.last_host}...")

        # Create VNA config and connect
        vna_config = create_vna_config(settings)
        vna = VNA(vna_config)

        def progress_callback(message: str, progress: float):
            print(f"  {message} ({progress:.0f}%)")

        vna.connect(progress_callback)
        print(f"Connected: {vna.idn}")

        # Perform measurement
        print("Starting measurement...")
        frequencies, s_parameters = vna.perform_measurement()
        print(f"Measurement complete: {len(frequencies)} points")

        # Disconnect
        vna.disconnect()

        # Prepare export parameters
        export_params = {}
        if settings.export_s11 and "S11" in s_parameters:
            export_params["S11"] = s_parameters["S11"]
        if settings.export_s21 and "S21" in s_parameters:
            export_params["S21"] = s_parameters["S21"]
        if settings.export_s12 and "S12" in s_parameters:
            export_params["S12"] = s_parameters["S12"]
        if settings.export_s22 and "S22" in s_parameters:
            export_params["S22"] = s_parameters["S22"]

        if not export_params:
            print("Warning: No S-parameters selected for export, exporting all")
            export_params = s_parameters

        # Export touchstone file
        exporter = TouchstoneExporter(
            freq_unit=settings.freq_unit, reference_impedance=50.0
        )

        filename = None
        if settings.use_custom_filename and settings.custom_filename:
            filename = settings.custom_filename

        s2p_path = exporter.export(
            frequencies,
            export_params,
            settings.output_folder,
            filename=filename,
            prefix=settings.filename_prefix,
        )
        print(f"S2P file saved: {s2p_path}")

        # Generate plots unless disabled
        if not args.no_plots:
            base_filename = os.path.splitext(os.path.basename(s2p_path))[0]
            export_plots_cli(
                frequencies,
                s_parameters,
                settings,
                settings.output_folder,
                base_filename,
            )

        print("Measurement complete!")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1
