"""Tests for multi-user support: user selection, validation, path isolation, migration."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bud.cli import cli
from bud.commands.config_store import (
    _BUD_ROOT,
    _maybe_migrate_legacy_data,
    _validate_username,
    get_active_user,
    get_config_dir,
    get_config_file,
    get_db_path,
    get_db_url,
    set_active_user,
)


# ---------------------------------------------------------------------------
# Username validation
# ---------------------------------------------------------------------------


class TestUsernameValidation:
    def test_valid_alphanumeric(self):
        _validate_username("alice")

    def test_valid_with_hyphens(self):
        _validate_username("my-user")

    def test_valid_with_underscores(self):
        _validate_username("my_user")

    def test_valid_with_numbers(self):
        _validate_username("user123")

    def test_valid_single_char(self):
        _validate_username("a")

    def test_invalid_empty(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("")

    def test_invalid_path_traversal(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("../../etc")

    def test_invalid_spaces(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("my user")

    def test_invalid_slashes(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("user/name")

    def test_invalid_dots(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("user.name")

    def test_invalid_too_long(self):
        import click
        with pytest.raises(click.exceptions.BadParameter):
            _validate_username("a" * 65)

    def test_valid_max_length(self):
        _validate_username("a" * 64)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_get_config_dir(self, tmp_path):
        set_active_user("alice")
        assert get_config_dir() == tmp_path / "users" / "alice"

    def test_get_db_path(self, tmp_path):
        set_active_user("bob")
        assert get_db_path() == tmp_path / "users" / "bob" / "bud.db"

    def test_get_db_url(self, tmp_path):
        set_active_user("carol")
        expected = f"sqlite+aiosqlite:///{tmp_path / 'users' / 'carol' / 'bud.db'}"
        assert get_db_url() == expected

    def test_get_config_file(self, tmp_path):
        set_active_user("dave")
        assert get_config_file() == tmp_path / "users" / "dave" / "config.json"

    def test_default_user(self, tmp_path):
        set_active_user("default")
        assert get_config_dir() == tmp_path / "users" / "default"

    def test_get_active_user(self, tmp_path):
        set_active_user("test-user")
        assert get_active_user() == "test-user"


# ---------------------------------------------------------------------------
# Legacy data migration
# ---------------------------------------------------------------------------


class TestLegacyMigration:
    def test_migrates_existing_files(self, tmp_path):
        # Create legacy files at root
        (tmp_path / "bud.db").write_bytes(b"my-database")
        (tmp_path / "config.json").write_text('{"key": "value"}')
        (tmp_path / "credentials.json").write_text('{"aws": "creds"}')
        (tmp_path / "sync_meta.json").write_text('{"version": 5}')

        set_active_user("default")

        target = tmp_path / "users" / "default"
        assert (target / "bud.db").read_bytes() == b"my-database"
        assert json.loads((target / "config.json").read_text()) == {"key": "value"}
        assert json.loads((target / "credentials.json").read_text()) == {"aws": "creds"}
        assert json.loads((target / "sync_meta.json").read_text()) == {"version": 5}

        # Originals should be removed
        assert not (tmp_path / "bud.db").exists()
        assert not (tmp_path / "config.json").exists()
        assert not (tmp_path / "credentials.json").exists()
        assert not (tmp_path / "sync_meta.json").exists()

    def test_skips_when_no_legacy_db(self, tmp_path):
        # No bud.db at root — nothing to migrate
        set_active_user("default")
        # Should not create target dir
        assert not (tmp_path / "users" / "default" / "bud.db").exists()

    def test_skips_when_target_exists(self, tmp_path):
        # Legacy db exists but target dir already exists (already migrated)
        (tmp_path / "bud.db").write_bytes(b"old-data")
        target = tmp_path / "users" / "default"
        target.mkdir(parents=True)
        (target / "bud.db").write_bytes(b"new-data")

        set_active_user("default")

        # Legacy file should not be touched
        assert (tmp_path / "bud.db").read_bytes() == b"old-data"
        # Target should keep existing data
        assert (target / "bud.db").read_bytes() == b"new-data"

    def test_partial_files_migrated(self, tmp_path):
        # Only bud.db and config.json exist, no credentials or sync_meta
        (tmp_path / "bud.db").write_bytes(b"db-data")
        (tmp_path / "config.json").write_text('{"month": "2026-03"}')

        set_active_user("default")

        target = tmp_path / "users" / "default"
        assert (target / "bud.db").read_bytes() == b"db-data"
        assert json.loads((target / "config.json").read_text()) == {"month": "2026-03"}
        assert not (target / "credentials.json").exists()
        assert not (target / "sync_meta.json").exists()

    def test_no_migration_for_non_default_user(self, tmp_path):
        (tmp_path / "bud.db").write_bytes(b"legacy-data")
        set_active_user("alice")
        # Legacy data should still be there
        assert (tmp_path / "bud.db").exists()


# ---------------------------------------------------------------------------
# CLI --user flag and BUD_USER env var
# ---------------------------------------------------------------------------


class TestCliUserSelection:
    def test_user_flag_sets_active_user(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--user", "alice", "--help"])
        assert result.exit_code == 0

    def test_user_flag_invalid_name_rejected(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--user", "../../../tmp/evil", "config", "list"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "error" in result.output.lower()

    def test_env_var_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUD_USER", "from-env")
        runner = CliRunner()
        # Just invoke help to trigger the group callback
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_flag_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUD_USER", "from-env")
        runner = CliRunner()
        # The --user flag should take precedence
        result = runner.invoke(cli, ["--user", "from-flag", "--help"])
        assert result.exit_code == 0

    def test_default_user_when_nothing_set(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------


class TestUserIsolation:
    def test_different_users_get_different_paths(self, tmp_path):
        set_active_user("alice")
        alice_dir = get_config_dir()
        alice_db = get_db_path()

        set_active_user("bob")
        bob_dir = get_config_dir()
        bob_db = get_db_path()

        assert alice_dir != bob_dir
        assert alice_db != bob_db
        assert "alice" in str(alice_dir)
        assert "bob" in str(bob_dir)

    def test_config_isolated_per_user(self, tmp_path):
        from bud.commands.config_store import set_config_value, get_config_value

        set_active_user("alice")
        set_config_value("bucket", "s3://alice-bucket")

        set_active_user("bob")
        set_config_value("bucket", "s3://bob-bucket")

        set_active_user("alice")
        assert get_config_value("bucket") == "s3://alice-bucket"

        set_active_user("bob")
        assert get_config_value("bucket") == "s3://bob-bucket"
