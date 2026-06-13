<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { useThemeStore } from "@/stores/theme";
import type { ChartPayload } from "@/types/dashboard";

const props = defineProps<{
  payload: ChartPayload | null;
}>();

const themeStore = useThemeStore();

// Palette for pie / proportion segments. All colors are mid/deep tones so a single
// white label color stays readable on every slice (no near-white colors here, and
// white is reserved for text — never used as a slice color).
const PROPORTION_COLORS = [
  "#8b5cf6",
  "#ca8a04",
  "#3b82f6",
  "#b45309",
  "#0ea5e9",
  "#16a34a",
  "#ef4444",
  "#ec4899",
  "#0d9488",
  "#ea580c",
];

interface ProportionSegment {
  label: string;
  pct: number;
  color: string;
}

const proportionSegments = computed((): ProportionSegment[] => {
  const p = props.payload;
  if (!p || p.type !== "proportion") return [];
  const data = (p.series?.[0]?.data ?? []) as number[];
  const labels = p.labels ?? [];
  const total = data.reduce((sum, v) => sum + (typeof v === "number" ? v : 0), 0);
  if (total <= 0) return [];
  return data.map((value, i) => ({
    label: String(labels[i] ?? `Series ${i + 1}`),
    pct: (Number(value) / total) * 100,
    color: PROPORTION_COLORS[i % PROPORTION_COLORS.length],
  }));
});

// ApexCharts pie/radialBar derive their radius from the resolved pixel height.
// height="100%" can resolve to 0 on first mount inside a flex card, leaving the
// chart invisible (the original pie-not-rendering bug). Track the real height and
// pass it as a number instead.
const containerRef = ref<HTMLElement | null>(null);
const chartHeight = ref(220);
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (!containerRef.value) return;
  resizeObserver = new ResizeObserver((entries) => {
    const h = entries[0]?.contentRect.height ?? 0;
    if (h > 0) chartHeight.value = Math.round(h);
  });
  resizeObserver.observe(containerRef.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
});

const isEmpty = computed((): boolean => {
  const p = props.payload;
  if (!p) return true;
  if (p.type === "table") return !p.rows || p.rows.length === 0;
  if (p.type === "numeric") return p.value === null || p.value === undefined;
  if (p.type === "gauge") return p.value === null || p.value === undefined;
  return !p.series || p.series.length === 0;
});

const numericValue = computed((): string => {
  const p = props.payload;
  if (!p || p.value === null || p.value === undefined) return "—";
  const raw = p.value;
  if (typeof raw === "number" && typeof p.decimals === "number") {
    return raw.toFixed(p.decimals);
  }
  return String(raw);
});

const apexType = computed((): "pie" | "bar" | "line" | "scatter" | "radialBar" => {
  const t = props.payload?.type;
  if (t === "pie") return "pie";
  if (t === "line") return "line";
  if (t === "scatter") return "scatter";
  if (t === "gauge") return "radialBar";
  return "bar";
});

// Gauge value as a 0-100 percentage of [min, max].
const gaugePercent = computed((): number => {
  const p = props.payload;
  if (!p || typeof p.value !== "number") return 0;
  const min = typeof p.min === "number" ? p.min : 0;
  const max = typeof p.max === "number" ? p.max : 100;
  if (max <= min) return 0;
  return Math.max(0, Math.min(100, ((p.value - min) / (max - min)) * 100));
});

const apexSeries = computed(() => {
  const p = props.payload;
  if (!p) return [];
  if (p.type === "pie") return p.series?.[0]?.data ?? [];
  if (p.type === "gauge") return [gaugePercent.value];
  return p.series ?? [];
});

const apexOptions = computed((): Record<string, unknown> => {
  const p = props.payload;
  if (!p) return {};
  const base: Record<string, unknown> = {
    chart: {
      toolbar: { show: false },
      animations: { enabled: false },
      background: "transparent",
    },
    theme: { mode: themeStore.isDark ? "dark" : "light" },
    grid: { borderColor: themeStore.isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)" },
  };
  // Only set `title` when there is one. Passing `title: undefined` makes ApexCharts
  // choke (the chart does not render) — this is why title-less pie charts were blank.
  if (p.title) {
    base.title = { text: p.title };
  }

  if (p.type === "pie") {
    return {
      ...base,
      labels: p.labels ?? [],
      colors: PROPORTION_COLORS,
      legend: {
        position: "bottom",
        labels: { colors: themeStore.isDark ? "#e2e8f0" : "#0f172a" },
      },
      // Slice gaps match the card background so slices read cleanly in dark mode.
      stroke: { colors: [themeStore.isDark ? "#0b1220" : "#ffffff"], width: 2 },
      dataLabels: { style: { colors: ["#ffffff"] }, dropShadow: { enabled: false } },
      tooltip: { theme: themeStore.isDark ? "dark" : "light", fillSeriesColor: false },
    };
  }

  if (p.type === "gauge") {
    const raw = typeof p.value === "number" ? p.value : 0;
    const unit = p.unit ?? "";
    // Scale the center value with the chart size so it fits the hollow at any
    // widget size (a fixed size overflows small gauges).
    const valueFontPx = Math.max(13, Math.min(34, Math.round(chartHeight.value * 0.13)));
    const nameFontPx = Math.max(9, Math.min(15, Math.round(chartHeight.value * 0.06)));
    return {
      ...base,
      plotOptions: {
        radialBar: {
          hollow: { size: "58%" },
          dataLabels: {
            name: { show: !!p.title, text: p.title ?? "", fontSize: `${nameFontPx}px` },
            value: {
              offsetY: p.title ? Math.round(valueFontPx * 0.48) : Math.round(valueFontPx * 0.38),
              fontSize: `${valueFontPx}px`,
              fontWeight: 600,
              color: themeStore.isDark ? "#f8fafc" : "#0f172a",
              formatter: (): string => `${raw}${unit}`,
            },
          },
        },
      },
      labels: [p.title ?? ""],
    };
  }

  if (p.type === "scatter") {
    return { ...base, xaxis: { type: "numeric" } };
  }

  return {
    ...base,
    xaxis: { categories: p.labels ?? [] },
    plotOptions: { bar: { horizontal: p.type === "bar" && p.orientation === "horizontal" } },
  };
});
</script>

<template>
  <div
    ref="containerRef"
    class="h-full w-full text-foreground"
  >
    <div
      v-if="isEmpty"
      class="flex h-full min-h-[120px] items-center justify-center text-sm text-muted-foreground"
    >
      No data
    </div>

    <div
      v-else-if="payload && payload.type === 'numeric'"
      class="flex h-full min-h-[120px] flex-col items-center justify-center"
    >
      <div class="text-4xl font-semibold tabular-nums text-foreground">
        {{ numericValue }}
      </div>
      <div
        v-if="payload.unit"
        class="mt-1 text-sm text-muted-foreground"
      >
        {{ payload.unit }}
      </div>
    </div>

    <div
      v-else-if="payload && payload.type === 'table'"
      class="h-full overflow-auto pb-3"
    >
      <table class="w-full text-sm text-foreground">
        <thead class="sticky top-0 bg-card">
          <tr class="border-b border-border">
            <th
              v-for="col in payload.columns"
              :key="col"
              class="px-2 py-1 text-left font-medium text-muted-foreground"
            >
              {{ col }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, rowIndex) in payload.rows"
            :key="rowIndex"
            class="border-b border-border/50"
          >
            <td
              v-for="(cell, cellIndex) in row"
              :key="cellIndex"
              class="px-2 py-1"
            >
              {{ cell }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-else-if="payload && payload.type === 'proportion'"
      class="flex h-full flex-col justify-center gap-4 px-1"
    >
      <div class="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        <div
          v-for="(seg, i) in proportionSegments"
          :key="i"
          class="h-full first:rounded-l-full last:rounded-r-full"
          :style="{ width: seg.pct + '%', backgroundColor: seg.color }"
          :title="`${seg.label} ${seg.pct.toFixed(2)}%`"
        />
      </div>
      <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm text-foreground">
        <div
          v-for="(seg, i) in proportionSegments"
          :key="i"
          class="flex items-center gap-2"
        >
          <span
            class="h-2.5 w-2.5 shrink-0 rounded-full"
            :style="{ backgroundColor: seg.color }"
          />
          <span class="truncate">{{ seg.label }} {{ seg.pct.toFixed(2) }}%</span>
        </div>
      </div>
    </div>

    <apexchart
      v-else
      :key="apexType"
      :type="apexType"
      :height="chartHeight"
      :options="apexOptions"
      :series="apexSeries"
    />
  </div>
</template>
