# Chart Output

The **Chart Output** node is the terminal node of a [dashboard widget](../tabs/dashboard-tab.md) workflow. It takes the rows produced by the upstream nodes and turns them into a standardized chart payload that the dashboard renders.

## Overview

| Property | Value |
|----------|-------|
| Inputs | 1 |
| Outputs | 0 (terminal) |
| Output | Standardized chart payload |

Place this node **last** in a dashboard-widget workflow. The node before it should produce an array of row objects, for example:

```json
[
  { "month": "Jan", "revenue": 120 },
  { "month": "Feb", "revenue": 150 }
]
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Node identifier (camelCase) |
| `chartType` | string | `pie`, `bar`, `line`, `table`, or `numeric` |
| `orientation` | string | `vertical` or `horizontal` (bar charts only) |
| `dataPath` | string | Dot path to the rows array inside the upstream output (e.g. `data` or `result.items`). Leave empty to auto-detect. |
| `labelField` | string | Row key used as the category label (pie/bar/line) |
| `valueField` | string | Row key used as the numeric value (pie/bar/line/numeric) |
| `series` | array | Optional multi-series definition `[{ "name": "Sent", "field": "sent" }]` for bar/line (overrides `valueField`) |
| `columns` | array | Optional column list for `table` (defaults to the keys of the first row) |
| `unit` | string | Optional unit shown next to a `numeric` value |
| `title` | string | Optional chart title |

## How data is resolved

1. If `dataPath` is set, the node follows that dot path into the upstream output.
2. Otherwise it looks for an array: a top-level list, a `data` array, or the first list-valued field.
3. For `table`, each row becomes a table row using `columns` (or the first row's keys).
4. For `numeric`, the value comes from `valueField` on the first row (or the first numeric field).

## Example

```json
{
  "type": "chartOutput",
  "data": {
    "label": "revenueChart",
    "chartType": "bar",
    "orientation": "vertical",
    "dataPath": "data",
    "labelField": "month",
    "valueField": "revenue",
    "title": "Monthly revenue"
  }
}
```

## Related

- [Dashboard tab](../tabs/dashboard-tab.md) — build and arrange widgets
- [Output node](output-node.md) — terminal node for regular workflows
