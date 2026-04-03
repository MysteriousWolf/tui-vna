"""Help modal with hybrid LaTeX rendering for TINA."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown

try:
    from pylatexenc.latex2text import LatexNodes2Text as _LatexNodes2Text

    _latex_converter = _LatexNodes2Text()
except ImportError:
    _latex_converter = None

try:
    from textual_image.widget import Image as ImageWidget

    TEXTUAL_IMAGE_AVAILABLE = True
except Exception:
    # Importing textual-image can trigger terminal capability probing at import
    # time. In non-interactive environments (such as test collection), that may
    # fail with runtime terminal/TTY errors rather than ImportError.
    ImageWidget = None
    TEXTUAL_IMAGE_AVAILABLE = False


def _pixel_graphics_available() -> bool:
    """
    Detect whether the terminal backend supports true pixel graphics (Sixel or Kitty TGP).

    Checks that the optional textual_image package is available and that its chosen
    image renderable is specifically the Sixel or Kitty TGP implementation; half-cell
    or Unicode/block renderers are not considered supported for pixel-accurate math
    rendering.

    Returns:
        `True` if pixel graphics via Sixel or Kitty TGP are available, `False` otherwise.
    """
    if not TEXTUAL_IMAGE_AVAILABLE:
        return False
    try:
        from textual_image.renderable import Image as _AutoRenderable
        from textual_image.renderable.sixel import Image as _SixelRenderable
        from textual_image.renderable.tgp import Image as _TGPRenderable

        return _AutoRenderable in (_SixelRenderable, _TGPRenderable)
    except Exception:
        return False


def _preprocess_inline_latex(text: str) -> str:
    """Convert inline ``$...$`` math spans to backtick-wrapped Unicode text.

    Each ``$expr$`` is replaced with `` `unicode` `` so Textual's
    ``Markdown`` widget renders it as inline code rather than raw LaTeX.
    When *pylatexenc* is unavailable the raw expression is kept as-is inside
    the backticks. Cross-line spans (containing a newline) are intentionally
    left untouched.

    Args:
        text: A markdown text segment that may contain ``$...$`` spans.
            Must NOT contain ``$$...$$`` display-math blocks (those are split
            out before this function is called in ``HelpScreen.compose``).

    Returns:
        The text with all inline math spans converted to backtick strings.
    """
    if _latex_converter is None:
        return re.sub(r"\$([^$\n]+?)\$", r"`\1`", text)

    def replace_inline(m: re.Match) -> str:
        """
        Convert an inline LaTeX match to plain-text wrapped in backticks.

        Parameters:
            m (re.Match): A regex match whose group(1) contains the inline LaTeX expression.

        Returns:
            str: The LaTeX expression converted to plain text, trimmed, and wrapped in backticks.
        """
        converter = _latex_converter
        if converter is None:
            return f"`{m.group(1)}`"
        return f"`{converter.latex_to_text(m.group(1)).strip()}`"

    return re.sub(r"\$([^$\n]+?)\$", replace_inline, text)


class HelpScreen(ModalScreen):
    """Help viewer modal with hybrid LaTeX rendering.

    Display math ($$...$$) is rendered as a matplotlib image when the terminal
    supports graphics, with a plain-text code-block fallback. Inline math
    ($...$) is always converted to Unicode via pylatexenc.
    """

    CSS_PATH = ["../styles/help.tcss"]

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(self, title: str, content: str) -> None:
        """
        Initialize the help viewer modal.

        Parameters:
            title (str): Heading displayed at the top of the modal.
            content (str): Raw Markdown text, optionally containing $$...$$ display-math blocks and $...$ inline math.
        """
        super().__init__()
        self._title = title
        self._raw_content = content
        self._temp_files: list[Path] = []

    @staticmethod
    def _prep_for_mathtext(expr: str) -> str:
        """
        Sanitize a LaTeX expression for use with matplotlib's mathtext engine.

        This function rewrites or removes LaTeX constructs that matplotlib.mathtext does not support,
        producing an expression that can be rendered without causing a ParseFatalException.

        Transformations performed:
        - Removes `\\boxed` while keeping its braced content.
        - Replaces `\\text{...}` with `\\mathrm{...}`.
        - Replaces `\\lvert` / `\\rvert` with `|`.
        - Removes size/bracket decorators such as `\\bigl`, `\\bigr`, `\\Bigl`, `\\Bigr`, `\\left`, and `\\right`.
        - Drops subscripts from `\\max_{...}` and `\\min_{...}`, leaving `\\max` / `\\min`.

        Parameters:
            expr (str): Raw LaTeX string (without surrounding `$` delimiters).

        Returns:
            str: Sanitized expression safe to pass to matplotlib mathtext (e.g., `fig.text(..., usetex=False)`).
        """
        expr = expr.replace("\\boxed", "")
        expr = re.sub(r"\\text\{([^{}]*)\}", r"\\mathrm{\1}", expr)
        expr = expr.replace("\\lvert", "|").replace("\\rvert", "|")
        for cmd in ("\\bigl", "\\bigr", "\\Bigl", "\\Bigr", "\\left", "\\right"):
            expr = expr.replace(cmd, "")
        expr = re.sub(r"\\(max|min)_\{[^{}]*\}", r"\\\1", expr)
        return expr

    def _render_math_image(self, latex_expr: str) -> tuple[Path, int, int] | None:
        """
        Render a LaTeX display-math expression to a tightly cropped PNG and return its file path and pixel dimensions.

        The input expression is sanitized for matplotlib's mathtext and rendered as a display-style formula. On success returns a temporary PNG Path and its width and height in pixels; returns `None` if rendering fails.

        Parameters:
            latex_expr (str): The LaTeX expression to render (may be raw math without surrounding `$$`).

        Returns:
            tuple[Path, int, int] | None: `(path, width_px, height_px)` on success, or `None` on failure.
        """
        try:
            from io import BytesIO

            from PIL import Image as PILImage
            from PIL import ImageColor

            v = self.app.get_css_variables()
            bg_hex = v.get("surface", "#1a1a1a")
            fg_hex = v.get("foreground", "#ffffff")

            expr = self._prep_for_mathtext(latex_expr.strip())

            with plt.rc_context({"font.family": "monospace"}):
                fig = plt.figure(figsize=(9, 1.5))
                fig.patch.set_facecolor("none")
                fig.text(
                    0.5,
                    0.5,
                    f"${expr}$",
                    ha="center",
                    va="center",
                    fontsize=14,
                    color=fg_hex,
                    usetex=False,
                )
                buf = BytesIO()
                fig.savefig(
                    buf,
                    format="png",
                    dpi=130,
                    bbox_inches="tight",
                    pad_inches=0.05,
                    transparent=True,
                )
                plt.close(fig)

            buf.seek(0)
            img = PILImage.open(buf).convert("RGBA")

            _, _, _, alpha = img.split()
            content_bbox = alpha.getbbox()
            if content_bbox:
                pad_px = 5
                content_bbox = (
                    max(0, content_bbox[0] - pad_px),
                    max(0, content_bbox[1] - pad_px),
                    min(img.width, content_bbox[2] + pad_px),
                    min(img.height, content_bbox[3] + pad_px),
                )
                img = img.crop(content_bbox)

            bg_rgba = ImageColor.getrgb(bg_hex) + (255,)
            bg_layer = PILImage.new("RGBA", img.size, bg_rgba)
            final = PILImage.alpha_composite(bg_layer, img)

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            final.convert("RGB").save(tmp_path, "PNG")
            tmp = Path(tmp_path)
            self._temp_files.append(tmp)
            return tmp, final.width, final.height
        except Exception:
            plt.close("all")
            return None

    def compose(self) -> ComposeResult:
        """
        Build the help modal contents from markdown and display-math segments.

        Text segments have inline LaTeX spans preprocessed for Markdown rendering;
        display-math segments are rendered to tightly-cropped PNG images when pixel
        graphics are available, otherwise emitted as a fenced-code plaintext fallback.

        Returns:
            ComposeResult: Child widgets composing the Help modal.
        """
        use_images = _pixel_graphics_available()
        parts = re.split(r"\$\$(.*?)\$\$", self._raw_content, flags=re.DOTALL)
        with Vertical(id="help-dialog"):
            yield Label(self._title, id="help-title")
            with VerticalScroll(id="help-body"):
                for i, part in enumerate(parts):
                    if i % 2 == 0:
                        processed = _preprocess_inline_latex(part)
                        if processed.strip():
                            yield Markdown(processed)
                    else:
                        result = self._render_math_image(part) if use_images else None
                        if result is not None:
                            img_path, img_w_px, img_h_px = result
                            try:
                                from textual_image._terminal import (
                                    get_cell_size as _gtcs,
                                )

                                tc = _gtcs()
                                cw = tc.width if tc.width > 0 else 8
                                ch = tc.height if tc.height > 0 else 16
                            except Exception:
                                cw, ch = 8, 16
                            w_cells = max(8, round(img_w_px / cw))
                            h_cells = max(1, round(img_h_px / ch))
                            if ImageWidget is None:
                                raise RuntimeError("textual-image widget unavailable")
                            img_widget = ImageWidget(str(img_path))
                            img_widget.styles.width = w_cells
                            img_widget.styles.height = h_cells
                            with Horizontal(classes="math-img-row"):
                                yield img_widget
                        else:
                            fallback = (
                                _latex_converter.latex_to_text(part).strip()
                                if _latex_converter is not None
                                else part.strip()
                            )
                            yield Markdown(f"\n```\n{fallback}\n```\n")
            with Horizontal(id="help-footer"):
                yield Button("Close", variant="primary", id="btn-help-close", flat=True)

    def on_unmount(self) -> None:
        """
        Attempt to delete temporary PNG files created for rendered math.

        Removes any paths in self._temp_files from the filesystem; failures during removal are ignored.
        """
        for f in self._temp_files:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    def action_close(self) -> None:
        """Close the help modal (via Escape key or action binding)."""
        self.dismiss()

    @on(Button.Pressed, "#btn-help-close")
    def close_help(self) -> None:
        """Dismiss the help modal."""
        self.dismiss()
