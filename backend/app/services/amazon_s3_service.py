"""Helpers for Amazon S3 object storage operations."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import boto3

S3_LIST_OBJECTS_MAX_KEYS = 1000


def normalize_s3_list_max_keys(value: int) -> int:
    """Clamp listObjects MaxKeys to the AWS S3 allowed range (1-1000)."""
    return min(S3_LIST_OBJECTS_MAX_KEYS, max(1, value))


class S3Service:
    """Execute Amazon S3 object storage operations."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._client = self._build_client()

    def _build_client(self):  # type: ignore[no-untyped-def]
        """Create a boto3 S3 client for Amazon S3 using the stored credential config."""
        session_token = str(self._config.get("aws_session_token", "") or "").strip() or None
        return boto3.client(
            "s3",
            aws_access_key_id=str(self._config.get("aws_access_key_id", "") or "").strip(),
            aws_secret_access_key=str(self._config.get("aws_secret_access_key", "") or "").strip(),
            aws_session_token=session_token,
            region_name=str(self._config.get("aws_region", "") or "").strip(),
        )

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        """Convert datetimes returned by boto3 into ISO-8601 strings."""
        return value.isoformat() if isinstance(value, datetime) else None

    def put_object(
        self,
        bucket: str,
        key: str,
        body: str,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a UTF-8 text payload to S3."""
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
            "Body": body.encode("utf-8"),
        }
        if content_type:
            kwargs["ContentType"] = content_type
        response = self._client.put_object(**kwargs)
        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "etag": str(response.get("ETag", "") or "").strip('"'),
            "version_id": response.get("VersionId"),
        }

    def get_object(
        self,
        bucket: str,
        key: str,
        include_binary: bool = False,
    ) -> dict[str, Any]:
        """Download an object and return either text or base64 content."""
        response = self._client.get_object(Bucket=bucket, Key=key)
        raw_body = response["Body"].read()
        output: dict[str, Any] = {
            "bucket": bucket,
            "key": key,
            "content_type": response.get("ContentType"),
            "content_length": response.get("ContentLength"),
            "etag": str(response.get("ETag", "") or "").strip('"'),
            "last_modified": self._serialize_datetime(response.get("LastModified")),
            "metadata": response.get("Metadata", {}),
        }
        if include_binary:
            output["body_base64"] = base64.b64encode(raw_body).decode("ascii")
        else:
            output["body_text"] = raw_body.decode("utf-8", errors="replace")
        return output

    def create_bucket(self, bucket: str, region: str) -> dict[str, Any]:
        """Create a bucket in the configured account region."""
        kwargs: dict[str, Any] = {"Bucket": bucket}
        normalized_region = str(region or "").strip()
        if normalized_region and normalized_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": normalized_region}
        self._client.create_bucket(**kwargs)
        return {
            "success": True,
            "bucket": bucket,
            "region": normalized_region or "us-east-1",
        }

    def delete_bucket(self, bucket: str) -> dict[str, Any]:
        """Delete an empty bucket."""
        self._client.delete_bucket(Bucket=bucket)
        return {
            "success": True,
            "bucket": bucket,
        }

    @staticmethod
    def _normalize_folder_prefix(folder_path: str) -> str:
        """Normalize a folder path to a prefix ending with /."""
        normalized = str(folder_path or "").strip().strip("/")
        if not normalized:
            raise ValueError("Amazon S3 folder path is required")
        return f"{normalized}/"

    def create_folder(self, bucket: str, folder_path: str) -> dict[str, Any]:
        """Create a folder marker object (zero-byte key ending with /)."""
        key = self._normalize_folder_prefix(folder_path)
        response = self._client.put_object(Bucket=bucket, Key=key, Body=b"")
        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "folder": key,
            "etag": str(response.get("ETag", "") or "").strip('"'),
        }

    def get_all_folder(self, bucket: str, folder_path: str) -> dict[str, Any]:
        """List all object metadata under a folder prefix (paginated)."""
        prefix = self._normalize_folder_prefix(folder_path)
        objects: list[dict[str, Any]] = []
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "Prefix": prefix,
                "MaxKeys": S3_LIST_OBJECTS_MAX_KEYS,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self._client.list_objects_v2(**kwargs)
            contents = response.get("Contents", [])
            objects.extend(
                {
                    "key": item.get("Key"),
                    "size": item.get("Size"),
                    "etag": str(item.get("ETag", "") or "").strip('"'),
                    "last_modified": self._serialize_datetime(item.get("LastModified")),
                    "storage_class": item.get("StorageClass"),
                }
                for item in contents
            )
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
        return {
            "bucket": bucket,
            "folder": prefix,
            "count": len(objects),
            "objects": objects,
        }

    def delete_folder(self, bucket: str, folder_path: str) -> dict[str, Any]:
        """Delete all objects under a folder prefix (paginated list + batch delete)."""
        prefix = self._normalize_folder_prefix(folder_path)
        deleted_keys: list[str] = []
        continuation_token: str | None = None
        while True:
            list_kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "Prefix": prefix,
                "MaxKeys": S3_LIST_OBJECTS_MAX_KEYS,
            }
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token
            response = self._client.list_objects_v2(**list_kwargs)
            contents = response.get("Contents", [])
            if contents:
                delete_response = self._client.delete_objects(
                    Bucket=bucket,
                    Delete={
                        "Objects": [{"Key": item["Key"]} for item in contents],
                        "Quiet": True,
                    },
                )
                errors = delete_response.get("Errors", [])
                if errors:
                    failed_keys = ", ".join(str(item.get("Key", "")) for item in errors[:5])
                    raise ValueError(
                        f"Failed to delete object(s) from folder prefix: {failed_keys}"
                    )
                deleted_keys.extend(str(item["Key"]) for item in contents)
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
        return {
            "success": True,
            "bucket": bucket,
            "folder": prefix,
            "deleted_count": len(deleted_keys),
            "deleted_keys": deleted_keys,
        }

    def list_buckets(self) -> dict[str, Any]:
        """List buckets visible to the configured credentials."""
        response = self._client.list_buckets()
        buckets = response.get("Buckets", [])
        owner = response.get("Owner") or {}
        return {
            "count": len(buckets),
            "owner_id": owner.get("ID"),
            "owner_display_name": owner.get("DisplayName"),
            "buckets": [
                {
                    "name": item.get("Name"),
                    "creation_date": self._serialize_datetime(item.get("CreationDate")),
                }
                for item in buckets
            ],
        }

    def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> dict[str, Any]:
        """Copy an object to another bucket/key."""
        response = self._client.copy_object(
            CopySource={"Bucket": source_bucket, "Key": source_key},
            Bucket=dest_bucket,
            Key=dest_key,
        )
        copy_result = response.get("CopyObjectResult") or {}
        etag = copy_result.get("ETag") or response.get("ETag")
        return {
            "success": True,
            "source_bucket": source_bucket,
            "source_key": source_key,
            "bucket": dest_bucket,
            "key": dest_key,
            "etag": str(etag or "").strip('"'),
            "last_modified": self._serialize_datetime(copy_result.get("LastModified")),
            "version_id": response.get("VersionId"),
        }

    def delete_object(self, bucket: str, key: str) -> dict[str, Any]:
        """Delete an object from the bucket."""
        response = self._client.delete_object(Bucket=bucket, Key=key)
        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "version_id": response.get("VersionId"),
            "delete_marker": response.get("DeleteMarker", False),
        }

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 100,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        """List objects inside a bucket prefix (single ListObjectsV2 page)."""
        max_keys = normalize_s3_list_max_keys(max_keys)
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Prefix": prefix,
            "MaxKeys": max_keys,
        }
        normalized_token = str(continuation_token or "").strip()
        if normalized_token:
            kwargs["ContinuationToken"] = normalized_token
        response = self._client.list_objects_v2(**kwargs)
        contents = response.get("Contents", [])
        return {
            "bucket": bucket,
            "prefix": prefix,
            "count": len(contents),
            "truncated": bool(response.get("IsTruncated", False)),
            "continuation_token": response.get("ContinuationToken"),
            "next_continuation_token": response.get("NextContinuationToken"),
            "objects": [
                {
                    "key": item.get("Key"),
                    "size": item.get("Size"),
                    "etag": str(item.get("ETag", "") or "").strip('"'),
                    "last_modified": self._serialize_datetime(item.get("LastModified")),
                    "storage_class": item.get("StorageClass"),
                }
                for item in contents
            ],
        }
