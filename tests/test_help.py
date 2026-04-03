"""
Tests for the help system: LaTeX utilities and HelpScreen.

Covers:
- _preprocess_inline_latex: inline $...$ → Unicode conversion
- _pixel_graphics_available: terminal graphics detection
- HelpScreen._prep_for_mathtext: LaTeX sanitisation for matplotlib
- HelpScreen._render_math_image: PNG rendering + crop + temp-file tracking
- HelpScreen cleanup: temp files removed on unmount
- Help file presence and structure, including output help
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.tina.gui.modals.help import (
    HelpScreen,
    _pixel_graphics_available,
    _preprocess_inline_latex,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_CSS_VARS = {"surface": "#1a1a1a", "foreground": "#ffffff"}


def _bare_screen() -> HelpScreen:
    """
    Create a HelpScreen instance without running Textual widget initialization.

    This allocates the object without invoking HelpScreen.__init__ and initializes
    _internal attributes used by tests: `_title` is set to "Test Help", `_raw_content`
    to an empty string, and `_temp_files` to an empty list.

    Returns:
        HelpScreen: A prepared HelpScreen instance suitable for unit tests.
    """
    screen = object.__new__(HelpScreen)
    screen._title = "Test Help"
    screen._raw_content = ""
    screen._temp_files = []
    return screen


@contextmanager
def _mock_app(screen: HelpScreen):
    """
    Temporarily patch the given HelpScreen's `app` property to return a mocked app.

    Patches `type(screen).app` with a PropertyMock for the duration of the context and yields
    the mocked app whose `get_css_variables()` returns predefined `_MOCK_CSS_VARS`.

    Parameters:
        screen (HelpScreen): The HelpScreen instance whose `app` property will be patched.

    Yields:
        MagicMock: The mocked app object.
    """
    mock_app = MagicMock()
    mock_app.get_css_variables.return_value = _MOCK_CSS_VARS
    with patch.object(
        type(screen), "app", new_callable=PropertyMock, return_value=mock_app
    ):
        yield mock_app


# ---------------------------------------------------------------------------
# _preprocess_inline_latex
# ---------------------------------------------------------------------------


class TestPreprocessInlineLaTeX:
    """Tests for the inline $...$ → Unicode conversion."""

    @pytest.mark.unit
    def test_plain_text_unchanged(self):
        """Text without math delimiters passes through unmodified."""
        text = "No math here, just plain text."
        assert _preprocess_inline_latex(text) == text

    @pytest.mark.unit
    def test_single_inline_expression(self):
        """Single $...$ block is wrapped in backticks."""
        result = _preprocess_inline_latex("Value $x$ here.")
        # Should be backtick-wrapped, not contain raw $
        assert "$x$" not in result
        assert "`" in result

    @pytest.mark.unit
    def test_multiple_inline_expressions(self):
        """Multiple $...$ blocks are all converted."""
        result = _preprocess_inline_latex("From $f_1$ to $f_2$.")
        assert result.count("`") >= 4  # at least 2 open + 2 close backticks
        assert "$" not in result

    @pytest.mark.unit
    def test_text_segment_without_math_unchanged(self):
        """A plain text segment (as produced by $$-splitting) has no $ to convert."""
        # In compose(), _preprocess_inline_latex only receives the text segments
        # between $$...$$ blocks — those never contain $$ themselves.
        text = "The sign reflects direction: positive if v2 > v1, negative otherwise."
        result = _preprocess_inline_latex(text)
        assert result == text

    @pytest.mark.unit
    def test_multiline_inline_not_matched(self):
        """Expressions that span a newline are not treated as inline math."""
        text = "Open $line one\nline two$ close."
        result = _preprocess_inline_latex(text)
        # Pattern uses [^$\n]+? so the cross-line expression is untouched
        assert "$" in result

    @pytest.mark.unit
    def test_empty_string(self):
        assert _preprocess_inline_latex("") == ""

    @pytest.mark.unit
    def test_fallback_when_converter_unavailable(self, monkeypatch):
        """When _latex_converter is None the raw expression is kept in backticks."""
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "_latex_converter", None)
        result = _preprocess_inline_latex("Value $\\alpha$ here.")
        assert "`\\alpha`" in result
        assert "$" not in result


# ---------------------------------------------------------------------------
# Help file presence
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _pixel_graphics_available
# ---------------------------------------------------------------------------


class TestPixelGraphicsAvailable:
    """Tests for terminal pixel-graphics detection."""

    @pytest.mark.unit
    def test_returns_false_when_textual_image_unavailable(self, monkeypatch):
        """Returns False immediately if textual_image isn't installed."""
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "TEXTUAL_IMAGE_AVAILABLE", False)
        assert _pixel_graphics_available() is False

    @pytest.mark.unit
    def test_returns_true_when_auto_is_sixel(self, monkeypatch):
        """Returns True when the auto-selected renderer is Sixel."""
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "TEXTUAL_IMAGE_AVAILABLE", True)

        sentinel = object()
        with patch.dict(
            "sys.modules",
            {
                "textual_image.renderable": MagicMock(Image=sentinel),
                "textual_image.renderable.sixel": MagicMock(Image=sentinel),
                "textual_image.renderable.tgp": MagicMock(Image=object()),
            },
        ):
            assert _pixel_graphics_available() is True

    @pytest.mark.unit
    def test_returns_true_when_auto_is_tgp(self, monkeypatch):
        """Returns True when the auto-selected renderer is TGP (Kitty)."""
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "TEXTUAL_IMAGE_AVAILABLE", True)

        sentinel = object()
        with patch.dict(
            "sys.modules",
            {
                "textual_image.renderable": MagicMock(Image=sentinel),
                "textual_image.renderable.sixel": MagicMock(Image=object()),
                "textual_image.renderable.tgp": MagicMock(Image=sentinel),
            },
        ):
            assert _pixel_graphics_available() is True

    @pytest.mark.unit
    def test_returns_false_when_auto_is_halfcell(self, monkeypatch):
        """
        Determine that pixel rendering is considered unavailable when the 'auto' renderer is a non-pixel renderer (e.g., halfcell/unicode).

        Simulates TEXTUAL_IMAGE_AVAILABLE and mock renderer modules, and asserts _pixel_graphics_available() returns False.
        """
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "TEXTUAL_IMAGE_AVAILABLE", True)

        auto = object()
        with patch.dict(
            "sys.modules",
            {
                "textual_image.renderable": MagicMock(Image=auto),
                "textual_image.renderable.sixel": MagicMock(Image=object()),
                "textual_image.renderable.tgp": MagicMock(Image=object()),
            },
        ):
            assert _pixel_graphics_available() is False

    @pytest.mark.unit
    def test_returns_false_on_import_error(self, monkeypatch):
        """Returns False gracefully if internal imports fail."""
        import src.tina.gui.modals.help as help_mod

        monkeypatch.setattr(help_mod, "TEXTUAL_IMAGE_AVAILABLE", True)

        with patch.dict(
            "sys.modules",
            {
                "textual_image.renderable": None,
            },
        ):
            assert _pixel_graphics_available() is False


# ---------------------------------------------------------------------------
# HelpScreen._prep_for_mathtext
# ---------------------------------------------------------------------------


class TestPrepForMathtext:
    """Tests for LaTeX sanitisation before passing to matplotlib mathtext."""

    @pytest.mark.unit
    def test_boxed_command_removed(self):
        """\\boxed is stripped; braced content is kept as a group."""
        result = HelpScreen._prep_for_mathtext(r"\boxed{x = 1}")
        assert "\\boxed" not in result
        assert "x = 1" in result

    @pytest.mark.unit
    def test_text_converted_to_mathrm(self):
        r"""\\text{foo} becomes \\mathrm{foo}."""
        result = HelpScreen._prep_for_mathtext(r"\text{linear}")
        assert "\\text" not in result
        assert "\\mathrm{linear}" in result

    @pytest.mark.unit
    def test_lvert_rvert_replaced(self):
        r"""\\lvert and \\rvert become | characters."""
        result = HelpScreen._prep_for_mathtext(r"\lvert c_1 \rvert")
        assert "\\lvert" not in result
        assert "\\rvert" not in result
        assert "| c_1 |" in result

    @pytest.mark.unit
    def test_size_decorators_removed(self):
        """\\bigl, \\bigr, \\left, \\right (and Bigl/Bigr) are stripped."""
        decorators = ["\\bigl", "\\bigr", "\\Bigl", "\\Bigr", "\\left", "\\right"]
        expr = " ".join(d + "(" for d in decorators)
        result = HelpScreen._prep_for_mathtext(expr)
        for dec in decorators:
            assert dec not in result

    @pytest.mark.unit
    def test_max_subscript_stripped(self):
        r"""\\max_{...} loses the subscript so matplotlib can parse it."""
        result = HelpScreen._prep_for_mathtext(r"\max_{x \in [-1,1]}")
        assert "_{" not in result
        assert "\\max" in result

    @pytest.mark.unit
    def test_min_subscript_stripped(self):
        result = HelpScreen._prep_for_mathtext(r"\min_{x \in [-1,1]}")
        assert "_{" not in result
        assert "\\min" in result

    @pytest.mark.unit
    def test_expression_unchanged_when_no_special_commands(self):
        """Plain expressions with no special commands pass through cleanly."""
        expr = r"\frac{a}{b} + c_1"
        assert HelpScreen._prep_for_mathtext(expr) == expr

    @pytest.mark.unit
    def test_distortion_boxed_expression(self):
        """Both distortion.md \\boxed expressions survive sanitisation."""
        exprs = [
            r"\boxed{\Delta y_{\text{linear}} = 2\,\lvert c_1 \rvert}",
            r"\boxed{\Delta y_{\text{parabolic}} = \frac{3}{2}\,\lvert c_2 \rvert}",
        ]
        for expr in exprs:
            result = HelpScreen._prep_for_mathtext(expr)
            assert "\\boxed" not in result
            assert "\\lvert" not in result
            assert "\\rvert" not in result
            assert "\\mathrm" in result


# ---------------------------------------------------------------------------
# HelpScreen._render_math_image
# ---------------------------------------------------------------------------


class TestRenderMathImage:
    """Tests for the PNG math renderer."""

    @pytest.mark.unit
    def test_returns_path_and_dimensions_for_valid_expr(self):
        """Valid LaTeX returns (Path, int, int) with a real file on disk."""
        screen = _bare_screen()
        with _mock_app(screen):
            result = screen._render_math_image(r"\Delta = v_2 - v_1")
        assert result is not None
        path, w, h = result
        assert path.exists()
        assert w > 0
        assert h > 0

    @pytest.mark.unit
    def test_temp_file_registered(self):
        """The rendered file is added to _temp_files for cleanup."""
        screen = _bare_screen()
        with _mock_app(screen):
            result = screen._render_math_image(r"x = 1")
        assert result is not None
        path, _, _ = result
        assert path in screen._temp_files

    @pytest.mark.unit
    def test_image_is_tightly_cropped(self):
        """Output PNG should be much smaller than a default 9×1.5in figure at 130 dpi."""
        screen = _bare_screen()
        with _mock_app(screen):
            result = screen._render_math_image(r"\frac{a}{b}")
        assert result is not None
        _, w, h = result
        # Full figure at 130 dpi would be 1170×195px; cropped should be far smaller
        assert w < 800
        assert h < 100

    @pytest.mark.unit
    def test_returns_none_on_render_failure(self):
        """Gracefully returns None when matplotlib raises during rendering."""
        screen = _bare_screen()
        with _mock_app(screen):
            with patch(
                "matplotlib.pyplot.figure", side_effect=RuntimeError("no display")
            ):
                result = screen._render_math_image(r"\Delta")
        assert result is None

    @pytest.mark.unit
    def test_boxed_expressions_render_without_error(self):
        """Expressions that previously broke matplotlib now succeed."""
        screen = _bare_screen()
        boxed_exprs = [
            r"\boxed{\Delta y_{\text{linear}} = 2\,\lvert c_1 \rvert}",
            r"\boxed{\Delta y_{\text{parabolic}} = \frac{3}{2}\,\lvert c_2 \rvert}",
        ]
        with _mock_app(screen):
            for expr in boxed_exprs:
                result = screen._render_math_image(expr)
                assert result is not None, f"Failed to render: {expr}"

    @pytest.mark.unit
    def test_cleanup_removes_all_temp_files(self):
        """on_unmount deletes every file added to _temp_files."""
        screen = _bare_screen()
        paths = []
        for _ in range(3):
            fd, p = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            paths.append(Path(p))
            screen._temp_files.append(Path(p))

        screen.on_unmount()

        for p in paths:
            assert not p.exists(), f"{p} was not deleted"

    @pytest.mark.unit
    def test_cleanup_tolerates_missing_files(self):
        """on_unmount does not raise if a temp file was already removed."""
        screen = _bare_screen()
        screen._temp_files.append(Path("/tmp/__nonexistent_help_test__.png"))
        screen.on_unmount()  # should not raise


# ---------------------------------------------------------------------------
# Content splitting helper (used by compose)
# ---------------------------------------------------------------------------


class TestContentSplitting:
    """Tests for the $$ splitting pattern used in compose()."""

    @pytest.mark.unit
    def test_no_display_math(self):
        """Content without $$ produces a single text segment."""
        import re

        content = "Just plain text."
        parts = re.split(r"\$\$(.*?)\$\$", content, flags=re.DOTALL)
        assert len(parts) == 1
        assert parts[0] == content

    @pytest.mark.unit
    def test_one_display_block(self):
        """One $$...$$ block yields [text, math, text]."""
        import re

        content = "Before $$x = 1$$ after."
        parts = re.split(r"\$\$(.*?)\$\$", content, flags=re.DOTALL)
        assert len(parts) == 3
        assert parts[0] == "Before "
        assert parts[1] == "x = 1"
        assert parts[2] == " after."

    @pytest.mark.unit
    def test_multiple_display_blocks(self):
        """Multiple $$...$$ blocks produce the correct number of segments."""
        import re

        content = "A $$x$$ B $$y$$ C"
        parts = re.split(r"\$\$(.*?)\$\$", content, flags=re.DOTALL)
        # 2 blocks → 5 parts: text, math, text, math, text
        assert len(parts) == 5
        assert parts[1] == "x"
        assert parts[3] == "y"

    @pytest.mark.unit
    def test_multiline_display_block(self):
        """$$ blocks that span newlines are captured (DOTALL flag)."""
        import re

        content = "Before $$\n\\frac{a}{b}\n$$ after."
        parts = re.split(r"\$\$(.*?)\$\$", content, flags=re.DOTALL)
        assert len(parts) == 3
        assert "\\frac{a}{b}" in parts[1]


# ---------------------------------------------------------------------------
# Help file presence and structure
# ---------------------------------------------------------------------------


class TestHelpFiles:
    """Verify the bundled help markdown files exist and have expected content."""

    _help_dir = Path(__file__).parent.parent / "src" / "tina" / "help"

    @pytest.mark.unit
    def test_cursor_md_exists(self):
        assert (self._help_dir / "cursor.md").exists()

    @pytest.mark.unit
    def test_distortion_md_exists(self):
        assert (self._help_dir / "distortion.md").exists()

    @pytest.mark.unit
    def test_output_md_exists(self):
        help_file = self._help_dir / "output.md"
        assert help_file.exists()
        assert help_file.read_text(encoding="utf-8").strip()

    @pytest.mark.unit
    def test_cursor_md_contains_display_math(self):
        content = (self._help_dir / "cursor.md").read_text(encoding="utf-8")
        assert "$$" in content

    @pytest.mark.unit
    def test_distortion_md_contains_display_math(self):
        content = (self._help_dir / "distortion.md").read_text(encoding="utf-8")
        assert "$$" in content

    @pytest.mark.unit
    def test_distortion_md_contains_boxed_expressions(self):
        content = (self._help_dir / "distortion.md").read_text(encoding="utf-8")
        assert "\\boxed" in content

    @pytest.mark.unit
    def test_cursor_md_contains_delta_section(self):
        content = (self._help_dir / "cursor.md").read_text(encoding="utf-8")
        assert "Delta" in content or "delta" in content.lower()

    @pytest.mark.unit
    def test_distortion_md_references_legendre(self):
        content = (self._help_dir / "distortion.md").read_text(encoding="utf-8")
        assert "Legendre" in content
