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

When you only have example/sample data (no real source), produce these rows with a **Set** node using `$array(dict(...), dict(...))` — for example `$array(dict(month="Jan", revenue=120), dict(month="Feb", revenue=150))`. Do **not** use `${...}` or bare `{...}` object literals; Heym builds objects only with `dict(key=value)`.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Node identifier (camelCase) |
| `chartType` | string | `pie`, `bar`, `line`, `area`, `table`, `numeric`, `gauge`, `scatter`, `proportion`, or `barGauge` |
| `orientation` | string | `vertical` or `horizontal` (bar charts only) |
| `dataPath` | string | Dot path to the rows array inside the upstream output (e.g. `data` or `result.items`). Leave empty to auto-detect. |
| `labelField` | string | Row key used as the category label (pie/bar/line) |
| `valueField` | string | Row key used as the numeric value (pie/bar/line/numeric/gauge) |
| `series` | array | Optional multi-series definition `[{ "name": "Sent", "field": "sent" }]` for bar/line (overrides `valueField`) |
| `columns` | array | Optional column list for `table` (defaults to the keys of the first row) |
| `xField` / `yField` | string | Row keys for the X and Y numeric axes (scatter) |
| `min` / `max` | number | Numeric range for `gauge` (default `0` / `100`) |
| `unit` | string | Optional unit shown next to a `numeric` or `gauge` value |
| `title` | string | Optional chart title |

## Chart types

- **bar / line / area / pie** — categorical charts driven by `labelField` + `valueField` (or `series` for multi-series bar/line/area). `area` is a filled trend chart.
- **table** — raw rows rendered as a scrollable table using `columns`.
- **numeric** — a single KPI value from the first row, with an optional `unit`.
- **gauge** — a single value shown against a `min`–`max` range (e.g. a percentage). Uses `valueField`.
- **scatter** — X/Y points from `xField` and `yField` for correlation plots.
- **proportion** — a single horizontal bar split into shares with a percentage legend (e.g. a language breakdown). Uses `labelField` + `valueField`.
- **barGauge** — one horizontal gauge per row with a red→green gradient and a value (e.g. free disk space). Uses `labelField` + `valueField`, optional `unit` and `max` (defaults to the largest row value).

## How data is resolved

1. If `dataPath` is set, the node follows that dot path into the upstream output.
2. Otherwise it looks for an array: a top-level list, a `data` array, or the first list-valued field.
3. For `table`, each row becomes a table row using `columns` (or the first row's keys).
4. For `numeric` and `gauge`, the value comes from `valueField` on the first row (or the first numeric field).
5. For `scatter`, each row becomes an `[xField, yField]` point.

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

Gauge (single value vs. a range):

```json
{
  "type": "chartOutput",
  "data": {
    "label": "cpuGauge",
    "chartType": "gauge",
    "dataPath": "rows",
    "valueField": "value",
    "min": 0,
    "max": 100,
    "unit": "%"
  }
}
```

Scatter (X/Y points):

```json
{
  "type": "chartOutput",
  "data": {
    "label": "correlation",
    "chartType": "scatter",
    "dataPath": "rows",
    "xField": "x",
    "yField": "y"
  }
}
```

Proportion (one bar split by share + percentage legend):

```json
{
  "type": "chartOutput",
  "data": {
    "label": "languages",
    "chartType": "proportion",
    "dataPath": "rows",
    "labelField": "name",
    "valueField": "value",
    "title": "Most Used Languages"
  }
}
```

Area (filled multi-series trend):

```json
{
  "type": "chartOutput",
  "data": {
    "label": "memCpu",
    "chartType": "area",
    "dataPath": "rows",
    "labelField": "time",
    "series": [
      { "name": "Memory", "field": "memory" },
      { "name": "CPU", "field": "cpu" }
    ],
    "title": "Memory / CPU"
  }
}
```

Bar gauge (per-row gradient gauge with values):

```json
{
  "type": "chartOutput",
  "data": {
    "label": "freeDisk",
    "chartType": "barGauge",
    "dataPath": "rows",
    "labelField": "name",
    "valueField": "value",
    "unit": "GB",
    "title": "Free disk space"
  }
}
```

## Example AI prompts

When generating a widget with **AI**, prompts like these map cleanly to each type:

- **Bar** — "Show monthly revenue for the last 6 months as a vertical bar chart with example data."
- **Line** — "Plot daily active users over the last 14 days as a line chart."
- **Pie** — "Break down execution status (success, error, cancelled) as a pie chart."
- **Gauge** — "Show current CPU usage as a gauge from 0 to 100 percent."
- **Scatter** — "Plot request latency versus payload size as a scatter chart with example data."
- **Proportion** — "Show my most used languages as a proportion bar: Kotlin 49.64%, JavaScript 23.73%, TypeScript 11.64%, Java 8.92%, Python 6.06%. Use example data."
- **Area** — "Show memory and CPU usage over the last 24 hours as an area chart with two series. Use example data."
- **Bar gauge** — "Show free disk space per volume (sda1 to sda7) as a bar gauge in GB. Use example data."

## Related

- [Dashboard tab](../tabs/dashboard-tab.md) — build and arrange widgets
- [Output node](output-node.md) — terminal node for regular workflows
