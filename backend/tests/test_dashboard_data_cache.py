import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import dashboard_data


def _widget(cached_payload=None, cached_at=None, version="v1", ttl=300):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.workflow_id = uuid.uuid4()
    w.cache_ttl_seconds = ttl
    w.cached_payload = cached_payload
    w.cached_at = cached_at
    w.cached_workflow_version = version
    w.chart_type = "bar"
    return w


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


def _db_returning_workflow(wf):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wf)))
    db.commit = AsyncMock()
    return db


class TestComputeWidgetData(unittest.IsolatedAsyncioTestCase):
    async def test_returns_cache_when_fresh(self):
        now = datetime.now(timezone.utc)
        widget = _widget(
            cached_payload={"type": "bar", "labels": ["x"]},
            cached_at=now - timedelta(seconds=10),
            version="2026-01-01T00:00:00+00:00",
        )
        wf = MagicMock()
        wf.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        wf.nodes = []
        wf.edges = []
        db = _db_returning_workflow(wf)

        resp = await dashboard_data.compute_widget_data(db, widget, _User(), force=False)

        self.assertTrue(resp.cached)
        self.assertEqual(resp.payload, {"type": "bar", "labels": ["x"]})

    async def test_recomputes_when_forced(self):
        now = datetime.now(timezone.utc)
        widget = _widget(
            cached_payload={"type": "bar"},
            cached_at=now,
            version="2026-01-01T00:00:00+00:00",
        )
        wf = MagicMock()
        wf.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        wf.nodes = [{"id": "c", "type": "chartOutput", "data": {}}]
        wf.edges = []
        db = _db_returning_workflow(wf)

        fake_result = MagicMock()
        fake_result.node_results = [
            {"node_type": "chartOutput", "output": {"type": "bar", "labels": ["new"]}}
        ]
        with patch.object(dashboard_data, "execute_workflow", return_value=fake_result):
            resp = await dashboard_data.compute_widget_data(db, widget, _User(), force=True)

        self.assertFalse(resp.cached)
        self.assertEqual(resp.payload, {"type": "bar", "labels": ["new"]})
        self.assertEqual(widget.cached_payload, {"type": "bar", "labels": ["new"]})

    async def test_recomputes_when_version_changed(self):
        now = datetime.now(timezone.utc)
        widget = _widget(
            cached_payload={"type": "bar", "old": True},
            cached_at=now,
            version="OLD",
        )
        wf = MagicMock()
        wf.updated_at = datetime(2026, 2, 2, tzinfo=timezone.utc)
        wf.nodes = [{"id": "c", "type": "chartOutput", "data": {}}]
        wf.edges = []
        db = _db_returning_workflow(wf)

        fake_result = MagicMock()
        fake_result.node_results = [
            {"node_type": "chartOutput", "output": {"type": "bar", "fresh": True}}
        ]
        with patch.object(dashboard_data, "execute_workflow", return_value=fake_result):
            resp = await dashboard_data.compute_widget_data(db, widget, _User(), force=False)

        self.assertFalse(resp.cached)
        self.assertEqual(resp.payload, {"type": "bar", "fresh": True})

    async def test_cache_miss_records_execution_history(self):
        from app.db.models import ExecutionHistory

        widget = _widget(cached_payload=None, cached_at=None, version="v")
        wf = MagicMock()
        wf.id = uuid.uuid4()
        wf.owner_id = uuid.uuid4()
        wf.name = "widget"
        wf.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        wf.nodes = [{"id": "c", "type": "chartOutput", "data": {}}]
        wf.edges = []
        db = _db_returning_workflow(wf)
        db.add = MagicMock()

        fake_result = MagicMock()
        fake_result.node_results = [{"node_type": "chartOutput", "output": {"type": "bar"}}]
        fake_result.outputs = {}
        fake_result.status = "success"
        fake_result.execution_time_ms = 12.0

        with (
            patch.object(dashboard_data, "execute_workflow", return_value=fake_result),
            patch(
                "app.api.analytics.upsert_workflow_analytics_snapshot",
                new=AsyncMock(),
            ),
        ):
            await dashboard_data.compute_widget_data(db, widget, _User(), force=True)

        added_types = [type(c.args[0]).__name__ for c in db.add.call_args_list]
        self.assertIn(ExecutionHistory.__name__, added_types)
