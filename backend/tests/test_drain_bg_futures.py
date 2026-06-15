"""Regression tests for drain_bg_futures exception handling.

Verifies that when a background sub-workflow future raises:
  1. A warning is logged (with exc_info).
  2. done_event.wait() still executes (via finally), so the done-callback
     has finished recording status="error" before drain_bg_futures returns.
"""

from __future__ import annotations

import threading
import unittest
from concurrent.futures import Future

from app.services.workflow_executor import WorkflowExecutor


class DrainBgFuturesExceptionTests(unittest.TestCase):
    """drain_bg_futures must log and wait even when the future raises."""

    def _make_failing_future(self, exc: Exception) -> Future:
        f: Future = Future()
        f.set_exception(exc)
        return f

    def test_warning_logged_and_done_event_waited_on_future_failure(self) -> None:
        executor = WorkflowExecutor(nodes=[], edges=[])

        error = RuntimeError("sub-workflow boom")
        fut = self._make_failing_future(error)

        # done_event simulates the bg_callback_done Event set by the done-callback.
        # We pre-set it so done_event.wait() returns immediately.
        done_event = threading.Event()
        done_event.set()

        # Manually inject the tuple the way the executor does.
        executor._bg_futures.append((fut, done_event, "wf-id", "WF Name", {}))

        with self.assertLogs("app.services.workflow_executor", level="WARNING") as log_ctx:
            executor.drain_bg_futures()

        # Warning must mention the exception message.
        self.assertTrue(
            any("sub-workflow boom" in line for line in log_ctx.output),
            f"Expected warning not found in: {log_ctx.output}",
        )

    def test_status_error_recorded_before_drain_returns(self) -> None:
        """done_event.wait() in finally ensures the done-callback has written
        status='error' to sub_workflow_executions before drain_bg_futures returns."""
        executor = WorkflowExecutor(nodes=[], edges=[])

        error = ValueError("failed bg wf")
        fut = self._make_failing_future(error)

        # Simulate a real done-callback: record status="error" then set the event.
        done_event = threading.Event()

        def fake_done_callback(_fut: Future) -> None:
            from app.services.workflow_executor import SubWorkflowExecution

            with executor.lock:
                executor.sub_workflow_executions.append(
                    SubWorkflowExecution(
                        workflow_id="wf-id",
                        inputs={},
                        outputs={},
                        status="error",
                        execution_time_ms=0.0,
                        node_results=[],
                        workflow_name="WF Name",
                        trigger_source="SUB_WORKFLOW",
                    )
                )
            done_event.set()

        fut.add_done_callback(fake_done_callback)

        executor._bg_futures.append((fut, done_event, "wf-id", "WF Name", {}))

        with self.assertLogs("app.services.workflow_executor", level="WARNING"):
            executor.drain_bg_futures()

        self.assertEqual(len(executor.sub_workflow_executions), 1)
        self.assertEqual(executor.sub_workflow_executions[0].status, "error")
