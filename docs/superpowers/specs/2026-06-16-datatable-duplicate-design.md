# DataTable Duplicate — Design

Date: 2026-06-16

## Goal

Let users one-click duplicate a DataTable from the DataTable list. A copy icon
appears in the card hover toolbar (alongside rename and delete). Clicking it
creates a full copy — schema plus all rows — owned by the current user.

## Behavior

- Hover toolbar on each DataTable card gains a `Copy` icon between the rename
  pencil and the delete trash.
- Clicking it calls a new clone endpoint and reloads the list.
- The copy is named `"<name> (Copy)"`, then `"<name> (Copy 2)"`, … if names
  collide within the owner's tables (matches `clone_vector_store`).
- Copy contains: all columns (verbatim) and all rows (verbatim). Shares are NOT
  copied — the copy is private to the current user.

## Backend

`backend/app/api/data_tables.py`

- New `POST /data-tables/{table_id}/clone` → `DataTableResponse` (201).
- Access checked with existing `_get_data_table_with_access`, so a user may also
  duplicate a table shared with them; the copy becomes theirs.
- Unique-name resolution loop against `DataTable.owner_id == current_user.id`,
  honoring the `uq_data_table_name` constraint.
- New `DataTable`: `columns` copied verbatim (column ids/names preserved — rows
  are keyed by column **name**, so this is safe). All `DataTableRow`s copied with
  fresh ids, `data` verbatim, `created_by`/`updated_by` = current user.
- Response includes the real `row_count`.

## Frontend

- `frontend/src/services/api.ts`: add `dataTablesApi.clone(id)` →
  `POST /data-tables/{id}/clone`.
- `frontend/src/components/DataTable/DataTablePanel.vue`: import lucide `Copy`,
  add a button to the hover toolbar with `@click.stop="handleDuplicate(table.id)"`,
  and a `handleDuplicate` function that calls the API, reloads tables, and sets
  `error` on failure.

## Tests

`backend/tests/` — new test covering: clone copies columns + rows; sequential
names `(Copy)` / `(Copy 2)`; shares not copied; 404 on inaccessible table.

## Out of scope (YAGNI)

- Bulk duplicate, duplicate-into-team, rename-on-duplicate dialog.
