# Heym Dashboards — Design Spec

**Date:** 2026-06-13
**Status:** Approved (pending spec review)
**Feature:** Grafana-style user-built dashboards in heymrun, where each widget is rendered from the output of a hidden Heym workflow.

## Summary

Add a new **Dashboards** feature to heymrun. Users get a `/dashboard` tab presenting a drag-resizable grid of widgets. Each widget renders a chart (pie, bar h/v, line, table, numeric/KPI) whose data is produced by a dedicated hidden Heym workflow ending in a new `chartOutput` node. Widgets load asynchronously, their results are cached in PostgreSQL with a per-widget TTL, widget titles are editable, and an **AI button** can generate a single widget (workflow + chart) from a natural-language prompt.

This is distinct from the existing **Analytics** tab, which shows fixed workflow-execution metrics. Dashboards are user-authored.

## Key Decisions (from brainstorming)

1. **Widget ↔ workflow:** Each widget owns its own hidden workflow. Double-click opens a canvas to edit it; the workflow's terminal node output becomes the chart data.
2. **Chart config location:** A dedicated `chartOutput` node defines chart type + field mapping. Presentation config lives in the node; `chart_type` is denormalized onto the widget for quick listing/rendering.
3. **Layout:** Grafana-style 12-column drag-resize grid with an edit-mode toggle.
4. **Caching:** Server-side, per-widget TTL, stored in **PostgreSQL** (Redis is optional/absent in many deploys — do not use it). Manual refresh override.
5. **AI button:** Generates a single widget (workflow DSL + chart config) from a prompt, reusing existing DSL-generation infra.
6. **Dashboard count:** One global dashboard per user for MVP; data model supports many for future expansion.
7. **Storage/canvas approach:** Reuse the real `Workflow` row + existing editor canvas; add a new `chartOutput` node type. Maximum reuse of executor, DSL, node types, and versioning.

## Architecture

### Navigation
- New `dashboard` tab in [DashboardView.vue](../../../frontend/src/views/DashboardView.vue): extend the `TabKey` union, add the sidebar entry and the `v-else-if="activeTab === 'dashboard'"` panel, mirroring the `analytics` tab. URL: `?tab=dashboard`.
- A new top-level panel component `frontend/src/components/Dashboards/DashboardsPanel.vue` (kept under 300 lines; split into subcomponents as needed: `DashboardGrid.vue`, `DashboardWidgetCard.vue`, `AddWidgetDialog.vue`, `AiWidgetDialog.vue`).
- One global dashboard per user, auto-created on first visit. UI shows a single dashboard; the table supports many.

### Drag-resize grid
- 12-column grid with an "Edit mode" toggle. In edit mode widgets can be moved and resized; layout `(x, y, w, h)` persists via `PATCH`.
- Use a Vue grid-layout library (e.g. `grid-layout-plus`, Vue 3 compatible) OR a lightweight custom CSS-grid + pointer-drag implementation. Implementation plan picks one; prefer an existing maintained library to avoid reinventing drag math, but verify bundle size and Vue 3 strict-mode compatibility first.

## Data Model

New tables (Alembic migration; UUID PKs; index FKs):

### `dashboards`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| owner_id | UUID FK → users | indexed |
| name | str | default "Dashboard" |
| created_at / updated_at | timestamptz | |

### `dashboard_widgets`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| dashboard_id | UUID FK → dashboards | indexed, cascade delete |
| workflow_id | UUID FK → workflows | the hidden widget workflow |
| title | str | user-editable; overrides display |
| chart_type | str | denormalized from `chartOutput` node (pie/bar/line/table/numeric) |
| layout | JSONB | `{x, y, w, h}` on the 12-col grid |
| cache_ttl_seconds | int | default e.g. 300 |
| position | int | ordering fallback |
| cached_payload | JSONB nullable | last ChartPayload |
| cached_at | timestamptz nullable | when cache computed |
| cached_workflow_version | str/int nullable | version the cache was computed against |
| created_at / updated_at | timestamptz | |

### `workflows` change
- Add a marker so widget workflows are excluded from the normal workflow list: a `kind` column (`'workflow'` default, `'dashboard_widget'` for widgets) or a boolean `is_dashboard_widget`. Update the workflows list query/filters to exclude widget workflows. Verify the exact `Workflow` model in `backend/app/db/models.py` and follow its existing column conventions.

## `chartOutput` Node (new node type)

- **Role:** terminal node of a widget workflow. Takes the upstream result and shapes it into a standardized chart payload.
- **Config:**
  - `chart_type`: `pie | bar | line | table | numeric`
  - `orientation`: `horizontal | vertical` (bar only)
  - field mapping: `label_field`, `value_field(s)` / series definitions
  - optional formatting: `unit`, `decimals`, `colors`, `title` override
- **Executor (backend):** add a dispatch branch in [workflow_executor.py](../../../backend/app/services/workflow_executor.py) (the `node_type == ...` chain around line 6546+). It reads upstream input (array of rows or object), applies the mapping, and emits a **ChartPayload**:
  ```json
  {
    "type": "bar",
    "labels": ["Jan", "Feb"],
    "series": [{ "name": "Revenue", "data": [120, 150] }],
    "columns": ["month", "revenue"],
    "rows": [["Jan", 120], ["Feb", 150]],
    "value": 270,
    "unit": "USD"
  }
  ```
  (Only the fields relevant to `type` are populated: `labels`/`series` for pie/bar/line, `columns`/`rows` for table, `value`/`unit` for numeric.)
- **Frontend:** `ChartOutputNode.vue` component + node-palette entry + registration in [workflow.ts](../../../frontend/src/types/workflow.ts) node types. A config panel for chart type, orientation, field mapping, formatting.
- **DSL:** extend [workflow_dsl_prompt.py](../../../backend/app/services/workflow_dsl_prompt.py) so the node is known to AI generation and templates.

## Data Flow / Rendering

1. `GET /dashboard` → dashboard + widget metadata (no chart data).
2. For each widget, the frontend asynchronously calls `GET /dashboard/widgets/{id}/data` → satisfies "load all graphs async on tab open".
3. Backend cache check (PostgreSQL): if `now - cached_at < cache_ttl_seconds` **and** `cached_workflow_version` matches the widget workflow's current version → return `cached_payload`. Otherwise run the widget workflow via `WorkflowExecutor`, extract the `chartOutput` node result, upsert `cached_payload`/`cached_at`/`cached_workflow_version`, and return.
4. Per-widget and global **Refresh** → `?force=true` bypasses cache and recomputes.
5. Frontend renders via **apexcharts** (already installed: `apexcharts` + `vue3-apexcharts`) for pie/bar/line/numeric, and an HTML table for `table`. `widget.title` overrides any node title.

## Widget Lifecycle

- **Add:** "Add widget" creates a hidden workflow (seeded with a `textInput`/trigger node + an empty `chartOutput` node) and a `dashboard_widgets` row, then opens the canvas to build it.
- **Edit (double-click):** opens the existing editor for that workflow in a dashboard context. On save, `chart_type` is denormalized back onto the widget; cache is invalidated by version change.
- **Title:** inline-editable on the widget card.
- **Grid:** drag/resize updates `layout`, persisted via `PATCH`.
- **Delete:** removes the widget row and its hidden workflow.

## AI Generation (single widget)

- An **AI button** opens a prompt dialog. It reuses the existing DSL-generation infra ([ai_assistant.py](../../../backend/app/api/ai_assistant.py), [workflow_dsl_prompt.py](../../../backend/app/services/workflow_dsl_prompt.py)).
- The prompt steers the model to produce a widget workflow DSL that **ends in a `chartOutput` node** with an appropriate chart type and field mapping for the requested metric.
- From the generated DSL, create the hidden workflow + widget row; it appears on the grid. One widget per generation.

## Caching (PostgreSQL — no Redis)

- Cache is stored on the `dashboard_widgets` row: `cached_payload` (JSONB), `cached_at`, `cached_workflow_version`. **One cache per widget (1:1)** — each recompute overwrites the previous payload in place; no cache history is kept.
- Freshness rule: serve cache when within TTL and version matches; otherwise recompute and upsert.
- `?force=true` always recomputes. Workflow edits change the version, auto-invalidating the cache.
- Redis is never used (it is optional/absent in deployments). This mirrors the existing PostgreSQL `WorkflowAnalyticsSnapshot` pattern.

## Backend API (`backend/app/api/dashboards.py`)

All endpoints owner-only, Pydantic request/response models, registered in the API router.

- `GET /dashboard` — dashboard + widgets metadata
- `POST /dashboard/widgets` — create widget (returns widget + `workflow_id`)
- `PATCH /dashboard/widgets/{id}` — update `title`, `layout`, `cache_ttl_seconds`, `chart_type`
- `DELETE /dashboard/widgets/{id}` — delete widget + its hidden workflow
- `GET /dashboard/widgets/{id}/data?force=` — render data (ChartPayload)
- `POST /dashboard/widgets/ai-generate` — prompt → widget

Pagination not required (small N per user).

## Testing

- **Backend pytest (required by AGENTS.md):**
  - `chartOutput` executor mapping for each chart type (pie/bar/line/table/numeric), including missing/empty data and bad mappings.
  - Dashboard auto-create + CRUD on widgets.
  - `…/data` cache behavior: miss → compute + store; hit within TTL → no recompute; version mismatch → recompute; `force=true` → recompute.
  - `ai-generate` with a mocked LLM producing a valid `chartOutput`-terminated DSL.
  - Access control: a user cannot read/modify another user's dashboard or widgets.
- **Frontend:** no automated tests (no Vitest harness). Verify with `bun run lint` + `bun run typecheck` + manual check. (See `feedback_no_frontend_ui_tests`.)
- Run `./check.sh` from repo root before push.

## Documentation

Medium/large feature (new UI, node type, APIs). Update docs via the `heym-documentation` skill as part of implementation.

## Out of Scope (YAGNI for MVP)

- Multiple dashboards per user (table supports it; UI deferred).
- Dashboard sharing / team visibility.
- Cross-widget variables / global dashboard filters.
- Real-time streaming widgets (polling/refresh only).
- AI generation of a whole multi-widget dashboard (single-widget only).
