<script setup lang="ts">
import { computed } from "vue";

import type { ChartPayload } from "@/types/dashboard";

const props = defineProps<{
  payload: ChartPayload | null;
}>();

const isEmpty = computed((): boolean => {
  const p = props.payload;
  if (!p) return true;
  if (p.type === "table") return !p.rows || p.rows.length === 0;
  if (p.type === "numeric") return p.value === null || p.value === undefined;
  return !p.series || p.series.length === 0 || (p.labels?.length ?? 0) === 0;
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

const apexType = computed((): "pie" | "bar" | "line" => {
  const t = props.payload?.type;
  if (t === "pie") return "pie";
  if (t === "line") return "line";
  return "bar";
});

const apexSeries = computed((): number[] | { name: string; data: number[] }[] => {
  const p = props.payload;
  if (!p) return [];
  if (p.type === "pie") return p.series?.[0]?.data ?? [];
  return p.series ?? [];
});

const apexOptions = computed((): Record<string, unknown> => {
  const p = props.payload;
  if (!p) return {};
  const base: Record<string, unknown> = {
    chart: { toolbar: { show: false }, animations: { enabled: false } },
    title: p.title ? { text: p.title } : undefined,
  };
  if (p.type === "pie") {
    return { ...base, labels: p.labels ?? [] };
  }
  return {
    ...base,
    xaxis: { categories: p.labels ?? [] },
    plotOptions: { bar: { horizontal: p.type === "bar" && p.orientation === "horizontal" } },
  };
});
</script>

<template>
  <div class="h-full w-full">
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
      <div class="text-4xl font-semibold tabular-nums">
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
      class="overflow-auto"
    >
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b">
            <th
              v-for="col in payload.columns"
              :key="col"
              class="px-2 py-1 text-left font-medium"
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

    <apexchart
      v-else
      :type="apexType"
      height="100%"
      :options="apexOptions"
      :series="apexSeries"
    />
  </div>
</template>
