import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.api.mcp import get_all_user_workflows, get_user_mcp_workflows


def _capturing_db() -> tuple[MagicMock, list[str]]:
    """Return a mock AsyncSession that records the compiled SQL of each query."""
    compiled_statements: list[str] = []

    async def execute(statement):  # type: ignore[no-untyped-def]
        compiled_statements.append(str(statement.compile()))
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute)
    return db, compiled_statements


class DashboardWidgetMcpFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_all_user_workflows_excludes_dashboard_widget(self) -> None:
        db, statements = _capturing_db()
        await get_all_user_workflows(db, uuid.uuid4())
        self.assertTrue(statements)
        self.assertTrue(
            any("kind" in s and "!=" in s for s in statements),
            f"Expected a kind inequality filter, got: {statements}",
        )

    async def test_get_user_mcp_workflows_excludes_dashboard_widget(self) -> None:
        db, statements = _capturing_db()
        await get_user_mcp_workflows(db, uuid.uuid4())
        # Both the owned and shared queries must filter out dashboard widgets.
        self.assertEqual(len(statements), 2)
        for s in statements:
            self.assertIn("kind", s)
            self.assertIn("!=", s)


if __name__ == "__main__":
    unittest.main()
