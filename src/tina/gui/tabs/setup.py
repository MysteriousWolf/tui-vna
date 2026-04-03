"""Setup tab composition helpers for the TINA GUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Checkbox, Input, Label, Select, Static


def compose_setup_tab(app) -> ComposeResult:
    """Compose the Setup tab contents."""
    with VerticalScroll():
        # Connection Settings
        with Container(classes="panel") as panel:
            panel.border_title = "Connection"
            with Horizontal(classes="connection-strip"):
                yield Label("Host:", classes="conn-label")
                yield Input(
                    value=app.settings.last_host,
                    placeholder="IP address (e.g., 192.168.1.100)",
                    id="input_host",
                    classes="conn-host",
                )
                yield Label("@", classes="conn-symbol")
                yield Input(
                    value=app.settings.last_port,
                    placeholder="inst0",
                    id="input_port",
                    classes="conn-port",
                )
                yield Label("🗘", classes="conn-symbol")
                yield Select(
                    options=[
                        ("Off", 0),
                        ("1s", 1),
                        ("2s", 2),
                        ("5s", 5),
                        ("10s", 10),
                        ("30s", 30),
                    ],
                    value=app.settings.status_poll_interval,
                    id="sb_poll_interval",
                    classes="conn-poll",
                )

        # Measurement Settings
        with Container(classes="panel") as panel:
            panel.border_title = "Measurement Parameters"
            with Horizontal(classes="param-row"):
                yield Label("Unit:", classes="col-label")
                yield Select(
                    options=[
                        ("Hz", "Hz"),
                        ("kHz", "kHz"),
                        ("MHz", "MHz"),
                        ("GHz", "GHz"),
                    ],
                    value=app.settings.freq_unit,
                    id="select_freq_unit",
                    classes="col-input",
                )
                yield Static("", classes="col-check")

            with Horizontal(classes="param-row"):
                yield Label("Frequency:", classes="col-label")
                yield Input(
                    value=str(app.settings.start_freq_mhz),
                    placeholder="Start",
                    id="input_start_freq",
                    classes="col-input",
                )
                yield Label("–")
                yield Input(
                    value=str(app.settings.stop_freq_mhz),
                    placeholder="Stop",
                    id="input_stop_freq",
                    classes="col-input",
                )
                yield Checkbox(
                    "Override",
                    id="check_set_freq",
                    value=app.settings.set_freq_range,
                    classes="col-check",
                )

            with Horizontal(classes="param-row"):
                yield Label("Points:", classes="col-label")
                yield Input(
                    value=str(app.settings.sweep_points),
                    placeholder="601",
                    id="input_points",
                    classes="col-input",
                )
                yield Label(" ")
                yield Static("", classes="col-input")
                yield Checkbox(
                    "Override",
                    id="check_set_points",
                    value=app.settings.set_sweep_points,
                    classes="col-check",
                )

            with Horizontal(classes="param-row"):
                yield Label("Averaging:", classes="col-label")
                yield Input(
                    value=str(app.settings.averaging_count),
                    placeholder="16",
                    id="input_avg_count",
                    classes="col-input",
                )
                yield Checkbox(
                    "Enable",
                    id="check_averaging",
                    value=app.settings.enable_averaging,
                    classes="col-input",
                )
                yield Checkbox(
                    "Override",
                    id="check_set_avg_count",
                    value=app.settings.set_averaging_count,
                    classes="col-check",
                )

        # Output Settings
        with Container(classes="panel") as panel:
            panel.border_title = (
                "Output [@click='app.show_output_help'][on $primary] ? [/]"
            )

            with Horizontal(classes="param-row"):
                yield Label("Filename:", classes="col-label")
                yield Input(
                    value=app.settings.filename_prefix,
                    placeholder="measurement_{date}_{time}",
                    id="input_filename_prefix",
                    classes="col-input",
                )
                yield Static(
                    "",
                    id="preview_filename_template",
                    classes="template-preview",
                )

            with Horizontal(classes="param-row"):
                yield Label("Folder:", classes="col-label")
                yield Input(
                    value=app.settings.output_folder,
                    placeholder="measurement",
                    id="input_output_folder",
                    classes="col-input",
                )
                yield Static(
                    "",
                    id="preview_folder_template",
                    classes="template-preview",
                )

            with Horizontal(classes="param-row output-export-row"):
                yield Label("Export:", classes="col-label")
                with Horizontal(classes="output-export-half"):
                    yield Checkbox(
                        "S11",
                        id="check_export_s11",
                        value=app.settings.export_s11,
                    )
                    yield Checkbox(
                        "S21",
                        id="check_export_s21",
                        value=app.settings.export_s21,
                    )
                    yield Checkbox(
                        "S12",
                        id="check_export_s12",
                        value=app.settings.export_s12,
                    )
                    yield Checkbox(
                        "S22",
                        id="check_export_s22",
                        value=app.settings.export_s22,
                    )
                with Horizontal(classes="output-export-half --right"):
                    yield Checkbox(
                        "s2p",
                        id="check_export_bundle_s2p",
                        value=app.settings.export_bundle_s2p,
                    )
                    yield Checkbox(
                        "csv",
                        id="check_export_bundle_csv",
                        value=app.settings.export_bundle_csv,
                    )
                    yield Checkbox(
                        "png",
                        id="check_export_bundle_png",
                        value=app.settings.export_bundle_png,
                    )
                    yield Checkbox(
                        "svg",
                        id="check_export_bundle_svg",
                        value=app.settings.export_bundle_svg,
                    )
