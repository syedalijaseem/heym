import unittest
from unittest.mock import patch

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


class TestVectorStoreFactory(unittest.TestCase):
    def test_qdrant_credential_returns_qdrant_service(self):
        from app.services.vector_store import (
            QdrantVectorStoreService,
            create_vector_store_service_for_credential,
        )

        config = {
            "qdrant_host": "localhost",
            "qdrant_port": 6333,
            "openai_api_key": "sk-test",
        }
        svc = create_vector_store_service_for_credential("qdrant", config)
        self.assertIsInstance(svc, QdrantVectorStoreService)

    def test_pgvector_credential_returns_pg_service(self):
        with patch("app.services.vector_store_pg.EmbeddingService"):
            from app.services.vector_store import create_vector_store_service_for_credential
            from app.services.vector_store_pg import PgVectorStoreService

            svc = create_vector_store_service_for_credential(
                "pgvector", {"openai_api_key": "sk-test"}
            )
            self.assertIsInstance(svc, PgVectorStoreService)

    def test_unknown_type_raises(self):
        from app.services.vector_store import create_vector_store_service_for_credential

        with self.assertRaises(ValueError):
            create_vector_store_service_for_credential("nope", {})


if __name__ == "__main__":
    unittest.main()
