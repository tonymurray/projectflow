# Layout View — Design Options

## Goal

The goal of a new layout is to provide a more focused project view particularly for working on Claude Code /Other AI projects. 

The user wants to have easy access to (1) shortcuts to the code folder (2) The documentation related to the coding project particularly written in Markdown or html, and to be able to edit the documentation within the application (3) Key project resources and research

## Suggested layout

Column 1 is much like existing column 2 with launchers

Column 2 provides a wide screen viewing and editing area with Markdown viewer/editor (including project notes), HTML/PDF/Web viewer and the File viewer.

## Alternative Functionality

Column 1 would display selected launchers from the project settings, but also:

Automatically scan for new documentation (on opening and with a rescan button) - so if AI created an explaination document, it can be read in Project flow immediately (or after refresh)

The launchers would be automatically divided into three key sections (1) Documentation (2) Shortcuts to the folder (Console), and aliases (3) Research and resources - websites and key documents

To avoid flooding documentation section with irrelevant markdown files (such as readmes for every library in a node_modules or vendor folder) - documents (.md/html ) found in the folder can be hidden (so the config for the folder would get an 'include' documents (additionally from outside the folder), and exclude (inside folder mark some html/md files as hidden -- then added to the exclude list --- this might be done with an eye toggle in edit mode)

## **Markup Editor and Viewer** - Marktext editor

Explore the possibility of using the core functionality of the open source Editor Mark text (https://github.com/marktext/marktext)

The editor is a desktop program written (i think) in Python. The key interesting part for project flow would be the Markdown viewer / combined editor, then save. Can this functionality be abstracted from the code and add into Project flow? The viewer and editor are combined. Only when you click on a heading or paragraph can you choose to change for example from a heading to a paragraph. Otherwise the text is presented in very attractive format.

--------------------------------------------------------

Previous planning

## Terminology

Qt/PyQt has no standard term for switching between full-screen layout arrangements. Within ProjectFlow the word "mode" is already used for viewer tab switching (`switch_to_viewer_mode`), so the outer switch is best called a **layout mode** (or just **layout**). The two layouts would be:

- **Layout 1 — Standard** (current): Launchers | Viewer | Notes (3 columns)
- **Layout 2 — Focus** (new): Launchers (1/3) | Viewer + Notes (2/3)

A toggle button in the top-right of the title bar switches between them.

---

## Current Architecture Constraints

Key facts that shape all options below:

| Constraint | Detail |
|---|---|
| `self.notepad` (CleanTextEdit) | Single widget — can only have one Qt parent at a time |
| `self.webview` (QWebEngineView) | Singleton created in `__init__`; same constraint |
| Column 2 viewer switching | Manual show/hide of 8 containers in `column2_stack_layout` — no QStackedWidget |
| QSplitter | Holds the 3 column widgets; state persisted to settings |
| `setChildrenCollapsible(False)` | Currently prevents columns collapsing to zero width |

---

## Layout Options

### Option 1 — Splitter Preset Snap *(simplest)*

**What:** A button snaps the splitter to `[1, 2, 0]` proportions and sets `childrenCollapsible(True)` on the notes column only. No new containers.

**How it works:**
- Store the current splitter sizes before switching
- Set splitter sizes to e.g. `[300, 600, 0]`
- Restore on switch back

**Pros:** ~20 lines of code. Reversible/home/tony/OMV/syncthingeoghan/. No widget reparenting.

**Cons:** Notes panel disappears entirely — not accessible in Focus mode. The launcher/viewer behavior stays the same.

**Verdict:** Good as a quick collapse toggle but doesn't fulfil the "notes as a viewer tab" goal.

---

### Option 2 — Notes as Viewer Tab via Widget Reparenting *(recommended for phase 1)*

**What:** Add a Notes tab to the column 2 viewer. When switching to Focus layout, move `self.notepad` from `notepad_widget` into `column2_stack_layout` (a new `notes_container`), hide the right column, and adjust the splitter. Reverse on switch back.

**How it works:**
```
Standard layout:           Focus layout:
[Launchers | Viewer | Notes]   [Launchers | Viewer+Notes]
                                            ↑ Notes tab added here
```
- `notes_container` is a `QWidget` created once in `_build_time_viewer` equivalent for notes
- On switch to Focus: `notes_container.layout().addWidget(self.notepad)`, hide `notepad_widget`, set splitter `[1, 2, 0]`
- On switch to Standard: move `self.notepad` back to `notepad_layout`, show `notepad_widget`, restore splitter

**Pros:** Single source of truth for note content. Consistent UX — notes editing works the same in both layouts. Column 2 tab system already exists.

**Cons:** Reparenting a live `QWidget` is supported in Qt but the widget briefly flickers/hides during the move. Auto-save timing needs care (save before reparenting).

**Implementation notes:**
- Call `self.notepad.setParent(None)` then add to new layout — standard Qt reparenting pattern
- The archive bar buttons (`📥 Archive`, `📜 View`) should move with `self.notepad` or be duplicated in the container

---

### Option 3 — QStackedWidget Wrapping the Splitter

**What:** Replace the splitter entirely with a `QStackedWidget` holding two pages:
- Page 0: existing 3-column `QSplitter` (unmodified)
- Page 1: a new 2-column `QSplitter` with `self.notepad` and all viewer containers moved in

**How it works:**
```python
self.layout_stack = QStackedWidget()
self.layout_stack.addWidget(splitter_standard)   # page 0
self.layout_stack.addWidget(splitter_focus)       # page 1
self.layout_stack.setCurrentIndex(0)
```

**Pros:** Cleanest architectural separation. Each layout is fully independent. Easy to add a third layout later.

**Cons:** The singleton widgets (`self.notepad`, `self.webview`) can only be in one page at a time, so switching still requires reparenting them. More boilerplate to set up two full splitters.

**Verdict:** Best long-term architecture if more than 2 layouts are planned; more upfront cost for the same reparenting problem as Option 2.

---

### Option 4 — Floating/Detached Notes Panel

**What:** A button pops the notes panel out as a separate top-level window. The main window collapses to 2 columns.

**How it works:**
- `self.notepad.setParent(None)` → wrap in a `QDialog` or `QMainWindow` → `show()`
- Main splitter collapses to `[1, 2]`

**Pros:** Very simple. Notes and viewer both at full size. Good for multi-monitor use.

**Cons:** Different UX model from what was described. Window management becomes the user's problem.

---

### Option 5 — File-Synced Dual Notes Widgets

**What:** Create a second `CleanTextEdit` in the notes container inside column 2. Both editors point at the same file; auto-save on one triggers a reload in the other.

**How it works:**
- Both `QTextEdit` instances monitor the notes file
- On switch: show the column-2 notes widget, hide the right column
- Changes in either editor auto-save; the other reloads on file change

**Pros:** No reparenting. Both layouts can coexist simultaneously.

**Cons:** Brief sync lag (file round-trip). Risk of conflicting edits if both are visible. Doubles memory for note content.

---

## Behavior Changes in Focus Layout

In Focus layout, the interaction model inverts:

| Action | Standard layout | Focus layout |
|---|---|---|
| Click launcher (web URL) | Opens Firefox (external) | Opens in webview pane |
| Click launcher (image file) | Opens Gwenview (external) | Opens in image viewer pane |
| Click launcher (PDF) | Opens external PDF viewer | Opens in PDF viewer pane |
| 🌐 preview button | Opens in webview pane | Opens in Firefox (external) |
| 🖼️ preview button | Opens in image viewer | Opens in Gwenview (external) |

**Implementation approach:**
- Add `self.layout_mode` flag (`"standard"` / `"focus"`) set when the toggle button is clicked
- In `open_in_app()`: check `self.layout_mode` before deciding whether to launch external or route to `switch_to_viewer_mode()`
- Preview buttons (🌐/🖼️): built in `build_main_content` — pass mode-aware handler or check flag in the lambda

The flag must exist from the start of phase 1 even if phase 2 isn't implemented yet, so the architecture doesn't require rework.

---

## Recommended Approach

**Phase 1 — Layout switcher**
- Implement **Option 2** (Notes-as-viewer-tab via reparenting)
- Add `self.layout_mode = "standard"` flag on `__init__`
- Add toggle button (e.g. ⊞ or ▣) to the title bar right side
- Notes tab appears in column 2 tab row only in Focus layout
- Splitter saved/restored per layout mode

**Phase 2 — Behavior in Focus layout**
- Modify `open_in_app()` to route web/image/PDF to viewer when `layout_mode == "focus"`
- Swap preview button roles (🌐/🖼️ become "open externally")
- Consider showing a small indicator (e.g. coloured dot on the toggle button) when in Focus mode

---

## Open Questions for Implementation

1. **Toggle button icon/label** — icon only (⊞/▣/⇔), text ("Focus"), or tooltip only?
2. **Per-project persistence** — should the last-used layout be saved per project config, or globally in settings?
3. **Archive bar in Focus layout** — move archive buttons into the Notes viewer container, or drop them from Focus mode?
4. **Viewer tab behaviour** — in Focus layout, does clicking a launcher that can't be previewed (e.g. a folder) still open externally, or switch to the Folder viewer?
