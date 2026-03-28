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
    def test_save_and_load(self, tmp_path):
        # _BUD_ROOT patched to tmp_path by conftest; creds go to users/default/
        save_credentials({"aws_access_key_id": "AKID", "aws_secret_access_key": "SECRET"})

        loaded = load_credentials()
        assert loaded["aws_access_key_id"] == "AKID"
        assert loaded["aws_secret_access_key"] == "SECRET"

    def test_file_permissions(self, tmp_path):
        save_credentials({"key": "value"})
        creds_file = tmp_path / "users" / "default" / "credentials.json"
        mode = os.stat(creds_file).st_mode & 0o777
        assert mode == 0o600

    def test_load_missing_file(self, tmp_path):
        # No credentials file exists yet
        assert load_credentials() == {}

    def test_set_credential(self, tmp_path):
        set_credential("aws_access_key_id", "MYKEY")
        set_credential("aws_secret_access_key", "MYSECRET")

        loaded = load_credentials()
        assert loaded["aws_access_key_id"] == "MYKEY"
        assert loaded["aws_secret_access_key"] == "MYSECRET"

    def test_get_aws_credentials_present(self, tmp_path):
        save_credentials({"aws_access_key_id": "AK", "aws_secret_access_key": "SK"})
        result = get_aws_credentials()
        assert result == ("AK", "SK")

    def test_get_aws_credentials_missing(self, tmp_path):
        assert get_aws_credentials() is None

    def test_get_gcp_credentials_path_present(self, tmp_path):
        save_credentials({"gcp_service_account_key_file": "/tmp/sa.json"})
        assert get_gcp_credentials_path() == "/tmp/sa.json"

    def test_get_gcp_credentials_path_missing(self, tmp_path):
        assert get_gcp_credentials_path() is None


# ---------------------------------------------------------------------------
# CLI configure commands
# ---------------------------------------------------------------------------


class TestConfigureAWS:
    def test_configure_aws_interactive(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "aws"], input="AKID123\nSECRET456\n")

        assert result.exit_code == 0
        assert "aws credentials saved" in result.output

        creds_file = tmp_path / "users" / "default" / "credentials.json"
        loaded = json.loads(creds_file.read_text())
        assert loaded["aws_access_key_id"] == "AKID123"
        assert loaded["aws_secret_access_key"] == "SECRET456"

    def test_configure_aws_with_options(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["config", "aws", "--access-key-id", "AK", "--secret-access-key", "SK"],
        )

        assert result.exit_code == 0
        creds_file = tmp_path / "users" / "default" / "credentials.json"
        loaded = json.loads(creds_file.read_text())
        assert loaded["aws_access_key_id"] == "AK"
        assert loaded["aws_secret_access_key"] == "SK"


class TestConfigureGCP:
    def test_configure_gcp_valid_file(self, tmp_path):
        key_file = tmp_path / "sa-key.json"
        key_file.write_text('{"type": "service_account"}')

        runner = CliRunner()
        result = runner.invoke(
            cli, ["config", "gcp", "--key-file", str(key_file)]
        )

        assert result.exit_code == 0
        assert "gcp credentials saved" in result.output
        creds_file = tmp_path / "users" / "default" / "credentials.json"
        loaded = json.loads(creds_file.read_text())
        assert loaded["gcp_service_account_key_file"] == str(key_file)

    def test_configure_gcp_missing_file(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["config", "gcp", "--key-file", "/nonexistent/path.json"]
        )

        assert result.exit_code != 0
        assert "file not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Auth error handling in push/pull
# ---------------------------------------------------------------------------


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
def sync_env(tmp_path):
    """Set up a temporary user directory for auth error tests.

    _BUD_ROOT is already patched to tmp_path by conftest autouse fixture.
    """
    user_dir = tmp_path / "users" / "default"
    user_dir.mkdir(parents=True)

    db_file = user_dir / "bud.db"
    db_file.write_text("fake-database-content")

    config_file = user_dir / "config.json"
    config_file.write_text(json.dumps({"bucket": "s3://test-bucket/prefix"}))

    return user_dir, db_file


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
        user_dir, db_file = sync_env
        # Switch to GCS bucket
        config_file = user_dir / "config.json"
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
        user_dir, db_file = sync_env
        config_file = user_dir / "config.json"
        config_file.write_text(json.dumps({"bucket": "gs://test-bucket"}))

        failing = FailingProvider("GCP", "bud configure-gcp")

        with patch("bud.services.storage.get_provider", return_value=failing):
            runner = CliRunner()
            result = runner.invoke(cli, ["db", "pull"])

        assert result.exit_code != 0
        assert "authentication failed" in result.output.lower()
        assert "bud configure-gcp" in result.output
