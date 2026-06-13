import unittest
import uuid

from app.services.workflow_executor import execute_workflow


def _chart_output_node_result(result):
    for nr in result.node_results:
        nr_type = nr["node_type"] if isinstance(nr, dict) else nr.node_type
        if nr_type == "chartOutput":
            return nr["output"] if isinstance(nr, dict) else nr.output
    return None


class TestChartOutputNode(unittest.TestCase):
    def test_chart_output_transforms_upstream_rows(self):
        nodes = [
            {
                "id": "src",
                "type": "textInput",
                "data": {"label": "Source"},
            },
            {
                "id": "chart",
                "type": "chartOutput",
                "data": {
                    "label": "Chart",
                    "chartType": "bar",
                    "orientation": "vertical",
                    "dataPath": "data",
                    "labelField": "month",
                    "valueField": "revenue",
                },
            },
        ]
        edges = [{"id": "e1", "source": "src", "target": "chart"}]

        result = execute_workflow(
            workflow_id=uuid.uuid4(),
            nodes=nodes,
            edges=edges,
            inputs={
                "headers": {},
                "query": {},
                "body": {
                    "data": [
                        {"month": "Jan", "revenue": 120},
                        {"month": "Feb", "revenue": 150},
                    ]
                },
            },
            test_run=True,
        )

        payload = _chart_output_node_result(result)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "bar")
        self.assertEqual(payload["labels"], ["Jan", "Feb"])
        self.assertEqual(payload["series"], [{"name": "revenue", "data": [120, 150]}])
