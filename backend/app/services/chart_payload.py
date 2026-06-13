"""Pure transformation of workflow output into a standardized chart payload.

Shared by the chartOutput executor node and (indirectly) the dashboard data API.
Keep this side-effect free so it stays trivially unit-testable.
"""

from typing import Any


def _resolve_rows(data: Any, data_path: str | None) -> list:
    """Resolve a list of row dicts (or scalars) from arbitrary upstream output."""
    if data_path:
        node: Any = data
        for part in data_path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        data = node

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if not data:
            return []
        if isinstance(data.get("data"), list):
            return data["data"]
        for value in data.values():
            if isinstance(value, list):
                return value
        return [data]
    return []


def _coerce_number(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    try:
        if isinstance(value, str) and value.strip() != "":
            return float(value) if "." in value else int(value)
    except (ValueError, TypeError):
        pass
    return value


def build_chart_payload(config: dict, data: Any) -> dict:
    """Transform resolved upstream data into a ChartPayload for the given chart type."""
    chart_type = config.get("chartType", "bar")
    title = config.get("title")
    rows = _resolve_rows(data, config.get("dataPath"))

    payload: dict = {"type": chart_type}
    if title:
        payload["title"] = title

    if chart_type == "table":
        columns = config.get("columns")
        if not columns:
            columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
        payload["columns"] = columns
        payload["rows"] = [
            [row.get(col) if isinstance(row, dict) else row for col in columns] for row in rows
        ]
        return payload

    if chart_type in ("numeric", "gauge"):
        value_field = config.get("valueField")
        value: Any = None
        if rows and isinstance(rows[0], dict):
            if value_field:
                value = rows[0].get(value_field)
            else:
                # first numeric field of the first row
                for candidate in rows[0].values():
                    if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                        value = candidate
                        break
        elif isinstance(data, dict) and "value" in data:
            value = data["value"]
        elif isinstance(data, (int, float)):
            value = data
        payload["value"] = _coerce_number(value)
        if config.get("unit"):
            payload["unit"] = config["unit"]
        if config.get("decimals") is not None:
            payload["decimals"] = config["decimals"]
        if chart_type == "gauge":
            payload["min"] = _coerce_number(config.get("min", 0))
            payload["max"] = _coerce_number(config.get("max", 100))
        return payload

    if chart_type == "scatter":
        x_field = config.get("xField") or config.get("labelField")
        y_field = config.get("yField") or config.get("valueField", "value")
        points: list = []
        for row in rows:
            if isinstance(row, dict):
                x = _coerce_number(row.get(x_field)) if x_field else None
                y = _coerce_number(row.get(y_field))
                points.append([x, y])
        payload["series"] = [{"name": config.get("seriesName") or y_field, "data": points}]
        return payload

    # pie / bar / line share labels + series
    label_field = config.get("labelField")
    if label_field:
        payload["labels"] = [
            (row.get(label_field) if isinstance(row, dict) else row) for row in rows
        ]
    else:
        payload["labels"] = [
            (row.get(next(iter(row))) if isinstance(row, dict) and row else row) for row in rows
        ]

    series_defs = config.get("series")
    if series_defs:
        payload["series"] = [
            {
                "name": s.get("name", s.get("field", "")),
                "data": [
                    _coerce_number(row.get(s["field"])) if isinstance(row, dict) else None
                    for row in rows
                ],
            }
            for s in series_defs
        ]
    else:
        value_field = config.get("valueField", "value")
        payload["series"] = [
            {
                "name": value_field,
                "data": [
                    _coerce_number(row.get(value_field))
                    if isinstance(row, dict)
                    else _coerce_number(row)
                    for row in rows
                ],
            }
        ]

    if chart_type == "bar":
        payload["orientation"] = config.get("orientation", "vertical")

    if chart_type == "barGauge":
        if config.get("unit"):
            payload["unit"] = config["unit"]
        if config.get("max") is not None:
            payload["max"] = _coerce_number(config["max"])

    return payload
