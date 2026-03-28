"""Tests for push/pull sync commands."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bud.cli import cli
from bud.services.storage import parse_bucket_url


# ---------------------------------------------------------------------------
# parse_bucket_url tests
# ---------------------------------------------------------------------------

class TestParseBucketUrl:
    def test_s3_simple(self):
        scheme, bucket, prefix = parse_bucket_url("s3://my-bucket")
        assert scheme == "s3"
        assert bucket == "my-bucket"
        assert prefix == ""

    def test_s3_with_prefix(self):
        scheme, bucket, prefix = parse_bucket_url("s3://my-bucket/some/path")
        assert scheme == "s3"
        assert bucket == "my-bucket"
        assert prefix == "some/path"

    def test_gcs_simple(self):
        scheme, bucket, prefix = parse_bucket_url("gs://my-bucket")
        assert scheme == "gcs"
        assert bucket == "my-bucket"
        assert prefix == ""

    def test_gcs_with_prefix(self):
        scheme, bucket, prefix = parse_bucket_url("gs://my-bucket/backups/bud")
        assert scheme == "gcs"
        assert bucket == "my-bucket"
        assert prefix == "backups/bud"

    def test_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported bucket URL scheme"):
            parse_bucket_url("http://example.com/bucket")

    def test_trailing_slash(self):
        scheme, bucket, prefix = parse_bucket_url("s3://my-bucket/")
        assert bucket == "my-bucket"
        assert prefix == ""


# ---------------------------------------------------------------------------
# Helpers to build a fake StorageProvider
# ---------------------------------------------------------------------------

class FakeProvider:
    """In-memory storage provider for testing."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.json_objects: dict[str, dict] = {}

    def upload(self, local_path: Path, remote_key: str) -> None:
        self.files[remote_key] = local_path.read_bytes()

    def download(self, remote_key: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.files[remote_key])

    def read_json(self, remote_key: str):
        return self.json_objects.get(remote_key)

    def upload_json(self, data: dict, remote_key: str) -> None:
        self.json_objects[remote_key] = data


# ---------------------------------------------------------------------------
# Push / Pull CLI tests
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_env(tmp_path):
    """Set up a temporary user directory and config for testing.

    _BUD_ROOT is already patched to tmp_path by conftest autouse fixture.
    """
    user_dir = tmp_path / "users" / "default"
    user_dir.mkdir(parents=True)

    db_file = user_dir / "bud.db"
    db_file.write_text("fake-database-content")

    config_file = user_dir / "config.json"
    config_file.write_text(json.dumps({"bucket": "s3://test-bucket/prefix"}))

    sync_meta = user_dir / "sync_meta.json"

    return user_dir, db_file, sync_meta


class TestPush:
    def test_push_no_bucket_configured(self, tmp_path):
        user_dir = tmp_path / "users" / "default"
        user_dir.mkdir(parents=True)
        db_file = user_dir / "bud.db"
        db_file.write_text("data")
        config_file = user_dir / "config.json"
        config_file.write_text("{}")

        runner = CliRunner()
        result = runner.invoke(cli, ["db", "push"])
        assert result.exit_code != 0
        assert "no bucket configured" in result.output.lower() or "no bucket configured" in (result.output + (result.stderr if hasattr(result, 'stderr') else '')).lower()

    def test_push_no_database(self, tmp_path):
        user_dir = tmp_path / "users" / "default"
        user_dir.mkdir(parents=True)
        # bud.db does not exist
        config_file = user_dir / "config.json"
        config_file.write_text(json.dumps({"bucket": "s3://test-bucket"}))

        runner = CliRunner()
        result = runner.invoke(cli, ["db", "push"])
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower()

    def test_push_first_time(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push"])

        assert result.exit_code == 0
        assert "version 1" in result.output.lower()
        assert "bud.db" in fake.files
        assert fake.json_objects["sync_meta.json"]["version"] == 1

        # Local meta should also be updated
        local_meta = json.loads(sync_meta.read_text())
        assert local_meta["version"] == 1

    def test_push_increments_version(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()
        # Simulate a previous push at version 3
        sync_meta.write_text(json.dumps({"version": 3}))
        fake.json_objects["sync_meta.json"] = {"version": 3}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push"])

        assert result.exit_code == 0
        assert "version 4" in result.output.lower()
        assert fake.json_objects["sync_meta.json"]["version"] == 4

    def test_push_blocked_when_remote_newer(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()
        sync_meta.write_text(json.dumps({"version": 2}))
        fake.json_objects["sync_meta.json"] = {"version": 5}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push"])

        assert result.exit_code != 0
        assert "newer" in result.output.lower()

    def test_push_force_overrides_newer_remote(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()
        sync_meta.write_text(json.dumps({"version": 2}))
        fake.json_objects["sync_meta.json"] = {"version": 5}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push", "--force"])

        assert result.exit_code == 0
        # version should be max(2,5) + 1 = 6
        assert "version 6" in result.output.lower()
        assert fake.json_objects["sync_meta.json"]["version"] == 6


class TestPull:
    def test_pull_no_remote_data(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code != 0
        assert "no database found" in result.output.lower()

    def test_pull_success(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        fake = FakeProvider()
        fake.files["bud.db"] = b"remote-database-content"
        fake.json_objects["sync_meta.json"] = {"version": 3, "pushed_at": 1000.0}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code == 0
        assert "version 3" in result.output.lower()
        assert db_file.read_bytes() == b"remote-database-content"

        local_meta = json.loads(sync_meta.read_text())
        assert local_meta["version"] == 3

    def test_pull_creates_backup(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        original_content = db_file.read_text()
        fake = FakeProvider()
        fake.files["bud.db"] = b"new-remote-content"
        fake.json_objects["sync_meta.json"] = {"version": 1}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code == 0
        backup = db_file.with_suffix(".db.bak")
        assert backup.exists()
        assert backup.read_text() == original_content

    def test_pull_blocked_when_local_newer(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        sync_meta.write_text(json.dumps({"version": 5}))
        fake = FakeProvider()
        fake.files["bud.db"] = b"remote-data"
        fake.json_objects["sync_meta.json"] = {"version": 2}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code != 0
        assert "newer" in result.output.lower()

    def test_pull_force_overrides_newer_local(self, setup_env):
        user_dir, db_file, sync_meta = setup_env
        sync_meta.write_text(json.dumps({"version": 5}))
        fake = FakeProvider()
        fake.files["bud.db"] = b"remote-data-forced"
        fake.json_objects["sync_meta.json"] = {"version": 2}

        with patch("bud.services.storage.get_provider", return_value=fake):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull", "--force"])

        assert result.exit_code == 0
        assert db_file.read_bytes() == b"remote-data-forced"
        local_meta = json.loads(sync_meta.read_text())
        assert local_meta["version"] == 2
