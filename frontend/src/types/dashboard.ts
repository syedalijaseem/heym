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
