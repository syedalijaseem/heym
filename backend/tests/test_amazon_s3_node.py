"""Unit tests for Amazon S3 service and workflow executor integration."""

import base64
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.amazon_s3_service import normalize_s3_list_max_keys


def _make_s3_config() -> dict:
    """Return a minimal valid S3 credential config."""
    return {
        "aws_access_key_id": "AKIA_TEST_123456",
        "aws_secret_access_key": "secret",
        "aws_region": "us-east-1",
    }


class NormalizeS3ListMaxKeysTests(unittest.TestCase):
    def test_clamps_to_upper_bound(self) -> None:
        self.assertEqual(normalize_s3_list_max_keys(5000), 1000)

    def test_clamps_to_lower_bound(self) -> None:
        self.assertEqual(normalize_s3_list_max_keys(0), 1)
        self.assertEqual(normalize_s3_list_max_keys(-10), 1)

    def test_passes_through_valid_values(self) -> None:
        self.assertEqual(normalize_s3_list_max_keys(25), 25)
        self.assertEqual(normalize_s3_list_max_keys(1000), 1000)


class S3ServiceTests(unittest.TestCase):
    def test_put_object_returns_metadata(self) -> None:
        fake_client = MagicMock()
        fake_client.put_object.return_value = {"ETag": '"abc123"'}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).put_object(
                "my-bucket", "docs/hello.txt", "hello", "text/plain"
            )

        fake_client.put_object.assert_called_once()
        self.assertEqual(result["bucket"], "my-bucket")
        self.assertEqual(result["key"], "docs/hello.txt")
        self.assertEqual(result["etag"], "abc123")

    def test_put_object_omits_content_type_when_empty(self) -> None:
        fake_client = MagicMock()
        fake_client.put_object.return_value = {"ETag": '"abc123"'}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            S3Service(_make_s3_config()).put_object("my-bucket", "hello.txt", "hello", None)

        fake_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="hello.txt",
            Body=b"hello",
        )

    def test_build_client_uses_aws_credentials(self) -> None:
        with patch("app.services.amazon_s3_service.boto3.client") as mock_boto_client:
            from app.services.amazon_s3_service import S3Service

            S3Service(_make_s3_config())

        _, kwargs = mock_boto_client.call_args
        self.assertEqual(kwargs["region_name"], "us-east-1")
        self.assertEqual(kwargs["aws_access_key_id"], "AKIA_TEST_123456")
        self.assertNotIn("endpoint_url", kwargs)

    def test_get_object_returns_text_by_default(self) -> None:
        fake_body = MagicMock()
        fake_body.read.return_value = b"hello world"
        fake_client = MagicMock()
        fake_client.get_object.return_value = {
            "Body": fake_body,
            "ContentType": "text/plain",
            "ContentLength": 11,
            "ETag": '"etag-1"',
            "LastModified": datetime(2026, 6, 12, tzinfo=timezone.utc),
            "Metadata": {"source": "test"},
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).get_object("bucket", "hello.txt")

        self.assertEqual(result["body_text"], "hello world")
        self.assertEqual(result["etag"], "etag-1")
        self.assertEqual(result["metadata"], {"source": "test"})

    def test_get_object_returns_base64_when_requested(self) -> None:
        fake_body = MagicMock()
        fake_body.read.return_value = b"\x00\x01\x02"
        fake_client = MagicMock()
        fake_client.get_object.return_value = {"Body": fake_body}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).get_object(
                "bucket", "blob.bin", include_binary=True
            )

        self.assertEqual(result["body_base64"], base64.b64encode(b"\x00\x01\x02").decode("ascii"))

    def test_create_bucket_uses_location_constraint_for_non_default_region(self) -> None:
        fake_client = MagicMock()
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).create_bucket("new-bucket", "eu-west-1")

        fake_client.create_bucket.assert_called_once_with(
            Bucket="new-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["bucket"], "new-bucket")
        self.assertEqual(result["region"], "eu-west-1")

    def test_create_bucket_omits_location_for_us_east_1(self) -> None:
        fake_client = MagicMock()
        config = _make_s3_config()
        config["aws_region"] = "us-east-1"
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            S3Service(config).create_bucket("new-bucket", "us-east-1")

        fake_client.create_bucket.assert_called_once_with(Bucket="new-bucket")

    def test_delete_bucket_returns_success(self) -> None:
        fake_client = MagicMock()
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).delete_bucket("old-bucket")

        fake_client.delete_bucket.assert_called_once_with(Bucket="old-bucket")
        self.assertTrue(result["success"])
        self.assertEqual(result["bucket"], "old-bucket")

    def test_copy_object_returns_metadata(self) -> None:
        fake_client = MagicMock()
        fake_client.copy_object.return_value = {
            "CopyObjectResult": {
                "ETag": '"copy-etag"',
                "LastModified": datetime(2026, 6, 12, tzinfo=timezone.utc),
            }
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).copy_object(
                "src-bucket", "a.txt", "dest-bucket", "b.txt"
            )

        fake_client.copy_object.assert_called_once_with(
            CopySource={"Bucket": "src-bucket", "Key": "a.txt"},
            Bucket="dest-bucket",
            Key="b.txt",
        )
        self.assertEqual(result["source_bucket"], "src-bucket")
        self.assertEqual(result["key"], "b.txt")
        self.assertEqual(result["etag"], "copy-etag")

    def test_create_folder_writes_marker_object(self) -> None:
        fake_client = MagicMock()
        fake_client.put_object.return_value = {"ETag": '"folder-etag"'}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).create_folder("my-bucket", "docs/archive/")

        fake_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="docs/archive/",
            Body=b"",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["folder"], "docs/archive/")

    def test_create_folder_normalizes_trailing_slash(self) -> None:
        fake_client = MagicMock()
        fake_client.put_object.return_value = {"ETag": '"folder-etag"'}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).create_folder("my-bucket", "docs/archive")

        fake_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="docs/archive/",
            Body=b"",
        )
        self.assertEqual(result["key"], "docs/archive/")

    def test_list_buckets_returns_metadata(self) -> None:
        fake_client = MagicMock()
        fake_client.list_buckets.return_value = {
            "Owner": {"ID": "owner-1", "DisplayName": "owner"},
            "Buckets": [
                {
                    "Name": "bucket-a",
                    "CreationDate": datetime(2026, 6, 12, tzinfo=timezone.utc),
                }
            ],
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).list_buckets()

        fake_client.list_buckets.assert_called_once_with()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["buckets"][0]["name"], "bucket-a")
        self.assertEqual(result["owner_id"], "owner-1")

    def test_list_buckets_handles_empty_response(self) -> None:
        fake_client = MagicMock()
        fake_client.list_buckets.return_value = {}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).list_buckets()

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["buckets"], [])
        self.assertIsNone(result["owner_id"])

    def test_create_folder_empty_path_raises(self) -> None:
        fake_client = MagicMock()
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            with self.assertRaises(ValueError) as ctx:
                S3Service(_make_s3_config()).create_folder("my-bucket", "   ")

        self.assertIn("folder path", str(ctx.exception).lower())
        fake_client.put_object.assert_not_called()

    def test_delete_object_returns_metadata(self) -> None:
        fake_client = MagicMock()
        fake_client.delete_object.return_value = {
            "VersionId": "ver-1",
            "DeleteMarker": True,
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).delete_object("my-bucket", "docs/hello.txt")

        fake_client.delete_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="docs/hello.txt",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["version_id"], "ver-1")
        self.assertTrue(result["delete_marker"])

    def test_list_objects_returns_metadata(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {
            "IsTruncated": True,
            "ContinuationToken": "req-token",
            "NextContinuationToken": "next-token",
            "Contents": [
                {
                    "Key": "docs/a.txt",
                    "Size": 12,
                    "ETag": '"obj-etag"',
                    "LastModified": datetime(2026, 6, 12, tzinfo=timezone.utc),
                    "StorageClass": "STANDARD",
                }
            ],
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).list_objects("my-bucket", "docs/", 25)

        fake_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket",
            Prefix="docs/",
            MaxKeys=25,
        )
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["continuation_token"], "req-token")
        self.assertEqual(result["next_continuation_token"], "next-token")
        self.assertEqual(result["objects"][0]["key"], "docs/a.txt")
        self.assertEqual(result["objects"][0]["etag"], "obj-etag")

    def test_list_objects_passes_continuation_token(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            S3Service(_make_s3_config()).list_objects(
                "my-bucket",
                "docs/",
                100,
                "page-2-token",
            )

        fake_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket",
            Prefix="docs/",
            MaxKeys=100,
            ContinuationToken="page-2-token",
        )

    def test_list_objects_ignores_blank_continuation_token(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            S3Service(_make_s3_config()).list_objects("my-bucket", "docs/", 100, "   ")

        fake_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket",
            Prefix="docs/",
            MaxKeys=100,
        )

    def test_list_objects_clamps_max_keys(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            S3Service(_make_s3_config()).list_objects("my-bucket", "", 0)

        fake_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket",
            Prefix="",
            MaxKeys=1,
        )

    def test_get_all_folder_paginates_until_complete(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.side_effect = [
            {
                "IsTruncated": True,
                "NextContinuationToken": "token-1",
                "Contents": [{"Key": "docs/a.txt", "Size": 1, "ETag": '"a"'}],
            },
            {
                "IsTruncated": False,
                "Contents": [{"Key": "docs/b.txt", "Size": 2, "ETag": '"b"'}],
            },
        ]
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).get_all_folder("my-bucket", "docs")

        self.assertEqual(result["folder"], "docs/")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["objects"][1]["key"], "docs/b.txt")
        self.assertEqual(fake_client.list_objects_v2.call_count, 2)
        fake_client.list_objects_v2.assert_any_call(
            Bucket="my-bucket",
            Prefix="docs/",
            MaxKeys=1000,
            ContinuationToken="token-1",
        )

    def test_get_all_folder_empty_path_raises(self) -> None:
        fake_client = MagicMock()
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            with self.assertRaises(ValueError) as ctx:
                S3Service(_make_s3_config()).get_all_folder("my-bucket", "   ")

        self.assertIn("folder path", str(ctx.exception).lower())
        fake_client.list_objects_v2.assert_not_called()

    def test_delete_folder_paginates_across_multiple_pages(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.side_effect = [
            {
                "IsTruncated": True,
                "NextContinuationToken": "token-1",
                "Contents": [{"Key": "docs/a.txt"}],
            },
            {
                "IsTruncated": False,
                "Contents": [{"Key": "docs/b.txt"}],
            },
        ]
        fake_client.delete_objects.return_value = {"Errors": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).delete_folder("my-bucket", "docs")

        self.assertEqual(result["deleted_count"], 2)
        self.assertEqual(fake_client.delete_objects.call_count, 2)
        fake_client.list_objects_v2.assert_any_call(
            Bucket="my-bucket",
            Prefix="docs/",
            MaxKeys=1000,
            ContinuationToken="token-1",
        )

    def test_delete_folder_batch_deletes_all_objects(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {
            "IsTruncated": False,
            "Contents": [
                {"Key": "docs/a.txt"},
                {"Key": "docs/archive/"},
            ],
        }
        fake_client.delete_objects.return_value = {"Deleted": [], "Errors": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).delete_folder("my-bucket", "docs/")

        fake_client.delete_objects.assert_called_once_with(
            Bucket="my-bucket",
            Delete={
                "Objects": [{"Key": "docs/a.txt"}, {"Key": "docs/archive/"}],
                "Quiet": True,
            },
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)
        self.assertEqual(result["folder"], "docs/")

    def test_delete_folder_empty_prefix_deletes_nothing(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"IsTruncated": False, "Contents": []}
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            result = S3Service(_make_s3_config()).delete_folder("my-bucket", "empty/")

        fake_client.delete_objects.assert_not_called()
        self.assertEqual(result["deleted_count"], 0)

    def test_delete_folder_raises_when_batch_delete_fails(self) -> None:
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {
            "IsTruncated": False,
            "Contents": [{"Key": "docs/a.txt"}],
        }
        fake_client.delete_objects.return_value = {
            "Errors": [{"Key": "docs/a.txt", "Code": "AccessDenied"}],
        }
        with patch("app.services.amazon_s3_service.boto3.client", return_value=fake_client):
            from app.services.amazon_s3_service import S3Service

            with self.assertRaises(ValueError) as ctx:
                S3Service(_make_s3_config()).delete_folder("my-bucket", "docs")

        self.assertIn("failed to delete", str(ctx.exception).lower())


def _make_s3_workflow(s3_data: dict) -> tuple[list, list, dict]:
    """Build a minimal workflow: textInput -> s3 -> output."""
    nodes = [
        {
            "id": "start",
            "type": "textInput",
            "position": {"x": 0, "y": 0},
            "data": {"label": "start", "value": "hello", "inputFields": [{"key": "text"}]},
        },
        {
            "id": "s3",
            "type": "s3",
            "position": {"x": 200, "y": 0},
            "data": {"label": "s3Node", **s3_data},
        },
        {
            "id": "out",
            "type": "output",
            "position": {"x": 400, "y": 0},
            "data": {"label": "out", "message": "$s3Node", "allowDownstream": False},
        },
    ]
    edges = [
        {"id": "e1", "source": "start", "target": "s3"},
        {"id": "e2", "source": "s3", "target": "out"},
    ]
    return nodes, edges, {"text": "hello"}


def _s3_node_result(result) -> dict | None:
    """Return the s3 node result dict from a workflow execution result."""
    return next((r for r in result.node_results if r["node_label"] == "s3Node"), None)


def _run_s3_executor(
    s3_data: dict,
    *,
    decrypt_return: dict | None = None,
    service_patch: tuple[str, object] | None = None,
    credential_not_found: bool = False,
):
    """Execute a minimal s3 workflow with standard credential/db mocks."""
    from app.services.workflow_executor import WorkflowExecutor

    nodes, edges, inputs = _make_s3_workflow(s3_data)
    decrypt_value = _make_s3_config() if decrypt_return is None else decrypt_return
    with patch("app.db.session.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_session.return_value = mock_db
        cred_patch = (
            patch.object(WorkflowExecutor, "_get_accessible_credential", return_value=None)
            if credential_not_found
            else patch.object(
                WorkflowExecutor,
                "_get_accessible_credential",
                return_value=MagicMock(encrypted_config="encrypted"),
            )
        )
        with cred_patch:
            with patch("app.services.encryption.decrypt_config", return_value=decrypt_value):
                if service_patch:
                    patch_path, patch_return = service_patch
                    with patch(patch_path, return_value=patch_return) as mock_service:
                        executor = WorkflowExecutor(
                            nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                        )
                        result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)
                    return result, mock_service
                executor = WorkflowExecutor(nodes=nodes, edges=edges, actor_user_id=uuid.uuid4())
                result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)
    return result, None


class EvaluateNonemptyMessageTemplateTests(unittest.TestCase):
    def test_blank_template_returns_empty_string(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor(nodes=[], edges=[])
        result = executor.evaluate_nonempty_message_template("", {"text": "hello"}, None)
        self.assertEqual(result, "")

    def test_whitespace_template_returns_empty_string(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor(nodes=[], edges=[])
        result = executor.evaluate_nonempty_message_template("   ", {"text": "hello"}, None)
        self.assertEqual(result, "")

    def test_nonempty_template_is_evaluated(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor(nodes=[], edges=[])
        result = executor.evaluate_nonempty_message_template("$input.text", {"text": "hello"}, None)
        self.assertEqual(result, "hello")


class S3ExecutorBranchTests(unittest.TestCase):
    def test_missing_credential_results_in_error(self) -> None:
        result, _ = _run_s3_executor({"credentialId": "", "s3Operation": "putObject"})
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("credential", s3_result.get("error", "").lower())

    def test_missing_operation_results_in_error(self) -> None:
        result, _ = _run_s3_executor({"credentialId": "cred-1", "s3Operation": ""})
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("operation", s3_result.get("error", "").lower())

    def test_invalid_credential_config_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {"credentialId": "cred-1", "s3Operation": "putObject", "s3Bucket": "b", "s3Key": "k"},
            decrypt_return={},
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("credential", s3_result.get("error", "").lower())

    def test_credential_not_found_in_db_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
            },
            credential_not_found=True,
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["status"], "error")
        self.assertIn("credential", s3_result.get("error", "").lower())

    def test_missing_bucket_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "   ",
                "s3Key": "docs/hello.txt",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("bucket", s3_result.get("error", "").lower())

    def test_empty_string_bucket_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "",
                "s3Key": "docs/hello.txt",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("bucket", s3_result.get("error", "").lower())

    def test_missing_object_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("object key", s3_result.get("error", "").lower())

    def test_empty_string_object_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("object key", s3_result.get("error", "").lower())

    def test_get_object_missing_object_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getObject",
                "s3Bucket": "my-bucket",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("object key", s3_result.get("error", "").lower())

    def test_delete_object_missing_object_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteObject",
                "s3Bucket": "my-bucket",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("object key", s3_result.get("error", "").lower())

    def test_unknown_operation_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "notReal",
                "s3Bucket": "my-bucket",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("unknown", s3_result.get("error", "").lower())

    def test_put_object_operation_calls_service(self) -> None:
        result, mock_put = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
                "s3Body": "$input.text",
                "s3ContentType": "text/plain",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.put_object",
                {"success": True, "bucket": "my-bucket", "key": "docs/hello.txt"},
            ),
        )

        mock_put.assert_called_once_with("my-bucket", "docs/hello.txt", "hello", "text/plain")
        self.assertEqual(result.status, "success")

    def test_put_object_blank_body_uploads_empty_string(self) -> None:
        result, mock_put = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/empty.txt",
                "s3Body": "",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.put_object",
                {"success": True, "bucket": "my-bucket", "key": "docs/empty.txt"},
            ),
        )

        mock_put.assert_called_once_with("my-bucket", "docs/empty.txt", "", None)
        self.assertEqual(result.status, "success")

    def test_put_object_omits_content_type_when_blank(self) -> None:
        result, mock_put = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
                "s3Body": "hello",
                "s3ContentType": "   ",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.put_object",
                {"success": True, "bucket": "my-bucket", "key": "docs/hello.txt"},
            ),
        )

        mock_put.assert_called_once_with("my-bucket", "docs/hello.txt", "hello", None)
        self.assertEqual(result.status, "success")

    def test_put_object_output_attached_to_node_result(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "putObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
                "s3Body": "hello",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.put_object",
                {
                    "success": True,
                    "bucket": "my-bucket",
                    "key": "docs/hello.txt",
                    "etag": "abc123",
                },
            ),
        )

        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["status"], "success")
        self.assertEqual(s3_result["output"]["bucket"], "my-bucket")
        self.assertEqual(s3_result["output"]["etag"], "abc123")

    def test_get_object_operation_calls_service(self) -> None:
        result, mock_get = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.get_object",
                {"body_text": "hello"},
            ),
        )

        mock_get.assert_called_once_with("my-bucket", "docs/hello.txt", include_binary=False)
        self.assertEqual(result.status, "success")

    def test_get_object_binary_flag_passed_to_service(self) -> None:
        result, mock_get = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getObject",
                "s3Bucket": "my-bucket",
                "s3Key": "blob.bin",
                "s3IncludeBinary": True,
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.get_object",
                {"body_base64": "AAEC"},
            ),
        )

        mock_get.assert_called_once_with("my-bucket", "blob.bin", include_binary=True)
        self.assertEqual(result.status, "success")

    def test_delete_object_operation_calls_service(self) -> None:
        result, mock_delete = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.delete_object",
                {"success": True, "bucket": "my-bucket", "key": "docs/hello.txt"},
            ),
        )

        mock_delete.assert_called_once_with("my-bucket", "docs/hello.txt")
        self.assertEqual(result.status, "success")

    def test_list_objects_operation_calls_service(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3Prefix": "docs/",
                "s3MaxKeys": "25",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "docs/", 25, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_empty_prefix_skips_template_evaluation(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3Prefix": "",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 100, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_invalid_max_keys_defaults_to_100(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3MaxKeys": "not-a-number",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 100, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_max_keys_clamped_to_1000(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3MaxKeys": "5000",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 1000, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_min_max_keys_clamped_to_1(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3MaxKeys": "0",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 1, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_accepts_float_max_keys(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3MaxKeys": "25.5",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 25, None)
        self.assertEqual(result.status, "success")

    def test_list_objects_passes_continuation_token_to_service(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3Prefix": "docs/",
                "s3ContinuationToken": "page-2-token",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {
                    "bucket": "my-bucket",
                    "objects": [],
                    "count": 0,
                    "truncated": False,
                },
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "docs/", 100, "page-2-token")
        self.assertEqual(result.status, "success")

    def test_list_objects_output_includes_next_continuation_token(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {
                    "bucket": "my-bucket",
                    "objects": [{"key": "a.txt"}],
                    "count": 1,
                    "truncated": True,
                    "next_continuation_token": "next-page",
                },
            ),
        )

        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertTrue(s3_result["output"]["truncated"])
        self.assertEqual(s3_result["output"]["next_continuation_token"], "next-page")

    def test_create_bucket_operation_calls_service(self) -> None:
        result, mock_create = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "createBucket",
                "s3Bucket": "new-bucket",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.create_bucket",
                {"success": True, "bucket": "new-bucket", "region": "us-east-1"},
            ),
        )

        mock_create.assert_called_once_with("new-bucket", "us-east-1")
        self.assertEqual(result.status, "success")

    def test_create_bucket_uses_credential_region(self) -> None:
        config = _make_s3_config()
        config["aws_region"] = "eu-west-1"
        result, mock_create = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "createBucket",
                "s3Bucket": "new-bucket",
            },
            decrypt_return=config,
            service_patch=(
                "app.services.amazon_s3_service.S3Service.create_bucket",
                {"success": True, "bucket": "new-bucket", "region": "eu-west-1"},
            ),
        )

        mock_create.assert_called_once_with("new-bucket", "eu-west-1")
        self.assertEqual(result.status, "success")

    def test_delete_bucket_operation_calls_service(self) -> None:
        result, mock_delete = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteBucket",
                "s3Bucket": "old-bucket",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.delete_bucket",
                {"success": True, "bucket": "old-bucket"},
            ),
        )

        mock_delete.assert_called_once_with("old-bucket")
        self.assertEqual(result.status, "success")

    def test_copy_object_operation_calls_service(self) -> None:
        result, mock_copy = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "dest-bucket",
                "s3SourceBucket": "src-bucket",
                "s3SourceKey": "a.txt",
                "s3Key": "b.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.copy_object",
                {"success": True, "bucket": "dest-bucket", "key": "b.txt"},
            ),
        )

        mock_copy.assert_called_once_with("src-bucket", "a.txt", "dest-bucket", "b.txt")
        self.assertEqual(result.status, "success")

    def test_copy_object_defaults_source_bucket_to_destination(self) -> None:
        result, mock_copy = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "same-bucket",
                "s3SourceKey": "a.txt",
                "s3Key": "b.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.copy_object",
                {"success": True},
            ),
        )

        mock_copy.assert_called_once_with("same-bucket", "a.txt", "same-bucket", "b.txt")
        self.assertEqual(result.status, "success")

    def test_copy_object_blank_source_bucket_uses_destination(self) -> None:
        result, mock_copy = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "same-bucket",
                "s3SourceBucket": "   ",
                "s3SourceKey": "a.txt",
                "s3Key": "b.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.copy_object",
                {"success": True},
            ),
        )

        mock_copy.assert_called_once_with("same-bucket", "a.txt", "same-bucket", "b.txt")
        self.assertEqual(result.status, "success")

    def test_create_folder_executes(self) -> None:
        result, mock_create = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "createFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/archive",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.create_folder",
                {
                    "success": True,
                    "bucket": "my-bucket",
                    "folder": "docs/archive/",
                },
            ),
        )

        mock_create.assert_called_once_with("my-bucket", "docs/archive")
        self.assertEqual(result.status, "success")

    def test_create_folder_missing_path_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "createFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("folder path", s3_result.get("error", "").lower())

    def test_empty_string_folder_path_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "createFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("folder path", s3_result.get("error", "").lower())

    def test_copy_object_missing_source_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "dest-bucket",
                "s3SourceKey": "   ",
                "s3Key": "b.txt",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("source object key", s3_result.get("error", "").lower())

    def test_empty_string_source_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "dest-bucket",
                "s3SourceKey": "",
                "s3Key": "b.txt",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("source object key", s3_result.get("error", "").lower())

    def test_copy_object_missing_destination_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "dest-bucket",
                "s3SourceKey": "a.txt",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("destination object key", s3_result.get("error", "").lower())

    def test_empty_string_destination_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "copyObject",
                "s3Bucket": "dest-bucket",
                "s3SourceKey": "a.txt",
                "s3Key": "",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("destination object key", s3_result.get("error", "").lower())

    def test_list_buckets_skips_bucket_requirement(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listBuckets",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_buckets",
                {"count": 1, "buckets": [{"name": "bucket-a"}]},
            ),
        )

        mock_list.assert_called_once_with()
        self.assertEqual(result.status, "success")

    def test_list_buckets_output_attached_to_node_result(self) -> None:
        buckets_output = {
            "count": 2,
            "buckets": [{"name": "bucket-a"}, {"name": "bucket-b"}],
        }
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listBuckets",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_buckets",
                buckets_output,
            ),
        )

        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["status"], "success")
        self.assertEqual(s3_result["output"]["count"], 2)
        self.assertEqual(s3_result["output"]["buckets"][0]["name"], "bucket-a")

    def test_delete_folder_executes(self) -> None:
        result, mock_delete = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/archive",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.delete_folder",
                {
                    "success": True,
                    "bucket": "my-bucket",
                    "folder": "docs/archive/",
                    "deleted_count": 2,
                },
            ),
        )

        mock_delete.assert_called_once_with("my-bucket", "docs/archive")
        self.assertEqual(result.status, "success")

    def test_get_all_folder_executes(self) -> None:
        result, mock_get_all = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getAllFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/archive",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.get_all_folder",
                {
                    "bucket": "my-bucket",
                    "folder": "docs/archive/",
                    "count": 1,
                    "objects": [{"key": "docs/archive/a.txt"}],
                },
            ),
        )

        mock_get_all.assert_called_once_with("my-bucket", "docs/archive")
        self.assertEqual(result.status, "success")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["output"]["count"], 1)

    def test_delete_folder_empty_path_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("folder path", s3_result.get("error", "").lower())

    def test_get_all_folder_missing_folder_path_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getAllFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "   ",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("folder path", s3_result.get("error", "").lower())

    def test_get_object_empty_string_key_results_in_error(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getObject",
                "s3Bucket": "my-bucket",
                "s3Key": "",
            }
        )
        self.assertEqual(result.status, "error")
        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertIn("object key", s3_result.get("error", "").lower())

    def test_get_object_output_attached_to_node_result(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "getObject",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/hello.txt",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.get_object",
                {
                    "body_text": "hello",
                    "content_type": "text/plain",
                    "content_length": 5,
                },
            ),
        )

        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["output"]["body_text"], "hello")
        self.assertEqual(s3_result["output"]["content_type"], "text/plain")

    def test_list_objects_blank_continuation_token_passes_none(self) -> None:
        result, mock_list = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "listObjects",
                "s3Bucket": "my-bucket",
                "s3ContinuationToken": "   ",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.list_objects",
                {"bucket": "my-bucket", "objects": [], "count": 0},
            ),
        )

        mock_list.assert_called_once_with("my-bucket", "", 100, None)
        self.assertEqual(result.status, "success")

    def test_delete_folder_output_attached_to_node_result(self) -> None:
        result, _ = _run_s3_executor(
            {
                "credentialId": "cred-1",
                "s3Operation": "deleteFolder",
                "s3Bucket": "my-bucket",
                "s3Key": "docs/archive",
            },
            service_patch=(
                "app.services.amazon_s3_service.S3Service.delete_folder",
                {
                    "success": True,
                    "bucket": "my-bucket",
                    "folder": "docs/archive/",
                    "deleted_count": 3,
                    "deleted_keys": ["docs/archive/a.txt"],
                },
            ),
        )

        s3_result = _s3_node_result(result)
        self.assertIsNotNone(s3_result)
        self.assertEqual(s3_result["output"]["deleted_count"], 3)
        self.assertEqual(s3_result["output"]["deleted_keys"][0], "docs/archive/a.txt")
