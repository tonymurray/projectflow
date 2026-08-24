# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Shared Human/AI Documentation

@ai/context.md
@ai/issues.md
@ai/.instructions.md

## Project Overview

ProjectFlow (formerly "Folder Opener") is a PyQt6-based KDE Plasma application that provides a graphical launcher for quickly opening projects, files, and folders in various applications. It uses JSON configuration files to define categorized shortcuts. The app displays a three-panel layout: Viewer (left), Shortcuts (center), and Notepad (right).

## Running the Application

The application uses nix-shell for dependency management:

```bash
./projectflow.py
```

The shebang handles all dependencies automatically via Nix:
- Python 3.13
- PyQt6

## Configuration System Architecture

### Configuration Loading Hierarchy

The app determines which config to load with this priority:

1. **Default config** (set via "Set as Default" button) stored in `.projectflow_settings.json`
2. **Last used config** (automatically tracked)
3. **Standard default**: `projectflow.json` in the project root or `projects/projectflow.json`

### Configuration File Structure

Config files are JSON files with this structure:

- `columns`: Array containing one column of categories and items
- `column_headers`: Array with header text (typically `["Shortcuts and Actions"]`)

Each item is an array: `[display_name, path, application]`

Example structure:
```json
{
  "column_headers": ["Shortcuts and Actions"],
  "columns": [
    [
      {
        "Category Name": [
          ["Display Name", "/path/to/item", "application"],
          ["Website", "https://example.com", "firefox"]
        ]
      }
    ]
  ]
}
```

### Settings Persistence

User preferences are stored in `.projectflow_settings.json`:
- `default_project`: The project file set as default
- `projects_directory`: Subdirectory containing additional projects (default: "projects")
- `last_used_project`: Most recently loaded project file
- `recent_projects`: List of up to 10 recently used main projects (for quick-access bar)
- `folder_projects`: List of up to 20 recently used `.projectflow` configs from folders (shown in separate "Folder Projects" section)
- `archived_folder_projects`: List of `.projectflow` paths that have been archived (hidden from Folder Projects; restored by moving back to `folder_projects`)
- `pinned_projects`: List of projects pinned to the front of the quick-access bar (drag to reorder/pin, ↺ to reset)
- `color_order`: Ordered list of color hex strings set by dragging swatches in the color strip. Drives the 🎨 sort order. Auto-pruned when colors are removed.
- `theme`: Color theme - `"light"`, `"dark"`, or `"system"` (default: `"system"` - follows desktop preference)
- `joplin_token`: Joplin Web Clipper API token (enables manual sync button in notepad toolbar)
- `notes_folder`: Path where notes are stored as markdown files (default: `notes/` in project dir). Set to `"~/Nextcloud/Notes/ProjectFlow/"` for Nextcloud sync
- `pdfviewer`: Path to an external PDF viewer application (e.g., `"~/Programs/notesviewer/notesviewer.py"`). When set, adds an "External" button to the PDF toolbar that opens the current PDF in this viewer. Omit this setting to hide the button.
- `open_note_external`: External markdown editor command (e.g., `"typora"`, `"zettlr"`, `"code"`, `"kate"`). When set, adds an "Open in {Editor}" footer button below the notepad, opening the current note's markdown file in this editor.
- `enable_baloo_tags`: Enable/disable Baloo tag querying for tagged files (default: `true`). Set to `false` on non-KDE systems.
- `browser_new_tab`: Whether `firefox`/`chrome` handlers open URLs in a new tab or a new window (default: `true`). Set to `false` to open new windows — useful when using the "open in virtual desktop" feature so each desktop gets its own browser window.
- `terminal`: External terminal application (default: auto-detected based on desktop environment). Used by terminal-related handlers and the Console viewer's "External" button. Leave empty for auto-detection.
- `editor`: Default code/text editor (default: auto-detected based on desktop environment). Used by `directorydev` handler. Leave empty for auto-detection. Auto-detection: KDE→kate, GNOME→gedit, XFCE→mousepad, etc.
- `file_manager`: Default file manager (default: auto-detected based on desktop environment). Used by `directorydev` and `dolphin_tabs` handlers. Leave empty for auto-detection. Auto-detection: KDE→dolphin, GNOME→nautilus, XFCE→thunar, etc.
- `fm_always_tabs`: When `true`, every file manager launch opens with `~/` as the first tab and the target path as the second tab (default: `false`). Applies to `file_manager`, `dolphin`, `directorydev`, and kate-fallback launches. Configurable via Settings → Advanced → "File Manager Tabs" checkbox.
- `default_app`: Default application pre-selected when opening the add-launcher dialog (e.g., `"firefox"`). Empty = first alphabetically.
- `kimai_url`: Kimai server base URL (e.g., `"https://kimai.example.com"`). Required to enable the ⏱ time tracking tab. Configured via Settings → Integrations.
- `kimai_token`: Kimai API bearer token. Required alongside `kimai_url`. Configured via Settings → Integrations.
- `kimai_csv_folder`: Folder to scan for CSV files generated by the `leave` skill for auto-import into Kimai (e.g., `"~/Nextcloud/ProjectFlowDocuments/times"`). Configured via Settings → Integrations.

### Per-Config Options

These options can be set in individual config JSON files:
- `project_name`: Display name for the project (shown in title bar, window title). If not set, defaults to the config filename (without extension) or parent folder name for `.projectflow` files.
- `pdf_file`: Default PDF file to load for this config
- `webview_url`: Default URL to load in web viewer for this config
- `image_file`: Default image file to load for this config
- `code_file`: Default file to load in the internal code editor for this config. Set via the 📌 pin button in the viewer tab row (shared with pdf/webview/image/etc. — see Code Editor above), not via Project Details (no dedicated dialog field yet).
- `console_path`: Default directory for the embedded console
- `folder_path`: Default starting directory for the folder browser. For `.projectflow` configs this defaults to the config's own directory. Set via the 📌 pin button in the folder toolbar, or via Project Details dialog.
- `column2_default`: Which viewer to show by default - `"pdf"`, `"webview"`, `"image"`, `"code"`, `"help"`, `"examples"`, `"console"`, `"folder"`, `"time"`, or `"notes"` (`"notes"` only has any effect in Focus layout, where Notes is one of the viewer tabs — Standard layout's Notes column is always shown regardless of this setting)
- `kimai_project_id`: Numeric Kimai project ID linked to this config. Set via the "Link Kimai Project…" button in the ⏱ viewer.
- `kimai_project_name`: Kimai project name (exact string). Used for CSV import matching — CSV rows whose `Project` column matches this are shown as "Pending Imports". Set automatically when linking via the picker.
- `terminal`: Terminal emulator override for this config (e.g., `"gnome-terminal"`, `"alacritty"`). Overrides global terminal setting.
- `browser_new_tab`: Override global `browser_new_tab` for this project. `true` = new tab, `false` = new window. Omit to inherit global setting.
- `notes_file`: Path to project-local notes file (e.g., `"./projectflow.md"`). When set, notes are loaded from this file instead of the global notes folder. Supports relative paths resolved from the config file location.
- `layout_mode`: `"focus"` to reopen this project in Focus layout (see UI Features → Focus Layout). Omitted (or any other value) means Standard layout. Written automatically when the ⊞/▣ title-bar toggle is clicked — not intended for manual editing. New projects created via `create_default_project()` or "Make Project" (`create_folder_project_config()`) now write `"focus"` explicitly; existing projects created before this change keep defaulting to Standard until toggled.
- `group_by_type`: `true`/`false` — remembers this project's last Group-by-Type launcher-view choice, **Standard layout only** (see UI Features → Group-by-Type Launcher View; Focus layout uses `active_launcher_tab` below instead). Omitted means "never explicitly set," which falls back to the layout-linked default (on for Focus, off for Standard — though Focus no longer visibly acts on this value). Written automatically when the "☰ Group" toggle is clicked — not intended for manual editing.
- `active_launcher_tab`: `"files"`/`"docs"`/`"resources"`/`"apps"` — remembers this project's last-opened Focus-layout launcher tab (see UI Features → Launcher Tab Bar), the fallback used when `launcher_tab_default` below isn't set. Omitted means `"files"` (the default). Written automatically when a tab is clicked — not intended for manual editing.
- `launcher_tab_default`: `"files"`/`"docs"`/`"resources"`/`"apps"` — pins a fixed default Focus-layout launcher tab for this project, overriding `active_launcher_tab`'s last-opened value on load (mirrors how `column2_default` overrides the viewer's last-opened mode). Set via the 📌 button in the launcher tab row, or the "Default Launcher Tab" field in Project Details. Omit to fall back to last-opened behavior.

These options can also be set via the 📌 button in each viewer toolbar (`set_viewer_as_default()`):
- Load a PDF, webpage, or image in the central viewer
- Click 📌 to save it as the default AND set that viewer as `column2_default`
- To change default viewer type: switch to the desired viewer, load content, click 📌
- Notes (Focus layout only) has its own 📌 in the notes archive-button row (next to Joplin/external-editor buttons, only shown while the Notes tab is active) — same mechanism, no separate content to save, just `column2_default: "notes"`

### Project-Local Configs (.projectflow)

The Folder Browser viewer can create `.projectflow` config files directly within any folder. These are hidden config files that live alongside your project code.

**Creating a project:**
1. Navigate to a folder using the Folder Browser viewer
2. Click "Make Project" to create `.projectflow` and `projectflow.md`
3. The app auto-detects project type (npm, Python, Git, Docker, etc.) and creates appropriate launchers

**Project-local config structure:**
```json
{
  "project_name": "MyProject",
  "column_headers": ["MyProject Project"],
  "columns": [[
    {
      "Development": [
        ["Open in Editor", ".", "editor"],
        ["Terminal Here", ".", "terminal"],
        ["File Manager", ".", "file_manager"]
      ]
    },
    {
      "npm": [
        ["npm install", ". install", "npm"],
        ["npm start", ". start", "npm"]
      ]
    }
  ]],
  "column2_default": "console",
  "console_path": ".",
  "notes_file": "./projectflow.md"
}
```

**Path conventions in .projectflow:**
- `.` = current folder (where .projectflow lives)
- `./file.txt` = relative file path
- `. command` = run command in folder (e.g., `. start` for `npm start`)
- All relative paths are automatically resolved to absolute paths when loaded

**Project detection indicators:**
| File/Folder | Auto-generated launchers |
|-------------|-------------------------|
| `package.json` | npm install, start, dev, build, test (based on scripts) |
| `requirements.txt` / `setup.py` / `pyproject.toml` | pip install |
| `Makefile` | make |
| `docker-compose.yml` | docker-compose up/down |
| `.git` | git status, git log |
| `README.md` | Open README |

**Project-local notes:**
- Notes are stored in `projectflow.md` in the same folder (specified by `notes_file`)
- These are visible, editable markdown files that live with your project
- Changes sync automatically with any markdown editor or version control

### Adding Resources

Files and folders can be associated with a config in two ways:

1. **Service menu** (recommended): Right-click files/folders in Dolphin → "Add to ProjectFlow" → select config. Creates entries in an "Added Resources" category with appropriate handlers:
   - Folders → open in Dolphin
   - Images (.png, .jpg, .jpeg, .webp, .gif, .bmp, .svg) → open in gwenview (with preview button 🖼️)
   - Other files → open with default application
   - Entries are editable via the normal edit interface

2. **Baloo tags** (automatic): Tag files in Dolphin with the project name (derived from config filename, e.g., `main.json` → tag "main"). These appear dynamically in a "Tagged Files" category at the bottom of the shortcuts column. To remove, untag in Dolphin.

To install the service menu:
```bash
mkdir -p ~/.local/share/kio/servicemenus
cp utilities/projectflow-servicemenu.desktop ~/.local/share/kio/servicemenus/
chmod +x utilities/add-projectflow-servicemenu.sh
```

### Notes Storage

Notes are stored as markdown files in the configured `notes_folder`:
- Each config gets its own `.md` file (e.g., `work.json` → `work.md`)
- Notes edited live in Muya (see Markdown Editor below) and autosave on a ~1.2s poll of the editor's dirty flag — no manual save button
- Markdown format enables sync with Nextcloud Notes or any markdown-compatible tool
- Legacy HTML notes in JSON projects are automatically migrated to markdown files (`html_to_markdown()`, still used for this one-time migration path only)

### Notes Archive

Notes can be archived to a hidden `.archive` subfolder within the notes folder:
- Archive files mirror the notes naming convention (e.g., `notes/.archive/work.md`)
- Archive buttons (📥 Archive, 📜 View) appear at the bottom-right of the notepad
- Clicking 📥 Archive prepends current notes to the archive with a dated separator, then clears the notepad
- Newest archived content appears at the top of the archive file
- Clicking 📜 View opens a read-only dialog showing the archive content
- Archive folder is hidden from file browsers and notes apps by default (dot-prefix)
- If an external editor is configured, the View Archive dialog includes an "Open in Editor" button

Archive file format:
```markdown
------------------------------
14:35 -- 2nd March 2026
------------------------------

[Most recent archived notes]

------------------------------
09:12 -- 28th February 2026
------------------------------

[Previous archived notes]
```

## Key Classes and Methods

### `ProjectFlowApp` (main class in projectflow.py)

**Initialization and Settings:**
- `load_settings()`: Loads JSON settings from `.projectflow_settings.json`
- `save_settings()`: Persists settings to JSON
- `get_config_file_to_use()`: Determines which config file to load based on priority

**Configuration Management:**
- `load_config()`: Executes the Python config file and extracts variables
- `create_default_project(config_file)`: Generates a template project file
- `switch_to_config(config_path)`: Switches to a different config and refreshes UI
- `refresh_projects()`: Reloads configuration and rebuilds the entire UI

**UI Construction:**
- `init_ui()`: Creates main window with scroll area
- `create_title_bar()`: Creates title bar with searchable project name (uses `ClickableSearchTitle` widget)
- `create_projects_section()`: Builds the quick-access section for recent/all projects
- `build_main_content()`: Constructs the three-column layout with all buttons

**User Actions:**
- `open_in_app(path, app)`: Opens a file/folder/URL in the specified application
- `open_all_in_group(items)`: Opens all items in a category
- `edit_config()`: Opens current config file in Kate
- `set_as_default_project()`: Marks current project as default
- `load_different_config()`: File picker to select a new config

**Terminal Detection:**
- `detect_default_terminal()`: Auto-detects appropriate terminal based on `XDG_CURRENT_DESKTOP` (KDE→konsole, GNOME→gnome-terminal, etc.) with fallback to checking installed terminals
- `get_configured_terminal()`: Returns configured terminal or auto-detected default
- `_get_terminal_workdir_command(path)`: Builds terminal command to open at directory
- `_get_terminal_command(shell_cmd, hold)`: Builds terminal command to run shell command

**Baloo Tagged Files:**
- `get_tag_name_for_config()`: Derives Baloo tag name from config filename
- `get_tagged_files()`: Returns list of files tagged in Baloo with the project's tag name

**Kimai Time Tracking:**
- `_build_time_viewer()`: Builds `self.time_container` — shown/hidden based on viewer mode
- `_kimai_request(method, path, data, params)`: HTTP helper wrapping `urllib.request`; normalises base URL (strips accidental `/api` suffix)
- `_kimai_load_entries(period)`: Fetches timesheets for current period, populates table + summary label, then calls `_kimai_refresh_csv_section()`
- `_kimai_load_activities()`: Fetches activities for linked project, populates the Log Time activity dropdown (cached per project load)
- `_kimai_submit_entry()`: Validates and POSTs a new timesheet entry, then refreshes the table
- `_kimai_link_project_dialog()`: Shows project picker (fetched from API), saves `kimai_project_id` + `kimai_project_name` to project config
- `_kimai_scan_csv_imports()`: Scans `kimai_csv_folder` for CSV files; filters rows matching `kimai_project_name`
- `_kimai_refresh_csv_section()`: Rebuilds the Pending Imports UI section from scan results
- `_kimai_import_csv_file(fpath, rows)`: POSTs each CSV row to `/api/timesheets`, moves file to `.archive/` on success

### `SettingsDialog` (settings dialog in projectflow.py)

- `__init__(parent)`: Creates tabbed dialog with Settings, Applications, Integrations, Icons, and Launch Handlers tabs
- `_create_settings_tab()`: Builds form for core `.projectflow_settings.json` options
- `_create_applications_tab()`: Editor, file manager, terminal, and related app settings
- `_create_integrations_tab()`: Kimai (URL, API token, CSV folder) and Joplin (API token) settings
- `_create_icons_tab()`: List view for `icon_preferences.json` management
- `_create_handlers_tab()`: Launch handlers CRUD with type badges [Custom]/[Built-in]/[Python]
- `apply_settings()`: Saves all tabs' settings to their respective files
- `update_theme()`: Refreshes dialog styling when theme changes

### `ClickableSearchTitle` (widget in projectflow.py)

Custom widget for the title bar that transforms between display and search modes:
- Uses `QStackedWidget` to switch between label (display) and `QLineEdit` (search)
- `QCompleter` provides autocomplete dropdown with case-insensitive substring matching
- Click title to enter search mode, Enter to select, Escape/click elsewhere to cancel
- Emits `configSelected` signal with config path when user selects a match

## Application Launching Logic

The `open_in_app()` method (line 779) handles different types of launches:

1. **Terminal commands**: Detects `&&`, `||`, `;`, or commands starting with `cd`/`npm` and launches in Konsole
2. **Flatpak apps**: Detects app names starting with "com" and launches via `flatpak run`
3. **Kate with directories**: Opens Dolphin instead (kate doesn't handle folder opening well from CLI)
4. **Standard apps**: Direct subprocess launch with `[app, expanded_path]`

Paths support tilde expansion (`~/`) via `os.path.expanduser()`.

## Launch Handlers

Launch handlers define how files, folders, and URLs are opened in various applications. There are three sources of handlers:

### Built-in Handlers (always available)

- `browser` / `file_manager` / `editor` / `default` - Use xdg-open
- `konsole` / `terminal` - Open folder in configured terminal (auto-detected or from settings)

### Simple Handlers (from launch_handlers.py)

These are defined in `LAUNCH_HANDLERS` dict in `launch_handlers.py`:
- `firefox` - Open URL in Firefox new window
- `chrome` - Open URL in Chrome via Flatpak
- `tail_log` - Tail a log file; pass a directory (auto-detects `debug.log` or `error.log`) or a specific file path
- `rsync_backup` - Run rsync with common excludes

### Custom Handlers (from launch_handlers_custom.json)

User-defined handlers are stored in `launch_handlers_custom.json`. These can be created/edited via Settings > Launch Handlers tab.

Custom handlers override built-in handlers with the same name. Format:

```json
{
  "my_terminal": {
    "command": ["alacritty", "--working-directory", "{path}"],
    "description": "Open in Alacritty"
  },
  "deploy": {
    "type": "shell",
    "command": "cd {path} && ./deploy.sh",
    "terminal": true,
    "hold": true,
    "description": "Run deploy script"
  }
}
```

**Handler fields:**
- `command`: List of arguments (for exec) or string (for shell). Use `{path}` as placeholder.
- `type`: `"exec"` (default) runs command directly, `"shell"` runs through `bash -c`
- `terminal`: `true` to wrap command in configured terminal
- `hold`: `true` to keep terminal open after command finishes
- `description`: Human-readable description shown in UI

**Complex handlers** (COMPLEX_HANDLERS):

`npm` - Run npm commands in terminal:
```python
("My App", "~/projects/myapp", "npm")           # npm start
("My App", "~/projects/myapp dev", "npm")       # npm run dev
("My App", "~/projects/myapp build", "npm")     # npm run build
("My App", "~/projects/myapp test", "npm")      # npm test
("My App", "~/projects/myapp install", "npm")   # npm install
```

`ssh_session` (alias: `ssh_cd_npm`) - SSH with cd/command support:
```python
("Server", "user@host", "ssh_session")                      # SSH, run bash
("Server", "user@host cd /var/www", "ssh_session")          # SSH, cd to dir
("Server", "user@host cd /app npm start", "ssh_session")    # SSH, cd, run command
```

`directorydev` - Open full dev environment (file manager + terminal + editor, optionally npm):
```python
("My Project", "~/projects/myapp", "directorydev")           # Opens 3 apps (no npm)
("My Project", "~/projects/myapp dev", "directorydev")       # Also runs npm run dev
("My Project", "~/projects/myapp build", "directorydev")     # Also runs npm run build
("My Project", "~/projects/myapp test", "directorydev")      # Also runs npm test
```

Uses the configured `editor` and `file_manager` settings (auto-detected if not set).

The main button opens all apps at once. Individual icon buttons (🗄️ $_ 💠) to the right of the main button allow opening each app separately. The npm button (⚡) only appears if a recognized command is specified: start, dev, build, test, install, run.

## UI Features

- **Three-panel layout**: Viewer (left) | Shortcuts (center) | Notepad (right)
- **Viewer panel**: Tab buttons at top to switch between viewers (Web, PDF, Image, Terminal). Active viewer is highlighted. Each viewer has its own toolbar with an "External" button to open in a standalone application. There is no "Folder" tab — folder browsing now lives in the launcher column (see Quick File Browser Panel below) in Focus layout, or via the 📁-preview/"Add to Project" flows; `column2_mode == "folder"` still exists internally as the viewer's fallback mode. Help/Examples was moved out of this row entirely (see Help viewer below).
- **Viewer resize handle**: a thin draggable bar (`ViewerResizeHandle`, a `QLabel` subclass — not `DragHandle`, which is drag-and-drop reordering, not live resizing) sits below `column2_stack`. `column2_stack` uses `setFixedHeight()`, not `setMinimumHeight()` — a minimum is only a floor, and on a project with a tall enough launcher column the surrounding layout stretches `column2_stack` well past any floor anyway (both sit in the same row), which made an earlier minimum-based version of this feature have no visible effect and pushed the handle itself far down the page. A fixed height opts `column2_stack` out of that stretching entirely — extra vertical space from a tall launcher column is simply left blank below the handle instead — so the handle always sits a short, predictable distance down regardless of launcher-list length, and dragging (which also calls `setFixedHeight()`, both to shrink and grow) always has a visible effect. On release, the resulting height is saved to `.projectflow_settings.json` as `viewer_height` (default `1000`) via `_save_viewer_height()`. Deliberately a **per-machine** setting, not per-project — how tall feels comfortable depends on the monitor's resolution/DPI, not which project is open.
- **Shortcuts panel**: Single column of categorized launchers with "Open All" buttons per category. Edit/Refresh buttons at top (no header label).
- **Notepad panel**: Same live Muya WYSIWYG editor as standalone `.md` files (see Markdown Editor below), on a dedicated persistent `notes_webview` — no separate formatting toolbar (Muya provides its own in-editor markdown-shortcut typing). Rendered with a Typora-style "paper on page" look (see Markdown Editor → Paper Theme).
- **Folder browser** (internal/fallback viewer mode, and the engine behind the launcher-column Quick File Browser Panel): Navigate the filesystem, detect project folders with `.projectflow` configs, and create new projects. Folders with existing `.projectflow` show [P] badge and can be opened directly. Toggle between tree/details and a Dolphin-style icon grid (☰/⊞ button, `folder_view_mode` setting, shared across every folder-browsing surface in the app). Clicking `.html`/`.htm` files opens them in the built-in webview; clicking `.md` files opens the built-in Muya markdown editor (see Markdown Editor below). All other files open via `xdg-open`. Folder icons are a hand-drawn flat icon (`_folder_icon()`) rather than the system theme's, for consistent coloring everywhere. A Dolphin-style filter bar (`_build_folder_filter_bar()`) sits below the file list on both this viewer and the launcher panel — live substring-filters entries by filename as you type, shared/synced state (`self.folder_filter_text`) between the two boxes, re-rendered from a cached scan (`_render_folder_views_from_cache()`) rather than re-reading the disk per keystroke. No folder-preserving "lock" toggle yet — a filter currently hides non-matching folders too. Both this viewer and the launcher panel also have an "Open in {file manager}" footer button (`folder_open_external()`). A "⌂⌂ project folder" button sits next to the plain "⌂ home" button on both toolbars, always visible. Once the project has a `folder_path` pinned, it's styled normally and jumps there (`folder_go_project_default()`); with no `folder_path` set, it's greyed out (still clickable) and instead pins the currently browsed folder as the project's default (`_pin_current_folder_as_project_default()`, mirroring the `set_viewer_as_default()`/`_set_launcher_tab_as_default()` pin pattern) — clicking it then rebuilds the UI via `refresh_projects()` so the button switches to its active style/behavior immediately. `populate_folder_browser()` expanduser()s its `path` argument unconditionally — `folder_path`/`config_folder_path` values are never resolved earlier in the loading pipeline (`resolve_relative_paths_in_config()` only handles `.`/`./`-prefixed relative paths, and only for `.projectflow` configs at that), so a literal `~`-prefixed `folder_path` in a plain `projects/*.json` config would otherwise reach `os.listdir()` unexpanded and fail with "No such file or directory". Right-clicking **empty space** (no item under the cursor) in any of the four folder-browsing view widgets (main tree/icons, launcher-panel tree/icons) opens a background menu (`_build_folder_background_context_menu()`) with a single "New from Template" submenu, sourced from the freedesktop Templates folder (`XDG_TEMPLATES_DIR`, resolved by `_get_templates_folder()` — reads `~/.config/user-dirs.dirs`, falling back to `~/Templates`). `_get_template_entries()` supports both conventions found in the wild: plain files/folders copied as-is, and KDE/Dolphin-style `.desktop` `Type=Link` wrapper files (`Name=`/`URL=`) that give a friendlier display name than the real target file (`_resolve_desktop_template()`) — both a wrapper and its raw target file can legitimately appear as separate entries if both exist directly in the folder, matching real Dolphin behavior. Selecting an entry (`_create_from_template()`) prompts for a name (pre-filled with the template's own name), checks for a collision, then `shutil.copy2()`s a file or `shutil.copytree()`s a folder into the current directory and refreshes the view — for folders, only the top-level copied folder is renamed; contents are copied untouched. Right-clicking an *existing* item is unaffected — that's still `_build_folder_context_menu()`, unchanged.
- **Help viewer** (`help_container`/`self.help_browser`, a `QWebEngineView`): combines the README and launch-handler documentation (formerly a separate "Examples" viewer tab) into one page with two HTML tabs — "README" (default) and "Launcher Examples". Not part of the per-project viewer tab row — it's reference material, not something tied to a specific project — so it's opened via the footer's "❓ Help" button (`switch_to_viewer_mode("help")`) instead, sitting between "⌨️ Aliases" and "📄 New Project". Tab switching (`_build_help_html()`) uses a pure-CSS radio-button `:checked ~` sibling-selector pattern rather than JavaScript — `QWebEngineView` does support JS (used elsewhere: Muya, ttyd, the Aliases page's search box), but a static two-tab page has no real need for it. The Examples tab's content (still `EXAMPLES.html`, theme placeholders substituted by `_load_examples_html_fragment()`) is embedded via `<iframe srcdoc="...">` rather than merged into one shared stylesheet, since it's already a complete self-contained document with its own `<style>` block — an iframe keeps that CSS isolated instead of risking class-name collisions with the README's rendering. Two footer buttons ("Open README in {editor}" / "Open Examples in {editor}") replace the old single per-viewer External button, since there are now two source files. `column2_default: "examples"` from old configs is translated to `"help"` on load for backward compatibility (`load_notes()`) — the value is no longer a real mode.
- **Embedded console**: IPython/qtconsole for quick Python and shell commands (`!ls`, `!git status`). Limitations: no interactive programs (nano, vim) - use External button for full terminal. An optional `ttyd`-backed real-terminal mode is available (see below) that removes this limitation.
  - **Why qtconsole**: Well-established Jupyter project with strong community support. Alternatives considered:
    - `termqt` - Pure Python terminal (supports nano/vim), but small community (61 stars), single maintainer
    - `pyqtermwidget` / `qtermwidget` - C++ based, requires compilation, complex bindings
    - `QProcess + QTextEdit` - Simple but no colors, no terminal features
  - Current approach: qtconsole + External button provides best balance of features and reliability for the **default**, zero-extra-binary path.
  - **KDE KParts/KonsolePart** was investigated as a native alternative (research session, 2026-08-21): ruled out — the current PyKDE6 module list (KCoreAddons, KGuiAddons, KWidgetsAddons, KStatusNotifierItem, KNotifications, KUnitConversion, KXmlGui, per `develop.kde.org`'s Python-bindings docs) does not include KParts, and Python KParts bindings are widely described as deprecated/unmaintained. Not revisited unless that changes upstream.
  - **`qtermwidget`** (the LXQt terminal widget) has its own sip-based PyQt bindings upstream, but nixpkgs only packages the C++ library, not the bindings — adopting it would mean writing and maintaining a custom Nix derivation. Not pursued for that reason; `ttyd` (below) turned out to need none of that.
- **`console_backend` setting** (`"qtconsole"` default / `"ttyd"` / `"auto"`, configured in Settings → Advanced): an optional real-terminal Console backend built on [`ttyd`](https://github.com/tsl0922/ttyd) (packaged as-is in nixpkgs, `pkgs.ttyd`) embedded via `self.console_ttyd_webview`, a `QWebEngineView` loading ttyd's own web UI (xterm.js). Gives full PTY behavior — nano, vim, htop all work — unlike qtconsole. `resolve_console_backend()` resolves `"auto"` to `"ttyd"` only if `shutil.which("ttyd")` finds the binary, else falls back to `"qtconsole"`.
  - **Process lifecycle (the design problem this solves)**: the existing qtconsole block recreates its in-process kernel on every `build_main_content()` rebuild (every refresh) — harmless there since it holds no OS resource. This is NOT safe to copy for ttyd, which spawns a real subprocess bound to a real port. `_ensure_ttyd_console(cwd)` guards against this: it's a no-op if `self.console_ttyd_proc` is already alive for the same `cwd` (mirrors the `_notes_loaded_for` reload-gate pattern), only killing and respawning when the directory actually changes (via `console_open_directory()`) or the backend setting changes away from ttyd (`_stop_ttyd_console()`, called defensively in the qtconsole branch too).
  - **Persistent webview**: `self.console_ttyd_webview` is created once in `__init__` (like `self.webview`/`self.notes_webview`) and follows the same documented safe reparenting pattern (`setParent(self)` in `init_ui()` before `setCentralWidget()` tears down the old tree — see "Two Muya sessions" above) rather than being recreated per-rebuild.
  - **Stretch-factor gotcha**: `console_container_layout.addWidget(self.console_ttyd_webview, 1)` — the `1` is required, not cosmetic. Without it, on any project with a long enough launcher list to make the whole page (inside `main_scroll`) taller than the viewport, `column2_stack`/`console_container` get stretched to that full oversized page height, but a plain `QWebEngineView` added with no stretch factor only claims its own sizeHint and ends up vertically centered in the leftover space — a small terminal floating with blank space above and below it, rather than filling the column. `webview_container_layout.addWidget(self.webview, 1)` already uses this exact fix for the same widget type; this was simply missed when `console_ttyd_webview` was added and took a live screenshot-driven debugging session to track down (JS-side "xterm.js not fitting" was a red herring — this is a plain Qt layout issue, nothing to do with ttyd/xterm.js itself).
  - **Spawn command**: `ttyd -i 127.0.0.1 -p 0 -W -O -w <cwd> <$SHELL>` — `-i 127.0.0.1` binds loopback-only (verified empirically, never `0.0.0.0`), `-p 0` picks a random free port and prints `Listening on port: NNNN` to stdout, which `_ensure_ttyd_console` parses (reliable, no race). `start_new_session=False` is deliberate — unlike this app's other subprocess launches (external terminal/editor/file-manager, always `start_new_session=True` so they outlive the app), ttyd is an internal implementation detail and must die with the app. `ProjectFlowApp.closeEvent()` (previously nonexistent — the app had no close handler at all) calls `_stop_ttyd_console()` for this reason.
  - **Security note**: ttyd's shell has no authentication configured — acceptable since it's loopback-only, so any other local process running as the same OS user already has equivalent access (same trust boundary as the rest of the desktop session). The one risk loopback binding alone does NOT cover: WebSocket connections aren't subject to the same-origin policy the way fetch/XHR are, so without `-O`/`--check-origin` any JavaScript running in any browser tab on the machine could open a WebSocket straight to the port and get a shell, regardless of which site served that JS — a "malicious webpage" attack class seen against other unauthenticated localhost dev servers (Ollama, various Electron apps, router/NAS admin UIs). `-O` is passed for exactly this reason, rejecting connections whose `Origin` header doesn't match. Multi-OS-user machines (shared servers, some container/namespace setups) remain a residual gap `-O` doesn't address — a different local account could still connect — but that's out of scope for a single-user desktop app.
  - **Alias quick-jump buttons**: when the ttyd backend is active, `create_console_toolbar()` adds one small button per `alias`-type launcher item from the *current project's own* `self.COLUMN_1` (`_get_current_project_aliases()` — not the separate cross-project `projects/aliases.json`/alias-file system), placed after the path label (opposite side of the toolbar) so they sit top-right. Clicking one runs that alias's resolved command in the live terminal via `_run_alias_in_ttyd_console()`. Not offered for qtconsole — it has no interactive-shell notion of "type this into the running session," only discrete `.execute()` calls, so a partial (cd-only) equivalent would behave inconsistently for aliases with extra commands. Capped at 10 buttons (`ALIAS_TOOLBAR_LIMIT`) so a project with many aliases doesn't crowd the toolbar — order follows the project's own config order (categories/items top-to-bottom), so reordering there controls which ones make the cut. Anything past the cap is still reachable via a trailing "+N" button (`_show_alias_overflow_menu()`) that pops up the rest in a `QMenu`.
    - **Mechanism (non-obvious)**: `window.term.paste(text)` alone does not execute anything — xterm.js always wraps pasted content in bracketed-paste escape sequences, and bash's readline treats a bracketed paste as literal text to insert rather than auto-submitting it, even if the pasted string contains `\r`/`\n` (confirmed empirically — pasting `"cmd\r"` just leaves `cmd` sitting unexecuted on the prompt line). Since there's no public xterm.js API to simulate pressing Enter, the working sequence is: paste the command text with no trailing newline, then separately call the private `window.term._core.coreService.triggerDataEvent('\r', true)` to submit it (wrapped in try/catch — this reaches into xterm.js internals, not its public `Terminal` interface, so a future ttyd bundle update that changes this shape should degrade to "pasted but not submitted" rather than a JS error).
  - **Internal log tailing (Focus layout)**: `.log` files and `app == "tail_log"` launcher items route into this same live ttyd terminal (`_open_log_file_in_console()`, wired into `open_in_app()`'s Focus-layout inversion block) instead of always spawning an external terminal — `tail -n 300 -f <resolved path>`, via the same paste-and-submit mechanism as alias buttons. `_resolve_tail_log_target()` mirrors `handle_tail_log()`'s (launch_handlers.py) directory→debug.log/error.log resolution, so both the internal and external paths pick the same file. **Gated on `resolve_console_backend() == "ttyd"`** — qtconsole's `!command` shell-out blocks the kernel until the command exits, and `tail -f` never exits, so qtconsole is left untouched (falls through to the existing external-terminal `tail_log` handler unchanged) rather than silently hanging the kernel forever.
    - **Two real timing bugs found and fixed while building this** (both affect the pre-existing alias mechanism too, not just log-tailing — it just has a much higher chance of hitting the cold-start path, since a log file can be clicked from anywhere without the Console tab ever having been opened yet):
      1. `console_ttyd_proc` being alive only means the OS process started — it says nothing about whether the webview's page has finished loading. `_ensure_ttyd_console()`'s `setUrl()` triggers an async navigation; pasting immediately after (as the code previously did whenever the process happened to already be alive, which is the common case since `build_main_content()` auto-starts ttyd unconditionally on the ttyd backend) raced that navigation and silently dropped the paste. Fixed with a persistent ready-flag, `self._console_ttyd_ready`, wired to `console_ttyd_webview.loadFinished` once in `__init__` and reset to `False` right before every `setUrl()` in `_ensure_ttyd_console()`. `_run_in_ttyd_when_ready()` polls this flag (100ms interval, ~5s cap) instead of inferring readiness from process liveness.
      2. Even once `loadFinished` fires, ttyd's xterm.js frontend hasn't necessarily finished its WebSocket handshake with the backing PTY yet — confirmed empirically: pasting right on the ready transition was dropped nearly every time, while the identical paste 500ms later landed reliably every time tested. `_run_in_ttyd_when_ready()` applies a fixed 500ms settle delay after the ready flag flips before actually pasting.
      3. Separately: `page().runJavaScript(script)` called **without** a callback was observed to silently no-op on this exact paste-and-submit script often enough to be unusable — same script, same state, the only difference being presence of a callback argument. `_paste_and_submit_in_ttyd()` now always passes a callback, even a no-op `lambda _result: None` — whatever PyQt6/QtWebEngine's fire-and-forget path does differently internally, providing a callback made it reliable every time tested.
- **Preview buttons**: Web links (firefox/chrome) show 🌐 button to preview in webview; images (gwenview/gimp/krita) show 🖼️ button to preview in image viewer; local `.md` files show 📄 button to open the built-in markdown editor. In Focus layout these buttons invert to "open externally" instead (see Focus Layout below), since the main click already opens internally there.
- **Projects section**: Unified project switcher with four modes (Recent/Main/Folder/Archive buttons):
  - **Recent mode** (default): Shows pinned + recent main projects (up to 10) with drag-drop reordering. Pinned projects shown with underline. ↺ button resets pinned order.
  - **Main Projects mode**: Shows all projects from the projects/ folder in rows of 10, sorted alphabetically.
  - **Folder Projects mode**: Shows recently used `.projectflow` configs from folders (up to 10). Stored in settings to avoid filesystem scanning.
  - **Archive mode**: Shows archived projects (greyed out). Each has a ↩ restore button. Right-click for restore or permanent delete.
- **Project color coding**: Assign a color to any project for visual grouping and filtering.
  - **Assign**: Right-click a project button → "🎨 Set Color..." (opens system color picker), or Settings dialog → Project Defaults tab → "Project Color:" row.
  - **Visual indicator**: Colored projects display a 5px solid bar on their left edge in the chosen color.
  - **Color strip**: A row of color swatches appears inline in the projects header (between the mode buttons and the title label). Each swatch is 10px tall and clickable. A striped "no color" swatch is always shown at the end.
  - **Filter by color**: Click a swatch to show only projects with that color; click it again to clear the filter.
  - **Filter uncolored**: Click the striped swatch at the end of the strip to show only projects with no color assigned.
  - **Archive swatch**: A fixed `#cccccc` grey swatch at the far right of the strip is a shortcut to archive mode (same as the Archive button). Active border highlights when archive mode is already open. No color is written to project files — restored projects automatically revert to their original color.
  - **Sort by color**: The 🎨 button (beside the mode buttons) sorts all main projects by the custom swatch order, with uncolored projects last. Click again to reverse. Clicking any mode button returns to normal mode.
  - **Drag-to-reorder swatches**: Drag color swatches left or right to set a custom priority order (e.g. red = urgent first). This order drives the 🎨 color sort and persists in `settings["color_order"]`. Newly added colors are appended in hue order until manually repositioned. Stale colors (no longer assigned to any project) are automatically pruned.
  - **Color picker pre-fill**: The color picker's custom color slots are pre-filled with all currently assigned project colors (in swatch order) so you can easily reuse existing palette colors.
  - Color stored as `"project_color": "#rrggbb"` directly in the project's own JSON/`.projectflow` config file — travels with the project and syncs via Nextcloud.
- **Project archiving**: Right-click any project button to archive it. Archived projects are hidden from normal views.
  - Main projects (`projects/*.json`) are moved to `projects/.archive/` on archive; moved back on restore.
  - Folder projects (`.projectflow`) are never moved — archiving removes them from `folder_projects` and adds to `archived_folder_projects` in settings.
  - Archiving the currently open project auto-switches to another available project.
  - Archived folder projects remain openable at any time (the file never moves); archiving only hides them from the list.
  - Paths containing `/.archive/` are always filtered out of Recent and Main views, preventing archived projects from appearing even if they entered the recent list.
- **Category headers**: Clickable "Open All" buttons for each category (light blue #3498db)
- **Item buttons**: Individual launchers with application icons. Drag to reorder within category or drag to a different category to move it (saves to config immediately).
- **Quick-add**: "+ Add" button in the launcher column header opens the add-launcher dialog targeting the first category. No need to enter edit mode. Default application is configurable via `default_app` setting.
- **Launcher search**: A search box in the launcher header (left of the Edit/Add buttons) filters visible items as you type. Matches against display name, path, and app/command name (case-insensitive). Categories with no matching items are hidden entirely. Clearing the box restores all items. Hidden automatically when in edit mode. Implemented via widget visibility toggling (no rebuild); references stored in `self._launcher_search_refs`.
- **Viewer tab buttons**: Notes, Web, Edit (the code editor — `column2_mode` stays `"code"` internally, only the tab label/status text reads "Edit"), Terminal (Console), PDF, Image, ⏱ Time. Each has a bundled white flat icon under `assets/tab-icons/{mode}.png` (webview/console/pdf/image/notes/code) rather than a `QIcon.fromTheme()` lookup — those proved unreliable across desktop environments/Nix setups (many common names resolved to nothing), so every tab now gets a guaranteed, consistent icon; tab buttons have a small 60px floor but otherwise stretch (`QSizePolicy.Expanding` + equal layout stretch factor) to fill the row's full width between them — a flat fixed width per button (previously 175px, matching the launcher tab row) started overflowing/clipping once Code brought the tab count to 6-7. ⏱ Time is the exception — still an emoji + text label, not a bundled icon — and only appears (appended last) when `kimai_url` + `kimai_token` are configured. The Terminal tab additionally always keeps a subtle border regardless of active state, to stand out slightly as built-in real-terminal/shell access. Help/Examples is deliberately not in this row — see Help viewer below. A single shared 📌 button sits at the end of this row (after the last tab) calling `set_viewer_as_default()` against whichever tab is currently active (`self.column2_mode`) — this replaced individual 📌 buttons that used to live in each viewer's own toolbar (PDF/webview/image/console/notes/time), consolidated for consistency with the launcher tab row's single pin button (see Launcher Tab Bar below). The Folder viewer (internal/fallback mode, not part of this tab row) keeps its own separate 📌 in its toolbar, since it has no shared row to consolidate into.
- **Open-button icon** (`_open_icon()`): every file-picker "Open" button (Code editor, Notes, PDF, Image, Terminal's "Navigate to a directory") shares one plain single-color open-folder glyph instead of the previous mix of emoji (📂/📤) — those render as a yellow/manila Windows-style folder via most systems' color emoji font, inconsistent with the app's flat monochrome icon language used everywhere else (tab icons, `_folder_icon()`). Source SVG lives at `assets/icons/open-folder.svg`; two pre-rendered PNGs (`open-folder-light.png` at `#333333`, `open-folder-dark.png` at `#c0c0c0` — the theme's actual `fg_primary` values, not arbitrary black/white) are picked at runtime by `self.current_theme`, cached per-theme on the instance. Pre-rendered PNGs rather than `_folder_icon()`'s dynamic-QPainter-per-arbitrary-color approach because that method only ever needed one caller-supplied color at a time (e.g. the blue folder-browser icon); this needed a light-theme/dark-theme pair matched to the app's own text color, which a fixed two-variant lookup expresses more directly. Regenerate via `nix-shell -p librsvg --run "rsvg-convert -w 32 -h 32 <colored-svg> -o <name>.png"` after editing the source SVG's stroke color.
- **Kimai time viewer (⏱)**: Appears last when Kimai is configured. Shows recent time entries for the linked project in a table (Description/Date/Time/Duration), a period selector (Week/Month/3M/6M), a total-hours summary row, and a Log Time form (description, activity dropdown, date, from/to times). If no project is linked, shows "Link Kimai Project…" button instead. Pending Imports section appears below the log form when CSV files matching the project name exist in `kimai_csv_folder` — shows file details and an [Import] button that POSTs entries to Kimai and archives the CSV. Table header uses `fg_on_dark` on `bg_panel`; total row uses `fg_on_dark` on `bg_category` (readable in both light and dark themes).
- **Edit mode**: "✏️ Edit" button toggles edit mode — shows "Add Entry" buttons per category, "Add Category" at bottom, "Project Details" for the full settings editor, "🔍 Scan Docs" (see Per-Config Options), and the "⇄" path-mapping toggle (only shown here — it's an obscure per-project setting, kept out of the normal view to avoid confusion with the Focus layout toggle).
- **Title bar search**: Click the project title to enter search mode. Type to filter configs with autocomplete dropdown (case-insensitive substring match). Press Enter to switch to the first/selected match, or click elsewhere to cancel.
- **Archive buttons**: At bottom-right of notepad. "📥 Archive" saves notes with timestamp and clears notepad. "📜 View" opens archive dialog (greyed out when no archive exists).

### Focus Layout

An alternative two-column layout (Launchers | wide Viewer) for documentation-heavy work, toggled via the ⊞/▣ button in the title bar (right side, next to the path-mapping/edit controls).

- **Standard layout** (default): the usual three-column Launchers | Viewer | Notepad.
- **Focus layout**: Notepad is reparented into a "Notes" viewer tab (alongside Folder/Web/PDF/Image/Examples/Console); the right column collapses/hides; the splitter becomes `[launcher(1/3), viewer(2/3)]`.
- **Per-project persistence**: the chosen layout is written to the project's own config as `layout_mode` (see Per-Config Options) and restored automatically whenever that project is opened or switched to — implemented in `load_config()`/`toggle_layout_mode()`/`_save_layout_mode_to_config()`.
- **Interaction inversion**: in Focus layout, clicking a launcher that would normally open externally (web link, image, PDF, local `.md`/`.html`) instead routes into the built-in viewer via `switch_to_viewer_mode()` — implemented as a routing block at the top of `open_in_app()`. The small preview buttons (🌐/🖼️/📄) invert accordingly, becoming "open externally" (pass `force_external=True` to `open_in_app()` to bypass the routing).
- **Focus layout defaults the launcher column to Group-by-Type** (see below) — set in `load_config()` alongside `layout_mode`, but only when actually switching projects (tracked via `self._group_default_applied_for`) so a manual Group-by-Type toggle during the same session on the same project isn't silently reverted by an unrelated refresh.
- Splitter sizes are tracked separately per layout (`splitter_state` vs `splitter_state_focus` in settings) so resizing one layout doesn't disturb the other.

### Launcher Tab Bar (Focus Layout)

The Focus-layout launcher column has a row of 4 tabs — **Docs / Resources / Files / Apps** (content tabs first, utility tabs last — deliberately not construction order, see `_build_apps_tab_items` etc. for where each is actually defined) — styled with the same blue (`bg_category`/`bg_category_hover`) used by the category header bars these tabs switch between, not the wide-viewer tab row's green (the two rows sit in adjacent columns, visually separated by the 📌 pin button — see below — at the end of this row rather than a dedicated spacer). Active tab is `self.active_launcher_tab` (`"files"`/`"docs"`/`"resources"`/`"apps"`), switched via `_switch_launcher_tab()`, persisted per-project (`active_launcher_tab` in the project config, see Per-Config Options — `_save_active_launcher_tab_to_config()`, defaults to `"files"` so it's omitted from clean configs). This replaced two separate older mechanisms — a standalone "File Browser" accordion toggle and the "☰ Group" toggle — unifying them into one tab selection. Standard layout is untouched: it still shows the plain launcher category list plus the legacy "☰ Group" toggle (see Group-by-Type Launcher View below), since it has no wide tab-styled viewer to visually match and no embedded file browser panel.
- Each of the 4 tabs has its own bundled white flat icon (`assets/tab-icons/{docs,resources,files,apps}.png`), same convention and pipeline as the wide-viewer tab row's icons (see Viewer tab buttons below — plain SVG source, `stroke="#FFFFFF"`, rendered to a 64px PNG via `rsvg-convert`, loaded with `setIconSize(QSize(16, 16))`). Docs is a two-page stack (distinct from the single folded-corner page used for the Notes viewer tab, since Docs covers multiple documentation files, not one note); Resources is the generic "layers" glyph; Files reuses the same open-folder path as the Open-button icon (see above) redrawn in fixed white rather than theme-matched light/dark, since these tab buttons always sit on the colored `bg_category` background, never a plain button background; Apps is a plain 2×2 grid.

- **Files tab**: renders the Quick File Browser Panel (below) via `_build_launcher_folder_panel()`, replacing the category list for that build.
- **Docs tab**: filters `_build_grouped_categories()`'s output down to the AI/Docs pooled buckets (see Group-by-Type Launcher View for the classifier) — the search box and "+ Add" button still show above it (no "☰ Group" button in Focus layout, the tabs subsume that role). Falls back to the raw `self.COLUMN_1` list while editing (deferred, see `ai/issues.md`).
- **Resources tab**: shows every real category from `_build_grouped_categories()`'s output except the AI/Docs buckets — real category names/headers, not one merged bucket. Fully editable (drag-reorder, rename, delete-category, add-entry) whether or not `self.edit_mode` is on, since these are real categories, not a pool.
- **Apps tab**: renders `_build_apps_tab()`, a curated per-project application grid — see below.
- Both Files and Apps replace the category list entirely (`hide_launchers_for_folder_panel` — the flag name predates the tab bar but now covers both tabs — also hides the search/add header row, since there's nothing to search/add to in either).
- **📌 pin button**: sits at the end of the tab row (after Apps) — its own visual separation from the viewer tab row now replaces the old dedicated 20px spacer, which was removed as redundant. Calls `_set_launcher_tab_as_default()`, writing `launcher_tab_default` (see Per-Config Options) into the project's own config — mirrors each viewer's own 📌 (`set_viewer_as_default()`/`column2_default`). When set, it overrides `active_launcher_tab`'s last-opened value on load (`load_config()`); with no pin, last-opened behavior is unchanged. No dynamic "currently pinned" highlight, matching every other 📌 button in the app. Also settable via the "Default Launcher Tab" field in Project Details (Project Defaults Tab).

#### Quick File Browser Panel

A file browser embedded in the launcher column (reached via the Files tab above). Lets you browse the filesystem from the narrow launcher column and pop files straight into the wide viewer next to it, without leaving Focus mode.

- **Shares state, not widgets**: reuses `self.folder_current_path`/`populate_folder_browser()`/`_scan_folder_entries()` — same navigation as the main folder-browsing infrastructure — but renders into its own `self.launcher_folder_browser` (tree) / `self.launcher_folder_icon_view` (icon grid, toggled via `self.launcher_folder_view_toggle_btn`, sharing the global `folder_view_mode` setting) inside a `self.launcher_folder_view_stack`. `_render_folder_tree()`/`_render_folder_icons()` both take an optional `target` widget for this reason.
- **Ordering gotcha**: this panel is built earlier in `build_main_content()`'s column-1 section than the main Folder-viewer-tab widgets (`folder_path_label`/`folder_browser`/`folder_icon_view`, built later in the "viewer panel" section). Since the active tab persists, a project can open directly onto the Files tab — before those main-viewer widgets exist. `populate_folder_browser()` scans and caches (`self._folder_raw_entries`/`self._folder_scan_error`) then delegates to `_render_folder_views_from_cache()`, which guards all four target widgets (main + launcher-panel, tree + icons) with `getattr(self, 'x', None) is not None` for this reason, not just the launcher-panel ones.
- **Click routing**: unlike the main folder browser's default click (navigate/xdg-open), clicking a file here always routes into the best built-in viewer via `_open_path_in_best_viewer()` (image/PDF/Markdown/Web by extension, else `xdg-open`) — that's the point of a browser embedded next to the viewer. Right-click still gets the full standard context menu (`_build_folder_context_menu()`, shared with the other folder-browsing surfaces), including plain "Open".
- **Toolbar**: Up / Home / Refresh / tree-or-icon-grid toggle, plus a path label — moved here from the (now tab-less) main Folder viewer's toolbar. Below the file list: a filter bar (`_build_folder_filter_bar()`, see Folder browser above) and an "Open in {file manager}" footer button (`folder_open_external()`).
- **Stale-widget-reference guard**: since these widgets are only (re)built when the Files tab is actually active, `build_main_content()` explicitly resets `launcher_folder_path_label`/`launcher_folder_browser`/`launcher_folder_icon_view`/`launcher_folder_view_stack`/`launcher_folder_view_toggle_btn`/`launcher_folder_filter_input` to `None` on every build *before* the conditional (re)construction — otherwise a different-tab refresh leaves these attributes pointing at widgets Qt already destroyed, and any later `getattr(self, 'x', None)`-guarded access (e.g. from `populate_folder_browser()`) raises `RuntimeError: wrapped C/C++ object ... has been deleted`.

#### Apps Tab

A curated, icon-grid mini app-launcher (large tiles, system-theme icons via `QIcon.fromTheme`) showing the real applications this specific project's own launchers reference — a focused per-project app-switcher, not a generic desktop menu.

- **Tile sourcing** (`_build_apps_tab_items()`): scans every item across the whole project (all real categories, not just the active bucket) and resolves each item's `app` value to a candidate tile, deduplicated by resolved binary name. Structural/path-action handlers are excluded (`npm`, `ssh_session`, `directorydev`, `alias`, `dolphin_tabs`, `tail_log`, `rsync_backup*`, `file_manager`, `konsole`/`terminal`, `default`/`browser`, and any custom handler with `"type": "shell"`) — those are actions on a specific path, not standalone apps to open blank, and stay reachable only via their normal launcher items in the Resources tab. The project's configured **Terminal** and **Editor** (`get_configured_terminal()`/`get_configured_editor()`) are always force-included regardless of whether any item literally uses them, merged into the same dedup set. Built-in content-viewer tiles (Markdown/PDF/Images) are added on top when the project actually has matching content (a local `.md`/`.pdf`/image-extension item, or `pdf_file`/`image_file` set). PDF/Image tiles just call `switch_to_viewer_mode()` since `pdf_file`/`image_file` already give those viewers known content to reveal; Markdown has no equivalent per-project default file, so its tile instead carries the first local `.md` item's actual path (`kind: 'markdown'`) and opens it directly via `_open_markdown_in_webview()` — calling `switch_to_viewer_mode('webview')` alone would just reveal whatever (if anything) was already loaded, which is normally nothing on a fresh project load.
- **Click behavior** (`_on_apps_tab_item_clicked()`): built-in viewer tiles call `switch_to_viewer_mode()`; external-app tiles reuse `open_in_app()` pointed at the project's own folder (`self.config_folder_path`) with `force_external=True` (bypassing Focus layout's normal content-type routing, since these tiles are explicitly meant to open the real external app — e.g. a plain folder path would otherwise get intercepted into the internal folder preview). Browser apps (firefox/chrome) get `"about:blank"` instead of the folder path, since their launch command always templates the path in as a URL, not a directory.
- **`setUniformItemSizes` gotcha**: the grid's `QListWidget` deliberately does **not** call `setUniformItemSizes(True)`, unlike the visually-similar folder icon grid above. The folder grid only ever shows one repeated icon (the same flat folder glyph), so uniform sizing never mattered; the Apps grid mixes items with a real system-theme icon and items whose icon lookup failed (empty `QIcon`) since not every resolved app name has a matching theme icon on every system. Empirically confirmed: with uniform sizing on, any item that has a real icon renders the icon but its text label vanishes entirely (Qt computes a uniform cell size from an inconsistent reference item and clips the label) — off, both icon and text render correctly regardless of icon presence. A related gotcha in `_theme_icon()`/`_scaled_icon()`: `QIcon.pixmap(size)` is only a size *request* for icon-engine-backed theme icons — it commonly returns the icon's native resolution unchanged (e.g. asking a 128px Firefox icon for 64px still returns 128px) rather than actually scaling, so the returned pixmap must be explicitly `.scaled()` down before wrapping in a fresh `QIcon`, not just re-requested at the desired size.

### Markdown Editor

Local `.md` files opened via the viewer (launcher click, folder browser, preview buttons, Focus-layout routing) open directly into a live WYSIWYG editor by default, rather than a static preview. The **Notes panel** (right column in Standard layout, a viewer tab in Focus layout) uses this exact same editor on its own dedicated instance — see "Two Muya sessions" below.

- Built on **Muya** (`@muyajs/core`), the standalone editor engine extracted from the [MarkText](https://github.com/marktext/marktext) project — a framework-agnostic browser library, embedded via `QWebEngineView` since it has no Python/Electron dependency of its own.
- Vendored as a pre-built UMD bundle under `assets/muya/` (`lib/umd/index.js` + `lib/assets/` + `lib/core.css`, plus `assets-shim.js` which maps the bundle's expected `window.__assets_*` globals to the vendored asset paths — required because the UMD build's browser-global code path expects an asset-loader to have already populated those, unlike its CJS/AMD paths). `assets/muya/editor.html` is the shell page that boots it, with the app's theme colors (`__PF_BG__`/`__PF_FG__`) and optional extra CSS (`__PF_EXTRA_CSS__`, used for the paper theme below) substituted in.
- **Autosave**: each Muya session has its own `QTimer` (~1.2s interval, see `MuyaSession` below) that polls the editor's own `json-change`-driven dirty flag (`window.__muyaIsDirty()`) and writes to disk via `window.__getMuyaMarkdown()` — no manual save button.
- **👁 Preview / ✏️ Edit** toggle buttons in the webview toolbar (main editor only — Notes has no preview mode) switch to/from the themed read-only rendering (`_open_markdown_preview()`, the original Qt-`QTextDocument`-based renderer). Switching to preview flushes the latest editor content first.
- `_open_markdown_in_webview(path)` is the stable entry point used everywhere in the codebase for the main viewer — it just calls `_open_markdown_in_muya_editor(path)`. Call `_open_markdown_preview(path)` directly for the read-only view.
- To regenerate the vendored bundle from source: see `packages/muya` in a checkout of the marktext monorepo, `pnpm --filter @muyajs/core build` (no need to install/build the rest of the monorepo — that requires a C toolchain for Electron native deps that this project doesn't need).

**Two Muya sessions:** `MuyaSession` (a small class bundling `webview`/`editing`/`path`/`pending_markdown`/`autosave_timer`) lets two independent Muya instances share the same bridge logic without stepping on each other:
- `self._muya_session` wraps `self.webview` — the main viewer, used for launcher-clicked/documentation `.md` files.
- `self._notes_muya_session` wraps `self.notes_webview` — a **second, independent, persistent `QWebEngineView`** dedicated to the Notes panel, created once in `__init__` and detached-then-readded on every rebuild via the exact same safe pattern as `self.webview` (see `init_ui()`'s `notes_webview.setParent(self)` before `setCentralWidget()` tears down the old tree). This was necessary because `QWebEngineView` breaks if moved via incremental `setParent(None)` after being shown — which is how the old `notes_panel` reparenting between Focus/Standard layouts used to work when Notes was a plain `QTextEdit`. `build_main_content()` now places `notes_panel` (containing `notes_webview`) directly into whichever container matches the current `self.layout_mode` at construction time — `_enter_focus_layout()`/`_enter_standard_layout()` no longer reparent it, and deliberately don't touch `notepad_column_widget.hide()` either (only `setMinimumWidth(0)`) since hiding it while it still contains the live `notes_webview`, moments before a full rebuild, previously left the webview stuck at a stale tiny size after being reparented into the fresh tree.
- Shared bridge methods (`_load_muya_shell`, `_open_path_in_muya_session`, `_muya_autosave_tick`, `_muya_save`) all take a `session` parameter. `_open_notes_in_muya()` is the notes-specific opener — it sources content from `self.notes_data` (already read by `load_notes()`) rather than re-reading the file, since the notes file may not exist yet for a brand-new project.
- Notes content only reloads into the webview when `(current_config_file, layout_mode, current_theme)` changes since the last load (`_notes_loaded_for` in `build_main_content()`) — not on every incidental refresh, since the paper theme (below) depends on layout and theme too.

**Notes/webview markdown consolidation (Focus layout only):** every "open this `.md` file" action in Focus layout (launcher click via `open_in_app()`, folder-browser click, right-click "Open in Markdown Editor", the Apps-tab markdown tile, the Quick File Browser Panel) routes through `_open_markdown_file(path)`, a layout-aware dispatcher — Focus layout sends it to `_open_note_in_notes_tab(path)` (the Notes tab), Standard layout keeps the pre-existing behavior (`_open_markdown_in_webview(path)`, the general webview). This replaced the previous behavior where *every* `.md` file except the project's own note opened in the general webview ("Web" tab) regardless of layout, which was most visibly redundant for the synthetic pinned "{Project} project notes" Docs entry (see Group-by-Type Launcher View below) — clicking it used to open the project's own note into the Web tab, right next to the Notes tab already showing that exact file.
- **`self.notes_md_path`** (init in `__init__` alongside `_notes_muya_session`) mirrors `webview_md_path`: `None` means "showing the project's own note"; any other value is an explicitly-opened arbitrary note. `_open_notes_in_muya()` checks it first — if set (and not equal to the project's own note path), it loads that file from disk via the already-generic `_open_path_in_muya_session()` (the same function the general webview uses, just pointed at `self._notes_muya_session`); otherwise it falls back to the existing `self.notes_data`-sourced project-note load.
- **Deliberately reset only in `switch_to_config()`, not in `load_notes()`** — `load_notes()` reruns on every incidental refresh (editing a launcher, toggling theme), and resetting there would reproduce the exact `webview_md_path`/`toggle_theme()` "gotcha" documented above (a workaround needed specifically because `load_notes()` unconditionally clears that variable). Since `_open_notes_in_muya()` itself is only re-triggered by the `_notes_loaded_for` gate (project/layout/theme change, not incidental edits), an explicitly-loaded note already survives incidental refreshes for free; resetting only on an actual project switch is what makes the Notes tab "always falls back to the project note once nothing else is loaded, but doesn't reset it every incidental refresh."
- **Focus-layout-only by design**: Standard layout's Notes column is a fixed pane in the permanent third splitter column, not a `column2_mode`/`switch_to_viewer_mode()` target at all — there is no "tab" to redirect other notes into without permanently displacing the always-visible project note, which would defeat the point of that column. `_open_markdown_file()`'s Standard branch is therefore a verbatim no-op passthrough to the pre-existing general-webview behavior.
- **New Notes toolbar** (`create_notes_toolbar()`, Focus layout only — `self.notes_current_label`/`notes_open_btn`/`notes_home_btn` are left `None` in Standard layout, and every toolbar-touching method guards on that): an "Open" file-picker button (`open_note_file()`, mirrors the Code editor's Open button — see Open-button icon below), a filename label (shows `"{Project Name} project notes"` when showing the project's own note, matching the pinned Docs entry's title, else the arbitrary note's filename), and a "🏠 Project Note" button (visible only when viewing something else, jumps back via `_open_note_in_notes_tab(self.get_notes_file_path())` — which naturally clears `notes_md_path` again through the same equality check). `_update_notes_toolbar()` refreshes the label/button and is called both at toolbar construction and from `_open_notes_in_muya()`.
  - **Archive/Joplin/external-editor controls hidden for arbitrary notes**: `archive_notes()`, `view_archive()`, `sync_to_joplin()`, and `open_note_in_external_editor()` are all hardcoded to the project's own `get_notes_file_path()`/`get_archive_file_path()` — none of them take a path parameter. Showing them while an arbitrary note is loaded in the Notes tab would silently act on the wrong file: `archive_notes()` in particular reads whatever's live in the webview (the arbitrary note) but writes it into the *project's* archive, then calls `save_notes("")`, wiping the *project's own* notes file to empty — real data loss, not just a stray-folder concern. These controls now live in one container, `self.notes_archive_section` (built once in `build_main_content()`, containing the archive/view/Joplin button row plus the "Open in {editor}" footer), toggled via `.setVisible(is_project_note)` from `_update_notes_toolbar()` — a live toggle rather than a build-time decision, since switching notes via `_open_note_in_notes_tab()` does not rebuild `notes_panel`, only re-runs `_open_notes_in_muya()`/`_update_notes_toolbar()`.

**Paper theme:** both Muya sessions render with a Typora/Documentary-style "paper card floating on a tinted page" look, via `_notes_paper_css()` injected as `extra_css` into the shell. Light mode uses specific user-supplied Documentary-theme colors (page `rgb(229,231,237)`, paper `rgba(240,240,240,·)`, ink `#263241`); dark mode uses a separate user-supplied palette (page `#141414`, paper `#363B40`, ink `#DEDEDE`, black shadow) — neither is derived from the app's own `themes.py` palette, they're independent, purpose-picked colors. Paper opacity is 90% in Standard layout, 80% in Focus layout. The `#editor` element gets `width: 90%` + `box-sizing: border-box` (padding-inclusive, to avoid a horizontal scrollbar) and `margin: 24px auto 48px` so it visibly floats with shadow on both sides rather than touching the viewport edge.
- **Theme-change gotcha**: `toggle_theme()` must capture whether a markdown file is open in the *general* viewer (`self._muya_session.editing` + `self.webview_md_path`) **before** calling `refresh_projects()`, not after — `refresh_projects()` → `load_notes()` unconditionally clears `webview_md_path`, and the general viewer isn't covered by the Notes-only `_notes_loaded_for` auto-reload, since its webview's base URL points at `assets/muya/` (not the `.md` file itself), so the pre-existing "restore `webview_url` on refresh" mechanism never recognizes it as markdown.
- **`ForceDarkMode` gotcha**: `self.webview`'s `QWebEngineSettings.WebAttribute.ForceDarkMode` (applied to force-darken plain web pages in dark theme) must be set explicitly both ways (`self.current_theme == "dark"`) every rebuild — it's a persistent WebEngine setting that only ever being set `True` (never `False`) left it stuck on permanently after the first switch to dark mode, affecting both plain web browsing and (since it shares `self.webview`) the general markdown viewer as an unwanted extra dark filter layered on top of the correctly-reloaded paper CSS.

### Code Editor

A separate internal editor for source code (JS/Python/HTML/CSS/PHP), reached via the viewer tab row's "Code" tab (`column2_mode == "code"`). Built on [CodeMirror 6](https://codemirror.net/), vendored the same way as Muya (a pre-built static bundle, no runtime JS build step), but deliberately its **own** container/session/tool rather than reusing `self.webview`'s Muya multiplexing — a code editor has no URL bar/back/forward relevance, matching how PDF/Image/Console/Notes/Time each get their own container in `column2_stack` rather than sharing one.

- **Comes with more than syntax highlighting**: `basicSetup` (the `codemirror` meta-package's bundled extension set, pulled in as-is rather than hand-assembled) wires up find & replace (Ctrl+F), find-next/previous (F3 / Ctrl+G), go to line (Ctrl+Alt+G), select-all-matches (Ctrl+Shift+L), select-next-occurrence/multi-cursor (Ctrl+D), code folding (Ctrl+Shift+[/], fold/unfold-all Ctrl+Alt+[/]), undo/redo (Ctrl+Z/Ctrl+Y), bracket matching, auto-close brackets/quotes, and basic keyword/snippet autocompletion (Ctrl+Space) — all for free, none of it hand-wired. Verified against the actual bundled `searchKeymap`/`foldKeymap`/`completionKeymap`/`historyKeymap` arrays (not assumed from memory) via a throwaway introspection build before documenting — see README.md's Features list for the user-facing summary. Not currently surfaced in the UI beyond the keyboard shortcuts themselves (e.g. no visible "Find" button) — CM6 draws its own find/goto-line panels inline in the editor when triggered.
- **Vendored bundle**: `assets/codemirror/lib/codemirror-bundle.js`, a single minified IIFE built from `codemirror-bundle-src/` (tracked in git — `package.json`/`rollup.config.js`/`entry.js` are small and hand-written, unlike the huge third-party `marktext-develop/` checkout used for Muya, so there's no reason to gitignore the source itself; only `codemirror-bundle-src/node_modules/` and `codemirror-bundle-src/dist/` are gitignored). Exposes a single global, `window.PFCodeMirror`, bundling core (`@codemirror/state`/`view`/`commands`/`language`, plus the `codemirror` meta-package for `basicSetup`) and the five official language packages (`@codemirror/lang-{javascript,python,html,css,php}`). Regenerate via `cd codemirror-bundle-src && npm install && npm run build`, then copy `dist/codemirror-bundle.js` over the committed one.
- **Shell page**: `assets/codemirror/editor.html`, structurally parallel to `assets/muya/editor.html` — same `__PF_BG__`/`__PF_FG__`/`__PF_EXTRA_CSS__` placeholder-substitution pattern, plus editor-specific placeholders (`__PF_FG_SECONDARY__`/`__PF_GUTTER_BG__`/`__PF_ACTIVE_LINE__`/`__PF_SELECTION__`/`__PF_IS_DARK__`/`__PF_SYNTAX_JSON__`) filled in by `_load_code_editor_shell()`. Exposes `window.__initCodeEditor(content, language)`/`__getCodeEditorContent()`/`__codeEditorIsDirty()`/`__codeEditorClearDirty()`. `language` is a short key (`js`/`py`/`html`/`css`/`php`) computed in **Python** (`_code_editor_language_for()`, extension → key) and passed in — the shell itself has zero extension-specific knowledge, matching how the Muya shell has zero Python-specific knowledge of what it's editing. An unrecognized extension still opens (plain text with line numbers), never refuses.
- **No autosave — Save button/Ctrl+S instead**: unlike Muya, there is no `autosave_timer`. It's easier to fat-finger an unwanted keystroke into a code file than into prose, so saving is always an explicit action. `CodeEditorSession` (parallel to `MuyaSession` but a genuinely separate class, not a shared base) has a `dirty_poll_timer` (~800ms) instead — `_code_editor_dirty_poll_tick()` uses it *only* to refresh the Save button's "💾 Save" / "💾 Save (unsaved changes)" label, never to write. `_code_editor_save()` is the **only** method in the whole feature that ever writes to disk, called from the toolbar Save button or Ctrl+S. Keeping the timer's absence structural (not just "don't call the write method") is deliberate — it's the guardrail against someone later wiring up autosave "for consistency" with Muya.
- **Ctrl+S**: the app already had a global `Ctrl+S` shortcut bound straight to `toggle_edit_mode()` (a pre-existing, unrelated binding — launcher edit mode, not file saving). Rather than adding a second competing shortcut on the same key sequence, `_on_global_ctrl_s()` now intercepts: saves the code editor first if it's the active viewer and editing, otherwise falls through to the original `toggle_edit_mode()` unchanged. The CM6 `keymap` in `entry.js`/`editor.html` also binds `Mod-s` to a no-op that returns `true`, purely to swallow the browser's native "Save Page As" behavior inside the `QWebEngineView` — there's no JS→Python push channel for it to call instead (see below).
- **No JS→Python push channel**: every Python↔JS interaction in this app (Muya's included) is Python-initiated `page().runJavaScript(js, callback)` — pull-based, never push. A `pfbridge://` URL scheme referenced in `assets/muya/editor.html` for link-click handling has no interceptor anywhere in `projectflow.py` and appears to be unfinished/dead — don't build on it. The code editor follows the same pull-only pattern throughout.
- **Theming**: reuses the `__PF_BG__`/`__PF_FG__` placeholder pattern, plus a CM6 `EditorView.theme({...})` for editor chrome (gutter/selection/active-line, sourced from existing `themes.py` keys — `bg_secondary` for gutter, `bg_category` for selection — rather than new theme-dict entries) and a small `HighlightStyle`/`syntaxHighlighting()` extension for syntax tokens. The syntax palette (keyword/string/comment, ~3 colors) is **hand-picked per theme**, independent of `themes.py`, the same reasoning as the Notes paper theme's hand-picked colors above — a 2-3 color accent scheme doesn't map cleanly onto the app's background/foreground palette, so it's picked to look right rather than derived. `_code_editor_syntax_colors()` holds the two palettes (light: GitHub-light-inspired `#cf222e`/`#0a3069`/`#6e7781`; dark: GitHub-dark-inspired `#ff7b72`/`#a5d6ff`/`#8b949e`).
- **`.html`/`.htm` stay rendered by default — code editing is opt-in via a Preview/Source toggle pair**, mirroring Muya's 👁 Preview / ✏️ Edit UX language: the webview toolbar's `"</> Edit Source"` button (visible only when a local `.html`/`.htm` file is currently rendered there, `_open_html_source_from_webview()`) switches into the code editor; the code editor toolbar's `"👁 Rendered"` button (visible only when the open file is `.html`/`.htm`, `_code_editor_switch_to_rendered()`, guards on unsaved changes first) switches back. `_handle_folder_item_activation()`/`open_in_app()`'s existing `.html` branches are untouched — this is purely additive, zero risk to the existing default-renders-HTML behavior.
- **New default routing for `.py`/`.js`/`.css`/`.php`**: these previously had no internal handling anywhere (silently fell through to `xdg-open`), so routing them into the code editor is a pure upgrade. Wired into `open_in_app()`'s Focus-layout interaction-inversion block (Focus layout only, mirroring `.md`'s existing asymmetry — Standard layout keeps opening these externally, same as today, no inline preview-icon button for them yet) and, unconditionally regardless of layout, into `_handle_folder_item_activation()`/`_open_path_in_best_viewer()` (the folder-browser click paths), since those already special-case `.md`/`.html` unconditionally too. `_CODE_ROUTE_EXTENSIONS` (a class attribute, `_CODE_EXT_LANGUAGE` minus `.html`/`.htm`) is the shared extension set for all three call sites.
- **Unsaved-changes guard**: `_confirm_discard_code_changes()` — `QMessageBox.question(...Yes|No...)`, the app's standing destructive-action-confirmation idiom — guards every way to lose a dirty code file: `closeEvent()` (now calls `event.ignore()` on cancel, a new behavior for that method — it previously never ignored the close event), `switch_to_config()` (aborts the switch on cancel), and `_open_code_file_in_editor()` itself (guards on entry when a *different* file is already open and dirty, so every click-routing/toggle call site gets this for free by going through that one stable entry point). Uses the timer-polled `session.dirty` flag directly (up to ~800ms stale) rather than a synchronous re-query — acceptable for a discard-confirmation on non-realtime paths, and avoids restructuring three call sites into async callback chains for a rare edge case.
- **Only one session/webview** (`self._code_session` wrapping `self.code_webview`, created once in `__init__` and detached-then-readded on every rebuild via the same safe pattern as `notes_webview`/`console_ttyd_webview`) — no second UI surface analogous to the Notes panel exists for code yet, so there's no reason to build a second persistent webview speculatively.
- **"Open in {editor}" footer button** (`open_code_file_in_external_editor()`, using the standard `_make_viewer_footer()` pattern shared with every other viewer's footer) opens the file as it currently exists **on disk** in the configured external editor (`get_configured_editor()`) — it doesn't touch or flush the internal editor's own unsaved state either way, matching how the equivalent PDF/image/folder footer buttons are simple fire-and-forget external opens with no discard-guard (nothing here is actually discarded, since it's a separate external window, not a replacement of the internal session).
- **Line-wrap toggle** ("↩ Wrap" in the toolbar, `code_wrap_btn`/`_code_editor_toggle_wrap()`): CM6's `basicSetup` leaves line wrapping off by default (long lines just scroll horizontally), which is the opposite of what most people expect from a document-style code viewer inside a desktop app. `EditorView.lineWrapping` lives in its own CM6 `Compartment` (`wrapCompartment` in `editor.html`, exposed as `window.__setCodeEditorWrap(enabled)`) so toggling it **reconfigures the live editor in place** rather than reloading the file — no lost undo history, no dirty-state disruption. Persisted per-machine as `settings['code_editor_wrap']` (default `True`), read fresh on every `__initCodeEditor()` call (`_on_code_editor_webview_load_finished`) and reflected in the toolbar button's initial checked-state — same "personal preference, not project content" reasoning as `viewer_height`/`folder_view_mode`.
- **"📂 Open" button** (`open_code_file()`, `QFileDialog.getOpenFileName()` filtered to common code extensions, mirrors `open_pdf_file()`/`open_image_file()`'s existing pattern): opens an arbitrary file not already referenced by the project, not just launcher/folder-browser-triggered files. The Notes panel gained the same button (`open_note_file()`) for the same reason — see "Notes/webview markdown consolidation" above.

### Group-by-Type Launcher View

A "🗂️ Group" toggle in the launcher column header (Standard layout only — Focus layout uses the Docs/Resources tabs above instead, sharing the same underlying classifier) dynamically splits every launcher into **Docs** (a pooled virtual bucket, see below) and **Resources** — which, unlike Docs, is *not* pooled: it's the project's real categories, shown under their own real names, filtered to hide only their doc-classified items — without ever modifying the project's category structure or JSON file.

- **Classifier** (`_classify_launcher_item()`): local file with a doc extension (`.md`/`.html`/`.htm`/`.pdf`/`.txt`, and not a website) → Docs; everything else stays visible under its real category (Resources). `_is_website_item()` (a `http(s)://` path or `firefox`/`chrome` app) is checked separately, used to exclude an item from Docs — items no longer get cross-category sorted (websites-first) now that Resources shows real per-category order instead of one pooled list.
- **AI/Docs stay pooled; Resources is real categories, not a pool**: `_build_grouped_categories()` (`projectflow.py`) still pools AI/Docs items from `self.COLUMN_1` into virtual buckets for rendering only, tracking true `(category_name, index)` in `self._group_view_origin` (keyed by object identity). Resources categories, by contrast, are returned under their real names with their **full, unfiltered** item lists — doc-classified items within them are recorded in `self._grouped_hidden_item_ids` (a transient, per-render set) so the render loop skips drawing just those items, without touching anyone's index. This means real categories rendered under Resources are genuinely the same data Standard layout edits directly — not a copy, not reindexed.
- **Drag-and-drop**: disabled only for the still-pooled AI/Docs blocks (`grouped_active = self._is_grouped_view_active() and category_name in ("AI", "Docs")` in the render loop) — real Resources categories get full `DraggableItemButton`/`CategoryDropZone` drag-and-drop, identical to Standard layout's normal categories, since there's no pooling ambiguity to protect against. `CategoryDropZone._get_drop_index()` returns the true `item_idx` from `self.item_widgets` rather than the visual loop position, specifically so this stays correct when a category has hidden (doc-classified) items interspersed among its visible ones.
- **Editing while in this view**: `_is_grouped_view_active()` no longer blanket-disables itself during `self.edit_mode` — Docs and Resources both stay on `_build_grouped_categories()`'s output regardless of `edit_mode` (`build_main_content()`'s tab dispatch checks `active_launcher_tab in ("docs", "resources")`, not `not edit_mode`). Resources categories are real, so they're fully editable outright; Docs mixes a real "Docs" category (equally fully editable) with still-pooled AI/discovered items (👁 hide toggle only). Only Files/Apps still fall back to the raw, un-grouped `self.COLUMN_1` list while editing — there's nothing meaningful to manage on those tabs. The Files/Docs/Resources/Apps tab bar itself is always visible in Focus layout, including during edit mode. `build_main_content()`'s Standard-layout dispatch branch (`elif ... self.group_by_type:`) explicitly excludes `self.layout_mode == "focus"` — Focus-layout projects default `group_by_type` to `True` too (a vestigial value no longer used for its own display, see the per-project persistence bullet below), and without that guard it would incorrectly hijack Focus's own tab dispatch whenever that falls through unhandled (Files/Apps while editing) — this was the root cause of an early bug where entering edit mode on the Docs tab showed unrelated Resources-style content instead.
- **A real "Docs" category**: a category literally named `"Docs"` in `self.COLUMN_1` is a special case in `_build_grouped_categories()` — every item in it goes straight into the pooled Docs bucket with its **true** origin `("Docs", idx)` (no classifier, never hidden), the one intentional place a real category name and a pooled bucket name coincide. This makes it fully editable (drag/rename/delete/add-entry) exactly like a Resources category, merged seamlessly into the same Docs bucket that also shows the still-pooled AI section and dynamically-discovered doc items from other categories. The render loop's per-item `grouped_active` check is therefore per-*item*, not per-category, for the Docs bucket specifically: `category_name == "AI" or (category_name == "Docs" and true_category != "Docs")` — only items whose true origin is the real Docs category get full drag capability. A "➕ Create Docs Category" button (shown in edit mode whenever no real "Docs" category exists yet, next to "➕ Add Category") creates it empty via `_create_docs_category()` — no other special-casing; renaming it away from "Docs" simply stops it being treated specially (re-creatable any time via the same button).
- **👁 Hide toggle**: every dynamically-discovered Docs item (AI items, and doc-typed files still physically living in another category — i.e. anything with `is_pooled` true) gets an inline 👁 button instead of drag/edit controls, since there's no single real category behind them to manage. **Edit-mode only** — curation controls have no place on the front end. In view mode the same slot instead shows the normal preview/open-externally icon any other launcher of that type would get (`_build_doc_preview_icon_button()`, scoped to the file shapes `_classify_launcher_item()`/AI discovery can actually pool: local `.md`/`.html`/`.htm` — a `.pdf`/`.txt` doc item gets no icon there either, same as such items get none in the main per-item render branch). AI items call `_toggle_ai_item_hidden()`, storing hidden paths in `.projectflow_settings.json`'s `ai_hidden_paths[<config path>]` (checked by `_get_ai_category_items()`) — a personal declutter preference, never written to the project file. Other pooled items call `_hide_pooled_doc_item()`, setting a third grouping-override value, `'Hidden'` (alongside the existing `'Docs'`/`'Resources'`), which `_build_grouped_categories()` excludes from both the Docs pool and the item's real category's Resources rendering. The pinned notes entry (see below) deliberately never gets this button — hiding it wouldn't take effect anyway, since its insertion into the Docs bucket bypasses the override check entirely. Hidden items are fully removed from view (not dimmed) — the only way back is the "👁 N hidden — Manage" button, likewise edit-mode-only, which opens a minimal `_show_hidden_items_dialog()` (plain list + "Show Again", modeled on the View Archive dialog's simplicity) backed by `_get_all_hidden_items()`/`_unhide_item()`.
  - **Render-loop gotcha**: an item pooled into Docs is added to *both* `buckets['Docs']` and `self._grouped_hidden_item_ids` (the latter so its real Resources category skips drawing the duplicate) — the render loop's early `if id(item) in self._grouped_hidden_item_ids: continue` therefore needs a `category_name != "Docs"` guard, otherwise the Docs bucket's own render pass immediately skips every item it just pooled in, silently dropping them from view (AI items were unaffected, since they're never added to this set — the bug only showed up for doc files discovered pooled from elsewhere).
- **"📁 Move to category"**: `_show_launcher_context_menu()`'s old cosmetic "Move display to" (Docs/Resources-only classification override) is now a real, physical move to *any* existing category, populated from `self.COLUMN_1`'s real category names and executed via the same `handle_item_move_to_category()` that already backs drag-and-drop cross-category moves. This is how a dynamically-pooled item gets "promoted" to fully editable — moving it into the real "Docs" category (or anywhere else) relocates it for good. The old `'Docs'`/`'Resources'` override values, no longer settable from this menu, still work as pure classification hints for any project that already has them saved (`_get_grouping_override()`'s existing back-compat mapping is the natural home for this).
- **Per-project persistence**: toggling Group-by-Type writes `"group_by_type": true/false` into the project's own config file (`_save_group_by_type_to_config()`, mirrors `_save_layout_mode_to_config()`), and `load_config()` reads it back on the next open of that project. If a project has never had the toggle touched (key absent), it falls back to the layout-linked default — on automatically for Focus layout, off for Standard. (Focus layout no longer actually uses this value for display — the launcher tab bar's own `active_launcher_tab` took over that role — but the setting/toggle logic itself wasn't removed, since Standard layout still depends on it.)
- **Pinned notes entry**: `_build_grouped_categories()` always inserts a synthetic, non-editable item titled `"{Project Name} project notes"` (path = `get_notes_file_path()`, app = `"default"`) as the *first* entry in the Docs bucket — a second way to reach the same file as the Notes panel/tab, deliberately overlapping with it. Because of this the Docs bucket (and therefore the Focus-layout Docs tab) is never empty, even for a project with zero authored doc items. It rides the same click path as any other local `.md` Docs item (Focus layout opens it via `open_in_app()`'s routing → `_open_markdown_file()` → `_open_note_in_notes_tab()`, landing in the already-existing Notes tab rather than a separate Web-tab session, per the Notes/webview consolidation above; Standard layout opens it externally, with the usual 📄 preview button for the built-in editor) — no dedicated click handler. It's excluded from edit/delete/drag/"Move to category" via a sentinel origin (`self._group_view_origin[id(item)] = (None, None)`); the render loop skips wiring `_wire_launcher_context_menu()` whenever the resolved origin's category is `None`.
- **Automatic AI category**: if the project's default folder (`config_folder_path`) contains an `ai/` subfolder (see `~/Templates/ai/.instructions.md`'s human/AI-shared-docs convention), `_build_grouped_categories()` surfaces an **AI** bucket — always rendered above Docs — via `_get_ai_category_items()`: every non-dotfile file directly inside `ai/`, plus whichever of `CLAUDE.md`/`AGENTS.md`/`CHANGELOG.md`/`Specification.md`/`SPEC.md` exist at the project root (matched case-insensitively against what's actually on disk). Live/dynamic like the pinned notes entry — computed fresh from the filesystem every render, nothing written to the project JSON, same `(None, None)` sentinel origin (no edit/delete/drag/"Move to category"). Any authored `COLUMN_1` item whose resolved path matches one already surfaced in AI is skipped when building Docs/Resources, so nothing appears twice. Absent entirely (no empty header shown) for the common case of a project with no `ai/` folder.
- **Open Project Folder footer**: a `_make_viewer_footer()` strip reading "Open Project Folder in {file manager}" is inserted right below the Docs category's item list (`open_project_folder_external()`), whenever `config_folder_path` is set and not in edit mode. Deliberately labeled "Open Project Folder" rather than "Open in {file manager}" alone, since the project's default folder isn't necessarily where any given document in the list actually lives — it's a shortcut to the pinned project folder, not to "wherever these docs are."

### Theme System

The app supports light and dark themes, defined in `themes.py`. Toggle via the 🌙/☀️ button at the bottom.

**Theme settings:**
- `"system"` (default): Follows desktop dark/light preference
- `"light"`: Light theme with grey/blue/green accents
- `"dark"`: Dark theme with navy blue panels (#0C2958) on off-black background (#070414)

**Theme architecture:**
- `themes.py`: Contains `THEMES` dict with `"light"` and `"dark"` color schemes
- `init_theme()`: Initializes theme from settings or system preference
- `t(key)`: Helper method to get theme color by key (e.g., `self.t('bg_panel')`)
- `toggle_theme()`: Switches between light/dark and refreshes UI

**Key theme color keys:**
- `bg_primary`, `bg_secondary`: Main backgrounds
- `bg_panel`: Column/section headers
- `bg_button`, `bg_button_hover`: Toolbar buttons
- `bg_category`, `bg_category_hover`: Category headers
- `bg_navy`, `bg_green_1` to `bg_green_4`: Bottom action buttons
- `fg_primary`, `fg_secondary`, `fg_on_dark`: Text colors
- `border`, `border_dark`, `border_light`: Border colors
- `bg_viewer`: PDF/image viewer background
- `bg_help`, `fg_help_h1`, `fg_help_h2`, `fg_help_h3`: Help viewer colors
- `bg_code_inline`, `border_help_h1`, `border_help_h2`: Help markdown styling

**Viewer dark mode:**
- **PDF viewer**: Inverts colors in dark mode for readability (white pages become dark)
- **Image viewer**: Uses theme background color
- **Help viewer**: Full theme support with dark backgrounds and light text
- **Webview**: Uses Qt's `ForceDarkMode` setting when in dark theme
- Applies browser-level dark filter to web pages

**Design Principles:**
- Compact layout with minimal vertical space
- Clear visual hierarchy through color and size
- Consistent cool color palette (greys, blues, greens in light; navy/purple in dark)
- Current selection indicated by size and border rather than drastically different colors

### Settings Dialog

Access via the ⚙️ button in the footer. The dialog has five tabs:

**Project Defaults Tab** - Configure viewer defaults for the current config:
- Default Viewer: Select which viewer opens by default (notes, webview, console, pdf, image, code, time, help — ordered to match the viewer tab row, with help appended last since it isn't a tab)
- Default Launcher Tab: Pin a fixed Focus-layout launcher tab (docs, resources, files, apps) — see `launcher_tab_default` in Per-Config Options; blank falls back to last-opened
- PDF File: Path to default PDF file with browse button
- Web URL: Default URL for webview
- Image File: Path to default image with browse button
- Console Path: Working directory for embedded console with browse button

**Integrations Tab** - Third-party service configuration:
- **Kimai section**: Server URL (base URL, `/api` suffix auto-stripped), API Token, CSV Import Folder
- **Joplin section**: API Token for Joplin Web Clipper sync
- Settings saved to `.projectflow_settings.json` as `kimai_url`, `kimai_token`, `kimai_csv_folder`, `joplin_token`

**Icon Preferences Tab** - Manage `icon_preferences.json` entries:
- Lists all application icon mappings with icon preview, app key, display name, and icon name
- **Add**: Create new icon preference entry
- **Edit**: Modify selected entry's display name and icon
- **Delete**: Remove selected entry

**Launch Handlers Tab** - Manage custom launch handlers:
- Lists all handlers with type badges: [Custom], [Built-in], [Python]
- **Add Handler**: Create new custom handler
- **Edit Selected**: Edit custom handlers (disabled for built-in/Python handlers)
- **Delete Selected**: Remove custom handler (disabled for built-in/Python handlers)
- **Copy as Custom**: Copy a built-in handler to customize it (allows overriding)
- Double-click to edit custom handlers
- Handler edit dialog includes: name, command, type (exec/shell), terminal options, description

**Advanced Settings Tab** - Edit `.projectflow_settings.json` global options:
- **Theme**: Dropdown to select "System", "Light", or "Dark"
- **PDF Viewer**: Path to external PDF viewer application
- **Note Editor**: Command for external markdown editor
- **Terminal**: Terminal application for console external button (auto-detected if empty)
- **Editor**: Default code/text editor for directorydev handler (auto-detected if empty)
- **File Manager**: Default file manager for directorydev handler (auto-detected if empty)
- **Notes Folder**: Path where markdown notes are stored
- **Enable Baloo Tags**: Checkbox to enable/disable KDE Baloo tag integration
- *(Joplin Token moved to Integrations tab)*

**Button workflow:**
- **Apply**: Save changes without closing dialog
- **Cancel**: Discard changes and close
- **OK**: Save changes and close

The dialog is theme-aware and updates styling when theme changes.

## Development Notes

### Modifying the UI

The UI is dynamically generated from config data in `build_main_content()`. To change the layout structure, modify this method. The app rebuilds the entire UI on refresh rather than updating in place.

### Adding New Application Types

To support new application launch patterns, modify `open_in_app()` in projectflow.py:779. Add detection logic before the else clause for standard apps.

### Config File Location

Configs should be stored:
- **Recommended**: In the `projects/` subdirectory for organization and version control
- Alternatively: Anywhere on the filesystem (use "Load Config..." to select)

The standard default config is `projects/projectflow.json`.

## Code Organization Conventions

### Project Structure

```
projectflow/
├── projectflow.py              # Main application
├── themes.py                   # Light/dark theme color definitions
├── CLAUDE.md                   # Development documentation
├── .gitignore                  # Git exclusions
├── launch_handlers.py          # Built-in launch handlers (Python)
├── launch_handlers_custom.json # User-defined launch handlers (editable via UI)
├── icon_preferences.json       # App icon/name mappings
├── assets/muya/                # Vendored Muya markdown editor bundle (see Markdown Editor)
│   ├── editor.html              # Editor shell page loaded into QWebEngineView
│   └── lib/                     # Pre-built UMD bundle + assets + shim (see docs above)
├── projects/                   # Project files (synced via Nextcloud)
│   └── [project].json          # User-specific projects
├── notes/                      # Markdown notes (synced via Nextcloud)
│   └── [project-name].md       # Per-project notes
├── utilities/                  # Optional utility scripts
│   ├── add-projectflow-servicemenu.sh  # KDE service menu handler
│   ├── projectflow-servicemenu.desktop # KDE service menu definition
│   └── generate_menu_items.py  # Create KDE panel .desktop files
└── docs/                       # Development documentation
    └── build_specification.md  # Design specification
```

### Naming Conventions

- **Application name**: "ProjectFlow" (consolidated branding)
- **Main class**: `ProjectFlowApp`
- **Window titles**: Should reference "ProjectFlow"
- **Config files**: Use descriptive names (e.g., `myproject.json`, `work.json`)

### Version Control Patterns

**Files to commit:**
- Main application code (`projectflow.py`)
- Documentation (`CLAUDE.md`)
- Default/example projects in `projects/`
- Configuration affecting all users (`.gitignore`)

**Files to exclude (in `.gitignore`):**
- `.projectflow_settings.json` - Per-machine user preferences (auto-generated)
- Python cache files (`__pycache__/`, `*.pyc`)
- Editor-specific files (`.vscode/`, `.idea/`, `*.swp`)

### Code Cleanup Guidelines

When maintaining this codebase:

1. **Avoid hardcoded paths**: Never add user-specific or machine-specific paths directly in the code. Use configuration files instead.

2. **No silent side effects**: Methods like `refresh_projects()` should only do what their name implies. Avoid adding unrelated operations (file copying, network calls, etc.).

3. **Consistent branding**: All user-facing strings should use "ProjectFlow" naming consistently across:
   - Window titles
   - Application metadata
   - UI labels
   - Documentation

4. **Config organization**: Keep all configuration files in the `projects/` directory for clarity and to separate code from configuration.

5. **Remove duplicates**: If multiple config files are identical, consolidate to a single source of truth.

---

## Mobile App (Android Companion)

A personal Android companion app lives in `mobile/`. It connects to Nextcloud via WebDAV and mirrors the core ProjectFlow experience on mobile.

### Structure

```
mobile/
├── proxy.py              # Local CORS proxy for browser-based testing
├── webdav-test.html      # Standalone WebDAV test page
└── app/                  # Capacitor + Svelte app
    ├── resources/
    │   └── icon.svg                    # Master app icon (SVG); @capacitor/assets generates all mipmap sizes
    ├── src/
    │   ├── App.svelte                  # Root: shows Setup or Main; defines all CSS theme variables
    │   ├── components/
    │   │   ├── Setup.svelte            # First-run connection config + QR scanner + path alias
    │   │   ├── Main.svelte             # Project bar (pinned+recent) + ≡ picker + tab layout
    │   │   ├── ProjectPicker.svelte    # All-projects alphabetical grid with per-project pin toggle
    │   │   ├── Launchers.svelte        # Filtered launcher list + Links (viewers) section + NC↗ items
    │   │   ├── Notes.svelte            # Markdown viewer/editor
    │   │   ├── Viewers.svelte          # Unused (kept for reference; features merged into Launchers)
    │   │   └── QrScanner.svelte        # Camera overlay for Nextcloud QR scan
    │   └── lib/
    │       ├── store.js                # Svelte stores + async actions + pinned/recent ordering
    │       └── webdav.js               # WebDAV client + Nextcloud path resolver
    ├── android/
    │   └── app/src/main/java/eu/ruadesign/projectflow/
    │       ├── MainActivity.java       # Registers WebDavPlugin
    │       └── WebDavPlugin.java       # Custom OkHttp plugin for PROPFIND
    └── capacitor.config.json
```

### Key Technical Decisions

- **Custom `WebDavPlugin.java`**: Capacitor's built-in `CapacitorHttp` only accepts standard HTTP methods (GET, POST, PUT, etc.) — it rejects `PROPFIND` with a method enum error. `WebDavPlugin` wraps OkHttp directly, allowing arbitrary methods. Registered in `MainActivity.java`. `webdav.js` detects `Capacitor.isNativePlatform()` and routes through the plugin on Android, falling back to `fetch` in the browser.
- **CORS in browser testing**: Use `proxy.py` which forwards WebDAV requests to Nextcloud with CORS headers. Run with `python3 proxy.py https://your-nextcloud-url`. Set Server URL in the app to `http://localhost:8765`.
- **All config persisted**: Server URL, username, app password, folder paths, and optional path alias are all saved to `localStorage` so the setup screen is only needed once.
- **QR code setup**: Setup screen has a "Scan QR Code" button that opens the rear camera. Scans Nextcloud's `nc://login/server:...&user:...&password:...` QR code (shown when creating an app password) and auto-fills all three credential fields. Uses `jsqr` pure-JS library via `getUserMedia` — no native plugin needed, just CAMERA permission in `AndroidManifest.xml`.
- **No Viewers tab**: The Viewers tab was removed. The project's `webview_url` appears as a "Links (viewers)" section at the bottom of the Resources tab. External sites that block iframe embedding are not attempted.
- **Nextcloud path resolution** (`webdav.js: resolveToNextcloudRelPath`): Launcher items whose path contains `/Nextcloud/` (e.g. `~/Nextcloud/Projects/cop/guide.pdf`) are automatically detected as Nextcloud files. An optional path alias in Setup handles symlinked paths (e.g. `~/Projects` → `Projects` on Nextcloud). Detected items show **NC↗** and open the Nextcloud web files UI at the containing folder in the system browser.
- **Project ordering**: Top bar shows pinned projects first, then recently used (up to 8 total), stored in `localStorage` (`pf_pinned`, `pf_recent`). The `≡` button opens `ProjectPicker.svelte` — an alphabetical grid of all projects with per-item pin/unpin toggle.
- **App icon**: `resources/icon.svg` is the master source. `deploy_mobile.sh` runs `@capacitor/assets generate --android` on every build to regenerate all mipmap sizes automatically.
- **Responsive sizing**: `font-size: clamp(16px, 2.2vw, 26px)` on `html` provides fluid scaling. Each component also has `@media (min-width: 550px)` overrides for larger screens (tablets, e-ink readers like Boox) — phones (≤450px) are unaffected.
- **Theme system**: Full light/dark CSS variable system in `App.svelte`. Dark mode uses high-brightness text (`--t-primary: #ffffff`, `--t-sec: #f0f0f0`) for readability on e-ink screens. Theme persisted to `localStorage` (`pf_theme`). Toggle button (☀️/🌙) in the bottom nav bar.
- **Notes path is separate**: Projects live at one Nextcloud path (e.g. `ProjectFlow`), notes at another (e.g. `Notes/@Project Notes`). Both are configured in the Setup screen.

### Building the APK (NixOS)

Use the top-level `deploy_mobile.sh` script — it handles all steps automatically:

```bash
./deploy_mobile.sh
```

Steps: check ADB + Java → build web assets (`npm run build`) → regenerate Android icons from `resources/icon.svg` → sync to Android project (`cap sync android`) → build APK (Gradle) → install via ADB.

APK is at `mobile/app/android/app/build/outputs/apk/debug/app-debug.apk`.

### Setup Screen Configuration

| Field | Example value | Notes |
|---|---|---|
| Server URL | `https://your-nextcloud.example.com` | |
| Username | `youruser` | |
| App Password | `xxxx-xxxx-xxxx-xxxx` | Nextcloud → Settings → Security → App passwords |
| Projects folder | `ProjectFlow` | Folder containing `.json` project files |
| Notes folder | `Notes/@Project Notes` | Folder containing `.md` notes files |
| Local path prefix | `~/Projects` | Optional — for symlinks into Nextcloud |
| Nextcloud path | `Projects` | Optional — NC root-relative path the prefix resolves to |

The local path prefix + Nextcloud path pair handles symlinked directories. For example, if `~/Projects` is a symlink to `~/Nextcloud/Projects`, entering `~/Projects` / `Projects` lets the app detect launcher entries pointing to `~/Projects/cop/guide.pdf` as Nextcloud-accessible.
