"""Command-line interface for tina."""

from .parser import apply_cli_settings, create_cli_parser
from .runner import run_cli_measurement

__all__ = ["create_cli_parser", "apply_cli_settings", "run_cli_measurement"]
