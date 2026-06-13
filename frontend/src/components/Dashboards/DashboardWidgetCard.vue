<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Loader2, Pencil, RefreshCw, Trash2 } from "lucide-vue-next";

import ChartRenderer from "@/components/Dashboards/ChartRenderer.vue";
import { dashboardApi } from "@/services/api";
import type { ChartPayload, DashboardWidget } from "@/types/dashboard";

const props = defineProps<{
  widget: DashboardWidget;
  editMode: boolean;
}>();

const emit = defineEmits<{
  (e: "edit", workflowId: string): void;
  (e: "delete", widgetId: string): void;
  (e: "title-change", payload: { id: string; title: string }): void;
}>();

const payload = ref<ChartPayload | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const editingTitle = ref(false);
const titleDraft = ref(props.widget.title);

async function loadData(force = false): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const response = await dashboardApi.getWidgetData(props.widget.id, force);
    payload.value = response.payload;
    error.value = response.error ?? null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load widget";
  } finally {
    loading.value = false;
  }
}

function commitTitle(): void {
  editingTitle.value = false;
  const next = titleDraft.value.trim();
  if (next && next !== props.widget.title) {
    emit("title-change", { id: props.widget.id, title: next });
  } else {
    titleDraft.value = props.widget.title;
  }
}

function onBodyDoubleClick(): void {
  emit("edit", props.widget.workflow_id);
}

onMounted(() => {
  void loadData();
});
</script>

<template>
  <div class="flex h-full flex-col rounded-lg border bg-card shadow-sm">
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <input
        v-if="editingTitle"
        v-model="titleDraft"
        class="w-full bg-transparent text-sm font-medium outline-none"
        autofocus
        @blur="commitTitle"
        @keyup.enter="commitTitle"
      >
      <button
        v-else
        class="truncate text-left text-sm font-medium hover:text-primary"
        :title="widget.title"
        @click="editingTitle = true"
      >
        {{ widget.title }}
      </button>

      <div class="flex shrink-0 items-center gap-1">
        <button
          class="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="Refresh"
          @click="loadData(true)"
        >
          <RefreshCw class="h-3.5 w-3.5" />
        </button>
        <button
          class="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="Edit workflow"
          @click="emit('edit', widget.workflow_id)"
        >
          <Pencil class="h-3.5 w-3.5" />
        </button>
        <button
          v-if="editMode"
          class="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          title="Delete"
          @click="emit('delete', widget.id)"
        >
          <Trash2 class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <div
      class="flex-1 overflow-hidden p-3"
      @dblclick="onBodyDoubleClick"
    >
      <div
        v-if="loading"
        class="flex h-full min-h-[120px] items-center justify-center text-muted-foreground"
      >
        <Loader2 class="h-5 w-5 animate-spin" />
      </div>
      <div
        v-else-if="error"
        class="flex h-full min-h-[120px] items-center justify-center px-2 text-center text-xs text-destructive"
      >
        {{ error }}
      </div>
      <ChartRenderer
        v-else
        :payload="payload"
      />
    </div>
  </div>
</template>
