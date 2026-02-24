"""Cloud storage providers for database sync."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class CloudAuthError(Exception):
    """Raised when a cloud operation fails due to missing or invalid credentials."""

    def __init__(self, provider: str, message: str, configure_hint: str):
        self.provider = provider
        self.configure_hint = configure_hint
        super().__init__(message)


class StorageProvider(ABC):
    """Abstract base for cloud storage backends."""

    @abstractmethod
    def upload(self, local_path: Path, remote_key: str) -> None:
        """Upload a local file to remote storage."""

    @abstractmethod
    def download(self, remote_key: str, local_path: Path) -> None:
        """Download a remote file to a local path."""

    @abstractmethod
    def read_json(self, remote_key: str) -> Optional[dict]:
        """Read a JSON object from remote storage. Returns None if not found."""

    @abstractmethod
    def upload_json(self, data: dict, remote_key: str) -> None:
        """Upload a JSON object to remote storage."""


class S3Provider(StorageProvider):
    """AWS S3 storage provider."""

    def __init__(self, bucket: str, prefix: str = ""):
        import boto3

        from bud.credentials import get_aws_credentials

        self._bucket = bucket
        self._prefix = prefix

        stored = get_aws_credentials()
        if stored:
            key_id, secret = stored
            self._client = boto3.client(
                "s3",
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
            )
        else:
            # Fall back to default boto3 credential chain (env vars, instance
            # profile, ~/.aws/credentials, etc.)
            self._client = boto3.client("s3")

    def _key(self, remote_key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{remote_key}"
        return remote_key

    def upload(self, local_path: Path, remote_key: str) -> None:
        self._wrap_auth_errors(
            lambda: self._client.upload_file(str(local_path), self._bucket, self._key(remote_key))
        )

    def download(self, remote_key: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._wrap_auth_errors(
            lambda: self._client.download_file(self._bucket, self._key(remote_key), str(local_path))
        )

    def read_json(self, remote_key: str) -> Optional[dict]:
        try:
            resp = self._wrap_auth_errors(
                lambda: self._client.get_object(Bucket=self._bucket, Key=self._key(remote_key))
            )
            return json.loads(resp["Body"].read())
        except self._client.exceptions.NoSuchKey:
            return None

    def upload_json(self, data: dict, remote_key: str) -> None:
        self._wrap_auth_errors(
            lambda: self._client.put_object(
                Bucket=self._bucket,
                Key=self._key(remote_key),
                Body=json.dumps(data).encode(),
                ContentType="application/json",
            )
        )

    def _wrap_auth_errors(self, fn):
        """Execute *fn* and translate credential/permission errors into CloudAuthError."""
        from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

        try:
            return fn()
        except NoCredentialsError:
            raise CloudAuthError(
                provider="AWS",
                message="No AWS credentials found.",
                configure_hint="bud configure-aws",
            )
        except PartialCredentialsError:
            raise CloudAuthError(
                provider="AWS",
                message="Incomplete AWS credentials.",
                configure_hint="bud configure-aws",
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"):
                raise CloudAuthError(
                    provider="AWS",
                    message=f"AWS access denied: {exc}",
                    configure_hint="bud configure-aws",
                )
            raise


class GCSProvider(StorageProvider):
    """Google Cloud Storage provider."""

    def __init__(self, bucket: str, prefix: str = ""):
        from google.cloud import storage

        from bud.credentials import get_gcp_credentials_path

        self._prefix = prefix

        key_file = get_gcp_credentials_path()
        if key_file and os.path.isfile(key_file):
            self._client = storage.Client.from_service_account_json(key_file)
        else:
            # Fall back to Application Default Credentials
            self._client = storage.Client()

        self._bucket_obj = self._client.bucket(bucket)

    def _key(self, remote_key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{remote_key}"
        return remote_key

    def upload(self, local_path: Path, remote_key: str) -> None:
        blob = self._bucket_obj.blob(self._key(remote_key))
        self._wrap_auth_errors(lambda: blob.upload_from_filename(str(local_path)))

    def download(self, remote_key: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket_obj.blob(self._key(remote_key))
        self._wrap_auth_errors(lambda: blob.download_to_filename(str(local_path)))

    def read_json(self, remote_key: str) -> Optional[dict]:
        from google.api_core.exceptions import NotFound

        blob = self._bucket_obj.blob(self._key(remote_key))
        try:
            data = self._wrap_auth_errors(lambda: blob.download_as_text())
            return json.loads(data)
        except NotFound:
            return None

    def upload_json(self, data: dict, remote_key: str) -> None:
        blob = self._bucket_obj.blob(self._key(remote_key))
        self._wrap_auth_errors(
            lambda: blob.upload_from_string(json.dumps(data), content_type="application/json")
        )

    def _wrap_auth_errors(self, fn):
        """Execute *fn* and translate credential/permission errors into CloudAuthError."""
        from google.api_core.exceptions import Forbidden
        from google.auth.exceptions import DefaultCredentialsError

        try:
            return fn()
        except DefaultCredentialsError:
            raise CloudAuthError(
                provider="GCP",
                message="No GCP credentials found.",
                configure_hint="bud configure-gcp",
            )
        except Forbidden as exc:
            raise CloudAuthError(
                provider="GCP",
                message=f"GCP access denied: {exc}",
                configure_hint="bud configure-gcp",
            )


def parse_bucket_url(url: str) -> tuple[str, str, str]:
    """Parse a bucket URL into (scheme, bucket, prefix).

    Supports:
        s3://bucket-name
        s3://bucket-name/path/prefix
        gs://bucket-name
        gs://bucket-name/path/prefix
    """
    if url.startswith("s3://"):
        scheme = "s3"
        rest = url[5:]
    elif url.startswith("gs://"):
        scheme = "gcs"
        rest = url[5:]
    else:
        raise ValueError(
            f"Unsupported bucket URL scheme: {url!r}. "
            "Use s3://bucket-name or gs://bucket-name."
        )

    parts = rest.strip("/").split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return scheme, bucket, prefix


def get_provider(bucket_url: str) -> StorageProvider:
    """Create a storage provider from a bucket URL."""
    scheme, bucket, prefix = parse_bucket_url(bucket_url)
    if scheme == "s3":
        return S3Provider(bucket, prefix)
    elif scheme == "gcs":
        return GCSProvider(bucket, prefix)
    else:
        raise ValueError(f"Unknown scheme: {scheme}")
