"""Tests for OpenTelemetry tracing instrumentation.

These exercise the span seams in the workflow executor and the read-only status
endpoint without depending on real node logic. Inner methods are patched so the
tests assert only the instrumentation behavior.
"""

import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability import tracing
from app.services.workflow_executor import (
    ExecutionResult,
    NodeResult,
    WorkflowExecutor,
)


def _make_executor() -> WorkflowExecutor:
    nodes = [{"id": "n1", "type": "set", "data": {"label": "My Node"}}]
    return WorkflowExecutor(nodes=nodes, edges=[], workflow_id=uuid.uuid4())


def _success_result() -> NodeResult:
    return NodeResult(
        node_id="n1",
        node_label="My Node",
        node_type="set",
        status="success",
        output={"value": 1},
        execution_time_ms=2.0,
    )


class TracingDisabledTest(unittest.TestCase):
    def test_get_tracer_is_safe_when_disabled(self) -> None:
        self.assertFalse(tracing.is_enabled())
        tracer = tracing.get_tracer()
        with tracer.start_as_current_span("x") as span:
            span.set_attribute("heym.test", 1)
        self.assertIsNotNone(tracer)

    def test_execute_node_takes_noop_fast_path_when_disabled(self) -> None:
        executor = _make_executor()
        with patch.object(executor, "_execute_node_inner", return_value=_success_result()) as inner:
            result = executor.execute_node("n1", {})
        self.assertEqual(result.status, "success")
        inner.assert_called_once()


class _EnabledTracingTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        # Bypass set-once guard so each test gets a fresh global provider.
        self._saved_global = trace._TRACER_PROVIDER
        trace._TRACER_PROVIDER = provider
        tracing._provider = provider  # mark tracing "enabled"

    def tearDown(self) -> None:
        tracing._provider = None
        trace._TRACER_PROVIDER = self._saved_global


class NodeSpanTest(_EnabledTracingTestBase):
    def test_node_span_emitted_with_attributes(self) -> None:
        executor = _make_executor()
        with patch.object(executor, "_execute_node_inner", return_value=_success_result()):
            executor.execute_node("n1", {})
        spans = self.exporter.get_finished_spans()
        node_spans = [s for s in spans if s.name == "heym.node.execute"]
        self.assertEqual(len(node_spans), 1)
        attrs = dict(node_spans[0].attributes)
        self.assertEqual(attrs["heym.node.id"], "n1")
        self.assertEqual(attrs["heym.node.type"], "set")
        self.assertEqual(attrs["heym.node.label"], "My Node")
        self.assertEqual(attrs["heym.node.status"], "success")

    def test_node_span_marks_error_status(self) -> None:
        executor = _make_executor()
        err = NodeResult(
            node_id="n1",
            node_label="My Node",
            node_type="set",
            status="error",
            output={"error": "boom"},
            execution_time_ms=1.0,
            error="boom",
        )
        with patch.object(executor, "_execute_node_inner", return_value=err):
            executor.execute_node("n1", {})
        node_spans = [
            s for s in self.exporter.get_finished_spans() if s.name == "heym.node.execute"
        ]
        self.assertEqual(len(node_spans), 1)
        self.assertEqual(node_spans[0].status.status_code, trace.StatusCode.ERROR)

    def test_llm_token_attributes_from_usage(self) -> None:
        executor = _make_executor()
        llm_result = NodeResult(
            node_id="n1",
            node_label="My Node",
            node_type="llm",
            status="success",
            output={
                "model": "gpt-4o",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
            execution_time_ms=3.0,
        )
        with patch.object(executor, "_execute_node_inner", return_value=llm_result):
            executor.execute_node("n1", {})
        attrs = dict(
            [s for s in self.exporter.get_finished_spans() if s.name == "heym.node.execute"][
                0
            ].attributes
        )
        self.assertEqual(attrs["heym.llm.model"], "gpt-4o")
        self.assertEqual(attrs["heym.llm.total_tokens"], 15)
        self.assertEqual(attrs["heym.llm.prompt_tokens"], 10)


class WorkflowSpanTest(_EnabledTracingTestBase):
    def test_root_span_emitted(self) -> None:
        executor = _make_executor()
        wf_id = executor.workflow_id
        result = ExecutionResult(
            workflow_id=wf_id, status="success", outputs={}, execution_time_ms=5.0
        )
        with patch.object(executor, "_execute_inner", return_value=result):
            executor.execute(wf_id, {})
        root_spans = [
            s for s in self.exporter.get_finished_spans() if s.name == "heym.workflow.execute"
        ]
        self.assertEqual(len(root_spans), 1)
        attrs = dict(root_spans[0].attributes)
        self.assertEqual(attrs["heym.workflow.id"], str(wf_id))
        self.assertEqual(attrs["heym.node.count"], 1)

    def test_node_span_nests_under_workflow_span_across_threads(self) -> None:
        """Node spans created in worker threads must parent to the workflow span."""
        executor = _make_executor()
        wf_id = executor.workflow_id

        def fake_inner(_wf_id: uuid.UUID, _inputs: dict) -> ExecutionResult:
            # Run node execution in a worker thread, like the real parallel path.
            with patch.object(executor, "_execute_node_inner", return_value=_success_result()):
                pool = ThreadPoolExecutor(max_workers=1)
                fut = pool.submit(executor.execute_node, "n1", {})
                fut.result()
                pool.shutdown()
            return ExecutionResult(
                workflow_id=_wf_id, status="success", outputs={}, execution_time_ms=5.0
            )

        with patch.object(executor, "_execute_inner", side_effect=fake_inner):
            executor.execute(wf_id, {})

        spans = self.exporter.get_finished_spans()
        root = next(s for s in spans if s.name == "heym.workflow.execute")
        node = next(s for s in spans if s.name == "heym.node.execute")
        self.assertEqual(node.parent.span_id, root.context.span_id)
        self.assertEqual(node.context.trace_id, root.context.trace_id)


class ObservabilityStatusEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_disabled_shape(self) -> None:
        from app.api.config import get_observability_status

        status = await get_observability_status(_user=object())
        dumped = status.model_dump()
        self.assertFalse(dumped["enabled"])
        self.assertEqual(dumped["instrumented"], [])
        self.assertEqual(dumped["spans"], [])
        self.assertNotIn("headers", dumped)
        self.assertEqual(dumped["endpoint"], "")

    async def test_status_enabled_no_secret_leak(self) -> None:
        from app.api import config as config_api

        with (
            patch.object(config_api.settings, "otel_enabled", True),
            patch.object(
                config_api.settings, "otel_exporter_otlp_endpoint", "http://collector:4318"
            ),
            patch.object(
                config_api.settings, "otel_exporter_otlp_headers", "authorization=Bearer secret"
            ),
        ):
            status = await config_api.get_observability_status(_user=object())
        dumped = status.model_dump()
        self.assertTrue(dumped["enabled"])
        self.assertEqual(dumped["endpoint"], "http://collector:4318")
        self.assertEqual(dumped["instrumented"], ["fastapi", "httpx"])
        self.assertEqual(dumped["spans"], ["workflow", "node"])
        # No secret/header value anywhere in the serialized status.
        self.assertNotIn("secret", str(dumped).lower())
        self.assertNotIn("authorization", str(dumped).lower())


if __name__ == "__main__":
    unittest.main()
