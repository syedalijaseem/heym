const TASK_ITEM_RE = /^(\s*)([-*+])\s+\[([ xX])\]\s+(.*)$/;

export interface TaskListItem {
  lineIndex: number;
  checked: boolean;
  text: string;
}

export type MarkdownBlock =
  | { type: "html"; content: string }
  | { type: "taskList"; items: TaskListItem[] };

export function hasTaskItems(markdown: string): boolean {
  return markdown.split("\n").some((line) => TASK_ITEM_RE.test(line));
}

export function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.split("\n");
  const blocks: MarkdownBlock[] = [];
  let htmlLines: string[] = [];
  let taskItems: TaskListItem[] = [];

  const flushHtml = (): void => {
    if (htmlLines.length > 0) {
      blocks.push({ type: "html", content: htmlLines.join("\n") });
      htmlLines = [];
    }
  };

  const flushTaskList = (): void => {
    if (taskItems.length > 0) {
      blocks.push({ type: "taskList", items: [...taskItems] });
      taskItems = [];
    }
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const match = TASK_ITEM_RE.exec(line);
    if (match) {
      flushHtml();
      taskItems.push({
        lineIndex: index,
        checked: match[3]?.toLowerCase() === "x",
        text: match[4] ?? "",
      });
      continue;
    }
    if (line.trim() === "" && taskItems.length > 0) {
      flushTaskList();
      htmlLines.push(line);
      continue;
    }
    flushTaskList();
    htmlLines.push(line);
  }

  flushHtml();
  flushTaskList();
  return blocks;
}

export function toggleTaskItemLocal(markdown: string, lineIndex: number): string {
  const lines = markdown.split("\n");
  const line = lines[lineIndex];
  if (line === undefined) {
    throw new Error(`Invalid line_index: ${lineIndex}`);
  }
  const match = TASK_ITEM_RE.exec(line);
  if (!match) {
    throw new Error(`Line ${lineIndex} is not a task list item`);
  }
  const indent = match[1] ?? "";
  const bullet = match[2] ?? "-";
  const check = match[3] ?? " ";
  const rest = match[4] ?? "";
  const newCheck = check.toLowerCase() === "x" ? " " : "x";
  lines[lineIndex] = `${indent}${bullet} [${newCheck}] ${rest}`;
  return lines.join("\n");
}
