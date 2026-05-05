"""Tests for config migration module."""

from pathlib import Path
from unittest.mock import patch

from src.tina.config.migration import (
    _NEW_APP_NAME,
    _OLD_APP_NAME,
    _try_remove,
    migrate_legacy_config,
)


class TestTryRemove:
    """Test the _try_remove helper."""

    def test_removes_directory(self, tmp_path):
        target = tmp_path / "to_remove"
        target.mkdir()
        (target / "file.txt").write_text("hello")
        _try_remove(target)
        assert not target.exists()

    def test_ignores_nonexistent(self, tmp_path):
        target = tmp_path / "does_not_exist"
        _try_remove(target)  # must not raise


class TestMigrateLegacyConfig:
    """Test migrate_legacy_config() and its branches."""

    def test_returns_none_when_old_dir_not_present(self):
        """When ~/.config/hp-e5071b/ doesn't exist, migration is skipped."""
        with patch("src.tina.config.migration.user_config_dir") as mock_cfg:
            mock_cfg.return_value = Path("/nonexistent/path")
            result = migrate_legacy_config()
        assert result is None

    def test_returns_none_and_cleans_when_new_config_already_exists(self, tmp_path):
        """When new config exists, old dir is cleaned up but migration returns None."""
        old_dir = tmp_path / _OLD_APP_NAME
        old_dir.mkdir()
        (old_dir / "settings.json").write_text('{"last_host": "old"}')

        new_dir = tmp_path / _NEW_APP_NAME
        new_dir.mkdir()
        (new_dir / "settings.yaml").write_text("key: value")

        with patch("src.tina.config.migration.user_config_dir") as mock_cfg:

            def side_effect(name):
                if name == _OLD_APP_NAME:
                    return old_dir
                return new_dir

            mock_cfg.side_effect = side_effect
            result = migrate_legacy_config()

        assert result is None
        assert not old_dir.exists()

    def test_migration_returns_message_on_success(self, tmp_path):
        """When old config exists and new doesn't, successful migration returns a message."""
        old_dir = tmp_path / _OLD_APP_NAME
        old_dir.mkdir()
        (old_dir / "settings.json").write_text('{"last_host": "192.168.1.50"}')

        new_dir = tmp_path / _NEW_APP_NAME
        new_dir.mkdir()  # new dir exists but no settings.yaml

        with patch("src.tina.config.migration.user_config_dir") as mock_cfg:

            def side_effect(name):
                if name == _OLD_APP_NAME:
                    return old_dir
                return new_dir

            mock_cfg.side_effect = side_effect
            result = migrate_legacy_config()

        assert result is not None
        assert "Migrated" in result

    def test_skips_missing_settings_json(self, tmp_path):
        """When settings.json doesn't exist, parse_failed stays False and cleanup proceeds."""
        old_dir = tmp_path / _OLD_APP_NAME
        old_dir.mkdir()
        # No settings.json

        new_dir = tmp_path / _NEW_APP_NAME
        new_dir.mkdir()

        with patch("src.tina.config.migration.user_config_dir") as mock_cfg:

            def side_effect(name):
                if name == _OLD_APP_NAME:
                    return old_dir
                return new_dir

            mock_cfg.side_effect = side_effect
            result = migrate_legacy_config()

        assert result is None  # no valid fields merged

    def test_corrupt_settings_json_skips_field(self, tmp_path):
        """When settings.json is corrupt, parse_failed is set but migration may still proceed."""
        old_dir = tmp_path / _OLD_APP_NAME
        old_dir.mkdir()
        (old_dir / "settings.json").write_text("not valid json{{{")
        (old_dir / "update_state.json").write_text("also not json{{{")

        new_dir = tmp_path / _NEW_APP_NAME
        new_dir.mkdir()

        with patch("src.tina.config.migration.user_config_dir") as mock_cfg:

            def side_effect(name):
                if name == _OLD_APP_NAME:
                    return old_dir
                return new_dir

            mock_cfg.side_effect = side_effect
            result = migrate_legacy_config()

        # Both files corrupt, parse_failed True, _try_remove skipped
        assert result is None

    def test_migration_exception_is_swallowed(self, tmp_path, monkeypatch):
        """Errors during migration must not propagate — returns None silently."""
        old_dir = tmp_path / _OLD_APP_NAME
        old_dir.mkdir()
        (old_dir / "settings.json").write_text('{"last_host": "192.168.1.50"}')

        new_dir = tmp_path / _NEW_APP_NAME
        new_dir.mkdir()

        def fake_user_config_dir(app_name, *args, **kwargs):
            if app_name == _OLD_APP_NAME:
                return old_dir
            return new_dir

        monkeypatch.setattr(
            "src.tina.config.migration.user_config_dir", fake_user_config_dir
        )

        from src.tina.config import settings

        original_sm_init = settings.SettingsManager.__init__

        def bad_init(self, *args, **kwargs):
            original_sm_init(self, *args, **kwargs)

            def failing_save(*a, **kw):
                raise OSError("disk error")

            self.save = failing_save

        monkeypatch.setattr(
            "src.tina.config.settings.SettingsManager.__init__", bad_init
        )

        result = migrate_legacy_config()
        assert result is None
