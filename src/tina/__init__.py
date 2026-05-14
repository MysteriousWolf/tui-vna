"""tina - Terminal UI Network Analyzer"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("tui-vna")
except PackageNotFoundError:
    # Running without a uv/pip install (e.g. raw IDE launch without venv)
    __version__ = "0.0.0.dev0"

from .config.settings import AppSettings, SettingsManager
from .drivers import HPE5071B as VNA
from .drivers import VNABase, VNAConfig
from .utils import TouchstoneExporter
from .worker import LogMessage, MeasurementWorker, MessageType

__all__ = [
    "VNA",
    "VNABase",
    "VNAConfig",
    "TouchstoneExporter",
    "MeasurementWorker",
    "MessageType",
    "LogMessage",
    "SettingsManager",
    "AppSettings",
]
