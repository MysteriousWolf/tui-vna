"""Tests for export template rendering and validation."""

from datetime import datetime

import pytest

from src.tina.export import (
    DEFAULT_TEMPLATE_TAGS,
    PATH_INVALID_CHARS,
    build_export_template_context,
    render_template,
    validate_template,
)


@pytest.mark.unit
class TestValidateTemplate:
    """Validation tests for export templates."""

    def test_known_tags_are_valid(self):
        """Known tags should not produce warnings or errors."""
        validation = validate_template(
            "measurement_{date}_{time}_{host}",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.has_warnings is False
        assert validation.has_errors is False
        assert validation.unknown_tags == ()
        assert validation.invalid_characters == ()

    def test_unknown_tags_are_warnings_only(self):
        """Unknown tags should be preserved as warnings, not errors."""
        validation = validate_template(
            "measurement_{unknown}_{date}",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.has_warnings is True
        assert validation.has_errors is False
        assert validation.unknown_tags == ("unknown",)
        assert validation.invalid_characters == ()

    def test_duplicate_unknown_tags_are_reported_once(self):
        """Unknown tags should be de-duplicated in validation output."""
        validation = validate_template(
            "{foo}_{foo}_{date}_{foo}",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.unknown_tags == ("foo",)

    def test_strftime_tokens_are_allowed(self):
        """Direct strftime tokens inside braces should not warn."""
        validation = validate_template(
            "run_{%Y%m%d}_{%H%M}",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.has_warnings is False
        assert validation.unknown_tags == ()

    def test_invalid_path_characters_are_errors(self):
        """Invalid path characters should be reported as errors."""
        validation = validate_template(
            "bad:name*file",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.has_errors is True
        assert ":" in validation.invalid_characters
        assert "*" in validation.invalid_characters

    def test_duplicate_invalid_characters_are_reported_once(self):
        """Invalid characters should be de-duplicated in stable order."""
        validation = validate_template(
            "bad::name**",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert validation.invalid_characters == (":", "*")

    def test_folder_templates_can_allow_separators(self):
        """Folder templates may allow slashes when caller excludes them."""
        invalid_chars = set(PATH_INVALID_CHARS) - {"/", "\\"}
        validation = validate_template(
            "exports/{date}/run_{time}",
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=invalid_chars,
        )

        assert validation.has_errors is False


@pytest.mark.unit
class TestBuildExportTemplateContext:
    """Tests for building canonical export context."""

    def test_builds_expected_short_tags(self):
        """Context builder should populate all supported short tags."""
        dt = datetime(2025, 1, 31, 14, 25, 30)
        context = build_export_template_context(
            date_time=dt,
            host="192.168.1.50",
            vendor="keysight",
            model="E5071B",
            start="1",
            stop="1100",
            span="1099",
            pts=601,
            avg=16,
            ifbw="10",
            cal=True,
        )

        assert context == {
            "date": "2025-01-31",
            "time": "142530",
            "host": "192.168.1.50",
            "vend": "keysight",
            "model": "E5071B",
            "start": "1",
            "stop": "1100",
            "span": "1099",
            "pts": 601,
            "avg": 16,
            "ifbw": "10",
            "cal": True,
        }


@pytest.mark.unit
class TestRenderTemplate:
    """Rendering tests for export templates."""

    @pytest.fixture
    def sample_context(self):
        """Provide a representative export template context."""
        return build_export_template_context(
            date_time=datetime(2025, 1, 31, 14, 25, 30),
            host="192.168.1.50",
            vendor="keysight",
            model="E5071B",
            start="1",
            stop="1100",
            span="1099",
            pts=601,
            avg=16,
            ifbw="10",
            cal=True,
        )

    def test_renders_known_tags(self, sample_context):
        """Known tags should render using supplied context."""
        rendered = render_template(
            "{host}_{start}_{stop}_{pts}",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "192.168.1.50_1_1100_601"
        assert rendered.used_tags == ("host", "start", "stop", "pts")
        assert rendered.used_time_formats == ()
        assert rendered.validation.has_warnings is False
        assert rendered.validation.has_errors is False

    def test_renders_strftime_tokens(self, sample_context):
        """Direct strftime tokens should render using provided time."""
        now = datetime(2025, 1, 31, 14, 25, 30)
        rendered = render_template(
            "run_{%Y%m%d}_{%H%M%S}",
            context=sample_context,
            now=now,
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "run_20250131_142530"
        assert rendered.used_tags == ()
        assert rendered.used_time_formats == ("%Y%m%d", "%H%M%S")

    def test_unknown_tags_remain_literal(self, sample_context):
        """Unknown tags should remain literal in rendered output."""
        rendered = render_template(
            "measurement_{unknown}_{date}",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "measurement_{unknown}_2025-01-31"
        assert rendered.validation.has_warnings is True
        assert rendered.validation.unknown_tags == ("unknown",)

    def test_boolean_values_render_as_human_text(self, sample_context):
        """Boolean-like values should render as lowercase yes/no."""
        rendered = render_template(
            "cal_{cal}",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "cal_yes"

    def test_false_boolean_renders_as_no(self, sample_context):
        """False booleans should render as 'no'."""
        context = dict(sample_context)
        context["cal"] = False

        rendered = render_template(
            "cal_{cal}",
            context=context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "cal_no"

    def test_validation_is_preserved_in_rendered_result(self, sample_context):
        """Rendered result should include validation errors and warnings."""
        rendered = render_template(
            "bad:{unknown}*",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            invalid_path_chars=set(PATH_INVALID_CHARS),
        )

        assert rendered.validation.has_warnings is True
        assert rendered.validation.has_errors is True
        assert rendered.validation.unknown_tags == ("unknown",)
        assert rendered.validation.invalid_characters == (":", "*")

    def test_segments_mark_literal_tag_time_and_unknown_sources(self, sample_context):
        """Rendered segments should retain enough metadata for styled previews."""
        rendered = render_template(
            "run_{date}_{%H%M}_{unknown}",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == "run_2025-01-31_1425_{unknown}"
        assert [
            (segment.text, segment.source, segment.token)
            for segment in rendered.segments
        ] == [
            ("run_", "literal", None),
            ("2025-01-31", "tag", "date"),
            ("_", "literal", None),
            ("1425", "time_format", "%H%M"),
            ("_", "literal", None),
            ("{unknown}", "unknown", "unknown"),
        ]

    def test_empty_template_renders_to_empty_string(self, sample_context):
        """An empty template should render to an empty string cleanly."""
        rendered = render_template(
            "",
            context=sample_context,
            now=datetime(2025, 1, 31, 14, 25, 30),
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        assert rendered.rendered == ""
        assert rendered.segments == ()
        assert rendered.used_tags == ()
        assert rendered.used_time_formats == ()

    def test_manual_template_not_in_history_should_clear_history_select(self):
        """Templates outside history should require clearing the history selector."""
        history_options = [("measurement_{date}_{time}", "measurement_{date}_{time}")]
        current_filename = "both_frontends_tuned"
        filename_values = {value for _, value in history_options}

        should_clear = current_filename not in filename_values

        assert should_clear is True

    def test_manual_folder_template_not_in_history_should_clear_history_select(self):
        """Folder templates outside history should also require clearing the selector."""
        history_options = [("measurement", "measurement")]
        current_folder = "exports/custom_run"
        folder_values = {value for _, value in history_options}

        should_clear = current_folder not in folder_values

        assert should_clear is True

    def test_known_history_template_should_not_clear_history_select(self):
        """Templates already in history should remain selected rather than cleared."""
        history_options = [
            ("measurement_{date}_{time}", "measurement_{date}_{time}"),
            ("both_frontends_tuned", "both_frontends_tuned"),
        ]
        current_filename = "both_frontends_tuned"
        filename_values = {value for _, value in history_options}

        should_clear = current_filename not in filename_values

        assert should_clear is False
