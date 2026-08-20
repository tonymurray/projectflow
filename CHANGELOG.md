# Changelog

All notable changes to ProjectFlow are documented here. This project doesn't use semantic versioning; entries are grouped by date.

## 2026-08-20

### Added
- **Dolphin-style icon grid view** for the folder browser: a ☰/⊞ toggle switches between the existing tree/details view and an icon grid, sharing the same navigation state and `.projectflow` project-folder badges. Choice persists via `folder_view_mode` setting.
- **"Open in Viewer" right-click actions** on folder-browser files: images/PDFs/Markdown/HTML now offer a direct "Open in Image/PDF/Markdown/Web Viewer" context-menu action, alongside the existing default "Open".
- **Quick File Browser Panel**: a collapsible file browser now lives at the top of the launcher column in Focus layout ("File Browser" toggle, styled like a category header). Expanding it replaces the launcher list with a compact tree/icon-grid browser (Up/Home/Refresh/view-toggle); clicking a file routes straight into the best built-in viewer (image/PDF/Markdown/Web) instead of navigating away, so you can browse and view side-by-side without leaving Focus mode. Right-click still offers the full standard context menu.
- **Group-by-Type is now remembered per project**: toggling "☰ Group" persists the choice into the project's own config, so it's restored exactly as left on the next open — rather than always resetting to the Focus-layout default.
- Folder icons across the whole app (tree, icon grid, launcher panel, toggle button) are now a consistent hand-drawn flat icon instead of the system theme's (which rendered yellow/manila on many setups).

### Changed
- The main viewer's "Folder" tab has been removed — folder browsing now happens via the new launcher-column Quick File Browser Panel (Focus layout) or as an internal fallback mode; its Home/Refresh/view-toggle controls moved to the new panel's toolbar.
- The ⏱ Kimai tab now shows "⏱ Time" instead of just the emoji.
- Header toolbar buttons (search box, Group/Add, viewer tabs, File Browser toggle) are a little shorter across the board.

### Fixed
- The Quick File Browser Panel's tree widget was only claiming ~50% of its available height due to an unweighted layout-stretch tie with a trailing spacer; it now correctly fills the full column.
- Several `hasattr(self, x) and self.x` truthiness checks around the new panel's widgets were silently false whenever the widget was empty, because PyQt's `QListWidget` implements `__len__` and Python falls back to it for boolean checks — replaced with identity checks (`getattr(self, x, None) is not None`).
- Fixed a crash ("wrapped C/C++ object of type QLabel has been deleted") that could occur when refreshing the UI (e.g. toggling Group-by-Type) after the Quick File Browser Panel had been expanded and then collapsed — its widget references weren't being reset to `None` when not rebuilt, leaving stale pointers to already-destroyed widgets.

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
