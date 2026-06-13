import datetime
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import dashboards as dash_api
from app.api import workflows as workflows_api
from app.models.dashboard_schemas import WidgetCreateRequest, WidgetLayout


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


def _wire_db_inserts(db):
    """Make a mocked DB assign PKs on flush and column defaults on refresh,
    emulating what PostgreSQL would do for newly added ORM objects."""

    def fake_flush():
        for call in db.add.call_args_list:
            obj = call.args[0]
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def fake_flush_async():
        fake_flush()

    async def fake_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "position", None) is None:
            obj.position = 0
        obj.updated_at = datetime.datetime.now()

    db.flush = AsyncMock(side_effect=fake_flush_async)
    db.refresh = AsyncMock(side_effect=fake_refresh)


class TestWorkflowListExcludesWidgets(unittest.TestCase):
    def test_list_query_filters_kind_workflow(self):
        # Guard: the source enforces kind == "workflow" on listing queries so that
        # hidden dashboard-widget workflows never appear in the normal workflow lists.
        src = workflows_api.__file__
        with open(src, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('Workflow.kind == "workflow"', content)


class TestSeedWidgetNodes(unittest.TestCase):
    def test_seed_creates_textinput_and_chartoutput(self):
        nodes, edges = dash_api._seed_widget_nodes("pie")
        types = [n["type"] for n in nodes]
        self.assertIn("textInput", types)
        self.assertIn("chartOutput", types)
        self.assertEqual(nodes[1]["data"]["chartType"], "pie")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["source"], nodes[0]["id"])
        self.assertEqual(edges[0]["target"], nodes[1]["id"])


class TestCreateWidget(unittest.IsolatedAsyncioTestCase):
    async def test_create_widget_creates_hidden_workflow(self):
        user = _User()
        db = MagicMock()
        # _get_or_create_dashboard: first query returns an existing dashboard
        dashboard = MagicMock(id=uuid.uuid4())
        existing = MagicMock()
        existing.scalars.return_value.first.return_value = dashboard
        db.execute = AsyncMock(return_value=existing)
        db.add = MagicMock()
        db.commit = AsyncMock()
        _wire_db_inserts(db)

        body = WidgetCreateRequest(title="Sales", chart_type="bar", layout=WidgetLayout())
        resp = await dash_api.create_widget(body=body, current_user=user, db=db)

        self.assertEqual(resp.title, "Sales")
        self.assertEqual(resp.chart_type, "bar")
        added_kinds = [getattr(c.args[0], "kind", None) for c in db.add.call_args_list]
        self.assertIn("dashboard_widget", added_kinds)


class TestAiGenerateWidget(unittest.IsolatedAsyncioTestCase):
    async def test_ai_generate_extracts_chart_type(self):
        user = _User()
        db = MagicMock()
        dashboard = MagicMock(id=uuid.uuid4())
        existing = MagicMock()
        existing.scalars.return_value.first.return_value = dashboard
        db.execute = AsyncMock(return_value=existing)
        db.add = MagicMock()
        db.commit = AsyncMock()
        _wire_db_inserts(db)

        fake_dsl = {
            "nodes": [
                {"id": "a", "type": "textInput", "data": {}},
                {"id": "b", "type": "chartOutput", "data": {"chartType": "pie"}},
            ],
            "edges": [{"id": "e", "source": "a", "target": "b"}],
        }

        from app.models.dashboard_schemas import AiWidgetRequest

        with patch.object(dash_api, "generate_widget_dsl", AsyncMock(return_value=fake_dsl)):
            resp = await dash_api.ai_generate_widget(
                body=AiWidgetRequest(prompt="show signups by month"),
                current_user=user,
                db=db,
            )
        self.assertEqual(resp.chart_type, "pie")
