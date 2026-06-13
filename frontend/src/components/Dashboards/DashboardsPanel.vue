<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Loader2, Pencil, Plus, RefreshCw, Sparkles } from "lucide-vue-next";

import AddWidgetDialog from "@/components/Dashboards/AddWidgetDialog.vue";
import AiWidgetDialog from "@/components/Dashboards/AiWidgetDialog.vue";
import DashboardGrid from "@/components/Dashboards/DashboardGrid.vue";
import Button from "@/components/ui/Button.vue";
import { dashboardApi } from "@/services/api";
import type { DashboardWidget, WidgetCreateRequest, WidgetLayout } from "@/types/dashboard";

const router = useRouter();

const widgets = ref<DashboardWidget[]>([]);
const loading = ref(true);
const editMode = ref(false);
const showAdd = ref(false);
const showAi = ref(false);
const reloadKey = ref(0);

async function loadDashboard(): Promise<void> {
  loading.value = true;
  try {
    const data = await dashboardApi.getDashboard();
    widgets.value = data.widgets;
  } finally {
    loading.value = false;
  }
}

function openEditor(workflowId: string): void {
  void router.push({ name: "editor", params: { id: workflowId } });
}

async function handleCreate(body: WidgetCreateRequest): Promise<void> {
  showAdd.value = false;
  const widget = await dashboardApi.createWidget(body);
  widgets.value = [...widgets.value, widget];
  openEditor(widget.workflow_id);
}

async function handleGenerate(payload: {
  prompt: string;
  credentialId: string;
  model: string;
}): Promise<void> {
  try {
    const widget = await dashboardApi.aiGenerateWidget(
      payload.prompt,
      payload.credentialId,
      payload.model,
    );
    widgets.value = [...widgets.value, widget];
    showAi.value = false;
  } catch {
    // keep the dialog open on failure so the user can retry
  }
}

async function handleDelete(widgetId: string): Promise<void> {
  await dashboardApi.deleteWidget(widgetId);
  widgets.value = widgets.value.filter((w) => w.id !== widgetId);
}

async function handleTitleChange(payload: { id: string; title: string }): Promise<void> {
  const updated = await dashboardApi.updateWidget(payload.id, { title: payload.title });
  widgets.value = widgets.value.map((w) => (w.id === updated.id ? updated : w));
}

async function handleLayoutChange(payload: { id: string; layout: WidgetLayout }): Promise<void> {
  await dashboardApi.updateWidget(payload.id, { layout: payload.layout });
  widgets.value = widgets.value.map((w) =>
    w.id === payload.id ? { ...w, layout: payload.layout } : w,
  );
}

function refreshAll(): void {
  reloadKey.value += 1;
}

onMounted(() => {
  void loadDashboard();
});
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="flex items-center justify-between border-b px-4 py-3">
      <h1 class="text-lg font-semibold">
        Dashboard
      </h1>
      <div class="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          @click="refreshAll"
        >
          <RefreshCw class="mr-1 h-4 w-4" /> Refresh
        </Button>
        <Button
          :variant="editMode ? 'default' : 'ghost'"
          size="sm"
          @click="editMode = !editMode"
        >
          <Pencil class="mr-1 h-4 w-4" /> {{ editMode ? "Done" : "Edit" }}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          @click="showAi = true"
        >
          <Sparkles class="mr-1 h-4 w-4" /> AI
        </Button>
        <Button
          size="sm"
          @click="showAdd = true"
        >
          <Plus class="mr-1 h-4 w-4" /> Add widget
        </Button>
      </div>
    </div>

    <div class="flex-1 overflow-auto p-4">
      <div
        v-if="loading"
        class="flex h-full items-center justify-center text-muted-foreground"
      >
        <Loader2 class="h-6 w-6 animate-spin" />
      </div>
      <div
        v-else-if="widgets.length === 0"
        class="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground"
      >
        <p>No widgets yet.</p>
        <div class="flex gap-2">
          <Button
            size="sm"
            @click="showAdd = true"
          >
            <Plus class="mr-1 h-4 w-4" /> Add widget
          </Button>
          <Button
            variant="ghost"
            size="sm"
            @click="showAi = true"
          >
            <Sparkles class="mr-1 h-4 w-4" /> Generate with AI
          </Button>
        </div>
      </div>
      <DashboardGrid
        v-else
        :key="reloadKey"
        :widgets="widgets"
        :edit-mode="editMode"
        @edit="openEditor"
        @delete="handleDelete"
        @title-change="handleTitleChange"
        @layout-change="handleLayoutChange"
      />
    </div>

    <AddWidgetDialog
      v-if="showAdd"
      @close="showAdd = false"
      @create="handleCreate"
    />
    <AiWidgetDialog
      v-if="showAi"
      @close="showAi = false"
      @generate="handleGenerate"
    />
  </div>
</template>
