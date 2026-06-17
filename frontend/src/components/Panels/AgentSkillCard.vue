<script setup lang="ts">
import {
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-vue-next";

import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import Label from "@/components/ui/Label.vue";
import Textarea from "@/components/ui/Textarea.vue";
import type { AgentSkill, AgentSkillFile } from "@/types/workflow";

interface Props {
  skill: AgentSkill;
  index: number;
  expanded: boolean;
  aiEditDisabled?: boolean;
  downloadLoading?: boolean;
}

defineProps<Props>();

const emit = defineEmits<{
  (e: "toggle-expand"): void;
  (e: "ai-edit"): void;
  (e: "download"): void;
  (e: "remove"): void;
  (e: "history"): void;
  (e: "update:name", value: string): void;
  (e: "update:timeout-seconds", value: number): void;
  (e: "update:content", value: string): void;
  (e: "update:file-content", fileIndex: number, value: string): void;
  (e: "remove-file", fileIndex: number): void;
}>();

function isTextSkillFile(file: AgentSkillFile): boolean {
  return !file.encoding || file.encoding === "text";
}

function isImageSkillFile(file: AgentSkillFile): boolean {
  return file.encoding === "base64" && (file.mimeType?.startsWith("image/") ?? false);
}

function getSkillFilePreviewSrc(file: AgentSkillFile): string {
  if (!isImageSkillFile(file) || !file.content) {
    return "";
  }
  const mimeType = file.mimeType || "image/png";
  return `data:${mimeType};base64,${file.content}`;
}
</script>

<template>
  <div class="rounded border p-3 space-y-2">
    <button
      type="button"
      class="flex w-full items-center gap-1.5 text-left text-sm font-medium hover:text-primary"
      :title="`Skill ${index + 1}: ${skill.name || '(unnamed)'}`"
      @click="emit('toggle-expand')"
    >
      <ChevronRight
        v-if="!expanded"
        class="w-3.5 h-3.5 shrink-0"
      />
      <ChevronDown
        v-else
        class="w-3.5 h-3.5 shrink-0"
      />
      <span class="break-words leading-tight">
        Skill {{ index + 1 }}: {{ skill.name || "(unnamed)" }}
      </span>
    </button>

    <div class="grid w-full grid-cols-4 gap-1.5 rounded-lg border border-border/60 bg-muted/10 p-1.5">
      <button
        type="button"
        class="flex h-7 w-full items-center justify-center rounded-md text-primary transition-colors hover:bg-primary/10 hover:text-primary disabled:pointer-events-none disabled:opacity-50"
        :disabled="aiEditDisabled"
        title="Edit with AI"
        aria-label="Edit with AI"
        @click="emit('ai-edit')"
      >
        <Sparkles class="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        class="flex h-7 w-full items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
        :disabled="downloadLoading"
        title="Download skill ZIP"
        aria-label="Download skill ZIP"
        @click="emit('download')"
      >
        <Loader2
          v-if="downloadLoading"
          class="w-3.5 h-3.5 animate-spin"
        />
        <Download
          v-else
          class="w-3.5 h-3.5"
        />
      </button>
      <button
        type="button"
        class="flex h-7 w-full items-center justify-center rounded-md text-destructive transition-colors hover:bg-destructive/10 hover:text-destructive"
        title="Remove skill"
        aria-label="Remove skill"
        @click="emit('remove')"
      >
        <Trash2 class="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        class="flex h-7 w-full items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        title="Skill history"
        aria-label="Skill history"
        @click="emit('history')"
      >
        <Clock class="w-3.5 h-3.5" />
      </button>
    </div>

    <div
      v-if="expanded"
      class="space-y-2 pt-2 border-t"
    >
      <div>
        <Label class="text-xs">Name</Label>
        <Input
          :model-value="skill.name"
          placeholder="skill-name"
          @update:model-value="emit('update:name', $event)"
        />
      </div>
      <div>
        <Label class="text-xs">Timeout (seconds)</Label>
        <Input
          type="number"
          :model-value="String(skill.timeoutSeconds ?? 30)"
          min="1"
          max="3600"
          placeholder="30"
          @update:model-value="emit('update:timeout-seconds', parseInt($event, 10) || 30)"
        />
      </div>
      <div>
        <Label class="text-xs">SKILL.md Content</Label>
        <Textarea
          :model-value="skill.content"
          placeholder="---&#10;name: my-skill&#10;---&#10;&#10;Instructions..."
          :rows="6"
          class="font-mono text-xs"
          @update:model-value="emit('update:content', $event)"
        />
      </div>
      <div
        v-if="skill.files?.length"
        class="space-y-1"
      >
        <Label class="text-xs">Files ({{ skill.files.length }})</Label>
        <div
          v-for="(file, fileIndex) in skill.files"
          :key="fileIndex"
          class="rounded border bg-muted/20 p-2 min-w-0"
        >
          <div class="flex justify-between items-center gap-2 mb-1 min-w-0">
            <span
              class="text-xs font-mono min-w-0 flex-1 truncate"
              :title="file.path"
            >{{ file.path }}</span>
            <Button
              variant="ghost"
              size="sm"
              class="gap-1 shrink-0 text-destructive hover:text-destructive hover:bg-destructive/10"
              @click="emit('remove-file', fileIndex)"
            >
              <Trash2 class="w-3.5 h-3.5" />
              Remove
            </Button>
          </div>
          <div
            v-if="isImageSkillFile(file)"
            class="space-y-2"
          >
            <img
              v-if="getSkillFilePreviewSrc(file)"
              :src="getSkillFilePreviewSrc(file)"
              :alt="file.path"
              class="max-h-56 w-auto max-w-full rounded border bg-background object-contain"
            >
            <p class="text-xs text-muted-foreground">
              Image preview stored as base64 to keep workflow saves UTF-8 safe.
            </p>
          </div>
          <Textarea
            v-else-if="isTextSkillFile(file)"
            :model-value="file.content"
            :rows="4"
            class="font-mono text-xs"
            @update:model-value="emit('update:file-content', fileIndex, $event)"
          />
          <p
            v-else
            class="text-xs text-muted-foreground"
          >
            Binary file stored as base64. Editing is disabled in the workflow editor.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
