"""Tests for cloud credentials configuration and auth error handling."""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bud.cli import cli
from bud.credentials import (
    get_aws_credentials,
    get_gcp_credentials_path,
    load_credentials,
    save_credentials,
    set_credential,
)
from bud.services.storage import CloudAuthError


# ---------------------------------------------------------------------------
# Credential store tests
# ---------------------------------------------------------------------------


class TestCredentialStore:
    def test_save_and_load(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        save_credentials({"aws_access_key_id": "AKID", "aws_secret_access_key": "SECRET"})

        loaded = load_credentials()
        assert loaded["aws_access_key_id"] == "AKID"
        assert loaded["aws_secret_access_key"] == "SECRET"

    def test_file_permissions(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        save_credentials({"key": "value"})
        mode = os.stat(creds_file).st_mode & 0o777
        assert mode == 0o600

    def test_load_missing_file(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "does_not_exist.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)

        assert load_credentials() == {}

    def test_set_credential(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        set_credential("aws_access_key_id", "MYKEY")
        set_credential("aws_secret_access_key", "MYSECRET")

        loaded = load_credentials()
        assert loaded["aws_access_key_id"] == "MYKEY"
        assert loaded["aws_secret_access_key"] == "MYSECRET"

    def test_get_aws_credentials_present(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        save_credentials({"aws_access_key_id": "AK", "aws_secret_access_key": "SK"})
        result = get_aws_credentials()
        assert result == ("AK", "SK")

    def test_get_aws_credentials_missing(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        assert get_aws_credentials() is None

    def test_get_gcp_credentials_path_present(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        save_credentials({"gcp_service_account_key_file": "/tmp/sa.json"})
        assert get_gcp_credentials_path() == "/tmp/sa.json"

    def test_get_gcp_credentials_path_missing(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        assert get_gcp_credentials_path() is None


# ---------------------------------------------------------------------------
# CLI configure commands
# ---------------------------------------------------------------------------


class TestConfigureAWS:
    def test_configure_aws_interactive(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["configure-aws"], input="AKID123\nSECRET456\n")

        assert result.exit_code == 0
        assert "AWS credentials saved" in result.output

        loaded = json.loads(creds_file.read_text())
        assert loaded["aws_access_key_id"] == "AKID123"
        assert loaded["aws_secret_access_key"] == "SECRET456"

    def test_configure_aws_with_options(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["configure-aws", "--access-key-id", "AK", "--secret-access-key", "SK"],
        )

        assert result.exit_code == 0
        loaded = json.loads(creds_file.read_text())
        assert loaded["aws_access_key_id"] == "AK"
        assert loaded["aws_secret_access_key"] == "SK"


class TestConfigureGCP:
    def test_configure_gcp_valid_file(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        key_file = tmp_path / "sa-key.json"
        key_file.write_text('{"type": "service_account"}')

        runner = CliRunner()
        result = runner.invoke(
            cli, ["configure-gcp", "--key-file", str(key_file)]
        )

        assert result.exit_code == 0
        assert "GCP credentials saved" in result.output
        loaded = json.loads(creds_file.read_text())
        assert loaded["gcp_service_account_key_file"] == str(key_file)

    def test_configure_gcp_missing_file(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "credentials.json"
        monkeypatch.setattr("bud.credentials.CREDENTIALS_FILE", creds_file)
        monkeypatch.setattr("bud.credentials.CONFIG_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["configure-gcp", "--key-file", "/nonexistent/path.json"]
        )

        assert result.exit_code != 0
        assert "file not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Auth error handling in push/pull
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


class FailingProvider:
    """Provider that raises CloudAuthError on every operation."""

    def __init__(self, provider_name: str, hint: str):
        self._provider_name = provider_name
        self._hint = hint

    def _raise(self):
        raise CloudAuthError(
            provider=self._provider_name,
            message=f"No {self._provider_name} credentials found.",
            configure_hint=self._hint,
        )

    def upload(self, *a, **kw):
        self._raise()

    def download(self, *a, **kw):
        self._raise()

    def read_json(self, *a, **kw):
        self._raise()

    def upload_json(self, *a, **kw):
        self._raise()


@pytest.fixture
def sync_env(tmp_path, monkeypatch):
    """Set up a temporary .bud directory and config for auth error tests."""
    bud_dir = tmp_path / ".bud"
    bud_dir.mkdir()

    db_file = bud_dir / "bud.db"
    db_file.write_text("fake-database-content")

    config_file = bud_dir / "config.json"
    config_file.write_text(json.dumps({"bucket": "s3://test-bucket/prefix"}))

    sync_meta = bud_dir / "sync_meta.json"

    monkeypatch.setattr("bud.commands.sync.CONFIG_DIR", bud_dir)
    monkeypatch.setattr("bud.commands.sync.DB_PATH", db_file)
    monkeypatch.setattr("bud.commands.sync.SYNC_META_FILE", sync_meta)
    monkeypatch.setattr("bud.commands.config_store.CONFIG_DIR", bud_dir)
    monkeypatch.setattr("bud.commands.config_store.CONFIG_FILE", config_file)

    return bud_dir, db_file, sync_meta


class TestPushAuthError:
    def test_push_aws_auth_error(self, sync_env):
        failing = FailingProvider("AWS", "bud configure-aws")

        with patch("bud.services.storage.get_provider", return_value=failing):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push"])

        assert result.exit_code != 0
        assert "authentication failed" in result.output.lower()
        assert "bud configure-aws" in result.output

    def test_push_gcp_auth_error(self, sync_env):
        _, db_file, _ = sync_env
        # Switch to GCS bucket
        bud_dir = db_file.parent
        config_file = bud_dir / "config.json"
        config_file.write_text(json.dumps({"bucket": "gs://test-bucket"}))

        failing = FailingProvider("GCP", "bud configure-gcp")

        with patch("bud.services.storage.get_provider", return_value=failing):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "push"])

        assert result.exit_code != 0
        assert "authentication failed" in result.output.lower()
        assert "bud configure-gcp" in result.output


class TestPullAuthError:
    def test_pull_aws_auth_error(self, sync_env):
        failing = FailingProvider("AWS", "bud configure-aws")

        with patch("bud.services.storage.get_provider", return_value=failing):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code != 0
        assert "authentication failed" in result.output.lower()
        assert "bud configure-aws" in result.output

    def test_pull_gcp_auth_error(self, sync_env):
        _, db_file, _ = sync_env
        bud_dir = db_file.parent
        config_file = bud_dir / "config.json"
        config_file.write_text(json.dumps({"bucket": "gs://test-bucket"}))

        failing = FailingProvider("GCP", "bud configure-gcp")

        with patch("bud.services.storage.get_provider", return_value=failing):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code != 0
        assert "authentication failed" in result.output.lower()
        assert "bud configure-gcp" in result.output
