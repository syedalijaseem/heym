import unittest

from fastapi import HTTPException

from app.api.credentials import get_masked_value, validate_credential_config
from app.db.models import CredentialType


class S3CredentialValidationTests(unittest.TestCase):
    def test_validate_requires_access_key(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(
                CredentialType.s3,
                {
                    "aws_secret_access_key": "secret",
                    "aws_region": "us-east-1",
                },
            )
        self.assertIn("aws_access_key_id", str(ctx.exception.detail))

    def test_validate_requires_secret_key(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(
                CredentialType.s3,
                {
                    "aws_access_key_id": "AKIA_TEST_123456",
                    "aws_region": "us-east-1",
                },
            )
        self.assertIn("aws_secret_access_key", str(ctx.exception.detail))

    def test_validate_requires_region(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(
                CredentialType.s3,
                {
                    "aws_access_key_id": "AKIA_TEST_123456",
                    "aws_secret_access_key": "secret",
                },
            )
        self.assertIn("aws_region", str(ctx.exception.detail))

    def test_validate_accepts_complete_config(self) -> None:
        validate_credential_config(
            CredentialType.s3,
            {
                "aws_access_key_id": "AKIA_TEST_123456",
                "aws_secret_access_key": "secret",
                "aws_region": "us-east-1",
            },
        )

    def test_masked_value_includes_region(self) -> None:
        masked = get_masked_value(
            CredentialType.s3,
            {
                "aws_access_key_id": "AKIA_TEST_1234567890",
                "aws_region": "us-east-1",
            },
        )
        self.assertIsNotNone(masked)
        self.assertIn("us-east-1", masked)

    def test_masked_value_access_key_only(self) -> None:
        masked = get_masked_value(
            CredentialType.s3,
            {
                "aws_access_key_id": "AKIA_TEST_1234567890",
            },
        )
        self.assertIsNotNone(masked)
        self.assertNotIn("us-east-1", masked)

    def test_masked_value_without_access_key_returns_none(self) -> None:
        masked = get_masked_value(
            CredentialType.s3,
            {
                "aws_region": "us-east-1",
            },
        )
        self.assertIsNone(masked)
