"""Unit tests for PNG and SVG metadata embedding and reading helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.tina.export.image_metadata import (
    ImageExportMetadata,
    build_image_export_metadata,
    embed_png_metadata,
    embed_svg_metadata,
    read_png_metadata,
    read_svg_metadata,
)


@pytest.fixture
def sample_machine_settings() -> dict[str, object]:
    """Provide representative machine-readable metadata for image exports."""
    return {
        "setup": {
            "host": "192.168.1.50",
            "port": "inst0",
            "freq_unit": "MHz",
        },
        "measurement": {
            "plot_type": "magnitude",
            "exported_traces": ["S11", "S21"],
            "raw_data": {
                "freqs_hz": [1.0e6, 2.0e6, 3.0e6],
                "sparams": {
                    "S11": {
                        "magnitude_db": [-10.0, -11.0, -12.0],
                        "phase_deg": [5.0, 6.0, 7.0],
                    }
                },
            },
        },
    }


@pytest.mark.unit
class TestBuildImageExportMetadata:
    """Tests for normalized image metadata payload construction."""

    def test_build_image_export_metadata_returns_structured_payload(
        self, sample_machine_settings: dict[str, object]
    ) -> None:
        """Builder should return notes plus normalized machine settings."""
        metadata = build_image_export_metadata(
            notes_markdown="## Notes\nMeasured after warm-up.",
            machine_settings=sample_machine_settings,
        )

        assert isinstance(metadata, ImageExportMetadata)
        assert metadata.notes_markdown == "## Notes\nMeasured after warm-up."
        assert metadata.machine_settings["metadata_version"] == 1
        assert metadata.machine_settings["setup"]["host"] == "192.168.1.50"

    def test_build_image_export_metadata_defaults_version_when_missing(
        self, sample_machine_settings: dict[str, object]
    ) -> None:
        """Builder should always inject a metadata version."""
        metadata = build_image_export_metadata(
            notes_markdown="",
            machine_settings=sample_machine_settings,
        )

        assert metadata.machine_settings["metadata_version"] == 1

    def test_build_image_export_metadata_preserves_explicit_version(self) -> None:
        """Builder should preserve an explicitly provided metadata version."""
        metadata = build_image_export_metadata(
            notes_markdown="",
            machine_settings={
                "metadata_version": 7,
                "setup": {"host": "lab-vna"},
            },
        )

        assert metadata.machine_settings["metadata_version"] == 7

    def test_build_image_export_metadata_handles_missing_machine_settings(self) -> None:
        """Builder should still return a valid payload without extra settings."""
        metadata = build_image_export_metadata(notes_markdown="hello")

        assert metadata.notes_markdown == "hello"
        assert metadata.machine_settings == {"metadata_version": 1}


@pytest.mark.unit
class TestEmbedPngMetadata:
    """Tests for PNG metadata embedding."""

    def test_embed_png_metadata_writes_notes_and_yaml_text_chunks(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """PNG helper should store notes and YAML metadata in text chunks."""
        image_path = tmp_path / "plot.png"
        Image.new("RGB", (16, 16), color="black").save(image_path)

        embed_png_metadata(
            image_path,
            notes_markdown="# DUT notes\n- calibrated",
            machine_settings=sample_machine_settings,
        )

        with Image.open(image_path) as image:
            assert image.info["tina_notes_markdown"] == "# DUT notes\n- calibrated"
            yaml_text = image.info["tina_metadata_yaml"]

        assert "metadata_version: 1" in yaml_text
        assert "setup:" in yaml_text
        assert "host: 192.168.1.50" in yaml_text
        assert "measurement:" in yaml_text
        assert "plot_type: magnitude" in yaml_text

    def test_embed_png_metadata_omits_notes_chunk_when_empty(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """Empty notes should not create a dedicated PNG notes chunk."""
        image_path = tmp_path / "plot.png"
        Image.new("RGB", (8, 8), color="white").save(image_path)

        embed_png_metadata(
            image_path,
            notes_markdown="",
            machine_settings=sample_machine_settings,
        )

        with Image.open(image_path) as image:
            assert "tina_notes_markdown" not in image.info
            assert "tina_metadata_yaml" in image.info

    def test_embed_png_metadata_preserves_existing_text_chunks(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """Embedding should keep unrelated pre-existing PNG text metadata."""
        image_path = tmp_path / "plot.png"

        from PIL import PngImagePlugin

        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("existing_key", "existing_value")
        Image.new("RGB", (10, 10), color="navy").save(image_path, pnginfo=png_info)

        embed_png_metadata(
            image_path,
            notes_markdown="notes",
            machine_settings=sample_machine_settings,
        )

        with Image.open(image_path) as image:
            assert image.info["existing_key"] == "existing_value"
            assert image.info["tina_notes_markdown"] == "notes"
            assert "tina_metadata_yaml" in image.info


@pytest.mark.unit
class TestEmbedSvgMetadata:
    """Tests for SVG metadata embedding."""

    def test_embed_svg_metadata_inserts_notes_and_yaml_comment_blocks(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """SVG helper should inject readable notes and machine metadata comments."""
        image_path = tmp_path / "plot.svg"
        image_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
            encoding="utf-8",
        )

        embed_svg_metadata(
            image_path,
            notes_markdown="# DUT notes\nMeasured after warm-up.",
            machine_settings=sample_machine_settings,
        )

        content = image_path.read_text(encoding="utf-8")

        assert "<!-- TINA NOTES BEGIN" in content
        assert "Raw markdown notes below. You may edit these manually." in content
        assert "# DUT notes" in content
        assert "Measured after warm-up." in content
        assert "TINA NOTES END -->" in content
        assert "<!-- TINA METADATA BEGIN" in content
        assert "Machine-readable settings for TINA import/recovery." in content
        assert "metadata_version: 1" in content
        assert "host: 192.168.1.50" in content
        assert "TINA METADATA END -->" in content

    def test_embed_svg_metadata_omits_notes_block_when_empty(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """Empty notes should not create the readable SVG notes block."""
        image_path = tmp_path / "plot.svg"
        image_path.write_text("<svg></svg>", encoding="utf-8")

        embed_svg_metadata(
            image_path,
            notes_markdown="",
            machine_settings=sample_machine_settings,
        )

        content = image_path.read_text(encoding="utf-8")

        assert "TINA NOTES BEGIN" not in content
        assert "TINA NOTES END" not in content
        assert "TINA METADATA BEGIN" in content

    def test_embed_svg_metadata_inserts_block_after_opening_svg_tag(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """Metadata comments should be inserted immediately after the root tag."""
        image_path = tmp_path / "plot.svg"
        original = (
            '<svg xmlns="http://www.w3.org/2000/svg">\n'
            '<g><circle cx="5" cy="5" r="4"/></g>\n'
            "</svg>\n"
        )
        image_path.write_text(original, encoding="utf-8")

        embed_svg_metadata(
            image_path,
            notes_markdown="notes",
            machine_settings=sample_machine_settings,
        )

        content = image_path.read_text(encoding="utf-8")
        svg_open_end = content.find(">")
        metadata_begin = content.find("<!-- TINA NOTES BEGIN")

        assert svg_open_end != -1
        assert metadata_begin != -1
        assert metadata_begin > svg_open_end
        assert "<g><circle" in content

    def test_embed_svg_metadata_rejects_missing_svg_root(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """Helper should fail clearly when the file is not an SVG document."""
        image_path = tmp_path / "not_svg.svg"
        image_path.write_text("<html></html>", encoding="utf-8")

        with pytest.raises(ValueError, match="does not contain an <svg> root element"):
            embed_svg_metadata(
                image_path,
                notes_markdown="notes",
                machine_settings=sample_machine_settings,
            )


@pytest.mark.unit
class TestReadPngMetadata:
    """Tests for reading PNG metadata back from exported images."""

    def test_read_png_metadata_returns_notes_and_machine_settings(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """PNG reader should recover both notes and YAML metadata."""
        image_path = tmp_path / "plot.png"
        Image.new("RGB", (16, 16), color="black").save(image_path)

        embed_png_metadata(
            image_path,
            notes_markdown="# DUT notes\n- calibrated",
            machine_settings=sample_machine_settings,
        )

        metadata = read_png_metadata(image_path)

        assert isinstance(metadata, ImageExportMetadata)
        assert metadata.notes_markdown == "# DUT notes\n- calibrated"
        assert metadata.machine_settings["metadata_version"] == 1
        assert metadata.machine_settings["setup"]["host"] == "192.168.1.50"
        assert metadata.machine_settings["measurement"]["plot_type"] == "magnitude"

    def test_read_png_metadata_returns_empty_payload_when_missing(
        self, tmp_path: Path
    ) -> None:
        """PNG reader should tolerate files without TINA metadata."""
        image_path = tmp_path / "plain.png"
        Image.new("RGB", (8, 8), color="white").save(image_path)

        metadata = read_png_metadata(image_path)

        assert metadata.notes_markdown == ""
        assert metadata.machine_settings == {}


@pytest.mark.unit
class TestReadSvgMetadata:
    """Tests for reading SVG metadata back from exported images."""

    def test_read_svg_metadata_returns_notes_and_machine_settings(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """SVG reader should recover both notes and YAML metadata."""
        image_path = tmp_path / "plot.svg"
        image_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
            encoding="utf-8",
        )

        embed_svg_metadata(
            image_path,
            notes_markdown="# DUT notes\nMeasured after warm-up.",
            machine_settings=sample_machine_settings,
        )

        metadata = read_svg_metadata(image_path)

        assert isinstance(metadata, ImageExportMetadata)
        assert metadata.notes_markdown == "# DUT notes\nMeasured after warm-up."
        assert metadata.machine_settings["metadata_version"] == 1
        assert metadata.machine_settings["setup"]["host"] == "192.168.1.50"
        assert metadata.machine_settings["measurement"]["plot_type"] == "magnitude"

    def test_read_svg_metadata_returns_empty_payload_when_missing(
        self, tmp_path: Path
    ) -> None:
        """SVG reader should tolerate files without TINA metadata."""
        image_path = tmp_path / "plain.svg"
        image_path.write_text("<svg></svg>", encoding="utf-8")

        metadata = read_svg_metadata(image_path)

        assert metadata.notes_markdown == ""
        assert metadata.machine_settings == {}


@pytest.mark.unit
class TestImageBasedImportPayloads:
    """Tests for image-export metadata carrying recoverable measurement payloads."""

    def test_png_metadata_can_carry_recoverable_measurement_payload(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """PNG metadata should preserve raw measurement payload for future import."""
        image_path = tmp_path / "recoverable.png"
        Image.new("RGB", (12, 12), color="navy").save(image_path)

        embed_png_metadata(
            image_path,
            notes_markdown="notes",
            machine_settings=sample_machine_settings,
        )

        metadata = read_png_metadata(image_path)

        raw_data = metadata.machine_settings["measurement"]["raw_data"]
        assert raw_data["freqs_hz"] == [1.0e6, 2.0e6, 3.0e6]
        assert raw_data["sparams"]["S11"]["magnitude_db"] == [-10.0, -11.0, -12.0]
        assert raw_data["sparams"]["S11"]["phase_deg"] == [5.0, 6.0, 7.0]

    def test_svg_metadata_can_carry_recoverable_measurement_payload(
        self, tmp_path: Path, sample_machine_settings: dict[str, object]
    ) -> None:
        """SVG metadata should preserve raw measurement payload for future import."""
        image_path = tmp_path / "recoverable.svg"
        image_path.write_text("<svg></svg>", encoding="utf-8")

        embed_svg_metadata(
            image_path,
            notes_markdown="notes",
            machine_settings=sample_machine_settings,
        )

        metadata = read_svg_metadata(image_path)

        raw_data = metadata.machine_settings["measurement"]["raw_data"]
        assert raw_data["freqs_hz"] == [1.0e6, 2.0e6, 3.0e6]
        assert raw_data["sparams"]["S11"]["magnitude_db"] == [-10.0, -11.0, -12.0]
        assert raw_data["sparams"]["S11"]["phase_deg"] == [5.0, 6.0, 7.0]
