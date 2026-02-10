"""
Tests for path utilities.

Tests path truncation and display logic.
"""


from src.tina.utils.paths import truncate_path_intelligently


class TestTruncatePathIntelligently:
    """Test intelligent path truncation."""

    def test_path_fits_no_truncation(self):
        """Test path that fits within width is not modified."""
        path = "/home/user/file.txt"
        result = truncate_path_intelligently(path, max_width=50)
        assert result == path

    def test_exact_fit_no_truncation(self):
        """Test path that exactly fits."""
        path = "a" * 18  # 20 - 2 for emoji
        result = truncate_path_intelligently(path, max_width=20)
        assert result == path

    def test_simple_filename_no_truncation(self):
        """Test simple filename fits."""
        path = "file.txt"
        result = truncate_path_intelligently(path, max_width=20)
        assert result == "file.txt"

    def test_long_filename_only_truncated(self):
        """Test long filename without directories is truncated."""
        path = "very_long_filename_that_exceeds_width.txt"
        result = truncate_path_intelligently(path, max_width=20)
        # Should truncate with ellipsis (20 - 2 emoji = 18 chars)
        assert len(result) <= 18
        assert result.endswith("...")

    def test_drop_leading_directories(self):
        """Test progressive dropping of leading directories."""
        path = "/very/long/path/to/some/file.txt"
        result = truncate_path_intelligently(path, max_width=25)
        # Should start with .../ and preserve filename
        assert result.startswith("...")
        assert "file.txt" in result
        assert len(result) <= 23  # 25 - 2 for emoji

    def test_drop_multiple_directories(self):
        """Test dropping multiple directories progressively."""
        path = "/a/b/c/d/e/f/g/file.txt"
        result = truncate_path_intelligently(path, max_width=20)
        # Should drop directories until it fits
        assert "file.txt" in result
        assert len(result) <= 18

    def test_abbreviate_directory_names(self):
        """Test abbreviating directory names to first letter."""
        path = "/home/username/documents/projects/file.txt"
        result = truncate_path_intelligently(path, max_width=30)
        # Should abbreviate directories if needed
        assert len(result) <= 28

    def test_only_filename_shown(self):
        """Test showing only filename when path too long."""
        path = "/extremely/long/path/with/many/directories/file.txt"
        result = truncate_path_intelligently(path, max_width=15)
        # Should show just filename when nothing else fits
        assert result == "file.txt" or result.startswith("file")
        assert len(result) <= 13

    def test_truncate_filename_when_necessary(self):
        """Test filename itself is truncated if too long."""
        path = "/dir/extremely_long_filename_that_cannot_fit.extension"
        result = truncate_path_intelligently(path, max_width=20)
        # Should truncate filename
        assert len(result) <= 18
        assert result.endswith("...")

    def test_very_short_width(self):
        """Test with very short max width."""
        path = "/home/user/file.txt"
        result = truncate_path_intelligently(path, max_width=5)
        # Should handle gracefully (3 chars after emoji)
        assert len(result) <= 3

    def test_width_exactly_emoji_size(self):
        """Test with width exactly for emoji."""
        path = "/home/user/file.txt"
        result = truncate_path_intelligently(path, max_width=2)
        # Should return empty or minimal
        assert len(result) <= 1

    def test_absolute_vs_relative_paths(self):
        """Test both absolute and relative paths."""
        abs_path = "/home/user/docs/file.txt"
        rel_path = "docs/file.txt"

        result_abs = truncate_path_intelligently(abs_path, max_width=20)
        result_rel = truncate_path_intelligently(rel_path, max_width=20)

        assert len(result_abs) <= 18
        assert len(result_rel) <= 18

    def test_windows_style_paths(self):
        """Test Windows-style paths."""
        path = "C:\\Users\\username\\Documents\\file.txt"
        result = truncate_path_intelligently(path, max_width=25)
        assert len(result) <= 23
        # On Linux, pathlib treats this as a single filename, not a path
        # So we just check it's been truncated appropriately
        assert len(result) > 0

    def test_path_with_dots(self):
        """Test path with multiple dots in filename."""
        path = "/home/user/my.config.backup.tar.gz"
        result = truncate_path_intelligently(path, max_width=30)
        assert len(result) <= 28

    def test_hidden_files(self):
        """Test hidden files (starting with dot)."""
        path = "/home/user/.config/app/settings.json"
        result = truncate_path_intelligently(path, max_width=25)
        assert len(result) <= 23

    def test_nested_hidden_directories(self):
        """Test deeply nested hidden directories."""
        path = "/home/user/.local/.config/.cache/file.dat"
        result = truncate_path_intelligently(path, max_width=30)
        assert len(result) <= 28
        assert "file.dat" in result

    def test_unicode_in_path(self):
        """Test path with unicode characters."""
        path = "/home/用户/文档/file.txt"
        result = truncate_path_intelligently(path, max_width=25)
        # Should handle unicode gracefully
        assert "file.txt" in result or "file" in result

    def test_spaces_in_path(self):
        """Test path with spaces."""
        path = "/home/user/My Documents/Project Files/readme.txt"
        result = truncate_path_intelligently(path, max_width=30)
        assert len(result) <= 28

    def test_special_characters(self):
        """Test path with special characters."""
        path = "/home/user/data (copy)/file-v2.txt"
        result = truncate_path_intelligently(path, max_width=25)
        assert len(result) <= 23

    def test_path_ending_with_slash(self):
        """Test directory path ending with slash."""
        path = "/home/user/documents/"
        result = truncate_path_intelligently(path, max_width=15)
        assert len(result) <= 13

    def test_single_directory(self):
        """Test path with single directory."""
        path = "/home/file.txt"
        result = truncate_path_intelligently(path, max_width=20)
        # Should either show full or truncate minimally
        assert len(result) <= 18

    def test_two_directories(self):
        """Test path with two directories."""
        path = "/home/user/file.txt"
        result = truncate_path_intelligently(path, max_width=15)
        assert len(result) <= 13
        assert "file.txt" in result or "file" in result

    def test_many_short_directories(self):
        """Test path with many short directory names."""
        path = "/a/b/c/d/e/f/g/h/i/file.txt"
        result = truncate_path_intelligently(path, max_width=25)
        assert len(result) <= 23
        assert "file.txt" in result

    def test_long_extension(self):
        """Test filename with long extension."""
        path = "/home/user/archive.tar.gz.backup.old"
        result = truncate_path_intelligently(path, max_width=30)
        assert len(result) <= 28

    def test_no_extension(self):
        """Test filename without extension."""
        path = "/home/user/documents/README"
        result = truncate_path_intelligently(path, max_width=20)
        assert len(result) <= 18
        assert "README" in result or "READ" in result

    def test_ellipsis_placement(self):
        """Test ellipsis is placed correctly."""
        path = "/very/long/path/with/many/components/file.txt"
        result = truncate_path_intelligently(path, max_width=25)
        # Should start with .../ or end with ...
        assert "..." in result
        assert len(result) <= 23

    def test_preserves_filename_priority(self):
        """Test filename is preserved with highest priority."""
        path = "/extremely/long/path/structure/important_file.txt"
        result = truncate_path_intelligently(path, max_width=30)
        # Filename should be present
        assert "important_file.txt" in result or "important" in result

    def test_empty_path(self):
        """Test empty path string."""
        result = truncate_path_intelligently("", max_width=20)
        assert result == ""

    def test_root_path(self):
        """Test root directory."""
        result = truncate_path_intelligently("/", max_width=20)
        assert result == "/"

    def test_current_directory(self):
        """Test current directory notation."""
        result = truncate_path_intelligently(".", max_width=20)
        assert result == "."

    def test_parent_directory(self):
        """Test parent directory notation."""
        result = truncate_path_intelligently("..", max_width=20)
        assert result == ".."

    def test_relative_path_with_parent(self):
        """Test relative path with parent directory references."""
        path = "../../other/dir/file.txt"
        result = truncate_path_intelligently(path, max_width=20)
        assert len(result) <= 18

    def test_consistency(self):
        """Test same input gives same output."""
        path = "/home/user/documents/projects/code/file.py"
        result1 = truncate_path_intelligently(path, max_width=30)
        result2 = truncate_path_intelligently(path, max_width=30)
        assert result1 == result2

    def test_increasing_width_expands_path(self):
        """Test larger width shows more of path."""
        path = "/home/user/documents/projects/file.txt"

        result_10 = truncate_path_intelligently(path, max_width=10)
        result_20 = truncate_path_intelligently(path, max_width=20)
        result_50 = truncate_path_intelligently(path, max_width=50)

        # Longer width should show equal or more information
        assert len(result_10) <= len(result_20) <= len(result_50)

    def test_width_boundary_conditions(self):
        """Test behavior at width boundaries."""
        path = "/home/user/file.txt"

        # Test at various widths
        for width in [5, 10, 15, 20, 25, 30]:
            result = truncate_path_intelligently(path, max_width=width)
            assert len(result) <= width - 2  # Account for emoji
