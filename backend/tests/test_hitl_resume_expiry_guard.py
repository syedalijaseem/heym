"""Regression test: resume_hitl_request_in_background must not resume non-pending or expired requests."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_session(hitl_request: MagicMock) -> MagicMock:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = hitl_request
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_db
    mock_session.__aexit__.return_value = False
    return mock_session


class TestResumeHitlExpiryGuard(IsolatedAsyncioTestCase):
    async def test_non_pending_status_is_not_resumed(self) -> None:
        for status in ("expired", "accepted", "refused"):
            hitl_request = MagicMock()
            hitl_request.status = status
            hitl_request.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            with (
                patch(
                    "app.services.hitl_service.async_session_maker",
                    return_value=_mock_session(hitl_request),
                ),
                patch("app.services.hitl_service.resume_workflow_execution") as mock_resume,
            ):
                from app.services.hitl_service import resume_hitl_request_in_background

                await resume_hitl_request_in_background(uuid.uuid4())
                mock_resume.assert_not_called(), f"resume called for status={status}"

    async def test_pending_but_expired_is_not_resumed(self) -> None:
        hitl_request = MagicMock()
        hitl_request.status = "pending"
        hitl_request.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        with (
            patch(
                "app.services.hitl_service.async_session_maker",
                return_value=_mock_session(hitl_request),
            ),
            patch("app.services.hitl_service.resume_workflow_execution") as mock_resume,
        ):
            from app.services.hitl_service import resume_hitl_request_in_background

            await resume_hitl_request_in_background(uuid.uuid4())
            mock_resume.assert_not_called()
