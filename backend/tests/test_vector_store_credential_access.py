import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException, status

from app.db.models import Credential, CredentialType, VectorStore


def make_result(value: object) -> Mock:
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


class VectorStoreCredentialAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_clone_requires_access_to_backing_credential(self) -> None:
        from app.api.vector_stores import clone_vector_store

        user = SimpleNamespace(id=uuid.uuid4())
        store = VectorStore(
            id=uuid.uuid4(),
            name="Shared docs",
            description=None,
            collection_name="shared_collection",
            owner_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_result(store),
                make_result(None),
            ]
        )

        with (
            patch(
                "app.api.vector_stores.get_credential_config",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Credential not found",
                    )
                ),
            ) as get_config,
            patch("app.api.vector_stores.get_vector_store_service_from_config") as get_service,
        ):
            with self.assertRaises(HTTPException) as raised:
                await clone_vector_store(store.id, current_user=user, db=db)

        self.assertEqual(raised.exception.status_code, status.HTTP_404_NOT_FOUND)
        get_config.assert_awaited_once_with(store.credential_id, user.id, db)
        get_service.assert_not_called()
        db.add.assert_not_called()

    async def test_clone_uses_access_checked_credential_id(self) -> None:
        from app.api.vector_stores import clone_vector_store

        user = SimpleNamespace(id=uuid.uuid4())
        store = VectorStore(
            id=uuid.uuid4(),
            name="Shared docs",
            description="docs",
            collection_name="shared_collection",
            owner_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
        )
        credential = Credential(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            name="Shared Qdrant",
            type=CredentialType.qdrant,
            encrypted_config="encrypted",
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_result(store),
                make_result(None),
            ]
        )
        db.add = Mock()
        db.flush = AsyncMock()

        async def refresh(obj: VectorStore) -> None:
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        db.refresh = AsyncMock(side_effect=refresh)
        service = Mock()

        with (
            patch(
                "app.api.vector_stores.get_credential_config",
                new=AsyncMock(return_value=(credential, {"openai_api_key": "key"})),
            ),
            patch(
                "app.api.vector_stores.get_vector_store_service_from_config", return_value=service
            ),
            patch("app.api.vector_stores._get_store_stats", new=AsyncMock(return_value=None)),
        ):
            response = await clone_vector_store(store.id, current_user=user, db=db)

        cloned_store = db.add.call_args.args[0]
        self.assertEqual(cloned_store.owner_id, user.id)
        self.assertEqual(cloned_store.credential_id, credential.id)
        self.assertEqual(response.credential_id, credential.id)
        service.clone_collection.assert_called_once_with(
            store.collection_name, cloned_store.collection_name
        )
