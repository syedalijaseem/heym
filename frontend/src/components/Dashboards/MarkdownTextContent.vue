<script setup lang="ts">
import { computed } from "vue";
import DOMPurify from "dompurify";
import { Check } from "lucide-vue-next";
import { marked } from "marked";

import { parseMarkdownBlocks } from "@/lib/markdownTaskList";

const INLINE_ALLOWED_TAGS = ["strong", "em", "u", "s", "code", "a", "br"];
const INLINE_ALLOWED_ATTR = ["href", "target", "rel"];

const props = defineProps<{
  text: string;
  interactive: boolean;
  saving?: boolean;
}>();

const emit = defineEmits<{
  (e: "toggle", lineIndex: number): void;
}>();

const blocks = computed(() => parseMarkdownBlocks(props.text));

function renderHtml(content: string): string {
  if (!content.trim()) return "";
  const html = marked(content, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html);
}

function renderInline(content: string): string {
  if (!content.trim()) return "";
  const html = marked.parseInline(content, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: INLINE_ALLOWED_TAGS,
    ALLOWED_ATTR: INLINE_ALLOWED_ATTR,
  });
}

function onToggle(lineIndex: number): void {
  if (!props.interactive || props.saving) return;
  emit("toggle", lineIndex);
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- Sanitized via DOMPurify in renderHtml/renderInline -->
  <div class="chart-markdown h-full overflow-auto break-words px-1 py-1 text-sm text-foreground">
    <template
      v-for="(block, blockIndex) in blocks"
      :key="blockIndex"
    >
      <div
        v-if="block.type === 'html' && block.content.trim()"
        v-html="renderHtml(block.content)"
      />
      <ul
        v-else-if="block.type === 'taskList'"
        class="task-list list-none space-y-1.5 pl-0"
      >
        <li
          v-for="item in block.items"
          :key="item.lineIndex"
          class="flex items-start gap-2.5 rounded-md px-1 py-0.5"
          :class="
            interactive && !saving
              ? 'cursor-pointer hover:bg-muted/50'
              : 'cursor-default opacity-90'
          "
          @click.stop="onToggle(item.lineIndex)"
        >
          <span
            class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border transition-colors"
            :class="
              item.checked
                ? 'border-primary bg-primary text-primary-foreground'
                : 'bg-background'
            "
            role="checkbox"
            :aria-checked="item.checked"
            :aria-disabled="!interactive || saving"
          >
            <Check
              v-if="item.checked"
              class="h-3 w-3"
              aria-hidden="true"
            />
          </span>
          <span
            class="min-w-0 flex-1 leading-snug text-foreground"
            v-html="renderInline(item.text)"
          />
        </li>
      </ul>
    </template>
  </div>
  <!-- eslint-enable vue/no-v-html -->
</template>

<style scoped>
.chart-markdown :deep(p) {
  margin: 0 0 0.5rem;
}

.chart-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.chart-markdown :deep(h1),
.chart-markdown :deep(h2),
.chart-markdown :deep(h3) {
  margin: 0.5rem 0 0.35rem;
  font-weight: 700;
  line-height: 1.2;
}

.chart-markdown :deep(h1) {
  font-size: 1.5rem;
}

.chart-markdown :deep(h2) {
  font-size: 1.25rem;
}

.chart-markdown :deep(h3) {
  font-size: 1.05rem;
}

.chart-markdown :deep(ul:not(.task-list)),
.chart-markdown :deep(ol) {
  margin: 0 0 0.5rem;
  padding-left: 1.25rem;
}

.chart-markdown :deep(ul:not(.task-list)) {
  list-style: disc;
}

.chart-markdown :deep(ol) {
  list-style: decimal;
}

.chart-markdown :deep(a) {
  color: rgb(37 99 235);
  text-decoration: underline;
}

.chart-markdown :deep(code) {
  border-radius: 0.25rem;
  background: rgb(0 0 0 / 0.08);
  padding: 0.1rem 0.3rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.85em;
}

.chart-markdown :deep(pre) {
  margin: 0 0 0.5rem;
  overflow-x: auto;
  border-radius: 0.375rem;
  background: rgb(0 0 0 / 0.06);
  padding: 0.5rem 0.75rem;
}

.chart-markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.chart-markdown :deep(strong) {
  font-weight: 700;
}

.chart-markdown :deep(em) {
  font-style: italic;
}

.chart-markdown :deep(blockquote) {
  margin: 0 0 0.5rem;
  border-left: 3px solid rgb(0 0 0 / 0.15);
  padding-left: 0.75rem;
  color: rgb(0 0 0 / 0.65);
}

.chart-markdown :deep(hr) {
  margin: 0.5rem 0;
  border: none;
  border-top: 1px solid rgb(0 0 0 / 0.12);
}

:global(.dark) .chart-markdown :deep(a) {
  color: rgb(96 165 250);
}

:global(.dark) .chart-markdown :deep(code),
:global(.dark) .chart-markdown :deep(pre) {
  background: rgb(255 255 255 / 0.08);
}

:global(.dark) .chart-markdown :deep(blockquote) {
  border-left-color: rgb(255 255 255 / 0.2);
  color: rgb(255 255 255 / 0.7);
}

:global(.dark) .chart-markdown :deep(hr) {
  border-top-color: rgb(255 255 255 / 0.12);
}
</style>
