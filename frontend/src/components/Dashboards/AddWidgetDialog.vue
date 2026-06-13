<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { X } from "lucide-vue-next";

import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import type { ChartPayload, WidgetCreateRequest } from "@/types/dashboard";

const emit = defineEmits<{
  (e: "close"): void;
  (e: "create", body: WidgetCreateRequest): void;
}>();

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.stopPropagation();
    emit("close");
  }
}

// Capture phase so Escape reaches us before any ancestor keydown handler can
// stopPropagation (several exist in the dashboard view) and swallow the event.
onMounted(() => window.addEventListener("keydown", onKeydown, true));
onUnmounted(() => window.removeEventListener("keydown", onKeydown, true));

const title = ref("New widget");
const description = ref("");
const chartType = ref<ChartPayload["type"]>("bar");

const chartTypeOptions = [
  { value: "bar", label: "Bar" },
  { value: "line", label: "Line" },
  { value: "area", label: "Area" },
  { value: "pie", label: "Pie" },
  { value: "table", label: "Table" },
  { value: "numeric", label: "Numeric" },
  { value: "gauge", label: "Gauge" },
  { value: "scatter", label: "Scatter" },
  { value: "proportion", label: "Proportion" },
  { value: "barGauge", label: "Bar gauge" },
];

function submit(): void {
  emit("create", {
    title: title.value.trim() || "Untitled",
    description: description.value.trim() ? description.value.trim() : null,
    chart_type: chartType.value,
    layout: { x: 0, y: 0, w: 4, h: 4 },
    cache_ttl_seconds: 300,
  });
}
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="emit('close')"
    >
      <div class="w-full max-w-md rounded-lg border bg-card p-5 shadow-lg">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-base font-semibold">
            Add widget
          </h2>
          <button
            class="rounded p-1 text-muted-foreground hover:bg-accent"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="space-y-3">
          <div class="space-y-1">
            <label class="text-sm font-medium">Title</label>
            <Input v-model="title" />
          </div>
          <div class="space-y-1">
            <label class="text-sm font-medium">Description</label>
            <textarea
              v-model="description"
              rows="2"
              class="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
              placeholder="Optional. Shown on the canvas, not on the grid."
            />
          </div>
          <div class="space-y-1">
            <label class="text-sm font-medium">Chart type</label>
            <Select
              v-model="chartType"
              :options="chartTypeOptions"
            />
          </div>
        </div>

        <div class="mt-5 flex justify-end gap-2">
          <Button
            variant="ghost"
            @click="emit('close')"
          >
            Cancel
          </Button>
          <Button @click="submit">
            Create &amp; edit
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
