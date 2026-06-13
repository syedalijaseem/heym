import unittest

from app.api import workflows as workflows_api


class TestWorkflowListExcludesWidgets(unittest.TestCase):
    def test_list_query_filters_kind_workflow(self):
        # Guard: the source enforces kind == "workflow" on listing queries so that
        # hidden dashboard-widget workflows never appear in the normal workflow lists.
        src = workflows_api.__file__
        with open(src, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('Workflow.kind == "workflow"', content)
