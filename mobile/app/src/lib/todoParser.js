/**
 * Pure GFM task-list markdown parsing/mutation for the To-Dos feature — one task per
 * line, no nesting, no store/network dependency. Same line shape desktop's own
 * `_get_project_todo_items()` regex uses (^- \[( |x)\]\s*(.*)$), so a todo.md edited
 * from either app stays byte-for-byte compatible with the other.
 */

const LINE_RE = /^- \[( |x)\]\s*(.*)$/;

// Every real (non-empty) task line in `content`, in file order, each tagged with its
// own line index (needed to unambiguously target one specific line later, since two
// tasks can share identical text) and done state.
export function parseTodos(content) {
  const lines = (content || '').split('\n');
  const items = [];
  lines.forEach((line, lineIndex) => {
    const m = LINE_RE.exec(line);
    if (m && m[2].trim()) {
      items.push({ lineIndex, text: m[2], done: m[1] === 'x' });
    }
  });
  return items;
}

// Locates the line to mutate: prefer the exact lineIndex a caller already has (the
// common, fast-path case), but fall back to the first line whose task text matches —
// the file may have changed underneath since that lineIndex was computed (e.g. a
// concurrent edit from desktop), so a stale index must never silently corrupt an
// unrelated line. Returns -1 if the task is simply gone (already handled some other
// way) — callers treat that as a no-op, not an error.
function findLineIndex(lines, lineIndex, text) {
  const direct = lines[lineIndex];
  if (direct !== undefined) {
    const m = LINE_RE.exec(direct);
    if (m && m[2] === text) return lineIndex;
  }
  return lines.findIndex(l => {
    const m = LINE_RE.exec(l);
    return m && m[2] === text;
  });
}

export function toggleLine(content, lineIndex, text) {
  const lines = (content || '').split('\n');
  const idx = findLineIndex(lines, lineIndex, text);
  if (idx === -1) return content;
  const m = LINE_RE.exec(lines[idx]);
  lines[idx] = `- [${m[1] === 'x' ? ' ' : 'x'}] ${m[2]}`;
  return lines.join('\n');
}

// Preserves whichever checkbox marker (m[1]) the line already had — never hardcode
// `[ ]` here. An early version of this on desktop did exactly that, silently
// un-completing a renamed done task; this must not repeat that bug.
export function renameLine(content, lineIndex, oldText, newText) {
  const lines = (content || '').split('\n');
  const idx = findLineIndex(lines, lineIndex, oldText);
  if (idx === -1) return content;
  const m = LINE_RE.exec(lines[idx]);
  lines[idx] = `- [${m[1]}] ${newText}`;
  return lines.join('\n');
}

export function appendLine(content, text) {
  const base = (content || '').replace(/\n+$/, '');
  return (base ? base + '\n' : '') + `- [ ] ${text}`;
}
