<script setup lang="ts">
import { ref } from "vue";
import { X } from "lucide-vue-next";

import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import type { DashboardWidget, WidgetUpdateRequest } from "@/types/dashboard";

const props = defineProps<{
  widget: DashboardWidget;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "save", payload: WidgetUpdateRequest): void;
}>();

const title = ref(props.widget.title);
const description = ref(props.widget.description ?? "");
const cacheTtlSeconds = ref(props.widget.cache_ttl_seconds);

function save(): void {
  emit("save", {
    title: title.value.trim() || "Untitled",
    description: description.value.trim() ? description.value.trim() : null,
    cache_ttl_seconds: Number(cacheTtlSeconds.value) || 0,
  });
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('close')"
  >
    <div class="w-full max-w-md rounded-lg border bg-card p-5 shadow-lg">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-base font-semibold">
          Widget settings
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
            placeholder="Shown on the canvas; not displayed on the dashboard grid."
          />
        </div>
        <div class="space-y-1">
          <label class="text-sm font-medium">Cache duration (seconds)</label>
          <Input
            v-model.number="cacheTtlSeconds"
            type="number"
            min="0"
          />
          <p class="text-xs text-muted-foreground">
            How long a computed result is reused before the workflow runs again. Use the widget's
            Refresh button to bypass the cache.
          </p>
        </div>
      </div>

      <div class="mt-5 flex justify-end gap-2">
        <Button
          variant="ghost"
          @click="emit('close')"
        >
          Cancel
        </Button>
        <Button @click="save">
          Save
        </Button>
      </div>
    </div>
  </div>
</template>
