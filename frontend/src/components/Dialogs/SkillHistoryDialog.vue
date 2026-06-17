<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  Edit,
  Eye,
  Loader2,
  RotateCcw,
  Sparkles,
} from "lucide-vue-next";
import axios from "axios";

import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import {
  canPreviewSkillFile,
  getSkillFileImageSrc,
  getSkillFileTextContent,
  isImageSkillFile,
  isSvgSkillFile,
  isTextSkillFile,
} from "@/lib/skillFilePreview";
import {
  buildSkillHistoryEntries,
  formatSkillTimeoutChange,
  getSkillHistorySummary,
  getSkillTimeoutSeconds,
  type SkillHistoryEntry,
} from "@/lib/skillHistoryFromVersions";
import { workflowApi } from "@/services/api";
import { useWorkflowStore } from "@/stores/workflow";
import type { AgentSkill, AgentSkillFile } from "@/types/workflow";

interface Props {
  open: boolean;
  workflowId: string;
  agentNodeId: string;
  skill: AgentSkill | null;
  skillIndex: number;
  aiEditDisabled?: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "edit-snapshot", snapshot: AgentSkill, skillIndex: number): void;
  (e: "revert-snapshot", snapshot: AgentSkill, skillIndex: number): void;
  (e: "fine-tune", snapshot: AgentSkill): void;
  (e: "expand-skill"): void;
}>();

const workflowStore = useWorkflowStore();
const entries = ref<SkillHistoryEntry[]>([]);
const loading = ref(false);
const error = ref("");
const expandedPreviewIds = ref<Set<string>>(new Set());
const expandedFileKeys = ref<Set<string>>(new Set());

const skillName = computed(() => props.skill?.name || "(unnamed)");

async function loadHistory(): Promise<void> {
  if (!props.workflowId || !props.agentNodeId || !props.skill) {
    entries.value = [];
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    const versions = await workflowApi.getVersions(props.workflowId);
    const currentWorkflow = workflowStore.currentWorkflow;
    const currentNodes = currentWorkflow?.nodes ?? workflowStore.nodes;
    const currentUpdatedAt = currentWorkflow?.updated_at ?? new Date().toISOString();
    entries.value = buildSkillHistoryEntries(
      versions,
      currentNodes,
      props.agentNodeId,
      props.skill.id,
      currentUpdatedAt,
    );
  } catch (err: unknown) {
    entries.value = [];
    if (axios.isAxiosError(err)) {
      error.value = err.response?.data?.detail || "Failed to load skill history";
    } else {
      error.value = "Failed to load skill history";
    }
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.open, props.workflowId, props.agentNodeId, props.skill?.id] as const,
  ([open]) => {
    if (open) {
      document.body.dataset.heymOverlayEscapeTrap = "true";
      expandedPreviewIds.value = new Set();
      expandedFileKeys.value = new Set();
      void loadHistory();
    } else {
      delete document.body.dataset.heymOverlayEscapeTrap;
    }
  },
);

onUnmounted(() => {
  delete document.body.dataset.heymOverlayEscapeTrap;
});

function handleDialogEscape(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !props.open) {
    return;
  }
  event.stopImmediatePropagation();
  event.preventDefault();
  closeDialog();
}

function closeDialog(): void {
  emit("update:open", false);
}

function togglePreview(versionId: string): void {
  const next = new Set(expandedPreviewIds.value);
  if (next.has(versionId)) {
    next.delete(versionId);
  } else {
    next.add(versionId);
  }
  expandedPreviewIds.value = next;
}

function isPreviewExpanded(versionId: string): boolean {
  return expandedPreviewIds.value.has(versionId);
}

function getFilePreviewKey(versionId: string, filePath: string): string {
  return `${versionId}::${filePath}`;
}

function isFilePreviewExpanded(versionId: string, filePath: string): boolean {
  return expandedFileKeys.value.has(getFilePreviewKey(versionId, filePath));
}

function toggleFilePreview(versionId: string, file: AgentSkillFile): void {
  if (!canPreviewSkillFile(file)) {
    return;
  }
  const key = getFilePreviewKey(versionId, file.path);
  const next = new Set(expandedFileKeys.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  expandedFileKeys.value = next;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function getVersionLabel(entry: SkillHistoryEntry): string {
  return entry.versionId === "current" ? "Current" : `Version ${entry.versionNumber}`;
}

function editSnapshot(entry: SkillHistoryEntry): void {
  if (props.skillIndex < 0) {
    return;
  }
  emit("edit-snapshot", entry.skill, props.skillIndex);
  emit("expand-skill");
  closeDialog();
}

function revertSnapshot(entry: SkillHistoryEntry): void {
  if (entry.versionId === "current" || props.skillIndex < 0) {
    return;
  }
  const label = getVersionLabel(entry);
  if (!confirm(`Restore this skill to ${label}? Unsaved workflow changes are kept.`)) {
    return;
  }
  emit("revert-snapshot", entry.skill, props.skillIndex);
  emit("expand-skill");
  closeDialog();
}

function fineTuneSnapshot(entry: SkillHistoryEntry): void {
  emit("fine-tune", entry.skill);
  closeDialog();
}

function getChangeBadgeClass(changeLabel: string): string {
  if (changeLabel === "Current") {
    return "bg-primary/10 text-primary";
  }
  if (changeLabel === "Added") {
    return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  }
  if (changeLabel === "Timeout" || changeLabel.includes("Timeout")) {
    return "bg-sky-500/10 text-sky-700 dark:text-sky-400";
  }
  return "bg-amber-500/10 text-amber-700 dark:text-amber-400";
}

function getTimeoutChangeDetail(entry: SkillHistoryEntry, index: number): string | null {
  if (entry.versionId === "current" || index <= 0) {
    return null;
  }
  const newerEntry = entries.value[index - 1];
  if (!newerEntry) {
    return null;
  }
  return formatSkillTimeoutChange(entry.skill, newerEntry.skill);
}
</script>

<template>
  <Dialog
    :open="open"
    :title="`Skill History: ${skillName}`"
    size="3xl"
    :close-on-escape="false"
    @escape="handleDialogEscape"
    @close="closeDialog"
  >
    <div class="space-y-4">
      <p class="text-xs text-muted-foreground">
        History reflects workflow Edit History (last 7 days). Restoring a version updates only this
        skill, not the entire workflow.
      </p>

      <div
        v-if="error"
        class="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-destructive text-sm"
      >
        <AlertCircle class="w-4 h-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <div
        v-if="loading"
        class="flex items-center justify-center py-12"
      >
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="entries.length === 0"
        class="flex flex-col items-center justify-center py-12 text-center text-muted-foreground"
      >
        <Clock class="w-8 h-8 mb-3 opacity-50" />
        <p class="text-sm">
          No history yet for this skill.
        </p>
        <p class="text-xs mt-1">
          Save workflow changes after editing the skill to create history entries.
        </p>
      </div>

      <div
        v-else
        class="space-y-3"
      >
        <div
          v-for="(entry, entryIndex) in entries"
          :key="entry.versionId"
          class="rounded-lg border bg-card"
        >
          <div class="flex flex-col items-center gap-1 p-3 text-center sm:flex-row sm:flex-wrap sm:justify-center sm:gap-2 sm:text-left">
            <span class="text-sm font-medium">{{ getVersionLabel(entry) }}</span>
            <span
              class="text-xs px-2 py-0.5 rounded-full font-medium"
              :class="getChangeBadgeClass(entry.changeLabel)"
            >
              {{ entry.changeLabel }}
            </span>
            <span
              v-if="getTimeoutChangeDetail(entry, entryIndex)"
              class="text-xs px-2 py-0.5 rounded-full font-medium bg-sky-500/10 text-sky-700 dark:text-sky-400"
            >
              Timeout {{ getTimeoutChangeDetail(entry, entryIndex) }}
            </span>
            <span class="text-xs text-muted-foreground">{{ formatDate(entry.createdAt) }}</span>
            <span class="text-xs text-muted-foreground sm:ml-auto">
              {{ getSkillHistorySummary(entry.skill) }}
            </span>
          </div>

          <div class="grid w-full grid-cols-4 gap-1.5 border-t border-border/60 bg-muted/10 p-1.5">
            <button
              type="button"
              class="flex h-7 w-full items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="Preview"
              aria-label="Preview"
              @click="togglePreview(entry.versionId)"
            >
              <component
                :is="isPreviewExpanded(entry.versionId) ? ChevronDown : Eye"
                class="w-3.5 h-3.5"
              />
            </button>
            <button
              type="button"
              class="flex h-7 w-full items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="Edit"
              aria-label="Edit"
              @click="editSnapshot(entry)"
            >
              <Edit class="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              class="flex h-7 w-full items-center justify-center rounded-md text-primary transition-colors hover:bg-primary/10 hover:text-primary disabled:pointer-events-none disabled:opacity-50"
              :disabled="aiEditDisabled"
              title="AI Fine-tune"
              aria-label="AI Fine-tune"
              @click="fineTuneSnapshot(entry)"
            >
              <Sparkles class="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              class="flex h-7 w-full items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
              :disabled="entry.versionId === 'current'"
              title="Revert"
              aria-label="Revert"
              @click="revertSnapshot(entry)"
            >
              <RotateCcw class="w-3.5 h-3.5" />
            </button>
          </div>

          <div
            v-if="isPreviewExpanded(entry.versionId)"
            class="border-t bg-muted/10 p-3 space-y-3"
          >
            <div>
              <div class="text-xs font-medium text-muted-foreground mb-1">
                Name
              </div>
              <div class="text-sm font-mono">
                {{ entry.skill.name || "(unnamed)" }}
              </div>
            </div>
            <div>
              <div class="text-xs font-medium text-muted-foreground mb-1">
                Timeout
              </div>
              <div class="text-sm font-mono">
                {{ getSkillTimeoutSeconds(entry.skill) }}s
              </div>
            </div>
            <div>
              <div class="text-xs font-medium text-muted-foreground mb-1">
                SKILL.md
              </div>
              <pre
                class="text-xs font-mono whitespace-pre-wrap break-words rounded border bg-background p-2 max-h-48 overflow-y-auto"
              >{{ entry.skill.content || "(empty)" }}</pre>
            </div>
            <div v-if="entry.skill.files?.length">
              <div class="text-xs font-medium text-muted-foreground mb-1">
                Files ({{ entry.skill.files.length }})
              </div>
              <ul class="space-y-1">
                <li
                  v-for="file in entry.skill.files"
                  :key="file.path"
                  class="rounded border bg-background overflow-hidden"
                >
                  <button
                    type="button"
                    class="flex w-full items-center gap-1.5 px-2 py-1.5 text-left text-xs font-mono transition-colors hover:bg-muted/40 disabled:cursor-default disabled:hover:bg-background"
                    :disabled="!canPreviewSkillFile(file)"
                    @click="toggleFilePreview(entry.versionId, file)"
                  >
                    <ChevronRight
                      v-if="canPreviewSkillFile(file) && !isFilePreviewExpanded(entry.versionId, file.path)"
                      class="w-3 h-3 shrink-0 text-muted-foreground"
                    />
                    <ChevronDown
                      v-else-if="canPreviewSkillFile(file)"
                      class="w-3 h-3 shrink-0 text-muted-foreground"
                    />
                    <span
                      v-else
                      class="w-3 shrink-0"
                    />
                    <span class="min-w-0 break-all">{{ file.path }}</span>
                  </button>

                  <div
                    v-if="isFilePreviewExpanded(entry.versionId, file.path)"
                    class="border-t bg-muted/10 p-2 space-y-2"
                  >
                    <template v-if="isSvgSkillFile(file)">
                      <div>
                        <div class="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">
                          Preview
                        </div>
                        <div class="rounded border bg-background p-3 flex items-center justify-center min-h-24">
                          <img
                            v-if="getSkillFileImageSrc(file)"
                            :src="getSkillFileImageSrc(file)"
                            :alt="file.path"
                            class="max-h-48 w-auto max-w-full object-contain"
                          >
                        </div>
                      </div>
                      <div>
                        <div class="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">
                          Source
                        </div>
                        <pre
                          class="text-xs font-mono whitespace-pre-wrap break-words rounded border bg-background p-2 max-h-48 overflow-y-auto"
                        >{{ getSkillFileTextContent(file) }}</pre>
                      </div>
                    </template>

                    <template v-else-if="isImageSkillFile(file)">
                      <img
                        v-if="getSkillFileImageSrc(file)"
                        :src="getSkillFileImageSrc(file)"
                        :alt="file.path"
                        class="max-h-56 w-auto max-w-full rounded border bg-background object-contain"
                      >
                    </template>

                    <template v-else-if="isTextSkillFile(file)">
                      <pre
                        class="text-xs font-mono whitespace-pre-wrap break-words rounded border bg-background p-2 max-h-56 overflow-y-auto"
                      >{{ getSkillFileTextContent(file) }}</pre>
                    </template>

                    <p
                      v-else
                      class="text-xs text-muted-foreground"
                    >
                      Binary file stored as base64. Preview is not available.
                    </p>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div class="flex justify-end pt-4 border-t">
        <Button
          variant="outline"
          @click="closeDialog"
        >
          Close
        </Button>
      </div>
    </div>
  </Dialog>
</template>
