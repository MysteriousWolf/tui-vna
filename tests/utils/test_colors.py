"""
Tests for color utilities.

Tests color conversion, theme parsing, and plot color scheme generation.
"""

import pytest

from src.tina.config.constants import (
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_FOREGROUND_COLOR,
    DEFAULT_GRID_COLOR,
    SPARAM_FALLBACK_COLORS,
    TRACE_COLOR_DEFAULT,
)
from src.tina.utils.colors import get_plot_colors, hex_to_rgb


class TestHexToRGB:
    """Test hex color to RGB conversion."""

    def test_hex_to_rgb_full_format(self):
        """Test conversion with full 6-digit hex."""
        rgb = hex_to_rgb("#ff6b6b")
        assert rgb == (255, 107, 107)

    def test_hex_to_rgb_without_hash(self):
        """Test conversion without # prefix."""
        rgb = hex_to_rgb("00ff00")
        assert rgb == (0, 255, 0)

    def test_hex_to_rgb_short_format(self):
        """Test conversion with 3-digit hex (expands to 6)."""
        rgb = hex_to_rgb("#abc")
        # #abc -> #aabbcc
        assert rgb == (170, 187, 204)

    def test_hex_to_rgb_short_no_hash(self):
        """Test 3-digit hex without #."""
        rgb = hex_to_rgb("f0f")
        # f0f -> ff00ff
        assert rgb == (255, 0, 255)

    def test_hex_to_rgb_black(self):
        """Test black color."""
        assert hex_to_rgb("#000000") == (0, 0, 0)
        assert hex_to_rgb("000") == (0, 0, 0)

    def test_hex_to_rgb_white(self):
        """Test white color."""
        assert hex_to_rgb("#ffffff") == (255, 255, 255)
        assert hex_to_rgb("fff") == (255, 255, 255)

    def test_hex_to_rgb_case_insensitive(self):
        """Test hex parsing is case insensitive."""
        assert hex_to_rgb("#FF00AA") == hex_to_rgb("#ff00aa")
        assert hex_to_rgb("ABC") == hex_to_rgb("abc")

    def test_hex_to_rgb_various_colors(self):
        """Test various color conversions."""
        assert hex_to_rgb("#ff0000") == (255, 0, 0)  # Red
        assert hex_to_rgb("#00ff00") == (0, 255, 0)  # Green
        assert hex_to_rgb("#0000ff") == (0, 0, 255)  # Blue
        assert hex_to_rgb("#ffff00") == (255, 255, 0)  # Yellow
        assert hex_to_rgb("#ff00ff") == (255, 0, 255)  # Magenta
        assert hex_to_rgb("#00ffff") == (0, 255, 255)  # Cyan


class TestGetPlotColors:
    """Test plot color scheme generation."""

    def test_get_plot_colors_no_theme(self):
        """Test default colors when no theme provided."""
        colors = get_plot_colors(None)

        # Check structure
        assert "traces" in colors
        assert "traces_rgb" in colors
        assert "fg" in colors
        assert "bg" in colors
        assert "surface" in colors
        assert "grid" in colors
        assert "default_trace" in colors

        # Check defaults are used
        assert colors["fg"] == DEFAULT_FOREGROUND_COLOR
        assert colors["bg"] == DEFAULT_BACKGROUND_COLOR
        assert colors["grid"] == DEFAULT_GRID_COLOR
        assert colors["default_trace"] == TRACE_COLOR_DEFAULT

        # Check S-parameter fallback colors
        assert colors["traces"] == dict(SPARAM_FALLBACK_COLORS)

    def test_get_plot_colors_empty_theme(self):
        """Test with empty theme dict."""
        colors = get_plot_colors({})

        # Should use fallbacks
        assert colors["traces"] == dict(SPARAM_FALLBACK_COLORS)
        assert colors["fg"] == DEFAULT_FOREGROUND_COLOR
        assert colors["bg"] == DEFAULT_BACKGROUND_COLOR

    def test_get_plot_colors_with_theme(self):
        """Test with custom theme variables."""
        theme = {
            "error": "#ff0000",  # S11
            "primary": "#00ff00",  # S21
            "accent": "#0000ff",  # S12
            "success": "#ffff00",  # S22
            "foreground": "#ffffff",
            "background": "#000000",
            "surface": "#111111",
            "panel": "#222222",
        }

        colors = get_plot_colors(theme)

        # Custom colors should be used
        assert colors["fg"] == "#ffffff"
        assert colors["bg"] == "#000000"
        assert colors["surface"] == "#111111"
        assert colors["grid"] == "#222222"

        # S-parameters should use theme (mapped via SPARAM_THEME_KEYS)
        assert colors["traces"]["S11"] == "#ff0000"
        assert colors["traces"]["S21"] == "#00ff00"
        assert colors["traces"]["S12"] == "#0000ff"
        assert colors["traces"]["S22"] == "#ffff00"

    def test_get_plot_colors_partial_theme(self):
        """Test with partial theme (missing some vars)."""
        theme = {
            "primary": "#ff0000",  # S21
            "foreground": "#cccccc",
        }

        colors = get_plot_colors(theme)

        # Should use theme values where available
        assert colors["traces"]["S21"] == "#ff0000"  # primary maps to S21
        assert colors["fg"] == "#cccccc"

        # Should fallback for missing values
        assert (
            colors["traces"]["S11"] == SPARAM_FALLBACK_COLORS["S11"]
        )  # error not provided
        assert colors["bg"] == DEFAULT_BACKGROUND_COLOR

    def test_get_plot_colors_traces_rgb_conversion(self):
        """Test RGB tuples are generated correctly."""
        theme = {
            "error": "#ff0000",  # S11
            "primary": "#00ff00",  # S21
            "accent": "#0000ff",  # S12
            "success": "#ffff00",  # S22
        }

        colors = get_plot_colors(theme)

        # Check RGB conversions
        assert colors["traces_rgb"]["S11"] == (255, 0, 0)
        assert colors["traces_rgb"]["S21"] == (0, 255, 0)
        assert colors["traces_rgb"]["S12"] == (0, 0, 255)
        assert colors["traces_rgb"]["S22"] == (255, 255, 0)

    def test_get_plot_colors_invalid_hex_fallback(self):
        """Test fallback for invalid hex values."""
        theme = {
            "error": "not-a-hex",  # S11
            "primary": "#gggggg",  # S21
            "accent": "",  # S12
        }

        colors = get_plot_colors(theme)

        # Invalid hex should fallback to white in RGB
        assert colors["traces_rgb"]["S11"] == (255, 255, 255)
        assert colors["traces_rgb"]["S21"] == (255, 255, 255)

    def test_get_plot_colors_surface_fallback(self):
        """Test surface falls back to background."""
        theme = {
            "background": "#123456",
            # No surface specified
        }

        colors = get_plot_colors(theme)
        assert colors["surface"] == "#123456"

    def test_get_plot_colors_foreground_fallback_to_text(self):
        """Test foreground falls back to 'text' variable."""
        theme = {
            "text": "#abcdef",
            # No foreground specified
        }

        colors = get_plot_colors(theme)
        assert colors["fg"] == "#abcdef"

    def test_get_plot_colors_grid_fallback_chain(self):
        """Test grid color fallback chain."""
        # Test with 'panel'
        theme1 = {"panel": "#333333"}
        colors1 = get_plot_colors(theme1)
        assert colors1["grid"] == "#333333"

        # Test with 'surface-darken-1'
        theme2 = {"surface-darken-1": "#444444"}
        colors2 = get_plot_colors(theme2)
        assert colors2["grid"] == "#444444"

        # Test fallback to default
        theme3 = {}
        colors3 = get_plot_colors(theme3)
        assert colors3["grid"] == DEFAULT_GRID_COLOR

    def test_get_plot_colors_all_sparams_present(self):
        """Test all S-parameters are in output."""
        colors = get_plot_colors(None)

        for param in ["S11", "S21", "S12", "S22"]:
            assert param in colors["traces"]
            assert param in colors["traces_rgb"]
            assert isinstance(colors["traces"][param], str)
            assert isinstance(colors["traces_rgb"][param], tuple)
            assert len(colors["traces_rgb"][param]) == 3

    def test_get_plot_colors_rgb_values_in_range(self):
        """Test all RGB values are in valid range 0-255."""
        theme = {
            "primary": "#ff6b6b",
            "secondary": "#4ecdc4",
            "accent": "#ffe66d",
            "warning": "#a8dadc",
        }

        colors = get_plot_colors(theme)

        for param, rgb in colors["traces_rgb"].items():
            for component in rgb:
                assert 0 <= component <= 255
                assert isinstance(component, int)

    def test_get_plot_colors_consistency(self):
        """Test calling multiple times with same theme gives same results."""
        theme = {
            "primary": "#123456",
            "foreground": "#abcdef",
            "background": "#fedcba",
        }

        colors1 = get_plot_colors(theme)
        colors2 = get_plot_colors(theme)

        assert colors1 == colors2

    def test_get_plot_colors_short_hex_in_theme(self):
        """Test theme with 3-digit hex colors."""
        theme = {
            "error": "#f00",  # S11
            "primary": "#0f0",  # S21
            "accent": "#00f",  # S12
            "success": "#ff0",  # S22
        }

        colors = get_plot_colors(theme)

        # Should expand and convert correctly
        assert colors["traces_rgb"]["S11"] == (255, 0, 0)
        assert colors["traces_rgb"]["S21"] == (0, 255, 0)
        assert colors["traces_rgb"]["S12"] == (0, 0, 255)
        assert colors["traces_rgb"]["S22"] == (255, 255, 0)
