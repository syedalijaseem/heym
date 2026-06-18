"""Regression test: resume_hitl_request_in_background must only resume resolved requests with a decision."""

import uuid
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_db(hitl_request: MagicMock) -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = hitl_request
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = None  # workflow not found → safe early exit after guard
    return mock_db


def _make_session(mock_db: AsyncMock) -> MagicMock:
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_db
    mock_session.__aexit__.return_value = False
    return mock_session


def _make_request(status: str, decision: str | None) -> MagicMock:
    req = MagicMock()
    req.status = status
    req.decision = decision
    return req


class TestResumeHitlExpiryGuard(IsolatedAsyncioTestCase):
    async def _run(self, hitl_request: MagicMock) -> AsyncMock:
        mock_db = _make_mock_db(hitl_request)
        with patch(
            "app.services.hitl_service.async_session_maker", return_value=_make_session(mock_db)
        ):
            from app.services.hitl_service import resume_hitl_request_in_background

            await resume_hitl_request_in_background(uuid.uuid4())
        return mock_db

    async def test_resolved_with_decision_passes_guard(self) -> None:
        mock_db = await self._run(_make_request("resolved", "accept"))
        mock_db.get.assert_called()  # guard passed; function proceeded to workflow lookup

    async def test_pending_is_blocked(self) -> None:
        mock_db = await self._run(_make_request("pending", None))
        mock_db.get.assert_not_called()

    async def test_expired_is_blocked(self) -> None:
        mock_db = await self._run(_make_request("expired", None))
        mock_db.get.assert_not_called()

    async def test_resolved_without_decision_is_blocked(self) -> None:
        mock_db = await self._run(_make_request("resolved", None))
        mock_db.get.assert_not_called()
