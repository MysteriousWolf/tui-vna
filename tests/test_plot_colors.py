"""Unit tests for hex_to_rgb and get_plot_colors."""

from __future__ import annotations

import pytest

from tina.config.constants import THEME_WARNING
from tina.gui.plotting.colors import (
    DISTORTION_OVERLAY_COLORS,
    SPARAM_FALLBACK_COLORS,
    SPARAM_THEME_KEYS,
    TRACE_COLOR_DEFAULT,
    get_plot_colors,
    hex_to_rgb,
)


class TestHexToRgb:
    """Tests for the hex_to_rgb color conversion helper."""

    @pytest.mark.unit
    def test_six_digit_with_hash(self):
        """#RRGGBB format should parse correctly."""
        assert hex_to_rgb("#ff0000") == (255, 0, 0)
        assert hex_to_rgb("#00ff00") == (0, 255, 0)
        assert hex_to_rgb("#0000ff") == (0, 0, 255)

    @pytest.mark.unit
    def test_six_digit_without_hash(self):
        """RRGGBB format (no leading #) should also parse correctly."""
        assert hex_to_rgb("ff8000") == (255, 128, 0)

    @pytest.mark.unit
    def test_three_digit_shorthand_expansion(self):
        """3-digit shorthand (#RGB) should expand to 6-digit form before parsing."""
        assert hex_to_rgb("#abc") == (0xAA, 0xBB, 0xCC)
        assert hex_to_rgb("#fff") == (255, 255, 255)
        assert hex_to_rgb("#000") == (0, 0, 0)

    @pytest.mark.unit
    def test_three_digit_without_hash(self):
        """3-digit shorthand without # should also be handled."""
        assert hex_to_rgb("f0f") == (0xFF, 0x00, 0xFF)

    @pytest.mark.unit
    def test_invalid_length_raises_value_error(self):
        """Wrong-length hex strings should raise ValueError."""
        with pytest.raises(ValueError):
            hex_to_rgb("#12345")  # 5 digits
        with pytest.raises(ValueError):
            hex_to_rgb("#1234567")  # 7 digits
        with pytest.raises(ValueError):
            hex_to_rgb("")


class TestGetPlotColors:
    """Tests for the get_plot_colors color scheme builder."""

    @pytest.mark.unit
    def test_none_returns_all_expected_keys(self):
        """get_plot_colors(None) should return a dict with all required keys."""
        result = get_plot_colors(None)
        expected_keys = {
            "traces",
            "traces_rgb",
            "fg",
            "bg",
            "surface",
            "grid",
            "default_trace",
            "distortion_overlays",
            "distortion_overlays_rgb",
            "cursor1",
            "cursor1_rgb",
            "cursor2",
            "cursor2_rgb",
        }
        assert expected_keys <= result.keys()

    @pytest.mark.unit
    def test_none_uses_fallback_colors(self):
        """get_plot_colors(None) should use SPARAM_FALLBACK_COLORS for traces."""
        result = get_plot_colors(None)
        assert result["traces"] == SPARAM_FALLBACK_COLORS

    @pytest.mark.unit
    def test_empty_dict_uses_fallback_colors(self):
        """get_plot_colors({}) must use SPARAM_FALLBACK_COLORS (is not None regression guard)."""
        result = get_plot_colors({})
        for param in SPARAM_FALLBACK_COLORS:
            assert result["traces"][param] == SPARAM_FALLBACK_COLORS[param]
        assert result["distortion_overlays"] == list(DISTORTION_OVERLAY_COLORS)
        assert result["default_trace"] == TRACE_COLOR_DEFAULT

    @pytest.mark.unit
    def test_none_uses_fallback_distortion_overlays(self):
        """get_plot_colors(None) should use DISTORTION_OVERLAY_COLORS."""
        result = get_plot_colors(None)
        assert result["distortion_overlays"] == list(DISTORTION_OVERLAY_COLORS)

    @pytest.mark.unit
    def test_none_uses_trace_color_default(self):
        """get_plot_colors(None) should use TRACE_COLOR_DEFAULT for default_trace."""
        result = get_plot_colors(None)
        assert result["default_trace"] == TRACE_COLOR_DEFAULT

    @pytest.mark.unit
    def test_full_theme_vars_overrides_traces(self):
        """A full theme_vars mapping should override all trace colors."""
        theme = {
            SPARAM_THEME_KEYS["S11"]: "#111111",
            SPARAM_THEME_KEYS["S21"]: "#222222",
            SPARAM_THEME_KEYS["S12"]: "#333333",
            SPARAM_THEME_KEYS["S22"]: "#444444",
            "foreground": "#aaaaaa",
            "background": "#bbbbbb",
        }
        result = get_plot_colors(theme)
        assert result["traces"]["S11"] == "#111111"
        assert result["traces"]["S21"] == "#222222"
        assert result["traces"]["S12"] == "#333333"
        assert result["traces"]["S22"] == "#444444"
        assert result["fg"] == "#aaaaaa"
        assert result["bg"] == "#bbbbbb"

    @pytest.mark.unit
    def test_partial_theme_vars_falls_back_for_missing_traces(self):
        """Missing trace keys in theme_vars should fall back to SPARAM_FALLBACK_COLORS."""
        theme = {SPARAM_THEME_KEYS["S11"]: "#ff0000"}
        result = get_plot_colors(theme)
        assert result["traces"]["S11"] == "#ff0000"
        assert result["traces"]["S21"] == SPARAM_FALLBACK_COLORS["S21"]
        assert result["traces"]["S12"] == SPARAM_FALLBACK_COLORS["S12"]
        assert result["traces"]["S22"] == SPARAM_FALLBACK_COLORS["S22"]

    @pytest.mark.unit
    def test_invalid_hex_in_theme_vars_falls_back_to_white_rgb(self):
        """An invalid hex value in theme_vars traces should produce (255, 255, 255)."""
        theme = {SPARAM_THEME_KEYS["S11"]: "not-a-color"}
        result = get_plot_colors(theme)
        assert result["traces_rgb"]["S11"] == (255, 255, 255)

    @pytest.mark.unit
    def test_traces_rgb_matches_traces(self):
        """traces_rgb values should be the RGB equivalent of the corresponding traces hex."""
        result = get_plot_colors(None)
        for param, hex_val in result["traces"].items():
            assert result["traces_rgb"][param] == hex_to_rgb(hex_val)

    @pytest.mark.unit
    def test_cursor1_is_alias_for_warning(self):
        """cursor1 color must equal the warning color (they share the same resolved value)."""
        result = get_plot_colors(None)
        assert result["cursor1"] == result["warning"]
        assert result["cursor1_rgb"] == result["warning_rgb"]

    @pytest.mark.unit
    def test_invalid_warning_in_theme_vars_falls_back_to_theme_warning(self):
        """An invalid warning hex in theme_vars should fall back to THEME_WARNING for cursor1."""
        theme = {"warning": "not-a-color"}
        result = get_plot_colors(theme)
        assert result["cursor1_rgb"] == hex_to_rgb(THEME_WARNING)
