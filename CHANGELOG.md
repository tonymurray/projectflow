# Changelog

All notable changes to ProjectFlow are documented here. This project doesn't use semantic versioning; entries are grouped by date.

## 2026-08-21

### Added
- **"Open in {file manager}" button** below the Quick File Browser Panel's file list (Focus layout), matching the same footer button the main Folder viewer already had.
- **Dolphin-style filter bar** for the folder browser: a "Filter..." text box (with built-in clear button) now sits below the file list on both the main Folder viewer and the Quick File Browser Panel, live-filtering entries by substring match against the filename as you type. Both boxes share state and stay in sync, and filtering re-renders from a cached directory scan rather than re-reading the disk on every keystroke. No "lock" toggle yet — typing a filter currently hides non-matching folders too, same as files.
- **Focus layout is now the default for new projects**: `create_default_project()` (first-run default project) and `create_folder_project_config()` ("Make Project") now write `"layout_mode": "focus"` into the project they create, instead of implicitly defaulting to Standard. Existing projects are unaffected unless their config is explicitly migrated.
- **Optional real-terminal Console backend, built on `ttyd`**: a new `console_backend` setting (Settings → Advanced) lets the embedded Console use a real interactive terminal — nano, vim, htop all work — instead of (or alongside) the existing Jupyter qtconsole. `"qtconsole"` stays the default; `"ttyd"` or `"auto"` (uses ttyd only if the binary is found on PATH) opt in. Renders via a persistent `QWebEngineView` loading a loopback-only `ttyd` process (`127.0.0.1`, random port, never exposed to the network), following the same process-reuse-across-refreshes and safe-webview-reparenting patterns already used for Notes. The Console tab now shows a "Terminal" label next to its icon, matching the other viewer tabs.
- Every viewer's minimum height was raised from 600px to 900px, so short-launcher-list projects give viewers (especially the terminal) more room by default.

### Fixed
- A `QWebEngineView` added to a `QVBoxLayout` without an explicit stretch factor only claims its own size hint rather than filling available space — on any project with a long enough launcher list to make the page taller than the viewport, this left the terminal a small box floating in the middle of the viewer column with blank space above and below. Fixed by adding the stretch factor (`addWidget(webview, 1)`), matching the fix the main web viewer already had for the same underlying issue.

## 2026-08-20

### Added
- **Dolphin-style icon grid view** for the folder browser: a ☰/⊞ toggle switches between the existing tree/details view and an icon grid, sharing the same navigation state and `.projectflow` project-folder badges. Choice persists via `folder_view_mode` setting.
- **"Open in Viewer" right-click actions** on folder-browser files: images/PDFs/Markdown/HTML now offer a direct "Open in Image/PDF/Markdown/Web Viewer" context-menu action, alongside the existing default "Open".
- **Quick File Browser Panel**: a collapsible file browser now lives at the top of the launcher column in Focus layout ("File Browser" toggle, styled like a category header). Expanding it replaces the launcher list with a compact tree/icon-grid browser (Up/Home/Refresh/view-toggle); clicking a file routes straight into the best built-in viewer (image/PDF/Markdown/Web) instead of navigating away, so you can browse and view side-by-side without leaving Focus mode. Right-click still offers the full standard context menu.
- **Group-by-Type is now remembered per project**: toggling "☰ Group" persists the choice into the project's own config, so it's restored exactly as left on the next open — rather than always resetting to the Focus-layout default.
- Folder icons across the whole app (tree, icon grid, launcher panel, toggle button) are now a consistent hand-drawn flat icon instead of the system theme's (which rendered yellow/manila on many setups).
- **Notes panel now uses the live Muya WYSIWYG editor** — the same one already used for standalone `.md` files — instead of the old `QTextEdit`-based rich-text editor and its regex HTML↔Markdown round-trip. Runs on its own persistent, independent `QWebEngineView` (`self.notes_webview`) so it can coexist with whatever's showing in the main viewer.
- **Typora-style "paper on page" theme** for both the Notes panel and the general markdown viewer: a paper-colored card with a drop shadow floating on a tinted page background, in both light (Documentary-theme colors) and dark (custom dark palette) variants. Paper opacity is 90% in Standard layout, 80% in Focus layout.
- Viewer column now holds a 600px minimum height, so projects with short launcher lists no longer squish the viewer — the page grows/scrolls instead.
- **Notes can now be pinned as a project's default viewer** (Focus layout): a 📌 button next to the archive controls sets `column2_default` to Notes, the same way PDF/Web/Image/Console/Folder/Time already could be — open the project and land straight on its notes.
- **Quick File Browser Panel's expanded/collapsed state is now remembered per project**, the same way `layout_mode`/`group_by_type` already are, instead of always starting collapsed.
- Icon-grid folder browser (both the main viewer and the launcher panel) now shows the full filename as a tooltip on every item, and grid cells are taller so more of a long name wraps into view before it needs to truncate at all.

### Changed
- The main viewer's "Folder" tab has been removed — folder browsing now happens via the new launcher-column Quick File Browser Panel (Focus layout) or as an internal fallback mode; its Home/Refresh/view-toggle controls moved to the new panel's toolbar.
- The ⏱ Kimai tab now shows "⏱ Time" instead of just the emoji.
- Header toolbar buttons (search box, Group/Add, viewer tabs, File Browser toggle) are a little shorter across the board.
- The Focus-layout toggle button's "return to Standard" label changed from "▣ Notes" to "▣ 3 Columns" — clearer now that Notes has its own place in both layouts.

### Fixed
- The Quick File Browser Panel's tree widget was only claiming ~50% of its available height due to an unweighted layout-stretch tie with a trailing spacer; it now correctly fills the full column.
- Several `hasattr(self, x) and self.x` truthiness checks around the new panel's widgets were silently false whenever the widget was empty, because PyQt's `QListWidget` implements `__len__` and Python falls back to it for boolean checks — replaced with identity checks (`getattr(self, x, None) is not None`).
- Fixed a crash ("wrapped C/C++ object of type QLabel has been deleted") that could occur when refreshing the UI (e.g. toggling Group-by-Type) after the Quick File Browser Panel had been expanded and then collapsed — its widget references weren't being reset to `None` when not rebuilt, leaving stale pointers to already-destroyed widgets.
- Fixed the paper theme showing a horizontal scrollbar at some widths (padding was being added outside the 90% width instead of included within it — `box-sizing: border-box` now).
- Fixed Focus-mode Notes rendering at a stuck, tiny (~121px-tall) size after switching from Standard layout — `_enter_focus_layout()` was hiding the old right column while it still contained the live `notes_webview`, moments before a rebuild reparented it into the fresh layout, leaving the `QWebEngineView` stuck at a stale size.
- Fixed the general markdown viewer (documentation `.md` items) not re-styling for the new theme when toggling light/dark — its "currently open file" state has to be captured *before* `refresh_projects()` runs, since that call unconditionally clears it.
- Fixed `ForceDarkMode` on the main webview getting stuck permanently on after the first switch to dark theme — it was only ever being set `True`, never back to `False`, so plain web pages (and the markdown viewer, which shares the same webview) stayed dark-filtered even after returning to light mode.
- Fixed the pinned-projects row not correctly re-sizing when the window *shrinks* — its container only reliably re-fires its own resize event when growing, since it's deliberately sized to content rather than stretched. The main window's resize event now explicitly re-triggers it.
- Fixed a 2px height mismatch between the pinned-projects row and the main projects grid (26px vs. 28px) that made the two rows look slightly misaligned.
- Fixed a crash when the Quick File Browser Panel starts expanded (now possible since its state persists) on a project's very first-ever load — `populate_folder_browser()` assumed the main Folder-viewer-tab's widgets always existed already, but they're built later in the same pass; all four render targets are now guarded consistently.

### Removed
- `CleanTextEdit` (the old sanitizing `QTextEdit` subclass), its formatting toolbar, and all its `QTextCursor`-based formatting handlers (bold/italic/heading/lists/link/etc.) — superseded by the Muya editor, which provides its own in-editor markdown-shortcut typing.

## 2026-08-19

### Added
- **Focus layout**: a new two-column layout (launchers | wide viewer) alongside the existing three-column Standard layout, toggled via a title-bar button. Notes move into a viewer tab; launchers that would normally open externally (web links, images, PDFs, local `.md`/`.html`) route into the built-in viewer instead, with small per-item buttons to force-open externally.
- **Layout mode is now per-project**: each project remembers whether it was last viewed in Standard or Focus layout, stored in the project's own config file, and reopens in that layout automatically.
- **Live markdown editor**: `.md` files opened in the viewer now default to an embedded WYSIWYG editor (built on Muya, the standalone editor engine extracted from the MarkText project) with autosave — no more separate Save button. A "👁 Preview" toggle switches to the themed read-only rendering when wanted.
- **Group-by-Type launcher view**: a "🗂️ Group" toggle in the launcher header dynamically regroups all launchers into Documentation / Websites / Resources sections by heuristic (extension, app, URL), without ever touching the project's category structure on disk. Misclassifications can be corrected per-item via right-click → "Move display to…", stored as a settings-side override rather than a file edit. Focus layout now defaults to this grouped view automatically.

### Changed
- The "⇄ Path Mapping" toggle button — an obscure per-project setting that was getting confused with the new Focus layout toggle — now only appears in the title bar while Edit Project mode is active.

### Fixed
- The small 📄 preview button next to markdown launchers now follows the Focus-layout interaction inversion like its `.html`/image counterparts already did: "Open in built-in editor" in Standard layout, "Open externally" in Focus layout (previously it always opened internally, regardless of layout mode).
