# DataTable AI-Assisted Schema Generation — Design

**Date:** 2026-06-14
**Status:** Approved (brainstorming complete)

## Summary

Let users build DataTable schemas from natural language or pasted JSON. The user
opens a dialog, describes the table (plain text or JSON — both fed to an LLM),
reviews the generated columns in a fully editable form, and saves to either
create a new table or append columns to an existing one. ESC closes the dialog.

## Goals

- One input box for both plain description and JSON; everything goes through the LLM (single code path).
- Two entry points: **create a new table** and **extend an existing table** with new columns.
- A review step with **full inline editing** of generated columns before saving.
- Server-side LLM call + validation, consistent with the existing `ai_assistant` /
  `AIExpressionBuilderModal` patterns. Backend pytest coverage.

## Non-Goals

- No frontend/UI tests (no Vitest harness in this repo).
- No row/data generation — schema/columns only.
- No schema replacement for existing tables (append-only; no data-loss risk).

## Column Model (existing, unchanged)

`DataTableColumn` (`frontend/src/types/dataTable.ts`):
`id`, `name`, `type ∈ {string, number, boolean, date, json}`, `required` (= "notEmpty"),
`defaultValue`, `unique`, `order`.

## Architecture

### 1. Backend — new endpoint

`POST /api/data-tables/generate-schema`

- **Request body** (`DataTableSchemaGenerateRequest`):
  - `credential_id: UUID`
  - `model: str`
  - `prompt: str`
  - `existing_columns: list[DataTableColumnSchema] | None`
- **Credential resolution**: reuse `get_credential_for_user` (owner or shared LLM
  credential), instantiate `LLMService` the same way `ai_assistant.py` does.
- **System prompt**: instruct the model to return **exactly one fenced ```json
  object**:
  ```json
  {
    "name": "string",
    "description": "string",
    "columns": [
      { "name": "string", "type": "string|number|boolean|date|json", "required": false, "unique": false, "defaultValue": null }
    ]
  }
  ```
  When `existing_columns` is provided, instruct the model to return **only new
  columns** (not duplicates of the existing ones) and that `name`/`description`
  will be ignored.
- **Server-side normalization** (do not trust raw LLM output):
  - Parse the fenced block (reuse the `_parse_json_object` helper style from `ai_assistant.py`).
  - Coerce unknown/invalid `type` values → `string`.
  - Drop columns with blank names.
  - Dedupe generated column names against `existing_columns` (case-insensitive).
  - Assign fresh `id` (uuid) and sequential `order`.
- **Response** (`DataTableSchemaSuggestionResponse`): `{ name, description, columns: DataTableColumnSchema[] }`.
- **Errors** (FastAPI `HTTPException`):
  - No usable LLM credential → `400`.
  - LLM output cannot be parsed into the expected shape → `422`.

### 2. Frontend — new `DataTableAISchemaDialog.vue`

One dialog with two phases.

- **Props**: `mode: "create" | "extend"`, `existingTable?: DataTable`.
- **Emits**: `created`, `updated`, `close`.
- **Input phase**:
  - LLM credential dropdown + model dropdown. Defaults mirror
    `AIExpressionBuilderModal.vue` exactly: `credentialsApi.listLLM()` → first
    credential; `credentialsApi.getModels()` → latest model.
  - Textarea: "Describe your table, or paste JSON".
  - **Generate** button → calls `dataTablesApi.generateSchema(...)`.
- **Review phase** — editable column rows (mini spreadsheet):
  - `name` input, `type` dropdown, `default` input, `unique` checkbox,
    `notEmpty` (= `required`) checkbox, delete-row button, **+ Add column** row.
  - *create mode*: editable **Name** and **Description** fields (AI-prefilled).
  - *extend mode*: existing columns rendered **read-only / greyed** above the new
    editable ones, for context.
  - **Back / Regenerate** and **Save**.
- **ESC** closes the dialog (same keydown handler approach as `AIExpressionBuilderModal.vue`).
- **Save**:
  - create mode → `dataTablesApi.create({ name, description, columns })`, emit `created`.
  - extend mode → `dataTablesApi.update(id, { columns: [...existing, ...new] })`, emit `updated`.

### 3. Wiring in `DataTablePanel.vue`

- Table-list header / New-table area: a **"Generate with AI ✨"** button opening
  the dialog in `create` mode.
- Inside an opened table, near the existing **Add Column** button: an **AI columns**
  button opening the dialog in `extend` mode (passes current table as `existingTable`).
- On `created` → reload tables / open the new table; on `updated` → refresh the
  selected table.

### 4. Types & API client

- `frontend/src/types/dataTable.ts`: add `DataTableSchemaSuggestion` (and a column
  input shape if needed).
- `frontend/src/services/api.ts`: add `dataTablesApi.generateSchema(payload)` →
  `POST /data-tables/generate-schema`.
- `backend/app/models/schemas.py`: add `DataTableSchemaGenerateRequest` and
  `DataTableSchemaSuggestionResponse` Pydantic models.

## Data Flow

1. User opens dialog (create or extend).
2. Picks credential + model, types a description or pastes JSON, clicks Generate.
3. Frontend `POST /data-tables/generate-schema` with prompt (+ existing columns in extend mode).
4. Backend calls the LLM, parses + normalizes, returns a suggestion.
5. User edits columns inline, optionally adds/deletes rows, edits name/description.
6. Save → create or update via existing `dataTablesApi` endpoints.

## Error Handling

- **Frontend**: typed catch around `generateSchema`; show inline error in the
  dialog (e.g. "Couldn't generate a schema — try rephrasing"). Save errors reuse
  the existing panel error surface.
- **Backend**: `HTTPException` only — `400` (no credential), `422` (unparseable
  output). Never leak raw LLM text on parse failure.

## Testing (backend pytest, per AGENTS.md)

Mock `LLMService`. Cases:
- Success: valid fenced JSON → normalized columns + name/description.
- Type normalization: invalid `type` coerced to `string`; blank-name columns dropped.
- Dedupe: generated columns matching existing names (case-insensitive) are removed in extend mode.
- ID/order assignment present and sequential.
- Missing/invalid LLM credential → `400`.
- Malformed LLM output (no fenced JSON / wrong shape) → `422`.

No frontend tests (verify via lint + typecheck + manual).

## Documentation

Medium feature (new UI + API) → update docs via the `heym-documentation` skill.

## Reference Files

- `frontend/src/components/DataTable/DataTablePanel.vue` — wiring, create dialog.
- `frontend/src/components/DataTable/DataTableColumnEditor.vue` — column field shapes.
- `frontend/src/components/ui/AIExpressionBuilderModal.vue` — credential/model picker + ESC handling pattern.
- `backend/app/api/data_tables.py` — create/update endpoints, column normalization.
- `backend/app/api/ai_assistant.py` — LLMService usage, `_parse_json_object`, credential resolution.
- `backend/app/services/llm_service.py` — `LLMService.execute`.
