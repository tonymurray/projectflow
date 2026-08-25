# Viewer Technologies

A quick reference for what actually renders each viewer in ProjectFlow.

| Viewer | Technology |
|---|---|
| **Notes** | [Muya](https://github.com/marktext/marktext) (`@muyajs/core`) — the standalone WYSIWYG markdown editor engine extracted from the **MarkText** project, embedded via `QWebEngineView`. Vendored as a pre-built bundle under `assets/muya/`. |
| **Editor** | [CodeMirror 6](https://codemirror.net/), vendored as a custom Rollup bundle (`assets/codemirror/`), embedded via `QWebEngineView`. Bundles the official JS/Python/HTML/CSS/PHP language packages; JSON reuses the JS one, plain text needs none. |
| **Web** | `QWebEngineView` directly — Qt's own Chromium-based browser engine, no extra library. |
| **PDF** | [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) renders each page to an image, displayed in a plain Qt `QLabel`/`QScrollArea` — no browser engine involved at all. |
| **Image** | Plain Qt `QPixmap`/`QLabel` — same as PDF, no browser engine. |
| **Terminal** | Two selectable backends: **qtconsole** (a Jupyter/IPython kernel embedded directly, the default) or **ttyd** (a real PTY/shell, streamed to an `xterm.js` page inside a `QWebEngineView`) — see `console_backend` setting. |
| **Settings** | Plain PyQt6 widgets — no external library. |
| **Folder browser** | Plain PyQt6 widgets (`QTreeWidget` / icon grid) — no external library. |
| **Time (⏱ Kimai)** | Plain PyQt6 widgets, talking to the Kimai REST API over plain HTTP (`urllib`). |
| **Help** | `QWebEngineView` rendering static HTML generated from the README + Launcher Examples. |

## Notes

- **Muya** and **CodeMirror 6** are the two "real editors" — both are JavaScript libraries running inside a `QWebEngineView`, bridged to Python via `page().runJavaScript()` calls (see `CLAUDE.md`'s Markdown Editor / Code Editor sections for the bridge details, autosave behavior, and known gotchas).
- **PDF and Image are the only viewers with no browser engine at all** — they're just PyMuPDF/QPixmap rendering into ordinary Qt widgets, which is also why their multi-tab support (see `CLAUDE.md`) is essentially free: no extra renderer process per tab.
- **Web, Notes, and Editor each rely on exactly one `QWebEngineView` instance**, regardless of how many tabs are open in that viewer — switching tabs re-navigates the same view rather than spawning a new Chromium renderer process per tab.
