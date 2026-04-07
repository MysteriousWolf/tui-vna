"""Helpers for embedding and reading TINA export metadata in PNG and SVG files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin
from ruamel.yaml import YAML

_IMAGE_METADATA_VERSION = 1
_PNG_METADATA_KEY = "tina_metadata_yaml"
_PNG_NOTES_KEY = "tina_notes_markdown"
_SVG_NOTES_BEGIN = "TINA NOTES BEGIN"
_SVG_NOTES_END = "TINA NOTES END"
_SVG_METADATA_BEGIN = "TINA METADATA BEGIN"
_SVG_METADATA_END = "TINA METADATA END"

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 4096


@dataclass(slots=True, frozen=True)
class ImageExportMetadata:
    """Structured metadata payload for PNG and SVG exports."""

    notes_markdown: str
    machine_settings: dict[str, Any]


def _dump_yaml(data: dict[str, Any]) -> str:
    """Serialize a metadata dictionary to stable YAML text."""
    buffer = StringIO()
    _yaml.dump(data, buffer)
    return buffer.getvalue().rstrip("\n")


def _load_yaml(text: str) -> dict[str, Any]:
    """Parse YAML text into a dictionary, returning an empty mapping on failure."""
    try:
        parsed = _yaml.load(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_machine_settings(
    machine_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ensure image metadata always contains a schema version."""
    payload: dict[str, Any] = {"metadata_version": _IMAGE_METADATA_VERSION}
    if machine_settings:
        payload.update(machine_settings)
        payload["metadata_version"] = machine_settings.get(
            "metadata_version", _IMAGE_METADATA_VERSION
        )
    return payload


def build_image_export_metadata(
    *,
    notes_markdown: str = "",
    machine_settings: dict[str, Any] | None = None,
) -> ImageExportMetadata:
    """Build a normalized metadata payload for image exports."""
    return ImageExportMetadata(
        notes_markdown=notes_markdown,
        machine_settings=_normalize_machine_settings(machine_settings),
    )


def read_png_metadata(image_path: str | Path) -> ImageExportMetadata:
    """Read TINA notes and YAML metadata from a PNG file."""
    path = Path(image_path)
    with Image.open(path) as image:
        notes_markdown = str(image.info.get(_PNG_NOTES_KEY, ""))
        yaml_text = str(image.info.get(_PNG_METADATA_KEY, ""))
    return ImageExportMetadata(
        notes_markdown=notes_markdown,
        machine_settings=_load_yaml(yaml_text),
    )


def embed_png_metadata(
    image_path: str | Path,
    *,
    notes_markdown: str = "",
    machine_settings: dict[str, Any] | None = None,
) -> None:
    """Embed TINA notes and YAML metadata into a PNG file."""
    path = Path(image_path)
    metadata = build_image_export_metadata(
        notes_markdown=notes_markdown,
        machine_settings=machine_settings,
    )

    with Image.open(path) as image:
        png_info = PngImagePlugin.PngInfo()

        for key, value in image.info.items():
            if isinstance(key, (str, bytes)) and isinstance(value, str):
                png_info.add_text(key, value)

        if metadata.notes_markdown.strip():
            png_info.add_text(_PNG_NOTES_KEY, metadata.notes_markdown)

        png_info.add_text(
            _PNG_METADATA_KEY,
            _dump_yaml(metadata.machine_settings),
        )

        image.save(path, format="PNG", pnginfo=png_info)


def _build_svg_comment_block(
    *,
    notes_markdown: str,
    machine_settings: dict[str, Any],
) -> str:
    """Build the SVG comment block containing notes and YAML metadata."""
    lines: list[str] = []

    notes = notes_markdown.rstrip("\n")
    if notes:
        lines.append(f"<!-- {_SVG_NOTES_BEGIN}")
        lines.append("Raw markdown notes below. You may edit these manually.")
        lines.extend(notes.splitlines())
        lines.append(f"{_SVG_NOTES_END} -->")

    lines.append(f"<!-- {_SVG_METADATA_BEGIN}")
    lines.append("Machine-readable settings for TINA import/recovery.")
    lines.append("You may edit the markdown notes block manually, but avoid changing")
    lines.append("this machine settings block if reliable re-import is desired.")
    lines.extend(_dump_yaml(machine_settings).splitlines())
    lines.append(f"{_SVG_METADATA_END} -->")

    return "\n".join(lines) + "\n"


def _extract_svg_comment_block(
    svg_text: str,
    *,
    begin_marker: str,
    end_marker: str,
) -> str:
    """Extract one SVG metadata comment block by marker name."""
    pattern = re.compile(
        rf"<!--\s*{re.escape(begin_marker)}\n(.*?)\n{re.escape(end_marker)}\s*-->",
        re.DOTALL,
    )
    match = pattern.search(svg_text)
    return match.group(1) if match else ""


def read_svg_metadata(image_path: str | Path) -> ImageExportMetadata:
    """Read TINA notes and YAML metadata from an SVG file."""
    path = Path(image_path)
    svg_text = path.read_text(encoding="utf-8")

    notes_block = _extract_svg_comment_block(
        svg_text,
        begin_marker=_SVG_NOTES_BEGIN,
        end_marker=_SVG_NOTES_END,
    )
    metadata_block = _extract_svg_comment_block(
        svg_text,
        begin_marker=_SVG_METADATA_BEGIN,
        end_marker=_SVG_METADATA_END,
    )

    notes_lines = notes_block.splitlines()
    if (
        notes_lines
        and notes_lines[0] == "Raw markdown notes below. You may edit these manually."
    ):
        notes_lines = notes_lines[1:]

    metadata_lines = [
        line
        for line in metadata_block.splitlines()
        if line
        not in {
            "Machine-readable settings for TINA import/recovery.",
            "You may edit the markdown notes block manually, but avoid changing",
            "this machine settings block if reliable re-import is desired.",
        }
    ]

    return ImageExportMetadata(
        notes_markdown="\n".join(notes_lines).rstrip(),
        machine_settings=_load_yaml("\n".join(metadata_lines)),
    )


def embed_svg_metadata(
    image_path: str | Path,
    *,
    notes_markdown: str = "",
    machine_settings: dict[str, Any] | None = None,
) -> None:
    """Embed TINA notes and YAML metadata into an SVG file."""
    path = Path(image_path)
    metadata = build_image_export_metadata(
        notes_markdown=notes_markdown,
        machine_settings=machine_settings,
    )

    svg_text = path.read_text(encoding="utf-8")
    comment_block = _build_svg_comment_block(
        notes_markdown=metadata.notes_markdown,
        machine_settings=metadata.machine_settings,
    )

    if "<svg" not in svg_text:
        raise ValueError("SVG file does not contain an <svg> root element")

    insert_at = svg_text.find(">")
    if insert_at == -1:
        raise ValueError("SVG file does not contain a valid opening <svg> tag")

    updated_svg = (
        svg_text[: insert_at + 1] + "\n" + comment_block + svg_text[insert_at + 1 :]
    )
    path.write_text(updated_svg, encoding="utf-8")
