"""Regression test: _build_context must not raise RuntimeError when store_node_output runs concurrently."""

import threading
import unittest

from app.services.workflow_executor import WorkflowExecutor


class TestBuildContextConcurrency(unittest.TestCase):
    def test_no_dict_mutation_error_under_concurrent_store(self) -> None:
        ex = WorkflowExecutor(nodes=[], edges=[])
        stop = threading.Event()

        def writer() -> None:
            i = 0
            while not stop.is_set():
                ex.store_node_output(f"node_{i}", f"label_{i}", {"v": i})
                i += 1

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            for _ in range(500):
                ex._build_context({})
        finally:
            stop.set()
            t.join(timeout=2)
