"""GFM task list helpers for dashboard markdown text widgets."""

import re

TASK_ITEM_RE = re.compile(r"^(\s*)([-*+])\s+\[([ xX])\]\s+(.*)$")


def has_task_items(markdown: str) -> bool:
    """Return True when markdown contains at least one GFM task list line."""
    return any(TASK_ITEM_RE.match(line) for line in markdown.splitlines())


def parse_task_line_indices(markdown: str) -> list[int]:
    """Return 0-based line indices of GFM task list items in the markdown."""
    return [i for i, line in enumerate(markdown.splitlines()) if TASK_ITEM_RE.match(line)]


def toggle_task_item(markdown: str, line_index: int) -> str:
    """Flip `[ ]` ↔ `[x]` on the task list line at ``line_index``.

    Raises:
        ValueError: When the line index is out of range or not a task item.
    """
    lines = markdown.split("\n")
    if line_index < 0 or line_index >= len(lines):
        raise ValueError(f"Invalid line_index: {line_index}")
    match = TASK_ITEM_RE.match(lines[line_index])
    if match is None:
        raise ValueError(f"Line {line_index} is not a task list item")
    indent, bullet, check, rest = match.groups()
    new_check = " " if check.lower() == "x" else "x"
    lines[line_index] = f"{indent}{bullet} [{new_check}] {rest}"
    return "\n".join(lines)
