# Heym Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Grafana-style user-built dashboards to heymrun where each widget renders a chart (pie/bar/line/table/numeric) from the output of a hidden Heym workflow ending in a new `chartOutput` node, with per-widget PostgreSQL TTL caching and AI single-widget generation.

**Architecture:** Each widget owns a hidden `Workflow` row (`kind='dashboard_widget'`) reusing the existing executor, DSL, canvas and versioning. A new `chartOutput` terminal node shapes upstream data into a standardized `ChartPayload`. A new `dashboards` API serves widget metadata and computes/caches chart data on the widget row (1:1 overwrite). The frontend adds a `dashboard` tab with a 12-column drag-resize grid rendering payloads via apexcharts.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic (backend); Vue 3 `<script setup>` + TypeScript strict + Pinia + apexcharts/vue3-apexcharts (frontend); pytest (backend tests only — no frontend test harness).

Spec: [docs/superpowers/specs/2026-06-13-dashboards-design.md](../specs/2026-06-13-dashboards-design.md)

---

## File Structure

**Backend — create:**
- `backend/app/services/chart_payload.py` — pure `build_chart_payload(config, data)` → ChartPayload dict
- `backend/app/api/dashboards.py` — dashboards router (GET dashboard, widget CRUD, widget data, AI generate)
- `backend/app/services/dashboard_data.py` — runs widget workflow + extracts `chartOutput` result + cache read/write
- `backend/tests/test_chart_payload.py`
- `backend/tests/test_chart_output_node.py`
- `backend/tests/test_dashboards_api.py`
- `backend/tests/test_dashboard_data_cache.py`

**Backend — modify:**
- `backend/app/db/models.py` — add `Workflow.kind`; add `Dashboard`, `DashboardWidget` models
- `backend/app/services/workflow_executor.py` — add `node_type == "chartOutput"` branch
- `backend/app/services/workflow_dsl_prompt.py` — register `chartOutput` node for AI/DSL
- `backend/app/models/schemas.py` — add dashboard Pydantic schemas (or a new `app/models/dashboard_schemas.py`)
- `backend/app/main.py` — register dashboards router
- `backend/app/api/workflows.py` — exclude `kind='dashboard_widget'` from workflow list queries
- `backend/alembic/versions/` — one migration for `Workflow.kind` + `dashboards` + `dashboard_widgets`

**Frontend — create:**
- `frontend/src/components/Nodes/ChartOutputNode.vue` — canvas node component
- `frontend/src/components/Dashboards/DashboardsPanel.vue` — tab root
- `frontend/src/components/Dashboards/DashboardGrid.vue` — drag-resize 12-col grid
- `frontend/src/components/Dashboards/DashboardWidgetCard.vue` — single widget card + apex render + title edit
- `frontend/src/components/Dashboards/ChartRenderer.vue` — payload → apexchart / table / numeric
- `frontend/src/components/Dashboards/AddWidgetDialog.vue`
- `frontend/src/components/Dashboards/AiWidgetDialog.vue`
- `frontend/src/services/dashboardApi.ts` — typed API client
- `frontend/src/types/dashboard.ts` — TS types (ChartPayload, DashboardWidget, etc.)

**Frontend — modify:**
- `frontend/src/types/workflow.ts` — add `"chartOutput"` to `NodeType` union
- node palette/registry (locate the node catalog used by the canvas) — add `chartOutput` entry + Vue Flow node-type map
- `frontend/src/views/DashboardView.vue` — add `dashboard` to `TabKey`, sidebar entry, panel render

---

## Conventions for every backend task

- Backend tests: `unittest.IsolatedAsyncioTestCase` / `TestCase` with `AsyncMock` for DB (see `backend/tests/test_analytics_api.py` for the established pattern).
- Run a single test: `SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/<file>::<Class>::<test> -v` from `backend/`.
- Ruff must pass: `uv run ruff check . && uv run ruff format --check .`
- Commit after each task with a Conventional Commit message.

---

## Phase A — Backend: chartOutput node + payload builder

### Task 1: `build_chart_payload` pure function

**Files:**
- Create: `backend/app/services/chart_payload.py`
- Test: `backend/tests/test_chart_payload.py`

**Contract.** `build_chart_payload(config: dict, data: Any) -> dict`:
- `config` is the `chartOutput` node's `data` dict. Keys: `chartType` (`pie|bar|line|table|numeric`), `orientation` (`horizontal|vertical`, bar only, default `vertical`), `dataPath` (optional dot path into `data`), `labelField`, `valueField`, `series` (optional `list[{name, field}]`), `columns` (optional `list[str]`), `unit` (optional), `decimals` (optional int), `title` (optional).
- `data` is the resolved upstream input (dict or list).
- Returns a `ChartPayload` dict: keys `type`, `orientation?`, `labels?`, `series?`, `columns?`, `rows?`, `value?`, `unit?`, `title?`.

**Row resolution rules** (`_resolve_rows(data, data_path)`):
1. If `data_path` set, traverse dot path on `data`; the result becomes `data`.
2. If `data` is a `list`, rows = `data`.
3. If `data` is a `dict` with a list-valued `"data"` key, rows = `data["data"]`.
4. Else if `data` is a `dict` with any list-valued field, rows = first such list.
5. Else if `data` is a `dict`, rows = `[data]` (single row).
6. Else rows = `[]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_chart_payload.py
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
        data = {"rows": [{"day": "Mon", "sent": 10, "failed": 1}, {"day": "Tue", "sent": 12, "failed": 0}]}
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
        config = {"chartType": "pie", "labelField": "k", "valueField": "v", "dataPath": "result.items"}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_payload.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.chart_payload'`

- [ ] **Step 3: Implement `chart_payload.py`**

```python
# backend/app/services/chart_payload.py
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

    if chart_type == "numeric":
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
        return payload

    # pie / bar / line share labels + series
    label_field = config.get("labelField")
    payload["labels"] = [
        (row.get(label_field) if isinstance(row, dict) else row) for row in rows
    ] if label_field else [
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
                    _coerce_number(row.get(value_field)) if isinstance(row, dict) else _coerce_number(row)
                    for row in rows
                ],
            }
        ]

    if chart_type == "bar":
        payload["orientation"] = config.get("orientation", "vertical")

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_payload.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Lint & commit**

```bash
cd backend && uv run ruff format app/services/chart_payload.py tests/test_chart_payload.py && uv run ruff check app/services/chart_payload.py
git add backend/app/services/chart_payload.py backend/tests/test_chart_payload.py
git commit -m "feat(dashboards): add build_chart_payload transformer"
```

---

### Task 2: `chartOutput` executor node branch

**Files:**
- Modify: `backend/app/services/workflow_executor.py` (add branch in `_execute_node_logic`, after the trigger branches, near the other transform nodes ~line 6546+)
- Test: `backend/tests/test_chart_output_node.py`

The branch reads upstream inputs via `self.get_node_inputs(node_id)` (returns `{source_label: output_dict}`), merges the single/first upstream output, and calls `build_chart_payload`. Output is the ChartPayload dict.

- [ ] **Step 1: Write the failing test** (executes a 2-node workflow: a `set`-like upstream feeding `chartOutput`). Use a minimal upstream by pinning data through `textInput._initial_inputs`.

```python
# backend/tests/test_chart_output_node.py
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
                "data": {
                    "label": "Source",
                    "_initial_inputs": {
                        "data": [
                            {"month": "Jan", "revenue": 120},
                            {"month": "Feb", "revenue": 150},
                        ]
                    },
                },
            },
            {
                "id": "chart",
                "type": "chartOutput",
                "data": {
                    "label": "Chart",
                    "chartType": "bar",
                    "orientation": "vertical",
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
            inputs={},
            test_run=True,
        )

        payload = _chart_output_node_result(result)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "bar")
        self.assertEqual(payload["labels"], ["Jan", "Feb"])
        self.assertEqual(payload["series"], [{"name": "revenue", "data": [120, 150]}])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_output_node.py -v`
Expected: FAIL — `chartOutput` is unhandled, payload is `None` (or the node errors).

- [ ] **Step 3: Add the executor branch**

In `backend/app/services/workflow_executor.py`, add an import near the top with the other service imports:

```python
from app.services.chart_payload import build_chart_payload
```

In `_execute_node_logic`, add this branch alongside the other `elif node_type == ...` transform branches (e.g. right after the `consoleLog`/`set` family — place it before the final `else`/unknown handling):

```python
            elif node_type == "chartOutput":
                upstream = self.get_node_inputs(node_id)
                if len(upstream) == 1:
                    source_data = next(iter(upstream.values()))
                elif upstream:
                    merged: dict = {}
                    for value in upstream.values():
                        if isinstance(value, dict):
                            merged.update(value)
                    source_data = merged
                else:
                    source_data = {}
                output = build_chart_payload(node_data, source_data)
```

(If the executor's branch chain assigns to a local `output` and falls through to a shared `NodeResult(...)` builder, this matches the existing pattern shown for `textInput`/`cron`. Verify the surrounding structure and follow it exactly.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_output_node.py -v`
Expected: PASS

- [ ] **Step 5: Lint & commit**

```bash
cd backend && uv run ruff check app/services/workflow_executor.py
git add backend/app/services/workflow_executor.py backend/tests/test_chart_output_node.py
git commit -m "feat(dashboards): add chartOutput executor node"
```

---

### Task 3: Register `chartOutput` in the DSL prompt

**Files:**
- Modify: `backend/app/services/workflow_dsl_prompt.py`

- [ ] **Step 1: Locate the node catalog** in `workflow_dsl_prompt.py` (search for an existing node like `"jsonOutputMapper"` or `"consoleLog"` to find where node types are described for the AI builder).

Run: `cd backend && grep -n "consoleLog\|jsonOutputMapper\|node types\|## Nodes" app/services/workflow_dsl_prompt.py | head`

- [ ] **Step 2: Add a `chartOutput` description** following the exact format used for neighboring nodes. Content to add:

```
- chartOutput: Terminal node for dashboard widgets. Transforms upstream rows into a chart.
  data: { chartType: "pie"|"bar"|"line"|"table"|"numeric", orientation?: "horizontal"|"vertical",
  dataPath?: string (dot path to the rows array), labelField?: string, valueField?: string,
  series?: [{ name: string, field: string }], columns?: string[], unit?: string, title?: string }.
  Must be the last node. The workflow before it should produce an array of row objects.
```

- [ ] **Step 3: Verify the prompt still builds** (no test harness for the string; just import it):

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run python -c "from app.services.workflow_dsl_prompt import build_assistant_prompt; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/workflow_dsl_prompt.py
git commit -m "feat(dashboards): document chartOutput node in DSL prompt"
```

---

## Phase B — Backend: data model + migration

### Task 4: Add `Workflow.kind` and exclude widget workflows from listing

**Files:**
- Modify: `backend/app/db/models.py` (Workflow class, ~line 251)
- Modify: `backend/app/api/workflows.py` (list queries at `GET ""` ~519 and `GET /with-inputs` ~577)
- Test: `backend/tests/test_dashboards_api.py` (the list-exclusion test lives here; created in this task, extended later)

- [ ] **Step 1: Add the column** to `Workflow` in `models.py`, after `description`:

```python
    kind: Mapped[str] = mapped_column(String(32), default="workflow", nullable=False, index=True)
```

- [ ] **Step 2: Add exclusion to workflow list queries.** In `backend/app/api/workflows.py`, both the main list endpoint (`@router.get("")`, ~519) and `/with-inputs` (~577) build a `select(Workflow)...where(...)`. Add `.where(Workflow.kind == "workflow")` to each so dashboard-widget workflows never appear in the normal lists.

Run to find the exact filters: `cd backend && grep -n "select(Workflow)" app/api/workflows.py | head`

- [ ] **Step 3: Write the failing test** (DB-mocked list excludes widget workflows). Add to a new `backend/tests/test_dashboards_api.py`:

```python
import unittest

from app.api import workflows as workflows_api


class TestWorkflowListExcludesWidgets(unittest.TestCase):
    def test_list_query_filters_kind_workflow(self):
        # Guard: the source enforces kind == "workflow" on listing queries.
        src = workflows_api.__file__
        with open(src, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('Workflow.kind == "workflow"', content)
```

(This is a lightweight source-guard test; full integration is exercised by the API tests in Task 7. It prevents regressions where the filter is dropped.)

- [ ] **Step 4: Run test**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_dashboards_api.py -v`
Expected: PASS once Step 2 is done (FAIL before).

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff check app/db/models.py app/api/workflows.py
git add backend/app/db/models.py backend/app/api/workflows.py backend/tests/test_dashboards_api.py
git commit -m "feat(dashboards): add Workflow.kind and exclude widget workflows from lists"
```

---

### Task 5: `Dashboard` and `DashboardWidget` models + Alembic migration

**Files:**
- Modify: `backend/app/db/models.py` (add two classes after `WorkflowVersion`, ~line 356; add `dashboards` relationship to `User`)
- Create: `backend/alembic/versions/<rev>_add_dashboards.py`

- [ ] **Step 1: Add the models** in `models.py`:

```python
class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Dashboard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    widgets: Mapped[list["DashboardWidget"]] = relationship(
        "DashboardWidget", back_populates="dashboard", cascade="all, delete-orphan"
    )


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    chart_type: Mapped[str] = mapped_column(String(32), nullable=False, default="bar")
    layout: Mapped[dict] = mapped_column(JSON, default=lambda: {"x": 0, "y": 0, "w": 4, "h": 4})
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cached_workflow_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dashboard: Mapped["Dashboard"] = relationship("Dashboard", back_populates="widgets")
    workflow: Mapped["Workflow"] = relationship("Workflow")
```

- [ ] **Step 2: Generate the migration**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run alembic revision --autogenerate -m "add dashboards"`

- [ ] **Step 3: Review the generated migration** — confirm it (a) adds `workflows.kind` column with `server_default='workflow'` and an index, (b) creates `dashboards` and `dashboard_widgets` with the FKs and indexes above. If autogenerate misses `server_default` on `kind`, edit the `op.add_column` to include `server_default="workflow"` so existing rows backfill, then drop the server_default in a follow-up `op.alter_column` (or leave it — acceptable).

- [ ] **Step 4: Apply and verify**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run alembic upgrade head`
Expected: completes without error. Then `uv run alembic downgrade -1 && uv run alembic upgrade head` to confirm reversibility.

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff check app/db/models.py
git add backend/app/db/models.py backend/alembic/versions/
git commit -m "feat(dashboards): add Dashboard and DashboardWidget models + migration"
```

---

## Phase C — Backend: dashboards API

### Task 6: Pydantic schemas

**Files:**
- Create: `backend/app/models/dashboard_schemas.py`

- [ ] **Step 1: Write the schemas**

```python
# backend/app/models/dashboard_schemas.py
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WidgetLayout(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 4


class DashboardWidgetResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    title: str
    chart_type: str
    layout: WidgetLayout
    cache_ttl_seconds: int
    position: int
    updated_at: datetime


class DashboardResponse(BaseModel):
    id: uuid.UUID
    name: str
    widgets: list[DashboardWidgetResponse]


class WidgetCreateRequest(BaseModel):
    title: str = "Untitled"
    chart_type: str = "bar"
    layout: WidgetLayout = Field(default_factory=WidgetLayout)
    cache_ttl_seconds: int = 300


class WidgetUpdateRequest(BaseModel):
    title: str | None = None
    chart_type: str | None = None
    layout: WidgetLayout | None = None
    cache_ttl_seconds: int | None = None


class WidgetDataResponse(BaseModel):
    widget_id: uuid.UUID
    payload: dict[str, Any] | None
    cached: bool
    computed_at: datetime | None
    error: str | None = None


class AiWidgetRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
```

- [ ] **Step 2: Verify import**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run python -c "from app.models.dashboard_schemas import DashboardResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd backend && uv run ruff format app/models/dashboard_schemas.py
git add backend/app/models/dashboard_schemas.py
git commit -m "feat(dashboards): add dashboard Pydantic schemas"
```

---

### Task 7: Dashboards router — GET dashboard (auto-create) + widget CRUD

**Files:**
- Create: `backend/app/api/dashboards.py`
- Modify: `backend/app/main.py` (register router)
- Test: extend `backend/tests/test_dashboards_api.py`

Widget creation also creates a hidden seed `Workflow` (`kind="dashboard_widget"`) with a `textInput` + empty `chartOutput` node so the canvas opens with a valid starting point.

- [ ] **Step 1: Write the router**

```python
# backend/app/api/dashboards.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Dashboard, DashboardWidget, User, Workflow
from app.db.session import get_db
from app.models.dashboard_schemas import (
    DashboardResponse,
    DashboardWidgetResponse,
    WidgetCreateRequest,
    WidgetDataResponse,
    WidgetUpdateRequest,
)
from app.services.dashboard_data import compute_widget_data

router = APIRouter()


async def _get_or_create_dashboard(db: AsyncSession, user: User) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(Dashboard.owner_id == user.id).order_by(Dashboard.created_at)
    )
    dashboard = result.scalars().first()
    if dashboard is None:
        dashboard = Dashboard(owner_id=user.id, name="Dashboard")
        db.add(dashboard)
        await db.commit()
        await db.refresh(dashboard)
    return dashboard


def _seed_widget_nodes(chart_type: str) -> tuple[list, list]:
    src_id = str(uuid.uuid4())
    chart_id = str(uuid.uuid4())
    nodes = [
        {"id": src_id, "type": "textInput", "position": {"x": 0, "y": 0}, "data": {"label": "Data"}},
        {
            "id": chart_id,
            "type": "chartOutput",
            "position": {"x": 320, "y": 0},
            "data": {"label": "Chart", "chartType": chart_type},
        },
    ]
    edges = [{"id": str(uuid.uuid4()), "source": src_id, "target": chart_id}]
    return nodes, edges


def _widget_to_response(widget: DashboardWidget) -> DashboardWidgetResponse:
    return DashboardWidgetResponse(
        id=widget.id,
        workflow_id=widget.workflow_id,
        title=widget.title,
        chart_type=widget.chart_type,
        layout=widget.layout,
        cache_ttl_seconds=widget.cache_ttl_seconds,
        position=widget.position,
        updated_at=widget.updated_at,
    )


async def _load_widget(db: AsyncSession, widget_id: uuid.UUID, user: User) -> DashboardWidget:
    result = await db.execute(
        select(DashboardWidget)
        .join(Dashboard, DashboardWidget.dashboard_id == Dashboard.id)
        .where(DashboardWidget.id == widget_id, Dashboard.owner_id == user.id)
    )
    widget = result.scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    return widget


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    dashboard = await _get_or_create_dashboard(db, current_user)
    result = await db.execute(
        select(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard.id)
        .order_by(DashboardWidget.position)
    )
    widgets = result.scalars().all()
    return DashboardResponse(
        id=dashboard.id,
        name=dashboard.name,
        widgets=[_widget_to_response(w) for w in widgets],
    )


@router.post("/widgets", response_model=DashboardWidgetResponse, status_code=status.HTTP_201_CREATED)
async def create_widget(
    body: WidgetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    dashboard = await _get_or_create_dashboard(db, current_user)
    nodes, edges = _seed_widget_nodes(body.chart_type)
    workflow = Workflow(
        name=f"[widget] {body.title}",
        owner_id=current_user.id,
        kind="dashboard_widget",
        nodes=nodes,
        edges=edges,
    )
    db.add(workflow)
    await db.flush()
    widget = DashboardWidget(
        dashboard_id=dashboard.id,
        workflow_id=workflow.id,
        title=body.title,
        chart_type=body.chart_type,
        layout=body.layout.model_dump(),
        cache_ttl_seconds=body.cache_ttl_seconds,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)


@router.patch("/widgets/{widget_id}", response_model=DashboardWidgetResponse)
async def update_widget(
    widget_id: uuid.UUID,
    body: WidgetUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    widget = await _load_widget(db, widget_id, current_user)
    if body.title is not None:
        widget.title = body.title
    if body.chart_type is not None:
        widget.chart_type = body.chart_type
    if body.layout is not None:
        widget.layout = body.layout.model_dump()
    if body.cache_ttl_seconds is not None:
        widget.cache_ttl_seconds = body.cache_ttl_seconds
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)


@router.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(
    widget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    widget = await _load_widget(db, widget_id, current_user)
    workflow_id = widget.workflow_id
    await db.delete(widget)
    wf_result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if workflow is not None and workflow.kind == "dashboard_widget":
        await db.delete(workflow)
    await db.commit()


@router.get("/widgets/{widget_id}/data", response_model=WidgetDataResponse)
async def get_widget_data(
    widget_id: uuid.UUID,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WidgetDataResponse:
    widget = await _load_widget(db, widget_id, current_user)
    return await compute_widget_data(db, widget, current_user, force=force)
```

- [ ] **Step 2: Register the router** in `backend/app/main.py` near the other includes (after `analytics`, ~line 247):

```python
from app.api import dashboards  # add to the existing api imports block
app.include_router(dashboards.router, prefix="/api/dashboards", tags=["Dashboards"])
```

- [ ] **Step 3: Write API tests** (DB-mocked, following `test_analytics_api.py` patterns). Append to `backend/tests/test_dashboards_api.py`:

```python
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.api import dashboards as dash_api
from app.models.dashboard_schemas import WidgetCreateRequest, WidgetLayout


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


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
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        created_widget = {}

        async def fake_refresh(obj):
            created_widget["obj"] = obj
            if not getattr(obj, "id", None):
                obj.id = uuid.uuid4()
            obj.updated_at = __import__("datetime").datetime.now()

        db.refresh = AsyncMock(side_effect=fake_refresh)

        body = WidgetCreateRequest(title="Sales", chart_type="bar", layout=WidgetLayout())
        resp = await dash_api.create_widget(body=body, current_user=user, db=db)

        self.assertEqual(resp.title, "Sales")
        self.assertEqual(resp.chart_type, "bar")
        # a Workflow with kind dashboard_widget was added
        added_kinds = [getattr(c.args[0], "kind", None) for c in db.add.call_args_list]
        self.assertIn("dashboard_widget", added_kinds)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_dashboards_api.py -v`
Expected: PASS (note: `compute_widget_data` is imported but only Task 8 implements it — create a minimal stub now if import fails, then flesh out in Task 8, OR implement Task 8 before running the data endpoint. For this task's tests, `get_widget_data` is not exercised, so the import must still resolve: implement the `dashboard_data.py` stub in Step 5 below.)

- [ ] **Step 5: Add a minimal `dashboard_data.py` stub** so the import resolves (real logic in Task 8):

```python
# backend/app/services/dashboard_data.py  (stub — completed in Task 8)
from app.models.dashboard_schemas import WidgetDataResponse


async def compute_widget_data(db, widget, user, force: bool = False) -> WidgetDataResponse:
    raise NotImplementedError
```

- [ ] **Step 6: Commit**

```bash
cd backend && uv run ruff format app/api/dashboards.py app/main.py app/services/dashboard_data.py tests/test_dashboards_api.py && uv run ruff check app/api/dashboards.py
git add backend/app/api/dashboards.py backend/app/main.py backend/app/services/dashboard_data.py backend/tests/test_dashboards_api.py
git commit -m "feat(dashboards): add dashboards router with widget CRUD"
```

---

### Task 8: Widget data computation + PostgreSQL 1:1 cache

**Files:**
- Modify (replace stub): `backend/app/services/dashboard_data.py`
- Test: `backend/tests/test_dashboard_data_cache.py`

Cache logic: serve `widget.cached_payload` when `now - cached_at < cache_ttl_seconds` AND `cached_workflow_version == widget.workflow.updated_at.isoformat()` AND not `force`. Otherwise run the workflow via `execute_workflow` (in a thread), extract the `chartOutput` node output, overwrite the cache columns (1:1), commit, and return.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_dashboard_data_cache.py
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
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wf)))

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
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wf)))
        db.commit = AsyncMock()

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
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wf)))
        db.commit = AsyncMock()

        fake_result = MagicMock()
        fake_result.node_results = [
            {"node_type": "chartOutput", "output": {"type": "bar", "fresh": True}}
        ]
        with patch.object(dashboard_data, "execute_workflow", return_value=fake_result):
            resp = await dashboard_data.compute_widget_data(db, widget, _User(), force=False)

        self.assertFalse(resp.cached)
        self.assertEqual(resp.payload, {"type": "bar", "fresh": True})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_dashboard_data_cache.py -v`
Expected: FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement `dashboard_data.py`**

```python
# backend/app/services/dashboard_data.py
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DashboardWidget, User, Workflow
from app.models.dashboard_schemas import WidgetDataResponse
from app.services.workflow_executor import execute_workflow


def _version_token(workflow: Workflow) -> str:
    return workflow.updated_at.isoformat() if workflow.updated_at else ""


def _extract_chart_payload(result) -> dict | None:
    for nr in result.node_results:
        node_type = nr["node_type"] if isinstance(nr, dict) else nr.node_type
        if node_type == "chartOutput":
            return nr["output"] if isinstance(nr, dict) else nr.output
    return None


async def compute_widget_data(
    db: AsyncSession, widget: DashboardWidget, user: User, force: bool = False
) -> WidgetDataResponse:
    wf_result = await db.execute(select(Workflow).where(Workflow.id == widget.workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if workflow is None:
        return WidgetDataResponse(
            widget_id=widget.id, payload=None, cached=False, computed_at=None,
            error="Widget workflow not found",
        )

    version = _version_token(workflow)
    now = datetime.now(timezone.utc)
    fresh = (
        not force
        and widget.cached_payload is not None
        and widget.cached_at is not None
        and widget.cached_workflow_version == version
        and (now - widget.cached_at).total_seconds() < widget.cache_ttl_seconds
    )
    if fresh:
        return WidgetDataResponse(
            widget_id=widget.id, payload=widget.cached_payload, cached=True,
            computed_at=widget.cached_at,
        )

    try:
        result = await asyncio.to_thread(
            execute_workflow,
            workflow_id=workflow.id,
            nodes=workflow.nodes,
            edges=workflow.edges,
            inputs={},
            test_run=False,
            trace_user_id=user.id,
            actor_user_id=user.id,
        )
    except Exception as exc:  # surface execution errors to the widget, never 500 the dashboard
        return WidgetDataResponse(
            widget_id=widget.id, payload=None, cached=False, computed_at=None, error=str(exc)
        )

    payload = _extract_chart_payload(result)
    widget.cached_payload = payload
    widget.cached_at = now
    widget.cached_workflow_version = version
    await db.commit()
    return WidgetDataResponse(
        widget_id=widget.id, payload=payload, cached=False, computed_at=now,
        error=None if payload is not None else "Workflow produced no chartOutput",
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_dashboard_data_cache.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint & commit**

```bash
cd backend && uv run ruff format app/services/dashboard_data.py tests/test_dashboard_data_cache.py && uv run ruff check app/services/dashboard_data.py
git add backend/app/services/dashboard_data.py backend/tests/test_dashboard_data_cache.py
git commit -m "feat(dashboards): compute widget data with postgres 1:1 cache"
```

---

### Task 9: AI single-widget generation endpoint

**Files:**
- Modify: `backend/app/api/dashboards.py` (add `POST /widgets/ai-generate`)
- Test: extend `backend/tests/test_dashboards_api.py`

Reuse the existing DSL generator. First locate it.

- [ ] **Step 1: Locate the DSL generation entry point**

Run: `cd backend && grep -rn "def .*generate.*dsl\|Builder.*generate\|create_and_run_generated_workflow_tool\|def generate_workflow" app/api/ai_assistant.py app/services/*.py | head`

Use the same generator that `create_and_run_generated_workflow_tool` ([backend/app/api/ai_assistant.py:960](../../../backend/app/api/ai_assistant.py)) calls to turn a prompt into `{nodes, edges}`. Identify the callable (e.g. `generate_workflow_dsl(prompt, ...) -> dict`) and its module.

- [ ] **Step 2: Write the endpoint** in `dashboards.py`. It calls the generator with an augmented prompt instructing a `chartOutput` terminal node, creates the hidden workflow + widget, and returns the widget. Augmentation:

```python
from app.models.dashboard_schemas import AiWidgetRequest
# import the located generator, e.g.:
# from app.services.<module> import generate_workflow_dsl

_AI_WIDGET_SUFFIX = (
    " The workflow MUST end with a single chartOutput node that produces the chart. "
    "Choose an appropriate chartType (pie, bar, line, table, or numeric) and set "
    "labelField/valueField (or series) on the chartOutput node so it renders the requested metric."
)


@router.post("/widgets/ai-generate", response_model=DashboardWidgetResponse, status_code=status.HTTP_201_CREATED)
async def ai_generate_widget(
    body: AiWidgetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    dashboard = await _get_or_create_dashboard(db, current_user)
    dsl = await generate_workflow_dsl(body.prompt + _AI_WIDGET_SUFFIX, owner_id=current_user.id, db=db)
    nodes = dsl.get("nodes", [])
    edges = dsl.get("edges", [])
    chart_nodes = [n for n in nodes if n.get("type") == "chartOutput"]
    if not chart_nodes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI did not produce a chartOutput node",
        )
    chart_type = chart_nodes[-1].get("data", {}).get("chartType", "bar")
    workflow = Workflow(
        name="[widget] AI generated",
        owner_id=current_user.id,
        kind="dashboard_widget",
        nodes=nodes,
        edges=edges,
    )
    db.add(workflow)
    await db.flush()
    widget = DashboardWidget(
        dashboard_id=dashboard.id,
        workflow_id=workflow.id,
        title=body.prompt[:60],
        chart_type=chart_type,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)
```

(Match the real generator's signature — adjust the `generate_workflow_dsl(...)` call to the actual function found in Step 1. If it is synchronous, wrap with `asyncio.to_thread`.)

- [ ] **Step 3: Write the test** (mock the generator) — append to `test_dashboards_api.py`:

```python
class TestAiGenerateWidget(unittest.IsolatedAsyncioTestCase):
    async def test_ai_generate_extracts_chart_type(self):
        user = _User()
        db = MagicMock()
        dashboard = MagicMock(id=uuid.uuid4())
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=dashboard))))
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        async def fake_refresh(obj):
            if not getattr(obj, "id", None):
                obj.id = uuid.uuid4()
            obj.updated_at = __import__("datetime").datetime.now()

        db.refresh = AsyncMock(side_effect=fake_refresh)

        fake_dsl = {
            "nodes": [
                {"id": "a", "type": "textInput", "data": {}},
                {"id": "b", "type": "chartOutput", "data": {"chartType": "pie"}},
            ],
            "edges": [{"id": "e", "source": "a", "target": "b"}],
        }

        from app.api import dashboards as dash_api
        from app.models.dashboard_schemas import AiWidgetRequest

        with patch.object(dash_api, "generate_workflow_dsl", AsyncMock(return_value=fake_dsl)):
            resp = await dash_api.ai_generate_widget(
                body=AiWidgetRequest(prompt="show signups by month"),
                current_user=user,
                db=db,
            )
        self.assertEqual(resp.chart_type, "pie")
```

(Add `from unittest.mock import patch` to the test file imports.)

- [ ] **Step 4: Run tests**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_dashboards_api.py -v`
Expected: PASS

- [ ] **Step 5: Lint & commit**

```bash
cd backend && uv run ruff check app/api/dashboards.py && uv run ruff format app/api/dashboards.py tests/test_dashboards_api.py
git add backend/app/api/dashboards.py backend/tests/test_dashboards_api.py
git commit -m "feat(dashboards): add AI single-widget generation endpoint"
```

---

### Task 10: Full backend suite gate

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./run_tests.sh`
Expected: all pass (a single pre-existing OTel flake is acceptable per project memory; nothing new failing).

- [ ] **Step 2: Ruff format check**

Run: `cd backend && uv run ruff format --check . && uv run ruff check .`
Expected: clean.

- [ ] **Step 3: Commit any format-only diffs** (if produced).

---

## Phase D — Frontend

Frontend has no automated test harness (per project memory `feedback_no_frontend_ui_tests`). Verify every frontend task with:
`cd frontend && bun run lint && bun run typecheck`

### Task 11: Types + API client

**Files:**
- Create: `frontend/src/types/dashboard.ts`
- Create: `frontend/src/services/dashboardApi.ts`

- [ ] **Step 1: Write `dashboard.ts`**

```typescript
export interface ChartSeries {
  name: string;
  data: number[];
}

export interface ChartPayload {
  type: "pie" | "bar" | "line" | "table" | "numeric";
  orientation?: "horizontal" | "vertical";
  labels?: string[];
  series?: ChartSeries[];
  columns?: string[];
  rows?: unknown[][];
  value?: number | string | null;
  unit?: string;
  decimals?: number;
  title?: string;
}

export interface WidgetLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardWidget {
  id: string;
  workflow_id: string;
  title: string;
  chart_type: ChartPayload["type"];
  layout: WidgetLayout;
  cache_ttl_seconds: number;
  position: number;
  updated_at: string;
}

export interface DashboardData {
  id: string;
  name: string;
  widgets: DashboardWidget[];
}

export interface WidgetDataResponse {
  widget_id: string;
  payload: ChartPayload | null;
  cached: boolean;
  computed_at: string | null;
  error?: string | null;
}

export interface WidgetCreateRequest {
  title: string;
  chart_type: ChartPayload["type"];
  layout: WidgetLayout;
  cache_ttl_seconds: number;
}

export interface WidgetUpdateRequest {
  title?: string;
  chart_type?: ChartPayload["type"];
  layout?: WidgetLayout;
  cache_ttl_seconds?: number;
}
```

- [ ] **Step 2: Write `dashboardApi.ts`** following the existing axios client pattern in `frontend/src/services/api.ts` (import the shared axios instance; check its export name first with `grep -n "export" frontend/src/services/api.ts | head`).

```typescript
import { apiClient } from "@/services/api"; // adjust import to the actual exported instance
import type {
  DashboardData,
  DashboardWidget,
  WidgetCreateRequest,
  WidgetDataResponse,
  WidgetUpdateRequest,
} from "@/types/dashboard";

export const dashboardApi = {
  async getDashboard(): Promise<DashboardData> {
    const { data } = await apiClient.get<DashboardData>("/api/dashboards");
    return data;
  },
  async createWidget(body: WidgetCreateRequest): Promise<DashboardWidget> {
    const { data } = await apiClient.post<DashboardWidget>("/api/dashboards/widgets", body);
    return data;
  },
  async updateWidget(id: string, body: WidgetUpdateRequest): Promise<DashboardWidget> {
    const { data } = await apiClient.patch<DashboardWidget>(`/api/dashboards/widgets/${id}`, body);
    return data;
  },
  async deleteWidget(id: string): Promise<void> {
    await apiClient.delete(`/api/dashboards/widgets/${id}`);
  },
  async getWidgetData(id: string, force = false): Promise<WidgetDataResponse> {
    const { data } = await apiClient.get<WidgetDataResponse>(
      `/api/dashboards/widgets/${id}/data`,
      { params: { force } },
    );
    return data;
  },
  async aiGenerateWidget(prompt: string): Promise<DashboardWidget> {
    const { data } = await apiClient.post<DashboardWidget>("/api/dashboards/widgets/ai-generate", {
      prompt,
    });
    return data;
  },
};
```

- [ ] **Step 3: Verify**

Run: `cd frontend && bun run typecheck`
Expected: no errors (fix the `apiClient` import name to match `api.ts`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/dashboard.ts frontend/src/services/dashboardApi.ts
git commit -m "feat(dashboards): add dashboard types and API client"
```

---

### Task 12: `chartOutput` canvas node

**Files:**
- Create: `frontend/src/components/Nodes/ChartOutputNode.vue`
- Modify: `frontend/src/types/workflow.ts` (add `"chartOutput"` to `NodeType`)
- Modify: node registry / Vue Flow node-type map + palette (locate first)

- [ ] **Step 1: Add to `NodeType` union** in `frontend/src/types/workflow.ts` (line ~125 list): add `  | "chartOutput"`.

- [ ] **Step 2: Locate the node registry/palette** the canvas uses to render node types and list them in the add menu.

Run: `cd frontend && grep -rln "StickyNoteNode\|jsonOutputMapper\|nodeTypes\b" src/components src/composables src/stores | head`

Identify (a) the Vue Flow `:node-types` map (where `BaseNode`/custom components register) and (b) the palette catalog array that lists draggable nodes with labels/icons/categories.

- [ ] **Step 3: Create `ChartOutputNode.vue`** modeled on `BaseNode.vue` (read it first). It shows the node title + selected chart type and exposes a config panel with: `chartType` select, `orientation` (when bar), `dataPath`, `labelField`, `valueField`, optional `series` list, `columns` (table), `unit`/`decimals` (numeric), `title`. The node `data` keys MUST match the backend contract from Task 1 (`chartType`, `orientation`, `dataPath`, `labelField`, `valueField`, `series`, `columns`, `unit`, `decimals`, `title`). Keep the file under 300 lines; if the config form is large, extract `ChartOutputConfigForm.vue`.

- [ ] **Step 4: Register** the component in the Vue Flow node-types map and add a palette entry (label "Chart Output", an appropriate lucide icon e.g. `BarChart3`, category "Output").

- [ ] **Step 5: Verify**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Nodes/ChartOutputNode.vue frontend/src/types/workflow.ts <registry/palette files>
git commit -m "feat(dashboards): add chartOutput canvas node"
```

---

### Task 13: ChartRenderer (payload → apexcharts/table/numeric)

**Files:**
- Create: `frontend/src/components/Dashboards/ChartRenderer.vue`

Read `frontend/src/components/Analytics/AnalyticsDashboard.vue` first to copy the `apexchart` usage pattern (component registration, `:options`/`:series` props).

- [ ] **Step 1: Implement `ChartRenderer.vue`** — a single prop `payload: ChartPayload`. Branch on `payload.type`:
  - `pie`: `<apexchart type="pie" :series="payload.series?.[0]?.data ?? []" :options="{ labels: payload.labels }" />`
  - `bar`: `type="bar"`, `:series="payload.series"`, options `{ xaxis: { categories: payload.labels }, plotOptions: { bar: { horizontal: payload.orientation === 'horizontal' } } }`
  - `line`: `type="line"`, `:series="payload.series"`, options `{ xaxis: { categories: payload.labels } }`
  - `numeric`: render a large number `payload.value` (formatted to `payload.decimals` if set) + `payload.unit`
  - `table`: render an HTML `<table>` from `payload.columns` + `payload.rows`
  - empty/`null` payload: render a muted "No data" state.

- [ ] **Step 2: Verify**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Dashboards/ChartRenderer.vue
git commit -m "feat(dashboards): add ChartRenderer for chart payloads"
```

---

### Task 14: Widget card (async data load + title edit + refresh)

**Files:**
- Create: `frontend/src/components/Dashboards/DashboardWidgetCard.vue`

- [ ] **Step 1: Implement `DashboardWidgetCard.vue`** — props `widget: DashboardWidget`; emits `edit` (double-click → open editor), `delete`, `update` (after title/ttl change). On mount, it asynchronously calls `dashboardApi.getWidgetData(widget.id)` and stores `payload`/`loading`/`error` refs (each card loads independently → satisfies async-on-open). Renders `<ChartRenderer :payload="payload" />`. Header shows an inline-editable title (calls `dashboardApi.updateWidget(id, { title })` on blur), a manual **Refresh** button (calls `getWidgetData(id, true)`), and a kebab menu with Edit/Delete. Double-click on the card body emits `edit`.

- [ ] **Step 2: Verify**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Dashboards/DashboardWidgetCard.vue
git commit -m "feat(dashboards): add widget card with async data load and title edit"
```

---

### Task 15: Grid + dialogs + panel root

**Files:**
- Create: `frontend/src/components/Dashboards/DashboardGrid.vue`
- Create: `frontend/src/components/Dashboards/AddWidgetDialog.vue`
- Create: `frontend/src/components/Dashboards/AiWidgetDialog.vue`
- Create: `frontend/src/components/Dashboards/DashboardsPanel.vue`

- [ ] **Step 1: Choose the grid library.** Prefer `grid-layout-plus` (Vue 3, maintained). Verify Vue 3 + strict-mode compatibility and bundle size first:

Run: `cd frontend && bun add grid-layout-plus`

If it does not type-check cleanly under strict mode, fall back to a CSS-grid + pointer-drag implementation in `DashboardGrid.vue` (12 columns; persist `{x,y,w,h}`).

- [ ] **Step 2: Implement `DashboardGrid.vue`** — props `widgets: DashboardWidget[]`, `editMode: boolean`. Renders the 12-column grid; each cell hosts a `DashboardWidgetCard`. In edit mode, drag/resize is enabled; on layout change it emits `layout-change` with `{ id, layout }` per moved widget (debounced), which the parent persists via `dashboardApi.updateWidget`.

- [ ] **Step 3: Implement `AddWidgetDialog.vue`** — collects `title` + `chart_type`, emits `create` with `WidgetCreateRequest` (default layout `{x:0,y:0,w:4,h:4}`, ttl 300).

- [ ] **Step 4: Implement `AiWidgetDialog.vue`** — a prompt textarea; emits `generate` with the prompt string; shows a loading state while `aiGenerateWidget` runs.

- [ ] **Step 5: Implement `DashboardsPanel.vue`** — the tab root. On mount calls `dashboardApi.getDashboard()`; holds `widgets` ref. Toolbar: **Edit mode** toggle, **Add widget** (opens AddWidgetDialog → `createWidget` → push to grid → open editor), **AI** (opens AiWidgetDialog → `aiGenerateWidget` → push to grid), **Refresh all**. Handles `edit` from a card by navigating to the editor route for `widget.workflow_id` (use `router.push({ name: "editor", params: { id: workflowId } })`), `delete` via `deleteWidget`, and `layout-change` via `updateWidget`.

- [ ] **Step 6: Verify**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Dashboards/ frontend/package.json frontend/bun.lock
git commit -m "feat(dashboards): add grid, dialogs, and dashboards panel"
```

---

### Task 16: Wire the `dashboard` tab into DashboardView

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`

- [ ] **Step 1: Extend `TabKey`** (line ~105) with `"dashboard"`, and add `"dashboard"` to the `validTabs` set (line ~101).

- [ ] **Step 2: Import and render the panel** — add `import DashboardsPanel from "@/components/Dashboards/DashboardsPanel.vue";` to the imports block, and add a render branch alongside the others (near the `analytics` branch ~line 1977):

```vue
<DashboardsPanel v-else-if="activeTab === 'dashboard'" />
```

- [ ] **Step 3: Add the sidebar nav entry** for the new tab (follow the existing pattern that renders the `analytics` tab button — same icon/label structure; label "Dashboard", a lucide icon e.g. `LayoutDashboard`).

- [ ] **Step 4: Verify**

Run: `cd frontend && bun run lint && bun run typecheck && bun run build`
Expected: lint/typecheck clean; production build succeeds.

- [ ] **Step 5: Manual smoke test** (per project: verify via manual check, no UI tests). Start the app (`./run.sh`), open the **Dashboard** tab, Add a widget, confirm the editor opens with `textInput → chartOutput`, build a trivial chart, return to the dashboard, confirm the widget renders and Refresh works.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/DashboardView.vue
git commit -m "feat(dashboards): add Dashboard tab to DashboardView"
```

---

### Task 17: Documentation

**Files:**
- Docs site (heymweb) via the `heym-documentation` skill.

- [ ] **Step 1: Invoke the `heym-documentation` skill** to add a "Dashboards" docs page covering: creating a dashboard widget, building the widget workflow with the `chartOutput` node, chart types, the cache TTL, manual refresh, and AI widget generation. This is a medium/large feature (new UI + node type + APIs), so docs are required per AGENTS.md.

- [ ] **Step 2: Commit** the doc changes per that skill's flow.

---

### Task 18: Final gate

- [ ] **Step 1: Run `./check.sh`** from repo root:

Run: `cd /Users/mbakgun/Projects/heym/heymrun && SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./check.sh`
Expected: backend ruff format + lint + tests pass; frontend lint + typecheck pass. Commit any format-only diffs.

- [ ] **Step 2: Do NOT push.** Per project policy, never push without explicit user approval. Report completion and await the user's go-ahead.

---

## Self-Review Notes

- **Spec coverage:** tab/nav (Task 16), single global dashboard auto-create (Task 7), drag-resize 12-col grid (Task 15), widget↔hidden-workflow (Tasks 4–7), `chartOutput` node + chart types (Tasks 1–3, 12–13), async per-widget load (Task 14), PostgreSQL 1:1 TTL cache + force refresh (Tasks 5, 8, 14), editable titles (Tasks 7, 14), AI single-widget generation (Task 9, 15), backend tests (Tasks 1–10), docs (Task 17), `check.sh` gate (Task 18). All spec sections map to tasks.
- **Type consistency:** node `data` keys (`chartType`, `orientation`, `dataPath`, `labelField`, `valueField`, `series`, `columns`, `unit`, `decimals`, `title`) are identical across `build_chart_payload` (Task 1), the executor branch (Task 2), the DSL prompt (Task 3), and the frontend node + types (Tasks 11–12). `ChartPayload` keys match between backend output and `frontend/src/types/dashboard.ts`. `compute_widget_data(db, widget, user, force)` signature matches its call site in Task 7.
- **Known follow-ups requiring in-repo verification during execution (not placeholders, but lookups):** exact axios export name in `services/api.ts` (Task 11), the node registry/palette file locations (Task 12), and the real DSL generator callable/signature (Task 9). Each task states the exact `grep` to resolve these before writing code.
