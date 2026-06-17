# DataTable `count` Operation — Design

**Date:** 2026-06-16
**Status:** Approved

## Problem

To count rows matching a condition, users currently chain `getAll` → If/Else → Map in the
workflow canvas — two nodes of glue just to produce a number. We want a single first-class
`count` operation on the DataTable node that filters and counts DB-side.

## Goal

Add a `count` operation to the DataTable node that:
- Counts rows matching an optional filter, returning just an integer.
- Supports comparison operators (richer than `find`'s exact-match).
- Counts in the database (no row materialization).
- Requires only read access.

## Filter syntax (Mongo-style, type-aware)

`dataTableFilter` is a JSON object. A plain value means equality (backward-compatible with
`find`); an object value applies operators:

```json
{
  "status": "active",
  "age": { "$gt": 18 },
  "plan": { "$in": ["pro", "team"] },
  "name": { "$contains": "john" }
}
```

Supported operators:

| Operator | Meaning | SQL |
|----------|---------|-----|
| `$eq` (or plain value) | equals | `data ->> col = '<v>'` |
| `$ne` | not equals | `data ->> col != '<v>'` |
| `$gt` `$gte` `$lt` `$lte` | comparison | numeric columns cast `CAST(data ->> col AS NUMERIC)`, otherwise text compare |
| `$contains` | substring (case-insensitive) | `data ->> col ILIKE '%<v>%'` |
| `$in` | membership | `data ->> col IN (...)` |

- Numeric comparison casts to `NUMERIC` only when the column's declared `type == "number"`.
- Empty/omitted filter counts all rows.
- The filter template is run through `evaluate_message_template` first so `$`-expressions work,
  exactly like `find`/`upsert`.
- Unknown operators are ignored (no clause emitted).

## Implementation

### Backend — `backend/app/services/workflow_executor.py`

1. **New module-level helper** `_build_data_table_filter_clauses(filter_dict, columns) -> list`
   returns a list of SQLAlchemy `ColumnElement` clauses for the filter. Pure function (no DB),
   so it is unit-testable by compiling to SQL. Single home for the operator logic.
2. **New `elif operation == "count":` branch** in the `dataTable` node handler:
   - Resolve + parse `dataTableFilter` (same as `find`).
   - `query = db.query(DataTableRow).filter(DataTableRow.table_id == data_table_id)`
   - Apply `query.filter(*_build_data_table_filter_clauses(filter_dict, columns))`.
   - `total = query.count()` (emits `SELECT count(*)`, no ORM materialization).
   - Output: `{"success": True, "operation": "count", "count": int(total)}`.
3. **Read access:** add `"count"` to the read-only set in `_get_accessible_data_table`
   (`write_required = operation not in ("find", "getAll", "getById", "count")`).

### Frontend — `frontend/src/components/Panels/PropertiesPanel.vue`

- Add `{ value: "count", label: "Count Rows" }` to `dataTableOperationOptions`.
- Show the Filter field for `count` (add `'count'` to the filter `v-if` list) with a hint that
  comparison operators are supported. No row-data / sort / limit fields for count.

### DSL prompt — `backend/app/services/workflow_dsl_prompt.py`

- Add `count` to the `dataTableOperation` union and params notes (operator syntax).
- Add a row to the operations table.
- Add an example `count` node.
- Document the output ref `$nodeLabel.count`.

## Testing (backend pytest)

In `backend/tests/test_workflow_execution_api.py`:

1. **Operator clause builder** (`_build_data_table_filter_clauses`), compiling each clause to
   Postgres SQL and asserting structure:
   - plain value → equality
   - `$ne`, `$gt` on a number column (asserts `CAST(... AS NUMERIC)`), `$gt` on a string column
     (text compare, no cast), `$contains` → `ILIKE`, `$in` → `IN (...)`.
   - unknown operator → no clause.
2. **`count` via `execute_node`** with a fake session: returns `operation == "count"` and the
   count integer, both with no filter and with a filter (extend `_FakeQuery`/`_FakeDataTableSession`
   with a `count()` returning a preset).
3. **Read access:** `_get_accessible_data_table(..., "count")` with a read-only team share returns
   the table (no write required).

No frontend tests (repo convention — no Vitest harness).

## Docs

Update the DataTable node documentation via the `heym-documentation` skill: new `count` operation
and the operator filter reference.

## Out of scope

- `find`'s exact-match filter is unchanged (avoids executor/evaluator drift); `count` carries the
  richer operators standalone.
- No new sort/limit semantics for count.
