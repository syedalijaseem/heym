import unittest

from app.services.chart_payload import build_chart_payload


class TestBuildChartPayload(unittest.TestCase):
    def test_bar_vertical_single_series(self):
        config = {
            "chartType": "bar",
            "orientation": "vertical",
            "labelField": "month",
            "valueField": "revenue",
        }
        data = {"data": [{"month": "Jan", "revenue": 120}, {"month": "Feb", "revenue": 150}]}
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["type"], "bar")
        self.assertEqual(payload["orientation"], "vertical")
        self.assertEqual(payload["labels"], ["Jan", "Feb"])
        self.assertEqual(payload["series"], [{"name": "revenue", "data": [120, 150]}])

    def test_pie_uses_label_and_value_fields(self):
        config = {"chartType": "pie", "labelField": "name", "valueField": "count"}
        data = [{"name": "A", "count": 3}, {"name": "B", "count": 7}]
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["type"], "pie")
        self.assertEqual(payload["labels"], ["A", "B"])
        self.assertEqual(payload["series"], [{"name": "count", "data": [3, 7]}])

    def test_line_multi_series(self):
        config = {
            "chartType": "line",
            "labelField": "day",
            "series": [
                {"name": "Sent", "field": "sent"},
                {"name": "Failed", "field": "failed"},
            ],
        }
        data = {
            "rows": [
                {"day": "Mon", "sent": 10, "failed": 1},
                {"day": "Tue", "sent": 12, "failed": 0},
            ]
        }
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["labels"], ["Mon", "Tue"])
        self.assertEqual(
            payload["series"],
            [{"name": "Sent", "data": [10, 12]}, {"name": "Failed", "data": [1, 0]}],
        )

    def test_table_default_columns_from_first_row(self):
        config = {"chartType": "table"}
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["type"], "table")
        self.assertEqual(payload["columns"], ["a", "b"])
        self.assertEqual(payload["rows"], [[1, 2], [3, 4]])

    def test_table_explicit_columns(self):
        config = {"chartType": "table", "columns": ["b"]}
        data = [{"a": 1, "b": 2}]
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["columns"], ["b"])
        self.assertEqual(payload["rows"], [[2]])

    def test_numeric_reads_value_field_from_first_row(self):
        config = {"chartType": "numeric", "valueField": "total", "unit": "USD"}
        data = {"data": [{"total": 270}]}
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["type"], "numeric")
        self.assertEqual(payload["value"], 270)
        self.assertEqual(payload["unit"], "USD")

    def test_numeric_scalar_input(self):
        config = {"chartType": "numeric"}
        payload = build_chart_payload(config, {"value": 42})
        self.assertEqual(payload["value"], 42)

    def test_data_path_traversal(self):
        config = {
            "chartType": "pie",
            "labelField": "k",
            "valueField": "v",
            "dataPath": "result.items",
        }
        data = {"result": {"items": [{"k": "x", "v": 1}]}}
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["labels"], ["x"])

    def test_empty_data_returns_empty_payload(self):
        config = {"chartType": "bar", "labelField": "m", "valueField": "v"}
        payload = build_chart_payload(config, {})
        self.assertEqual(payload["labels"], [])
        self.assertEqual(payload["series"], [{"name": "v", "data": []}])

    def test_title_passthrough(self):
        config = {"chartType": "numeric", "valueField": "v", "title": "Total"}
        payload = build_chart_payload(config, {"data": [{"v": 1}]})
        self.assertEqual(payload["title"], "Total")
