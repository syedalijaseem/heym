import { onUnmounted, ref, watch, type Ref } from "vue";

function isFileDragEvent(event: DragEvent): boolean {
  return event.dataTransfer?.types.includes("Files") ?? false;
}

/** Tracks file drag anywhere in the Run panel so input fields can preview early. */
export function useRunPanelFileDrag(disabled: Ref<boolean>): {
  isActive: Ref<boolean>;
  reset: () => void;
  onDragEnter: (event: DragEvent) => void;
  onDragLeave: (event: DragEvent) => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
} {
  const isActive = ref(false);
  const dragCounter = ref(0);

  function reset(): void {
    isActive.value = false;
    dragCounter.value = 0;
  }

  function onDocumentDragEnd(): void {
    reset();
  }

  watch(isActive, (active) => {
    if (active) {
      document.addEventListener("dragend", onDocumentDragEnd, true);
    } else {
      document.removeEventListener("dragend", onDocumentDragEnd, true);
    }
  });

  onUnmounted(() => {
    document.removeEventListener("dragend", onDocumentDragEnd, true);
  });

  function onDragEnter(event: DragEvent): void {
    if (disabled.value || !isFileDragEvent(event)) return;
    event.preventDefault();
    dragCounter.value++;
    isActive.value = true;
  }

  function onDragLeave(event: DragEvent): void {
    if (disabled.value) return;
    event.preventDefault();

    const current = event.currentTarget as HTMLElement;
    const related = event.relatedTarget as Node | null;
    if (related && current.contains(related)) return;

    dragCounter.value--;
    if (dragCounter.value <= 0) {
      reset();
    }
  }

  function onDragOver(event: DragEvent): void {
    if (disabled.value || !isFileDragEvent(event)) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
    isActive.value = true;
  }

  /** Accept drop only to cancel browser default; file is handled on the input field. */
  function onDrop(event: DragEvent): void {
    event.preventDefault();
    reset();
  }

  return { isActive, reset, onDragEnter, onDragLeave, onDragOver, onDrop };
}
