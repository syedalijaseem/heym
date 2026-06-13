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


class TestIsDashboardWidgetWorkflow(unittest.TestCase):
    def test_detects_by_chart_output_node(self):
        from app.services.workflow_dsl_prompt import is_dashboard_widget_workflow

        wf = {"nodes": [{"type": "set"}, {"type": "chartOutput"}]}
        self.assertTrue(is_dashboard_widget_workflow(wf))

    def test_detects_by_kind_flag(self):
        from app.services.workflow_dsl_prompt import is_dashboard_widget_workflow

        self.assertTrue(is_dashboard_widget_workflow({"kind": "dashboard_widget", "nodes": []}))

    def test_normal_workflow_is_false(self):
        from app.services.workflow_dsl_prompt import is_dashboard_widget_workflow

        self.assertFalse(is_dashboard_widget_workflow({"nodes": [{"type": "llm"}]}))
        self.assertFalse(is_dashboard_widget_workflow(None))


class TestSeedWidgetNodes(unittest.TestCase):
    def test_seed_has_no_trigger_or_input_and_ends_in_chart(self):
        nodes, edges = dash_api._seed_widget_nodes("pie")
        types = [n["type"] for n in nodes]
        # Dashboard widgets must not start with a trigger or input node.
        for trigger in ("textInput", "cron", "slackTrigger", "telegramTrigger", "imapTrigger"):
            self.assertNotIn(trigger, types)
        self.assertIn("set", types)
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

        from app.db.models import CredentialType
        from app.models.dashboard_schemas import AiWidgetRequest

        credential = MagicMock(type=CredentialType.openai)

        with (
            patch.object(dash_api, "generate_widget_dsl", AsyncMock(return_value=fake_dsl)),
            patch.object(dash_api, "get_credential_for_user", AsyncMock(return_value=credential)),
        ):
            resp = await dash_api.ai_generate_widget(
                body=AiWidgetRequest(
                    prompt="show signups by month",
                    credential_id=uuid.uuid4(),
                    model="gpt-4o",
                ),
                current_user=user,
                db=db,
            )
        self.assertEqual(resp.chart_type, "pie")

    async def test_ai_generate_uses_dsl_name_and_description(self):
        user = _User()
        db = MagicMock()
        dashboard = MagicMock(id=uuid.uuid4())
        existing = MagicMock()
        existing.scalars.return_value.first.return_value = dashboard
        db.execute = AsyncMock(return_value=existing)
        added: list = []
        db.add = MagicMock(side_effect=lambda obj: added.append(obj))
        db.commit = AsyncMock()
        _wire_db_inserts(db)

        fake_dsl = {
            "name": "Signups by month",
            "description": "Monthly signups bar chart",
            "nodes": [{"id": "b", "type": "chartOutput", "data": {"chartType": "bar"}}],
            "edges": [],
        }

        from app.db.models import CredentialType
        from app.models.dashboard_schemas import AiWidgetRequest

        credential = MagicMock(type=CredentialType.openai)
        with (
            patch.object(dash_api, "generate_widget_dsl", AsyncMock(return_value=fake_dsl)),
            patch.object(dash_api, "get_credential_for_user", AsyncMock(return_value=credential)),
        ):
            resp = await dash_api.ai_generate_widget(
                body=AiWidgetRequest(prompt="anything", credential_id=uuid.uuid4(), model="m"),
                current_user=user,
                db=db,
            )
        self.assertEqual(resp.title, "Signups by month")
        self.assertEqual(resp.description, "Monthly signups bar chart")
        # the hidden workflow inherits the AI name/description
        workflows = [o for o in added if getattr(o, "kind", None) == "dashboard_widget"]
        self.assertTrue(workflows)
        self.assertEqual(workflows[0].name, "Signups by month")
        self.assertEqual(workflows[0].description, "Monthly signups bar chart")


class TestUpdateWidgetSync(unittest.IsolatedAsyncioTestCase):
    async def test_title_change_syncs_to_workflow(self):
        user = _User()
        widget = MagicMock()
        widget.id = uuid.uuid4()
        widget.workflow_id = uuid.uuid4()
        widget.title = "Old"
        widget.description = None
        widget.position = 0
        widget.layout = {"x": 0, "y": 0, "w": 4, "h": 4}
        widget.cache_ttl_seconds = 300
        widget.chart_type = "bar"
        workflow = MagicMock()

        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=widget)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=workflow)),
            ]
        )
        db.commit = AsyncMock()

        async def fake_refresh(obj):
            obj.updated_at = datetime.datetime.now()

        db.refresh = AsyncMock(side_effect=fake_refresh)

        from app.models.dashboard_schemas import WidgetUpdateRequest

        resp = await dash_api.update_widget(
            widget_id=widget.id,
            body=WidgetUpdateRequest(title="New", description="Desc"),
            current_user=user,
            db=db,
        )
        self.assertEqual(resp.title, "New")
        self.assertEqual(workflow.name, "New")
        self.assertEqual(workflow.description, "Desc")


class TestAiRefineWidget(unittest.IsolatedAsyncioTestCase):
    async def test_refine_updates_workflow_and_invalidates_cache(self):
        user = _User()
        widget = MagicMock()
        widget.id = uuid.uuid4()
        widget.workflow_id = uuid.uuid4()
        widget.chart_type = "bar"
        widget.position = 0
        widget.title = "W"
        widget.description = None
        widget.layout = {"x": 0, "y": 0, "w": 4, "h": 4}
        widget.cache_ttl_seconds = 300
        widget.cached_payload = {"old": True}
        widget.cached_at = datetime.datetime.now()
        widget.cached_workflow_version = "v"
        workflow = MagicMock()

        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=widget)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=workflow)),
            ]
        )
        db.commit = AsyncMock()

        async def fake_refresh(obj):
            obj.updated_at = datetime.datetime.now()

        db.refresh = AsyncMock(side_effect=fake_refresh)

        fake_dsl = {
            "nodes": [{"id": "c", "type": "chartOutput", "data": {"chartType": "line"}}],
            "edges": [],
        }

        from app.db.models import CredentialType
        from app.models.dashboard_schemas import AiRefineRequest

        credential = MagicMock(type=CredentialType.openai)
        with (
            patch.object(dash_api, "generate_widget_dsl", AsyncMock(return_value=fake_dsl)),
            patch.object(dash_api, "get_credential_for_user", AsyncMock(return_value=credential)),
        ):
            resp = await dash_api.ai_refine_widget(
                widget_id=widget.id,
                body=AiRefineRequest(
                    prompt="make it a line chart", credential_id=uuid.uuid4(), model="m"
                ),
                current_user=user,
                db=db,
            )
        self.assertEqual(resp.chart_type, "line")
        self.assertEqual(workflow.nodes, fake_dsl["nodes"])
        self.assertIsNone(widget.cached_payload)
        self.assertIsNone(widget.cached_at)
