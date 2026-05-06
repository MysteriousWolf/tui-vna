"""Regression tests for shared Tools result formatting helpers."""

from __future__ import annotations

from tina.gui.tabs import tools_logic


def test_measure_result_format_helper_preserves_output() -> None:
    """Measure helper output should keep the existing table layout unchanged."""
    measure_result = tools_logic.ToolResult(
        tool_name="measure",
        cursor1_freq_hz=1.0e6,
        cursor2_freq_hz=2.0e6,
        cursor1_value=-1.0,
        cursor2_value=-2.0,
        delta_value=-1.0,
        unit_label="dB",
        extra={},
    )

    expected_output = "\n".join(
        [
            "[dim]          Freq (MHz)         dB[/dim]",
            "[dim]──────────────────────────────[/dim]",
            "[bold #ff0000]Cursor 1[/]  [@click='app.copy_cell_value(\"1.0000\")']   1.0000[/]  [@click='app.copy_cell_value(\"-1.0000\")']  -1.0000[/]",
            "[bold #0000ff]Cursor 2[/]  [@click='app.copy_cell_value(\"2.0000\")']   2.0000[/]  [@click='app.copy_cell_value(\"-2.0000\")']  -2.0000[/]",
            "[dim]       Δ[/dim]  [@click='app.copy_cell_value(\"1.0000\")']   1.0000[/]  [@click='app.copy_cell_value(\"-1.0000\")']  -1.0000[/]",
        ]
    )

    measure_output = tools_logic._render_tool_result_markup(
        measure_result,
        freq_unit="MHz",
        multiplier=1.0e6,
        cursor1_color="#ff0000",
        cursor2_color="#0000ff",
        overlay_hex=["#111111"] * 6,
        comp_enabled=[False] * 6,
    )

    assert measure_output == expected_output
    assert measure_output == tools_logic._format_measure_result_table(
        measure_result,
        freq_unit="MHz",
        multiplier=1.0e6,
        cursor1_color="#ff0000",
        cursor2_color="#0000ff",
    )


def test_distortion_result_format_helper_preserves_output() -> None:
    """Distortion helper output should keep the existing table layout unchanged."""
    distortion_result = tools_logic.ToolResult(
        tool_name="distortion",
        unit_label="dB",
        extra={
            "coeffs": [1.0, 0.5, 0.25, 0.125, 0.0, -0.25],
            "delta_y": [0.0, 0.8, 0.4, 0.2, 0.0, 0.1],
        },
    )

    expected_output = "\n".join(
        [
            "[dim]n  Component     cₙ (dB)   Δyₙ (dB)[/dim]",
            "[dim]───────────────────────────────────[/dim]",
            "[dim]0[/dim]  [dim]Constant  [/dim]  [@click='app.copy_cell_value(\"1.0000\")']   1.0000[/]          —",
            "[dim]1[/dim]  [bold #222222]Linear    [/]  [@click='app.copy_cell_value(\"0.5000\")']   0.5000[/]  [@click='app.copy_cell_value(\"0.8000\")']   0.8000[/]",
            "[dim]2[/dim]  [dim]Parabolic [/dim]  [@click='app.copy_cell_value(\"0.2500\")']   0.2500[/]  [@click='app.copy_cell_value(\"0.4000\")']   0.4000[/]",
            "[dim]3[/dim]  [bold #444444]Cubic     [/]  [@click='app.copy_cell_value(\"0.1250\")']   0.1250[/]  [@click='app.copy_cell_value(\"0.2000\")']   0.2000[/]",
            "[dim]4[/dim]  [dim]Quartic   [/dim]  [@click='app.copy_cell_value(\"0.0000\")']   0.0000[/]  [@click='app.copy_cell_value(\"0.0000\")']   0.0000[/]",
            "[dim]5[/dim]  [dim]Quintic   [/dim]  [@click='app.copy_cell_value(\"-0.2500\")']  -0.2500[/]  [@click='app.copy_cell_value(\"0.1000\")']   0.1000[/]",
        ]
    )

    distortion_output = tools_logic._render_tool_result_markup(
        distortion_result,
        freq_unit="MHz",
        multiplier=1.0e6,
        cursor1_color="#ff0000",
        cursor2_color="#0000ff",
        overlay_hex=["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"],
        comp_enabled=[False, True, False, True, False, False],
    )

    assert distortion_output == expected_output
    assert distortion_output == tools_logic._format_distortion_result_table(
        distortion_result,
        overlay_hex=["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"],
        comp_enabled=[False, True, False, True, False, False],
    )
