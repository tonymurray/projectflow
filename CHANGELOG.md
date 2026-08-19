# Changelog

All notable changes to ProjectFlow are documented here. This project doesn't use semantic versioning; entries are grouped by date.

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
