# Supabase

The **Supabase** node reads and mutates tables exposed by a Supabase project's PostgREST API. Use it when you want workflow access to SQL-backed app state without hand-writing HTTP requests.

## Overview

| Property | Value |
|----------|-------|
| Inputs | 1 |
| Outputs | 1 |
| Credential | Supabase |
| Output | `$nodeLabel.rows`, `$nodeLabel.count`, `$nodeLabel.success` |

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `credentialId` | UUID | Supabase credential from [Credentials](../tabs/credentials-tab.md) |
| `supabaseOperation` | string | Operation: `select`, `insert`, `update`, `upsert`, or `delete` |
| `supabaseSchema` | expression | Schema name. If blank, the node uses the credential's default schema, then `public`. |
| `supabaseTable` | expression | Simple table name to query or mutate. Put the schema in `supabaseSchema`, not here. |
| `supabaseSelectColumns` | expression | Comma-separated PostgREST select list for `select` (default `*`) |
| `supabaseFilter` | expression | JSON filter object. Supports exact matches plus operator objects and logical groups, e.g. `{"id":123}`, `{"created_at":{"gte":"2026-01-01"}}`, or `{"or":[{"status":"active"},{"score":{"gte":10}}]}` |
| `supabaseLimit` | string | Maximum rows to return for `select` (`0` = fetch all matching rows with server-side pagination, negative values fall back to `100`) |
| `supabaseOrderBy` | expression | Optional column to sort by for `select` |
| `supabaseAscending` | boolean | Sort ascending when `true`, descending when `false` |
| `supabaseRowsInputMode` | string | For `insert`/`upsert`: `raw` JSON array mode or `auto` to map the single upstream input automatically |
| `supabaseDataInputMode` | string | For `update`: `raw` JSON object mode or `auto` to map the single upstream input automatically |
| `supabaseIgnoredInputFields` | string | Optional comma-separated field names to omit while auto-mapping input data |
| `supabaseRows` | expression | JSON array of row objects for `insert` and `upsert` |
| `supabaseOnConflict` | expression | Optional comma-separated conflict target columns for `upsert`, for example `id` or `tenant_id,email` |
| `supabaseData` | expression | JSON object of updated column values for `update` |

## Credential Setup

Create a **Supabase** credential in the [Credentials tab](../tabs/credentials-tab.md) with:

1. Your **Project URL**, for example `https://your-project.supabase.co`
2. An **API key** with access to the tables this workflow should use
3. An optional **default schema** (defaults to `public`)

The node talks to the Supabase PostgREST endpoint at `/rest/v1/<table>`.
Use `supabaseTable` for the table only, such as `users` or `profiles`. Do not pass `schema.table`, `rpc/...`, or other API paths there.

When a valid Supabase credential is selected, the editor can discover exposed tables and table
columns directly from the PostgREST OpenAPI metadata. Use the **discovered tables** dropdown to
pick a table and the **column chips** under **Select Columns** to quickly build a select list.

## Operations

| Operation | Required Fields | Description |
|-----------|-----------------|-------------|
| `select` | `supabaseTable` | Read rows with optional exact-match filters, limit, and ordering |
| `insert` | `supabaseTable`, `supabaseRows` or auto-map input | Insert one or more rows |
| `update` | `supabaseTable`, `supabaseData` or auto-map input, `supabaseFilter` | Update rows matching the filter |
| `upsert` | `supabaseTable`, `supabaseRows` or auto-map input | Insert or merge rows using Supabase upsert semantics. Use `supabaseOnConflict` when you need an explicit conflict target. |
| `delete` | `supabaseTable`, `supabaseFilter` | Delete rows matching the filter |

## Filter Syntax

`supabaseFilter` compiles structured JSON into PostgREST query parameters.

- Exact match: `{"status":"active"}`
- Comparison: `{"created_at":{"gte":"2026-01-01"}}`
- Membership: `{"status":{"in":["active","paused"]}}`
- Pattern match: `{"email":{"ilike":"*@example.com"}}`
- Logical OR: `{"or":[{"status":"active"},{"score":{"gte":10}}]}`
- Logical AND: `{"and":[{"score":{"gte":10}},{"score":{"lt":100}}]}`

For multiple operators on the same field, prefer a logical group:

```json
{
  "and": [
    { "score": { "gte": 10 } },
    { "score": { "lt": 100 } }
  ]
}
```

## Pagination

`select` now performs true server-side pagination against PostgREST.

- `supabaseLimit: "0"` fetches all matching rows page by page
- `supabaseLimit` values above 1000 automatically fan out into multiple requests
- Results are merged back into one `.rows` array and `.count` stays the total matching row count

When reading large tables, set a stable `supabaseOrderBy` to keep page boundaries predictable.

## Auto-map Input

For `insert`, `upsert`, and `update`, switch the node to **Auto-map input** when the single
upstream node already outputs the shape you want to write.

- A single object becomes one row or one update payload
- An array of objects becomes many rows for `insert` / `upsert`
- An upstream object with a `rows` array reuses that array directly
- `supabaseIgnoredInputFields` lets you drop fields such as `id`, `created_at`, or `success`

## Output Reference

| Output field | Type | Description |
|-------------|------|-------------|
| `.rows` | array | Returned row objects |
| `.count` | number | Number of returned or affected rows |
| `.success` | boolean | Whether the operation succeeded |

## Example – Select Active Users

```json
{
  "type": "supabase",
  "data": {
    "label": "activeUsers",
    "credentialId": "supabase-credential-uuid",
    "supabaseOperation": "select",
    "supabaseSchema": "public",
    "supabaseTable": "users",
    "supabaseSelectColumns": "id,email,status",
    "supabaseFilter": "{\"status\":\"active\"}",
    "supabaseLimit": "100",
    "supabaseOrderBy": "created_at",
    "supabaseAscending": false
  }
}
```

Access output: `$activeUsers.rows`, `$activeUsers.rows[0].email`, `$activeUsers.count`.

## Example – Upsert a Profile Row

```json
{
  "type": "supabase",
  "data": {
    "label": "saveProfile",
    "credentialId": "supabase-credential-uuid",
    "supabaseOperation": "upsert",
    "supabaseSchema": "public",
    "supabaseTable": "profiles",
    "supabaseRows": "[{\"id\": \"$input.userId\", \"display_name\": \"$input.name\"}]",
    "supabaseOnConflict": "id"
  }
}
```

## Related

- [Node Types](../reference/node-types.md) – Overview of all node types
- [Credentials Tab](../tabs/credentials-tab.md) – Add Supabase credentials
- [Third-Party Integrations](../reference/integrations.md) – Integration credential setup
