import unittest

from fastapi import HTTPException

from app.api.credentials import validate_credential_config
from app.db.models import CredentialType


class TestPgvectorCredentialValidation(unittest.TestCase):
    def test_pgvector_requires_openai_api_key(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(CredentialType.pgvector, {})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_pgvector_valid_config_passes(self):
        # Should not raise.
        validate_credential_config(
            CredentialType.pgvector, {"openai_api_key": "sk-test"}
        )


if __name__ == "__main__":
    unittest.main()
