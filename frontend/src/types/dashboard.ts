export interface ChartSeries {
  name: string;
  // number[] for pie/bar/line; [x, y] tuples for scatter
  data: number[] | (number | null)[][];
}

export interface ChartPayload {
  type: "pie" | "bar" | "line" | "table" | "numeric" | "gauge" | "scatter" | "proportion";
  orientation?: "horizontal" | "vertical";
  labels?: string[];
  series?: ChartSeries[];
  columns?: string[];
  rows?: unknown[][];
  value?: number | string | null;
  unit?: string;
  decimals?: number;
  min?: number;
  max?: number;
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
  description: string | null;
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
  description?: string | null;
  chart_type: ChartPayload["type"];
  layout: WidgetLayout;
  cache_ttl_seconds: number;
}

export interface WidgetUpdateRequest {
  title?: string;
  description?: string | null;
  chart_type?: ChartPayload["type"];
  layout?: WidgetLayout;
  cache_ttl_seconds?: number;
}
