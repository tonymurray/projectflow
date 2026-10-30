# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Shared Human/AI Documentation

@ai/context.md
@ai/issues.md
@ai/.instructions.md

## Project Overview

ProjectFlow (formerly "Folder Opener") is a PyQt6-based KDE Plasma application that provides a graphical launcher for quickly opening projects, files, and folders in various applications. It uses JSON configuration files to define categorized shortcuts. The app displays a three-panel layout: Viewer (left), Shortcuts (center), and Notepad (right).

## Running the Application

`projectflow.py` has a plain `#!/usr/bin/env python3` shebang — it does **not** auto-install dependencies itself. Three ways to get dependencies in place:

```bash
# NixOS: use the nix-shell wrapper, which provides Python 3.13 + all deps (including optional ttyd)
./projectflow-nix

# uv
uv venv && uv pip install PyQt6 PyQt6-WebEngine PyMuPDF qtconsole ipykernel
uv run projectflow.py

# pip (any Linux distro)
pip install -r requirements.txt   # or: pip install PyQt6 PyQt6-WebEngine PyMuPDF qtconsole ipykernel
./projectflow.py
```

`shell.nix` provides an equivalent `nix-shell` environment for interactive development (as opposed to `projectflow-nix`, which is the one-shot launcher wrapper). Both pull in `ttyd` as an optional dependency for the real-terminal Console backend (see `console_backend` setting below).

Pass a config path as the first CLI argument to open a specific project: `./projectflow.py projects/myproject.json` (or `./projectflow-nix projects/myproject.json`). A CLI-provided path always overrides the settings-driven startup logic below (see Configuration Loading Hierarchy).

An optional `--folder`/`-d <path>` flag opens straight to the Folder viewer at that directory: `./projectflow.py projects/myproject.json --folder ~/some/dir`. Transient only — sets `self.folder_current_path`/`self.column2_mode` directly in `ProjectFlowApp.__init__()` right after `load_notes()` (the function that would otherwise set `column2_mode` from the project's own saved/pinned state), so it wins on this one launch without ever writing anything to the project's config (`config_folder_path`/`folder_path` are untouched). This is what powers the **"Open Directory in ProjectFlow"** Dolphin service menu action (see Adding Resources below) — right-click a folder, pick an existing project, and a fresh instance opens there. Deliberately doesn't try to detect or reuse an already-open ProjectFlow window for this: there's no IPC between separate ProjectFlow processes, and window-focus detection would be unreliable on a Wayland session running ProjectFlow through XWayland anyway, so it always spawns a new instance instead — the same "just open it" precedent `open_config_in_new_window()`/"Add to ProjectFlow" already use.

## Configuration System Architecture

### Configuration Loading Hierarchy

`get_config_file_to_use()` determines which config to load with this priority:

1. **CLI argument** (`./projectflow.py projects/foo.json`) always wins if the path exists.
2. **`startup_mode` setting** (Settings tab → "Startup" dropdown; `"last_used"` default), one of:
   - `"specific"`: the exact path in `startup_project` (chosen from a project picker in Settings).
   - `"last_used"`: the `last_used_project` from settings (automatically tracked on every switch).
   - `"main"` (or any other value): falls through to the next step.
3. **Default config** (`default_project` setting, set via "Set as Default" button) — also the fallback when the `startup_mode` check above finds nothing.
4. **Standard default**: `projects/projectflow.json` (or whatever `projects_directory` is configured to) — created automatically from `examples/projectflow.json` on first run (`setup_first_run()`), or from `create_default_project()`'s built-in minimal template if `examples/` is missing or the file was otherwise deleted later. Always resolves inside the projects directory; there is no longer a separate project-root fallback location.

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
- `startup_mode`: Which project to open on launch — `"last_used"` (default), `"specific"` (use `startup_project`), or `"main"` (use `default_project`). Configured via the "Startup" dropdown in Settings → Settings tab. See Configuration Loading Hierarchy above.
- `startup_project`: Absolute path to the project to open when `startup_mode` is `"specific"`.
- `data_root`: Optional single root folder (e.g. `"~/Nextcloud/ProjectFlow"`) under which all four relocatable data folders — `projects/`, `notes/`, `documents/`, `images/` — live at once. Absent/empty = off. See "Relocatable Data Folders" below for the full 3-tier precedence (`_resolve_data_folder()`).
- `projects_directory` / `documents_folder` / `images_folder`: optional per-folder overrides for where each of those lives, same 3-tier resolution as `data_root`. See "Relocatable Data Folders" below.
- `last_used_project`: Most recently loaded project file
- `recent_projects`: List of up to 10 recently used main projects (for quick-access bar)
- `folder_projects`: List of up to 20 recently used `.projectflow` configs from folders (shown in separate "Folder Projects" section)
- `archived_folder_projects`: List of `.projectflow` paths that have been archived (hidden from Folder Projects; restored by moving back to `folder_projects`)
- `pinned_projects`: List of projects pinned to the front of the quick-access bar (drag to reorder/pin, ↺ to reset)
- `trusted_shared_projects`: List of `.projectflow` config paths this machine has explicitly trusted to run command-executing launchers (see UI Features → Sharing Projects). Local-only, machine-specific — deliberately never written into a project's own (synced) config file.
- `color_order`: Ordered list of color hex strings set by dragging swatches in the color strip. Drives the 🎨 sort order. Auto-pruned when colors are removed.
- `theme`: Color theme - `"light"`, `"dark"`, or `"system"` (default: `"system"` - follows desktop preference)
- `joplin_token`: Joplin Web Clipper API token (enables manual sync button in notepad toolbar)
- `speechnote_enabled`: Whether the Notes panel's "🎤 Dictate" button (voice dictation via the Speech Note flatpak, see UI Features → Voice Dictation) is shown. Default `false`. Also gated on the flatpak actually being installed (`_speechnote_available()`) — turning this on alone isn't enough to see the button. Configured via Settings → Integrations.
- `notes_folder`: Path where notes are stored as markdown files (default: `notes/` in project dir) — the original, longest-standing relocatable-folder override, still the one most likely to differ from the other three (e.g. pointed at a Nextcloud *Notes app's* own folder specifically).
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
- `backup_directory`: Root folder for the local backup feature (see Backup below). Absent/empty disables the feature entirely — no daily check, no folder-size lookups.
- `daily_backup_enabled`: Whether the once-per-day automatic backup runs at startup. Requires `backup_directory` to also be set — enabling this alone with no directory configured is a no-op.
- `backup_last_warned_unreachable`: Internal, not user-facing — a `YYYY-MM-DD` string used to throttle the "backup directory unreachable" modal warning to once per calendar day (see Backup below). Don't edit by hand.
- `folder_icon_pack`: Absent/empty (default) uses the app's own hand-drawn blue folder icon everywhere; set to an installed system icon theme's on-disk folder name (e.g. `"breeze-dark"`) to use that theme's own folder icon instead. Configured via Settings → Icons → "Folder Icon Pack" (dynamically populated from installed themes — see Folder browser above for why this is opt-in rather than the default).
- `check_for_updates`: Whether `_check_for_update_if_due()` pings GitHub's Releases API once per day at startup (default `true`). See Windows Packaging & Update Check below.
- `update_check_last_run`: Internal, not user-facing — a `YYYY-MM-DD` string throttling the update check to once per calendar day, the same pattern `backup_last_warned_unreachable` uses. Don't edit by hand.
- `enable_virtual_desktop_feature`: Whether the ⧉ "Open in New Virtual Desktop" button appears next to project buttons (default `true`). KDE-only regardless of this setting — see Settings Dialog → Features Tab below.

### Windows Packaging & Update Check

A `VERSION` file at the repo root (plain text, date-based — e.g. `2026.10.20`, matching this project's own CHANGELOG dating convention rather than semver) is the one source of truth for "what version is this build." `get_app_version(script_dir)` reads it (falling back to the deliberately unparseable `"dev"` if the file is missing); `_parse_version_tuple()` extracts every run of digits from a version/tag string via regex (not a `.`-split) so a leading `v` or un-padded numbers (`10` vs `2`) still compare correctly as real numbers, not per-digit.

- **`.github/workflows/windows-build.yml`**: builds the PyInstaller onedir package (`projectflow.spec`) on a `windows-latest` GitHub Actions runner — required, since PyInstaller can't cross-compile from Linux — whenever a `v*` tag is pushed (e.g. `git tag v2026.10.20 && git push --tags`), zips `dist\ProjectFlow`, and attaches it to a GitHub Release via `gh release create --generate-notes`. Deliberately tag-triggered rather than on every push to `master` — cutting a release is a separate, deliberate act, not something that should happen on every commit to an experimental, frequently-changing Windows port. `projectflow.spec`'s `datas` list bundles `VERSION` flat next to `ProjectFlow.exe`, same convention as `icon_preferences.json`.
- **`_check_for_update_if_due()`** (`projectflow.py`): called via `QTimer.singleShot(1500, ...)` from `__init__`, right after the (synchronous, local-filesystem-only) daily backup check — deliberately deferred rather than run inline, since a slow/unreachable network shouldn't delay the window's first paint. Throttled to once per calendar day via `update_check_last_run`, written *before* the network call so a hang/timeout still counts as "checked today" rather than retrying every launch. Pings GitHub's public, unauthenticated `.../releases/latest` API (4s timeout), compares the tag against the local `VERSION`, and on a newer release shows a plain **status-bar** hint with a link — never a modal — via `set_status()`. Fails completely silently on any exception (offline, rate-limited, no releases yet) — this is an optional ambient convenience, not something that should ever interrupt startup or show an error. No threading is used (matches this codebase's standing no-`QThread`/`QRunnable` convention, see Backup above) — a few seconds of main-thread blocking once the window is already up and interactive is the accepted tradeoff over building a worker-thread path for a once-a-day optional check. Opt-out via Settings → Settings tab → "Check for Updates" (`check_for_updates`, default **on**).
- See `INSTALL_WINDOWS.md` (repo root) for the three user-facing install paths this enables: downloading the prebuilt release zip (Option A, no Python needed), running from source (Option B), or building the `.exe` yourself (Option C, mirrors what the CI workflow does).

### Backup

A lightweight, local, zip-based safety net — added after a Nextcloud sync issue briefly caused real project config loss, so it's deliberately independent of whatever sync mechanism is otherwise in use. Configured entirely from Settings → Settings tab, in a "Backup" section right after Notes Folder.

- **Daily backup**: when `daily_backup_enabled` is on and `backup_directory` is set, `_run_daily_backup_if_needed()` runs once at startup (called right after `init_ui()` in `__init__` — it reports via `set_status()`, which needs `self.status_label`, not created until `init_ui()` runs) and writes `<backup_directory>/backup-YYYY-MM-DD.zip` containing the `projects_directory` tree (as `configs/`), the `notes_folder` tree (as `notes/`), the global Documents folder tree (`get_documents_folder()`, as `documents/`), the global Images folder tree (`get_images_folder()`, as `images/`), and `.projectflow_settings.json` itself at the zip root — `_perform_backup()`'s `sources` list is the single place all four folders are enumerated, each skipped via a plain `os.path.isdir()` check if absent, so a machine with no `documents/`/`images/` folder yet just gets a smaller zip rather than an error. Skipped silently if that day's zip already exists — if the app isn't opened on a given day, there's simply no backup for that day. No auto-pruning of old backups is done; the Settings tab shows the backup folder's total file count/size so old ones can be deleted manually.
- **Backup Now**: a button in the same section creates an additional, timestamped snapshot immediately (`snapshot-YYYY-MM-DD_HHMMSS.zip`) in `<backup_directory>/snapshots/`, via the same shared `_perform_backup(zip_path)` the daily check uses — this is the one place both callers share, so the zip-creation logic itself is written once. Two clicks within the same second get a `_2`/`_3`... suffix rather than silently overwriting each other. Reported via a `QMessageBox`, not just the status bar, since it's a deliberate user-triggered action.
- **Unreachable backup directory**: never fails silently — that would just reproduce the original sync-failure scenario this feature exists to guard against. The daily check first tries to create the directory if it doesn't exist yet (a freshly-typed, not-yet-created path is not the same as a genuinely unreachable one, e.g. an unmounted drive) via `os.makedirs()`, and only warns if that itself fails. `_warn_backup_dir_unreachable()` then shows one `QMessageBox` per calendar day (tracked via `backup_last_warned_unreachable`) and downgrades to a status-bar message on any further startup that same day, re-escalating to a modal the next day if still broken — a modal on every single startup while a drive stays unmounted for days would just train the user to reflexively dismiss it. Backup Now shows a modal warning every time with no throttling instead, since it's a synchronous, deliberate click, not an ambient background check.
- No threading is used anywhere in this feature — the codebase has no `QThread`/`QRunnable`/`threading` precedent at all. Config/notes folders are typically small, but since Documents/Images were folded in (2026-10-21) the zip can legitimately get large if those folders do — accepted deliberately (per the user: "potentially it will create a large archive, but that is fine") rather than threading the zip build or adding a size-based opt-out; `check_for_upgrade()`'s wait-cursor pattern is used for Backup Now so a slower synchronous zip at least doesn't look hung.

### Per-Config Options

These options can be set in individual config JSON files:
- `project_name`: Display name for the project (shown in title bar, window title). If not set, defaults to the config filename (without extension) or parent folder name for `.projectflow` files.
- `pdf_file`: Default PDF file to load for this config
- `webview_url`: Default URL to load in web viewer for this config
- `image_file`: Default image file to load for this config
- `code_file`: Default file to load in the internal code editor for this config. Set via the 📌 pin button in the viewer tab row (shared with pdf/webview/image/etc. — see Code Editor above), not via Project Details (no dedicated dialog field yet).
- `console_path`: Default directory for the embedded console
- `folder_path`: Default starting directory for the folder browser. For `.projectflow` configs this defaults to the config's own directory. Set via the 📌 pin button in the folder toolbar, or via the Project Settings viewer (see Project Details below).
- `column2_default`: Which viewer to show by default - `"pdf"`, `"webview"`, `"image"`, `"code"`, `"help"`, `"examples"`, `"console"`, `"folder"`, `"time"`, or `"notes"` (`"notes"` only has any effect in Focus layout, where Notes is one of the viewer tabs — Standard layout's Notes column is always shown regardless of this setting)
- `kimai_project_id`: Numeric Kimai project ID linked to this config. Set via the "Link Kimai Project…" button in the ⏱ viewer.
- `kimai_project_name`: Kimai project name (exact string). Used for CSV import matching — CSV rows whose `Project` column matches this are shown as "Pending Imports". Set automatically when linking via the picker.
- `terminal`: Terminal emulator override for this config (e.g., `"gnome-terminal"`, `"alacritty"`). Overrides global terminal setting.
- `browser_new_tab`: Override global `browser_new_tab` for this project. `true` = new tab, `false` = new window. Omit to inherit global setting.
- `notes_file`: Path to project-local notes file (e.g., `"./projectflow.md"`). When set, notes are loaded from this file instead of the global notes folder. Supports relative paths resolved from the config file location.
- `documents_subfolder`: Slug naming this project's own subfolder under the global Documents folder (see Documents Folder below), e.g. `"home_lab"` for a project named "Home Lab". Resolved and written automatically the first time it's needed (Docs toolbar button, "＋ New Note"/"＋ New File") — stored explicitly rather than recomputed from the project name each time, so a later rename doesn't orphan the folder or its contents. Not intended for manual editing.
- `viewer_tab_order`: This project's own drag-reordered viewer tab row order (Notes/To-Do/Editor/Terminal/Web/PDF/Image/Time — see Viewer tab buttons below), e.g. `["pdf", "notes", "code", ...]`. Omitted (or `[]`) means this project hasn't customized its own order, falling back to the global `viewer_tab_order` setting or the canonical order. Written automatically via drag-and-drop (`_reorder_tab_button()`) or cleared via the row's "↺" reset button — not intended for manual editing.
- `layout_mode`: `"focus"` to reopen this project in Focus layout (see UI Features → Focus Layout). Omitted (or any other value) means Standard layout. Written automatically when the "Use three columns view" checkbox in the Project Settings viewer (see below) is saved — not intended for manual editing. New projects created via `create_default_project()` or "Make Project" (`create_folder_project_config()`) now write `"focus"` explicitly; existing projects created before this change keep defaulting to Standard until toggled.
- `group_by_type`: `true`/`false` — remembers this project's last Group-by-Type launcher-view choice, **Standard layout only** (see UI Features → Group-by-Type Launcher View; Focus layout uses `active_launcher_tab` below instead). Omitted means "never explicitly set," which falls back to the layout-linked default (on for Focus, off for Standard — though Focus no longer visibly acts on this value). Written automatically when the "☰ Group" toggle is clicked — not intended for manual editing.
- `is_shared`: `true` if this project has been manually labeled as shared with someone else via a synced folder (see UI Features → Sharing Projects). A `.projectflow`-only field, set via the Project Settings viewer's "👥 This is a shared project" checkbox — never auto-detected. Gates command-executing launchers behind a separate, machine-local trust check (`trusted_shared_projects`, see Settings Persistence) rather than living in this same synced field, since a trust flag stored here could be silently flipped by anyone with folder access.
- `open_all_categories`: array of category names that have the "Open All" header button enabled (see UI Features → Category headers). Omitted or absent means no category has it — opt-in and off by default, including Documentation. Written automatically via the category header's right-click "Enable/Disable \"Open All\"" menu action — not intended for manual editing.
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
2. Click "Make Project" to create `.projectflow` and `projectflow.md` (a bare config — no launcher categories yet)
3. The project opens and the 🚀 Kickstart dialog appears automatically, pre-populated with everything detected in that folder (npm/Python/Git/Docker/etc., dev shortcuts, documentation) for review — see "Kickstart / Project Finder" below. Nothing is written to the project's categories until Apply is clicked.

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

### Sharing Projects

A `.projectflow` folder-project is already a fully self-contained, shareable unit — its config and notes live together in the project's own folder (never the personal `projects/`/`notes/` trees), so dropping that folder into a Nextcloud/Drive share already hands a collaborator everything they need. This section adds an explicit "Shared" label, a safeguard around what a shared project is allowed to run, and a path-resolution fallback for the common two-collaborators-two-different-absolute-paths case.

- **`is_shared`** (per-config, synced): a manual checkbox in the Project Settings viewer's "Sharing" row — **"👥 This is a shared project"**, `.projectflow`-only, never auto-detected.
- **Trust safeguard**: command-executing launcher items (`alias`/`run`/`terminal`/`ssh_session`/`npm`/`directorydev`/`rsync_backup*`/custom `"type": "shell"` handlers) are gated on a shared project until this specific machine has trusted it. `trusted_shared_projects` (local-only, never synced — if trust lived in the shared file, anyone with folder access could flip it) is granted either reactively (a "Shared Project — Untrusted" confirmation on first command-executing click, default Cancel) or proactively (a second "Trust this shared project" checkbox).
- **Automatic project-relative path fallback** (`_resolve_via_project_folder()`, a third tier in `_resolve_existing_path()` after the direct path and global path-mappings both fail): a launcher item's absolute path saved on userA's machine is simply wrong on userB's — this fix takes the basename of the *current* `config_folder_path` as an anchor, finds its **last** occurrence as a path segment in the broken path, and re-joins everything after it onto the current `config_folder_path`. Used only if the reconstructed path actually exists; never persisted. Applied unconditionally whenever `config_folder_path` is set, not gated on `is_shared` — equally useful for one person reorganizing their own projects across machines.
- **Discovery stays per-machine**: `folder_projects` is a local-only list — each collaborator independently discovers a shared project by browsing to the folder once.

### Adding Resources

Files and folders can be associated with a config in two ways:

1. **Service menu** (recommended): right-click files/folders in Dolphin → "Add to ProjectFlow" → select config. Creates entries in an "Added Resources" category (folders → Dolphin; images → gwenview with a 🖼️ preview button; other files → default application).
   - A second service menu action, **"Upload to ProjectFlow Docs"** (`utilities/upload-to-projectflow-docs.sh`) — the file-manager-side counterpart to the in-app "⬆ Upload Doc"/"⬆ Upload File" buttons (see Documents Folder below) — **copies** the selected file(s) into the target project's own `documents/<slug>/` folder (rather than just referencing them in place) and files each under that project's **"Project Files"** category. Reimplemented standalone (its own embedded Python, replicating the live app's slug-resolution/collision logic) rather than calling into a running `ProjectFlowApp` instance, since a KDE service menu always spawns a fresh process. Skips (doesn't overwrite) a same-name file in the target folder.
   - A third service menu action, **"Open Directory in ProjectFlow"** (`utilities/open-directory-in-projectflow.sh`) — right-click a folder (or a file, using its containing folder) → pick an existing project → launches a fresh ProjectFlow instance for that project with its Folder viewer pointed at that directory (via the `--folder` CLI flag). Doesn't create or modify anything, and doesn't try to detect/reuse an already-open ProjectFlow window (no IPC between processes, and unreliable under Wayland-via-XWayland regardless) — always spawns a new, detached instance. Launches via `projectflow-nix` when available (detected via `command -v nix-shell`), falling back to `projectflow.py` directly on a non-Nix install — needed because, unlike the other two actions (plain Python JSON I/O), this one starts the GUI app, and a Dolphin-spawned process on NixOS has no PyQt6 on its bare `python3`/PATH the way an already-`nix-shell`'d terminal does.
2. **Baloo tags** (automatic): tag files in Dolphin with the project's derived tag name (`get_tag_name_for_config()` — for `.projectflow` folder projects, this uses `project_name`/the parent folder name, since the filename is always literally `.projectflow`). Tagged files appear dynamically in a "Tagged Files" category (Focus layout: Resources tab only). `get_tagged_files()` excludes any tagged path that's already a real launcher item elsewhere in the project, to avoid rendering it twice. Settings → Integrations' "Create Baloo tags for all projects" button bootstraps a project's tag onto its own notes file, so it exists in Dolphin's autocomplete without hand-tagging first.

Install the service menu via `./utilities/install-servicemenu.sh` — copies `projectflow-servicemenu.desktop` to `~/.local/share/kio/servicemenus/` and rewrites its `Exec=` lines to this checkout's actual absolute path (the tracked file has no machine-specific path baked in, so a plain `cp` would leave unresolvable `Exec=` lines). Safe to re-run any time. No Dolphin restart needed — service menus are read live. A second, in-app equivalent exists: Settings dialog → Settings tab → "Install Dolphin Service Menu" (`install_kde_servicemenu()`, KDE only), same destination/rewrite contract, now kept in sync with the shell script's own regex so both installers always rewrite every action's `Exec=` line consistently.

*(Two real, since-fixed bugs from this feature's history — the in-app installer button that used to rewrite only the original action's `Exec` line, and an early `projectflow-nix`-vs-`projectflow.py` launch-portability bug in "Open Directory in ProjectFlow" — are recorded in `ai/CLAUDE_ARCHIVE.md` → "Adding Resources".)*

### Notes Storage

Notes are stored as markdown files in the configured `notes_folder`:
- Each config gets its own `.md` file (e.g., `work.json` → `work.md`)
- Notes edited live in Muya (see Markdown Editor below) and autosave on a ~1.2s poll of the editor's dirty flag — no manual save button
- Markdown format enables sync with Nextcloud Notes or any markdown-compatible tool
- Legacy HTML notes in JSON projects are automatically migrated to markdown files (`html_to_markdown()`, still used for this one-time migration path only)

### Relocatable Data Folders

The four personal-data folders — `projects/`, `notes/`, `documents/`, `images/` — all default to living inside the app's own install folder, but can each be redirected independently, or all at once via a single shared root, to a network/cloud-synced location (e.g. Nextcloud). Added because `notes_folder` used to be the *only* one of the four with any relocation support — `documents`/`images` were fully hardcoded, and `projects_directory` had a settings key but no UI field and ~26 call sites that bypassed its own getter.

- **`_resolve_data_folder(settings_dict, override_key, subfolder)`**: the one shared 3-tier resolver all four getters (`get_projects_directory()`/`get_notes_folder()`/`get_documents_folder()`/`get_images_folder()`) reduce to: (1) an explicit per-folder override if set; else (2) `<data_root>/<subfolder>` if `data_root` is set; else (3) `<script_dir>/<subfolder>`. Pure function of `settings_dict`, so it also previews not-yet-saved Settings-dialog values.
- **Settings → Settings tab, "Project Data Folder" cluster**: a single **Project Data Folder** field (`data_root`) for the simple case, plus an **"Advanced: configure each location separately"** checkbox revealing 4 individual override fields (Projects/Notes/Documents/Images Folder) via `QFormLayout.setRowVisible()` — pure UI disclosure, not a behavioral flag; opens pre-checked whenever any override is already saved.
- **Folder auto-creation on Apply/OK**: proactively `os.makedirs()`s all 4 resolved folders, warning (not silently failing) if any can't be created.
- **"📋 Copy Existing Data to New Location(s)"** (`_copy_data_to_new_locations()`): explicit, non-destructive, entirely separate from Apply/OK — compares each folder's currently-saved resolved path against what the dialog's not-yet-applied values would resolve to, and offers (default No) to `shutil.copytree()` any folder where that differs and the old path has real content. Exists for a user who's already created local projects before switching to a synced folder.
- **`setup_first_run()`** and the one-time legacy `configs/` → `projects/` migration both route through the same getters — the legacy migration uses `shutil.move()` instead of `os.rename()` since `projects_dir` can now resolve onto a network mount (`os.rename()` fails cross-device).
- **No automatic migration on a settings change alone** — only the explicit Copy button above copies anything.
- **`projects_directory`'s literal default needed a one-time migration**: `load_settings()` used to seed every fresh install with the literal `"projects_directory": "projects"`, which would always win tier 1 and permanently block `data_root`. Fixed by removing it from the defaults and adding a one-time migration step that deletes the key if it's still exactly `"projects"`.

*(A real `QFormLayout` row-height-overlap bug found while an earlier, more verbose version of this section's hint text was still in place — fixed via an explicit `setMinimumHeight()` floor — is recorded in `ai/CLAUDE_ARCHIVE.md` → "Relocatable Data Folders".)*

### Documents Folder

A per-project general-file store, separate from a project's own filesystem folder (`folder_path`) and the shared notes folder — a central place for project-related files (invoices, reference PDFs, exported reports). Mirrors the `images/`/`projects/` pattern.

- `get_documents_folder()` resolves via the same 3-tier precedence as the other relocatable folders (see above).
- Each project gets its own subfolder, `documents/<slug>/`, where `<slug>` is derived from the project's display name via `_slugify_project_name()` — resolved once and stored as `documents_subfolder` (see Per-Config Options) so a later rename doesn't orphan the folder. A slug collision between two projects gets a numeric suffix.
- `_get_or_create_project_documents_folder()` is the single resolver everything else goes through — creates the subfolder lazily, the first time it's actually needed.
- **"Project Files" shortcut** (Folder Browser's shortcuts row): `folder_go_project_documents(side)` resolves/creates the folder and navigates there — always shown, since a documents subfolder is always resolvable.
- **＋ New Note** (Notes toolbar) / **＋ New File** (Editor toolbar): prompt for a filename, create it directly in the documents folder, open it as a new tab, and file it as a launcher item — New Note under a new **"Notes"** category (pooled into the Docs bucket), New File under **"Project Files"** (plain Resources category). Both refresh folder views/launcher list immediately.
- **⬆ Upload Doc / ⬆ Upload File** (launcher header row): the file-picker counterpart — `QFileDialog.getOpenFileName()` picks an existing file, `shutil.copy2()`s it into the documents folder, and files it (Upload Doc → Documentation; Upload File → Project Files/Resources), sharing one `_upload_file_to_documents(category, dialog_title)` implementation. Warns (doesn't overwrite) on a same-name collision. In Focus layout, only the button matching the currently-active launcher tab (Docs vs. Resources) is shown, to avoid the ambiguity of "which bucket does this file into" — Standard layout shows both, with clarifying tooltips instead.
- **Creation timing**: eager for a brand-new project (created immediately after `switch_to_config()`); lazy for a pre-existing project (created on first real use of Docs/New Note/New File).
- `documents/` is gitignored, same as `projects/`/`notes/`/`images/`.

### To-Do

A per-project GFM checklist, `documents/<slug>/todo.md` (resolved via `_get_or_create_todo_file()` — no separate per-config field, since the location is always fully derived). Reuses **Muya's native interactive checkbox support** rather than any new UI: clicking a checkbox in the rendered view toggles `- [ ]`/`- [x]` directly in the markdown source, the same mechanism MarkText itself uses.

- **A third `MuyaSession`** (`self.todo_webview`/`_todo_muya_session`), simpler than Notes since there is always exactly one todo.md per project (no multi-tab machinery needed). Autosave uses the default ~1.2s interval (not Notes' lazier 15s), since prompt saving suits frequent quick checkbox-toggle edits.
- **"To-Do" viewer tab**, positioned right after Notes (`column2_mode == "todo"`). Its toolbar is just a single **"☑ Add Task"** button plus the webview and an "Open in {external editor}" footer button. Reload-gated on `(current_config_file, current_theme)`, mirroring Notes' own gate.
- **A brand-new todo.md is pre-seeded with one empty checklist item** (`TODO_STARTER_LINE = "- [ ] "`) rather than left truly blank, since an empty Muya document otherwise starts as a plain paragraph. The cursor seats right after this line on the file's very first open only.
- **Visually distinguished from Notes**: `_todo_paper_css()` layers its own pill-shaped checklist-row styling (light grey/dark teal-blue fill, "inky blue" text) on top of `_notes_paper_css()`'s paper structure, matched against reference screenshots for color/shape sense only. Checked rows fill with the app's established green accent and a white checkmark, plus strikethrough/dimmed text via `:has(.mu-checkbox-checked)`.
- **"☑ Add as To-Do" quick-capture**: a context-menu action on launcher items and Folder Browser entries, plus the To-Do tab's own "☑ Add Task" button, all prompting for a task title (pre-filled with the item's display name, editable). `_add_as_todo(title, source_path=None)` appends `- [ ] {title}` (plus a clickable `[source](file://...)` link when given a source) to todo.md — deliberately a plain markdown line, not a `COLUMN_1` launcher item, keeping todo.md the single source of truth for done/not-done state. **Session-aware**: if the To-Do tab is currently loaded, reads/writes the *live* (possibly unsaved) markdown via the Muya bridge rather than stale disk content.
- **Deliberately out of scope**: a cross-project aggregated "All To-Dos" view; third-party sync (CalDAV/Google Tasks); due dates/priority/structured metadata; a tab-button badge showing an open-item count.
- **Mobile app note**: the mobile app's own read-only `todo.md` viewer reads it relative to the project's linked Nextcloud folder, not this `documents/<slug>/` location — a known, not-yet-reconciled gap between desktop and mobile.

*(Two real rendering bugs found while building the checklist styling — a selector mismatch against Muya's actual `mu-`-prefixed classes, and a Chromium native-checkbox-paint quirk requiring a `::before`-on-the-row workaround since inputs don't generate pseudo-elements — are recorded in full, including the probe-script technique used to diagnose them, in `ai/CLAUDE_ARCHIVE.md` → "To-Do".)*

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
- `setup_first_run()`: Copies template files from `examples/` into `projects/`/the configured notes folder the first time the app runs (no-ops if `examples/` doesn't exist); also migrates a legacy `configs/` directory to `projects/` if found.
- `ensure_desktop_file_installed()`: Installs a base `.desktop` file to `~/.local/share/applications/` for GNOME/COSMIC dock icon matching (skipped on KDE, which doesn't need this — distinct from the per-project `.desktop` files created via `regenerate_desktop_file()`, see Project Settings Viewer → Integrations section's "Desktop Menu Entry").

**Configuration Management:**
- `load_config()`: Executes the Python config file and extracts variables
- `create_default_project(config_file)`: Generates a template project file — deliberately minimal (one Places item, one Websites item: Home + Wikipedia), kept in sync manually with `get_default_column_1()` (the in-memory equivalent) and `examples/projectflow.json` (the actual template `new_project()` copies when that file exists, which it normally does — `create_default_project()` is the fallback for when it's missing). More default links than that just gets deleted once a project has its own real launchers, so the starting point favors fewer over more.
- `switch_to_config(config_path)`: Switches to a different config and refreshes UI
- `refresh_projects()`: Reloads configuration and rebuilds the entire UI

**Kickstart / Project Finder** (see UI Features below for the full feature writeup):
- `_detect_project_indicators(folder_path)`: Shared detector — returns suggestion groups (npm/yarn/pnpm, Python, Rust, Go, Composer, Makefile, Docker, Git, README) for a folder
- `_build_dev_shortcut_suggestions(folder_path, combined)`: Returns either one combined `directorydev` suggestion or three separate editor/terminal/file-manager suggestions
- `_show_kickstart_dialog(folder_path=None, website_url="")`: Builds and shows the review dialog
- `_apply_kickstart_selections(...)`: Apply handler — writes checked items into `self.COLUMN_1`, optionally writes a project alias and/or website launcher, saves via `_save_project_config()`

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
- `get_tag_name_for_config()`: Derives Baloo tag name from config filename — special-cased for `.projectflow` (whose filename is always literally `.projectflow`, so this branches to `get_display_name_for_config_path()`'s own project_name-or-folder-name precedence instead; a real bug shipped briefly where every folder project got tagged `.projectflow` regardless of which project it was — see `ai/issues.md`)
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

- `__init__(parent)`: Creates tabbed dialog with Settings, Themes, Applications, Integrations, Icons, and Launch Handlers tabs
- `_create_settings_tab()`: Builds form for core `.projectflow_settings.json` options (startup behavior, launcher defaults, notes folder, path mappings) — theme and Muya heading colors live in the separate Themes tab instead
- `_create_themes_tab()`: Theme (system/light/dark) dropdown and Muya Notes/Markdown editor heading-color pickers
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
- `alias` - path = `"alias_name command_or_directory"` (the alias name is stripped before running; see below)
- `run` - path = a script/command to run as-is, optionally with trailing args (see below)

### `alias` / `run` — hardcoded, terminal-routed handlers

Both are handled directly in `open_in_app()` (not via `LAUNCH_HANDLERS`/`COMPLEX_HANDLERS`/custom handlers) and share one behavior: when the ttyd console backend is active, the launcher's **main click lands in the built-in Terminal viewer** (`_open_alias_launcher_in_console()`/`_open_run_launcher_in_console()`) instead of an external terminal — the one preview-icon inversion in this app that applies in **both** Standard and Focus layout (see Focus Layout → Interaction inversion above for why). Each item gets a small "$_" icon button next to it for "Open in external terminal" (`force_external=True`), and falls through to the always-external legacy behavior on the qtconsole backend (no live shell to paste into) or with the icon.

- **`alias`**: path = `"alias_name command_or_directory"` — the alias name (first word) is stripped and only used for the status message; the rest is parsed identically whether routed internally or externally: `cd <dir>` opens a shell at that directory, `cd <dir> && cmd` cd's outside the subshell then runs `cmd`, a plain directory opens a shell there, and a plain command runs then drops to an interactive prompt. This is the same format `_get_current_project_aliases()`/the ttyd toolbar's alias quick-jump buttons (see Embedded console below) already parse — those remain a *separate* mechanism (they act on the ACTIVE terminal tab, "do this in front of me"), whereas a launcher item click opens-or-reuses a tab at the resolved directory ("do this at this place"), matching `_open_terminal_launcher_in_console()`'s convention.
- **`run`**: path = a script/command run exactly as entered (e.g. `~/Programs/nixupdate.sh --check`) — no name prefix to strip, since the whole path *is* the command. The terminal (internal or external) lands in the script's own directory (`dirname` of the first whitespace-separated token) before running it, so relative paths inside the script and re-running from the resulting prompt behave as expected. Deliberately **not** wired into the shell-alias file/`projects/aliases.json` system (`_write_alias_to_file()`) — a `run` item is a per-launcher convenience, not something meant to be `source`d into a shell profile. Excluded from `_build_apps_tab_items()`'s `STRUCTURAL_APPS` set for the same reason `alias`/`terminal`/etc. are — it's an action on a specific path, not a standalone app to open blank.
- **Shell-name shadow guardrail**: naming an alias after a real shell builtin (most notably `cd`) is a real footgun — bash appends the alias's trailing invocation argument onto the alias's *own* command, so aliasing `cd` to e.g. `cd ~/some_folder` breaks every later bare `cd <dir>` anywhere else in the same shell ("too many arguments", since `cd`'s builtin takes at most one). `_classify_shell_name(name)` runs `bash -c 'type -t <name>'` against the real shell (rather than maintaining a static "top N commands" list — this reflects what's actually a builtin/keyword/PATH command/function on *this* machine, with no upkeep as commands come and go) and `_alias_shadow_warning(name)` turns a non-`alias`/non-empty classification into a human-readable warning. Existing **aliases** are deliberately exempt — redefining your own alias (e.g. `ls` → `ls -altr`) is normal and not what this guards against. Wired into both interactive alias-creation surfaces as a debounced (~400ms, since each check spawns a `bash` subprocess) live warning label as you type the name: the Add/Edit Item dialog (`_show_item_edit_dialog()`, shown only when Application is set to `alias`) and Kickstart's Project Alias field (`_show_kickstart_dialog()`, folded into its existing preview label). The Add/Edit Item dialog additionally re-checks and shows a Yes/No confirm (default No) right before writing on OK — declining only skips the `_write_alias_to_file()` call (the part that actually gets sourced into the real shell); the launcher item itself is still saved either way, since it's inert project data until sourced. Kickstart has no second confirm at Apply — its whole dialog is already a review-then-commit step, and the warning is visible before Apply is ever clicked.

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

- **Fullscreen mode**: `F11` toggles true window fullscreen (`toggle_fullscreen()`) via `WindowFullScreen` state, restoring the prior maximized/normal state on exit. `Escape` also exits (via `ProjectFlowApp.keyPressEvent()`, deferring to any focused widget that wants Escape first — `ClickableSearchTitle`'s search mode, an open `QDialog`). Every `QWebEngineView` in the app has HTML5 fullscreen wired through (`_enable_web_fullscreen_support()`) so embedded content (e.g. a video) can also drive window-level fullscreen. Not persisted across restarts.
- **Zen mode (immersive view)**: `Ctrl+F11` (`toggle_zen_mode()`) is a second, independent toggle. It collapses the launcher column (and, in Standard layout, the notepad column) via `setMinimumWidth(0)` *and* `setMaximumWidth(0)` on the collapsed columns — `setMinimumWidth(0)` alone isn't sufficient, since Qt's splitter falls back to a widget's `minimumSizeHint()` otherwise. It also hides nearly all chrome (title-bar buttons except the project title, footer, Projects section, viewer mode-tab row, every per-viewer toolbar/tab-strip/footer) via a tracked `self._immersive_hide_widgets` list rebuilt every `init_ui()` and re-applied via `_apply_zen_mode()` after every rebuild. A small "✕ Exit Immersive" title-bar button appears while active (built *after* the hide-collection loop so it's never added to the list it would hide). `Escape` does **not** exit zen mode (only `Ctrl+F11`/the exit button do) — zen mode leaves OS chrome visible, so there's no "stuck" scenario the way true fullscreen has. Not persisted across restarts. **Known gap**: the Kimai Time viewer has no toolbar/content split to hide, so it doesn't fully declutter.
- **Three-panel layout**: Viewer (left) | Shortcuts (center) | Notepad (right).
- **Viewer panel**: Tab buttons at top switch viewers (Notes, Editor, Terminal, Web, PDF, Image, Time). Each has its own toolbar with an "External" button. A small icon-only Files button (`folder_tab_btn`, between Time and the Settings cog) gives direct access to the Folder viewer in both layouts.
- **PDF fit-mode toggle**: the toolbar's fit button (`self.pdf_fit_btn`) cycles Fit Width → Fit Height → Fit Page (`pdf_toggle_fit_mode()`); `self.pdf_fit_mode` is per-session, not persisted. `pdf_apply_fit()` is the shared entry point every fit-triggering call site uses.
- **PDF footer paging controls**: `_build_pdf_footer_page_nav()` duplicates the toolbar's prev/page-indicator/next controls into the PDF footer strip; `self.pdf_page_label_bottom` mirrors `self.pdf_page_label`, both updated via `_set_pdf_page_label_text()`.
- **Viewer resize handle**: a draggable `ViewerResizeHandle` (`QLabel` subclass) below `column2_stack`, which uses `setFixedHeight()` (not a minimum, which the surrounding layout would otherwise stretch past) so dragging always has a visible effect. Saved per-machine as `viewer_height` (default `1000`).
- **Shortcuts panel**: Single column of categorized launchers with "Open All" buttons per category. Edit/Refresh buttons at top.
- **Notepad panel**: Same live Muya WYSIWYG editor as standalone `.md` files (see Markdown Editor below), on a dedicated persistent `notes_webview`. Rendered with a Typora-style "paper on page" look.
- **Folder browser** (via the viewer tab row's icon-only Files button, and the launcher-column Quick File Browser Panel): navigate the filesystem; folders with an existing `.projectflow` show a `[P]` badge and open directly. Toggle tree/details vs. a Dolphin-style icon grid (☰/⊞, `folder_view_mode`, shared across every folder-browsing surface). **Show Images** toggle (`folder_show_images`, off by default) renders real thumbnails for image files (`_get_image_thumbnail_icon()`, cached by `(path, mtime)` at a fixed 240px base, composited onto a square transparent canvas so mixed icon shapes don't break `setUniformItemSizes`); `.kra` isn't thumbnailed (a zip container, not natively decodable). Clicking `.html`/`.htm` opens the built-in webview; `.md` opens the built-in Muya editor; everything else uses `xdg-open`. Folder icons default to a hand-drawn flat blue icon (`_folder_icon()`) for consistent coloring across desktop environments; **opt-in** system icon-theme folders via Settings → Icons → "Folder Icon Pack" (`folder_icon_pack`, discovered via `_discover_icon_themes()`, resolved through `_folder_theme_icon()`, which brackets the process-global `QIcon.setThemeName()` override as tightly as possible). A Dolphin-style filter bar (`_build_folder_filter_bar()`) live-filters by filename, with shared state (`folder_filter_text`) between the main viewer and the launcher panel even though the two panels can browse different folders. Both surfaces have an "Open in {file manager}" footer button. A spelled-out **"Project Home"** shortcut jumps to the pinned `folder_path`; pin it via the toolbar's 📌 or the Project Settings viewer's "Folder Start Path" field. **Icon zoom** (icon-grid view only, Dolphin-style): `ICON_ZOOM_FACTORS` discrete steps (default index 3 = 1.0x) applied against per-side base sizes (`FOLDER_ICON_BASE`); changeable via a slider in the filter bar, Ctrl+scroll, or Ctrl+/Ctrl-/Ctrl+0; persisted as `folder_icon_zoom_index`. `populate_folder_browser()` expanduser()s its path argument unconditionally. Right-clicking empty space offers a **"New from Template"** submenu sourced from the freedesktop Templates folder (supports both plain files/folders and KDE/Dolphin `.desktop` `Type=Link` wrappers). `_build_folder_context_menu()` also offers Rename, "Add Baloo Tag...", Copy to.../Move to... (via `_copy_or_move_path()`), and two distinct "file this into a project" actions on files: **"Add to Documentation (link)..."** (references the file at its current, unchanged path, files under Documentation) vs. **"⬆ Upload to Project (copy)..."** (copies into that project's own `documents/<slug>/` folder first, files under "Project Files"). The launcher panel's own right-click menus add "Open in Right-Panel Viewer"/"Open This Folder in Right-Panel Viewer" (`allow_open_in_viewer`), sending a folder to the main viewer via `preview_in_folder_browser()`. **Independent left/right navigation**: the launcher panel and the main viewer browse genuinely independent folders via separate state (`folder_current_path` vs. `launcher_folder_current_path`), both funneling through `_populate_folder_side(path, side)`/`_render_folder_view_side(side)` — this is what makes real cross-panel drag-and-drop between two *different* folders meaningful. **Folder location shortcuts** row (above the toolbar on both surfaces, modeled on the Terminal toolbar's alias quick-jump buttons): "Project Home" first (if pinned), then up to 5 deduped file-manager-launcher-derived folders, plus an always-present, uncapped **"Project Files"** shortcut to the project's documents subfolder; each button highlights live when it matches the currently-browsed folder. An **"⬆ Add File..."** button copies an external file into whatever folder is currently browsed and files it under Project Files. Drag-and-drop works across all four folder-browsing widgets (tree + icon grid, both panels), encoded as real `file://` URLs (so dragging to/from a real file manager works too); dropping shows a Copy Here/Move Here/Cancel menu, reusing `_copy_or_move_path()`. A missing/unmounted folder shows a friendly inline message rather than a raw exception, with the icon grid temporarily switching to `ListMode` so the message isn't cramped into one grid cell. *(Several real historical Qt/drag-and-drop/thumbnailing bugs — the icon-grid drag never starting, a `QDropEvent.globalPosition()` crash, a non-square-thumbnail layout bug, and a max-zoom upscaling bug — and their fixes are recorded in `ai/CLAUDE_ARCHIVE.md` → "Folder browser".)*
- **`folder_current_path` sync**: the three places that interactively pin a *new* `config_folder_path` (Kickstart, Scan for Documents, the Project Settings viewer's "Folder Start Path" field) also set `self.folder_current_path` to match — otherwise the Files tab stays stuck on whatever it resolved to (e.g. Home) before a real folder was pinned.
- **Path-mapping fallback for missing paths** (`_resolve_existing_path()`): after the direct path and a `_resolve_via_project_folder()` project-relative re-anchor (see Sharing Projects) both fail, global `path_mappings` (Settings → Integrations) are tried as a last resort — **only when the direct path is missing**, never unconditionally, and the resolved path is never persisted back into any config file. Fires a "Path not found — opened via mapping instead" status-bar hint when it actually fires. A pale-blue badge/tooltip (`_style_folder_path_label()`, `get_item_button_style(mapped=True)`) marks a folder-browser path or a Documentation/Resources/AI launcher item that's currently showing via this fallback, so a silently-redirected path never looks like it worked by coincidence.
- **Help viewer** (`self.help_browser`, a `QWebEngineView`, opened via the title bar's "❓ Help" button — it's reference material, not a per-project viewer tab): assembled from `help/shell.html` (shared CSS + theme-color placeholders) plus auto-discovered `help/tabs/*.html` fragments (`_build_help_html()` — a leading `NN-` filename prefix controls order and is stripped for the tab label; dropping/renaming/deleting a file changes the tab bar with zero code changes). Tab switching is pure CSS (`:checked ~` sibling selectors) rather than JS `fetch()`, which is blocked for local `file://` origins in Chromium. Default tabs: Introduction, Launchers, Viewers, Handlers, Integrations, Settings, Example, Tips. `help/images/` ships empty (ready for screenshots, none added yet). `column2_default: "examples"` from old configs still maps to `"help"` for backward compatibility.
- **Embedded console**: IPython/qtconsole for quick Python and shell commands (`!ls`, `!git status`) by default — no interactive programs (nano/vim), use the External button for a full terminal. An optional real-PTY **ttyd** backend removes that limitation.
- **`console_backend` setting** (`"qtconsole"` default / `"ttyd"` / `"auto"`, Settings → Applications "Terminal Backend"): [`ttyd`](https://github.com/tsl0922/ttyd) is embedded per open terminal tab via a `QWebEngineView` loading its xterm.js web UI, spawned as `ttyd -i 127.0.0.1 -p 0 -W -O -w <cwd> <$SHELL>` (loopback-only; `-O`/`--check-origin` specifically blocks a cross-site-JS WebSocket-hijacking attack class seen against other unauthenticated localhost dev tools; `start_new_session=False` so it dies with the app, unlike this app's other, intentionally-outliving subprocess launches). `resolve_console_backend()` falls back to qtconsole if the `ttyd` binary isn't found (silently for `"auto"`, with a visible warning label/banner for an explicit `"ttyd"`). A tab is reused rather than duplicated when reopened at the same cwd (`_find_terminal_tab_for_cwd()`). When ttyd is active: `alias`/`run` launcher items (both layouts) and, in Focus layout, `terminal`/`konsole` launcher items and `.log`/`tail_log` items route their main click into a live terminal tab via a paste-and-submit mechanism (`_run_in_ttyd_when_ready()`/`_paste_and_submit_in_ttyd()` — empirically requires a per-tab `ready` flag, a further ~500ms settle delay after the WebSocket handshake, and an explicit (even no-op) JS callback on `runJavaScript`, each found to silently drop the paste otherwise) instead of spawning an external terminal; a small "$_" icon still opens one externally. Up to `ALIAS_TOOLBAR_LIMIT` (10) per-project alias quick-jump buttons appear in the toolbar, running the resolved command in the *active* terminal tab (overflow via a "+N" menu). Tailing a log is gated on the ttyd backend specifically, since qtconsole's blocking `!command` shell-out can't run `tail -f`.
- **Preview buttons**: Web links (firefox/chrome) show a 🌐 button to preview in the webview; images show 🖼️; local `.md` files show 📄 to open the built-in editor. In Focus layout these invert to "open externally" (see Focus Layout below).
- **"+ Add to Project" viewer footer button**: the PDF, Web, Image, Editor, and Folder viewers each get a footer button (`_add_viewer_item_to_project()`) that appends whatever's currently showing as a new launcher item in the open project, via a small Name/Category dialog (Documentation listed first, even if not yet created). Notes offers it only for an arbitrary open note, not the project's own (already represented by the pinned notes entry — see Group-by-Type below). Distinct from the Dolphin-service-menu `add_resource_to_project()` flow, which always targets a separately-chosen project's "Added Resources" category via direct disk I/O.
- **Project mega-menu (☰)**: a hamburger button at the top-left of the title bar opens a fast additional way to switch projects (`_show_project_mega_menu()`), via a `QWidgetAction`-embedded custom widget sized to ~90% of the screen and centered. Five columns: a combined **Pinned + Recent** column; **A to Z**; **By Color** (reusing the same custom `color_order` the 🎨 sort button uses); a combined **Folder Projects + Shared + Archived** column; and a combined **Within Projects (live cross-project content search) + Tasks** column. **Within Projects** debounces ~400ms, requires 3+ typed characters, and searches each project's notes text, `documents/<slug>/` filenames plus the content of a small allow-listed set of text extensions, and launcher item names (`_search_within_project()`) — scoped to all projects, capped at 5 match-lines/project and 20 matching projects, with no click-through on a match line yet. **Tasks** lists open checklist items from Pinned+Recent projects' own `todo.md` (`_get_project_pending_tasks()`, read-only — never creates a documents folder/todo.md as a side effect of merely opening the menu). Every column reuses the normal `_create_config_button()` (color bars, right-click context menu, open-in-new-window/desktop), now with an `on_select` callback so picking anything closes the menu — `QMenu` doesn't auto-close on a click inside a `QWidgetAction`'s custom widget otherwise.
- **Projects section**: unified project switcher with four modes — **Recent** (pinned + recent, up to 10, drag-reorder, ↺ reset), **Main Projects** (all of `projects/`, alphabetical rows of 10), **Folder Projects** (recently used `.projectflow` configs, up to 10), **Archive** (↩ restore per item, right-click for restore-or-permanent-delete). The whole section can be hidden (`show_projects_section`, default on) now that the mega-menu can fully replace it — toggled via a footer "▲/▸ Projects" button or a Settings-dialog checkbox, both staying in sync via a full rebuild.
- **Project color coding**: right-click a project → "🎨 Set Color..." (system color picker, pre-filled with every currently-assigned project color), or Settings dialog → Project Defaults tab. A 5px left-edge bar shows the assigned color. A swatch strip in the Projects header filters by color (click again to clear) or by "no color" (the striped swatch); drag swatches to set a custom priority order (`color_order`, drives the 🎨 color-sort button, auto-pruned when a color is no longer assigned to anything); a fixed grey swatch jumps to Archive mode. Stored as `project_color` directly in the project's own JSON/`.projectflow` file, so it travels with the project and syncs.
- **Project archiving**: right-click any project → archive. Main projects (`projects/*.json`) move to `projects/.archive/` (moved back on restore); `.projectflow` folder projects are never moved — archiving just delists them (`archived_folder_projects`), the file stays openable at any time. Archiving the currently open project auto-switches to another available one.
- **Category headers**: show the category name (light blue); right-click for Rename/Delete/"⚡ Enable/Disable \"Open All\"". "Open All" is **opt-in per category, off by default — including Documentation** (a category is just whatever's physically filed there, and `alias`/`run` items can execute arbitrary commands), persisted as `open_all_categories`; a second guard confirms before running any command-executing item even once enabled (`_items_with_command_execution()`). A small "+" icon next to the header adds directly into that category. Drag-to-reorder whole categories in edit mode via a `CategoryDragHandle` (⠿) onto another header — edit-mode-only, since that's the one place every category header has a consistent shape to attach a handle to. The header's right-click menu also offers "📄 Move to Docs"/"📂 Move to Resources" (`self.docs_categories`), which *pools* a category's items into the Group-by-Type Docs bucket display without renaming or merging the category itself — fully reversible.
- **Item buttons**: individual launchers with application icons; drag to reorder within a category or onto a different category to move it (saves immediately). While editing, clicking a launcher shows a status-bar hint instead of opening it (dragging to reorder/move is unaffected).
- **Quick-add**: "+ Add" in the launcher column header opens the add-launcher dialog targeting the first category, without needing edit mode — for a brand-new, zero-category project it auto-creates a starter "Resources" category first.
- **Launcher search**: a search box in the launcher header filters visible items live (name/path/app, case-insensitive); categories with no match are hidden entirely; hidden automatically while editing.
- **Viewer tab buttons**: Notes, Editor, Terminal, Web, PDF, Image, ⏱ Time (Kimai-gated, appended last) — ordered action-tabs-first (things you work in) then viewing-tabs (things you look at). Each has a bundled white flat icon (`assets/tab-icons/*.png`), since `QIcon.fromTheme()` proved unreliable across desktop environments/Nix setups. Tabs stretch to fill the row (`QSizePolicy.Expanding`) rather than a fixed width, which started overflowing once the tab count grew. **Drag-to-reorder** (`DraggableTabButton`, shared mechanism with the color-swatch strip) is persisted **per-project** (`viewer_tab_order`), falling back to a global preference then the canonical default via `_ordered_tab_ids()`, which backfills a newly-introduced tab id next to its nearest canonical neighbor rather than always appending it last. A tab for a content type this specific project hasn't used yet renders **de-emphasized** (muted colors, never disabled) via `_viewer_tab_has_content(mode)`, which checks both live session state (open tabs) and a persistent signal (e.g. a matching launcher item/pinned path) so a project with real but not-yet-opened content doesn't read as empty. One shared pin button (📌, end of the row) applies to whichever tab is currently active; a settings-cog shortcut sits right before it; a "↺" resets a customized order.
- **Open-button icon** (`_open_icon()`): every file-picker "Open" button (Code editor, Notes, PDF, Image, Terminal) shares one flat monochrome open-folder glyph (a theme-matched light/dark PNG pair rendered from `assets/icons/open-folder.svg`) instead of a mix of color emoji.
- **Pin-button icon**: the three icon-only 📌 pin buttons (launcher/viewer tab rows, Folder viewer toolbar) use a thumbtack glyph (Google Material Symbols "keep") — fixed-white when sitting on a colored tab-row background, theme-matched light/dark when sitting on a plain toolbar background.
- **Kimai time viewer (⏱)**: appears last when Kimai is configured. Time entries table, period selector (Week/Month/3M/6M), total-hours summary, a Log Time form, and a Pending Imports section sourced from CSV files in `kimai_csv_folder`.
- **Edit mode**: "✏️ Edit Project" (`toggle_edit_mode()`) enters edit mode and switches straight to the Project Settings viewer; becomes "💾 Save" to commit and exit (`_save_project_and_exit_edit_mode()`).
- **Title bar search**: click the project title to search by name (case-insensitive substring, autocomplete dropdown); indexes both `projects/*.json` and `.projectflow` folder projects.
- **Archive buttons**: at bottom-right of the notepad — "📥 Archive" (timestamp + clear notepad) / "📜 View" (read-only archive dialog, greyed out when empty).
### Focus Layout

An alternative two-column layout (Launchers | wide Viewer) for documentation-heavy work, toggled via the "Use three columns view" checkbox in the Project Settings Viewer (not a title-bar button — it's a per-project preference, see below).

- **Standard layout** (default): the usual three-column Launchers | Viewer | Notepad.
- **Focus layout**: the Notepad is reparented into a "Notes" viewer tab; the right column collapses/hides; the splitter becomes `[launcher(1/3), viewer(2/3)]`.
- **Per-project persistence**: written to the project's own config as `layout_mode` (see Per-Config Options), restored on open via `load_config()`/`toggle_layout_mode()`/`_save_layout_mode_to_config()`.
- **Interaction inversion**: in Focus layout, clicking a launcher that would normally open externally (web link, image, PDF, local `.md`/`.html`, `file_manager`/`dolphin`, and — ttyd backend only — `terminal`/`konsole`) instead routes into the built-in viewer via a routing block at the top of `open_in_app()`; the small preview icons (🌐/🖼️/📄/folder) invert accordingly to "open externally" (`force_external=True`). `alias`/`run` launchers are the one exception that route into the Terminal viewer in **both** layouts (ttyd backend only) — the Console tab exists in both layouts, so there's no "internal vs. external" distinction to invert there.
- Focus layout defaults the launcher column to Group-by-Type (see below), applied once per project switch (`self._group_default_applied_for`) so a manual toggle during the same session isn't silently reverted by an unrelated refresh.
- Splitter sizes are tracked separately per layout (`splitter_state` vs `splitter_state_focus`) so resizing one doesn't disturb the other.
### Launcher Tab Bar (Focus Layout)

The Focus-layout launcher column has a row of 4 tabs — **Docs / Resources / Files / Apps** — styled in the category-header blue (`bg_category`/`bg_category_hover`), replacing two older mechanisms (a standalone "File Browser" toggle and the "☰ Group" toggle). Standard layout is untouched — it still shows the plain category list plus the "☰ Group" toggle (see Group-by-Type Launcher View below).

- Each tab has its own bundled white flat icon (`assets/tab-icons/{docs,resources,files,apps}.png`), same pipeline as the wide-viewer tab row's icons.
- **Files tab**: renders the Quick File Browser Panel (`_build_launcher_folder_panel()`) — a second, independent folder browser sharing `populate_folder_browser()`'s navigation machinery but with its own `launcher_folder_current_path`/scan cache, letting it browse a different folder than the main Folder viewer at the same time (see "Independent left/right navigation" above). Toolbar: Up/Home/Refresh/tree-or-icon toggle + path label, plus a filter bar and an "Open in {file manager}" footer below the file list. Clicking a file here always routes into the best built-in viewer (`_open_path_in_best_viewer()` — image/PDF/Markdown/Web by extension, else `xdg-open`) rather than the main browser's default navigate/open behavior.
- **Docs tab**: the Group-by-Type Docs bucket (AI + the real Documentation category + the pinned notes entry) — fully editable where real (AI/pinned-notes stay read-only).
- **Resources tab**: every real category except the Docs bucket, shown under its own real name, fully editable regardless of `self.edit_mode`.
- **Apps tab**: `_build_apps_tab()` — a curated icon-grid app-switcher built from every real application this project's own launchers reference anywhere (deduped by resolved binary name; structural/path-action handlers like `npm`/`alias`/`run`/`directorydev`/`konsole` excluded, since those are actions on a path, not standalone apps), plus the project's configured Terminal/Editor always included, plus built-in Markdown/PDF/Image tiles when matching content exists. Tile click reuses `open_in_app()` with `force_external=True` for external apps, or `switch_to_viewer_mode()` for built-in viewers.
- Both Files and Apps replace the category list (and its search/add header row) entirely.
- Active tab (`self.active_launcher_tab`) persists per-project (`active_launcher_tab`, defaults `"files"`); a 📌 pin (`launcher_tab_default`) overrides last-opened behavior on load.
- **Drag-to-reorder** the tabs themselves (`DraggableTabButton`, shared mechanism with the color-swatch strip and the viewer tab row) is **per-machine** (`settings["launcher_tab_order"]`, default `[]` meaning canonical order), resolved via `_ordered_tab_ids(setting_key, canonical_order, valid_ids)` with backfill for a newly-introduced tab id; a "↺" button resets it. The Project Settings viewer's "Default Launcher Tab" dropdown rebuilds its item list from this same ordering call every time the form is populated.
### Markdown Editor

Local `.md` files opened via the viewer (launcher click, folder browser, preview buttons, Focus-layout routing) open directly into a live WYSIWYG editor by default. The **Notes panel** (Standard layout's right column / Focus layout's Notes viewer tab) uses this exact same editor on its own dedicated instance.

- Built on **Muya** (`@muyajs/core`), the standalone editor engine extracted from the MarkText project — embedded via `QWebEngineView` as a vendored pre-built UMD bundle under `assets/muya/` (`editor.html` is the shell page, substituting theme-color placeholders, plus an `assets-shim.js` that maps the bundle's expected asset-loader globals to the vendored paths).
- **Autosave**: each Muya session has its own `QTimer` polling `window.__muyaIsDirty()` and writing via `window.__getMuyaMarkdown()`. The general webview session (`_muya_session`) uses ~1.2s; the Notes session (`_notes_muya_session`) deliberately uses a lazier 15s (several notes tabs/devices can be open at once, so infrequent writes reduce write-clash odds) — covered by an explicit **Notes Save button** (`self.notes_save_btn`) that doubles as a passive dirty/clean indicator (`_update_notes_save_btn()`, muted when clean, bold when dirty). A shared `_flash_button_saved()` helper briefly turns any Save button's text green ("✓ Saved") after a successful save (text-color-only, so it doesn't disturb the dirty/clean background styling). No accompanying status-bar message for Notes/Code (both have their own Save button to flash); the general webview session (no Save button of its own) still gets one, since it has no other feedback mechanism.
- **👁 Preview / ✏️ Edit** toggle buttons (main editor only — Notes has no preview mode) switch to/from the themed read-only `QTextDocument` renderer (`_open_markdown_preview()`). `_open_markdown_in_webview(path)` is the stable "open" entry point used everywhere for the main viewer.
- **Two Muya sessions**: `MuyaSession` bundles `webview`/`editing`/`path`/`pending_markdown`/`autosave_timer` so two independent instances share bridge logic without stepping on each other — `self._muya_session` wraps the general `self.webview`; `self._notes_muya_session` wraps a second, persistent `self.notes_webview` (created once in `__init__`, detached-then-readded on every rebuild, same as every other persistent webview in this app). `build_main_content()` places `notes_panel` directly into whichever container matches the current layout at construction time, rather than reparenting it between layouts (which used to break `QWebEngineView`, since it can't survive being moved via `setParent(None)` after being shown).
- **Notes/webview markdown consolidation (Focus layout only)**: every "open this `.md`" action routes through `_open_markdown_file(path)` — Focus layout dispatches to the Notes tab (`_open_note_in_notes_tab()`), Standard layout keeps the pre-existing general-webview behavior (`_open_markdown_in_webview()`). `self.notes_md_path` (mirrors `webview_md_path`) tracks an explicitly-opened arbitrary note vs. the project's own; reset only on an actual project switch (`switch_to_config()`), never on an incidental `load_notes()` refresh, so an open arbitrary note survives e.g. a theme toggle.
- **Notes toolbar** (`create_notes_toolbar()`, Focus layout only): an Open file-picker button, a filename label, and a Save button. A permanent, labeled **"Project Note"** button (house icon + text, always the first item in the Notes tab strip) jumps to (or opens) the project's own note idempotently (`_jump_or_open_project_note()`) — this replaced an earlier two-piece design where the "Project Note" label only existed on a separate tab-group entry that vanished once only one tab remained. Archive/View/Joplin-sync/"Open in {editor}" controls (`self.notes_archive_section`) are hidden whenever an arbitrary note is loaded, since they're hardcoded to the project's own notes file and would otherwise silently act on the wrong file (a real data-loss risk, not just a stray-folder concern).
- **Paper theme**: both sessions render as a Typora-style "paper card floating on a tinted page" via `_notes_paper_css()` — separate hand-picked light/dark palettes (not derived from `themes.py`), 90%/80% paper opacity (Standard/Focus layout). **Heading colors (H2–H6)**: user-selectable per-level [Open Color](https://yeun.github.io/open-color/) hue (13 named hues + "None", plus a "Custom…" `QColorDialog` for a fully arbitrary color), via Settings → Themes tab "Muya Heading Colors" — the **shade** is always theme-derived for a preset hue (shade 9 light / shade 4 dark, so any hue choice is guaranteed readable in both themes), but theme-invariant for a custom hex (used identically in both themes, a deliberate opt-out of that guarantee). Stored as `settings['muya_heading_colors']` (`{level: hue_name_or_hex}`), defaulting to `{"h2": "Green", "h3": "Red", "h4": "Blue", "h5": "Grape", "h6": "Gray"}`. H1 stays fixed/neutral, not configurable.
- **Theme-change gotcha**: `toggle_theme()` must capture whether a markdown file is open in the *general* viewer **before** calling `refresh_projects()`, since that call's `load_notes()` unconditionally clears `webview_md_path` and the general viewer isn't covered by the Notes-only reload-gate.
- **`ForceDarkMode` gotcha**: `self.webview`'s `QWebEngineSettings.WebAttribute.ForceDarkMode` must be set explicitly both ways every rebuild (`current_theme == "dark"`) — it's a persistent WebEngine setting that only ever being set `True` left it stuck on permanently after the first switch to dark mode.

*(Several real historical rendering/undo-history/autosave bugs found while building this — a `::before`-on-void-element rendering dead end for To-Do checkboxes, a `setContent()` vs. `replaceContent()` undo-history-wipe bug, several Chromium checkbox-paint quirks — and their fixes are recorded in `ai/CLAUDE_ARCHIVE.md` → "Markdown Editor".)*

### Voice Dictation (Speech Note)

A "🎤 Dictate" button in the Notes panel's archive bar (both layouts — it lives in `archive_bar`, part of `notes_panel` itself, not the Focus-only `create_notes_toolbar()`) dictates speech directly into the Notes editor at the current cursor position, via [Speech Note](https://github.com/mkiol/dsnote) (`net.mkiol.SpeechNote`, a separately-installed flatpak).

- **Clipboard-capture design, not a D-Bus text signal**: an initial investigation assumed Speech Note's D-Bus interface would expose the transcribed text directly (e.g. via a signal). Live introspection (`busctl --user introspect net.mkiol.SpeechNote /net/mkiol/SpeechNote`) showed this isn't the case — the interface exposes only status integers (`State`/`TaskState`) and a generic `InvokeAction` method; no property or signal anywhere carries the text itself. The actual mechanism: trigger `flatpak run net.mkiol.SpeechNote --action start-listening-clipboard` (places the transcription on the system clipboard once done), poll `TaskState` via `qdbus` on a `QTimer` until it reports completion, then read the clipboard.
- **Self-calibrating completion detection**: rather than hardcoding a guessed "idle" `TaskState` integer, `_poll_speechnote_state()` captures `TaskState` as a baseline immediately before triggering and polls relative to it: differs from baseline = busy, returns to exactly the baseline = done. Works regardless of the literal enum values in use — confirmed live with "action invocation" (below) enabled: `TaskState` cycles `0` (idle) → `1` (listening) → `0` (done), a full real cycle taking ~12.5s with no speech given (Speech Note's own silence/VAD auto-stop), comfortably inside the 30s max-wait ceiling.
- **Requires a one-time manual step in Speech Note itself**: Speech Note refuses external CLI/D-Bus action triggers by default (confirmed live: `flatpak run net.mkiol.SpeechNote --action start-listening-clipboard` returns exit code 10, `"Action has failed. Action invocation is not enabled in settings."`) until **Speech Note → Accessibility → "Allow external applications to invoke actions"** is enabled — not found in any of its on-disk config files to auto-detect or toggle programmatically, so this is documented as a manual prerequisite (Settings → Integrations hint text) rather than something ProjectFlow can do on the user's behalf. `start_speechnote_dictation()` catches this specific stderr message and shows an actionable `QMessageBox` rather than a generic failure. **Not to be confused** with Speech Note's separate "Insert into active window" feature and its own `ydotool`-daemon requirement — that's Speech Note's own keystroke-simulation alternative (Method 2 from the original investigation doc) and is entirely unrelated to the clipboard-capture approach this feature actually uses; confirmed live that `start-listening-clipboard` works correctly with action invocation alone, no `ydotool` involved.
- **Insertion**: `__insertTextAtCursor(text, cursorState)` (`assets/muya/editor.html`) uses `document.execCommand('insertText', ...)` against the live contenteditable — a real browser editing action (same mechanism actual typing uses), so it participates in Muya's own `json-change`-driven dirty-flag tracking for free, rather than round-tripping through `getMarkdown()`/`replaceContent()` like `__setMuyaMarkdown()` does. `cursorState` is fetched fresh via `__getMuyaCursorState()` right before each insert (not cached from when listening started), since the user may keep editing during the several-second-to-30-second wait. Confirmed live via an offscreen `QWebEngineView` test (independent of Speech Note) that insertion lands at the exact given position and the dirty flag flips correctly; `Ctrl+Z` undo behavior could not be confirmed via automated synthetic key events in that offscreen harness (a control test showed even literal simulated typing doesn't undo there either — a harness limitation, not a finding either way) and needs a real live check.
- **Clipboard save/restore**: the system clipboard is the only available "transcription finished" signal (no D-Bus alternative exists, see above), so `start_speechnote_dictation()` saves whatever was on the clipboard before triggering and restores it immediately after reading the dictated text out — avoids silently destroying something the user had copied beforehand. This does **not** close the inherent race window between Speech Note finishing and ProjectFlow reading the clipboard (something else could in principle write to it first) — a structural limitation of the clipboard-capture approach, not fixable by different code, since no D-Bus call carrying the text exists to use instead.
- **Settings**: `speechnote_enabled` (bool, default off — Settings → Integrations), gates whether the button is even built; also gated on `_speechnote_available()` (a `flatpak info net.mkiol.SpeechNote` check) so turning the setting on without the flatpak installed never produces a button that silently fails every click.
- **No new microphone access for ProjectFlow**: ProjectFlow never touches audio directly — it only triggers Speech Note (a separately-trusted, sandboxed flatpak) via its own documented CLI action; Speech Note's flatpak permissions and its own action-invocation opt-in (above) both gate actual mic capture. Transcription runs fully locally (a local FasterWhisper model, per Speech Note's own `ActiveSttModel` D-Bus property) — no network call, no new stored credentials in `.projectflow_settings.json`.
- **A real, confirmed `QT_QPA_PLATFORM` leak bug**, found live (first on a real run, then reproduced exactly on demand): clicking Dictate failed with `qt.qpa.xcb: could not connect to display` / `Could not load the Qt platform plugin "xcb" ... even though it was found`. Root cause: `projectflow-nix`/`shell.nix` export `QT_QPA_PLATFORM=xcb` for **ProjectFlow's own** Qt build (to work around the QtWebEngine GPU-compositor crash — see `ai/issues.md`), and `subprocess.run()`/`Popen()` inherit the parent's full environment by default, so that same variable was leaking into every `flatpak run net.mkiol.SpeechNote ...` call. Speech Note's own bundled Qt, inside its flatpak sandbox, normally auto-selects a working platform on its own — forcing `xcb` on it from outside breaks that. Confirmed via isolated reproduction that `QT_QPA_PLATFORM` alone (not the nix-shell `LD_LIBRARY_PATH`, tested separately and found harmless) causes this. Fixed via `_external_tool_env()` — `os.environ.copy()` with `QT_QPA_PLATFORM` stripped — passed as `env=` to every Speech Note/`qdbus` subprocess call in this feature. A real instance of this codebase's broader "don't let a host-Qt-specific env var leak into an unrelated external process" risk — worth checking for if any *other* future feature shells out to a GUI app.
- **Two real bugs found on a second-machine live test, both fixed**:
  - **Duplicate inserted text, landing at document start instead of the cursor**: root-caused to two compounding issues. (1) The re-entrancy guard (`self._dictation_active`) was only set *after* the blocking `subprocess.run()` launch calls returned — up to several seconds on a cold start — leaving the button clickable during that window; moved to the very top of `start_speechnote_dictation()`, synchronously, before any blocking call, closing that gap (`_reset_dictate_button()` is the shared revert path on any failure). (2) If the cursor was never actually placed in the note body (Dictate clicked without first clicking into the text), `__getMuyaCursorState()` returns a null cursor, and `__insertTextAtCursor()` used to silently fall through to whatever the DOM's leftover default selection happened to be — document start. Now falls back explicitly to the **end** of the document via the plain Selection/Range API when no real cursor exists, a predictable "append" rather than an unpredictable default. (Honest caveat: a `QTimer`-driven GUI click race is hard to prove conclusively after the fact, so a Speech-Note-side audio/STT duplication on that particular machine can't be fully ruled out either — but the re-entrancy-timing gap was real and independently worth closing regardless.)
  - **Stale/wrong clipboard content inserted**: `TaskState` returning to its baseline (idle) does **not** guarantee Speech Note actually wrote anything new to the clipboard — if nothing intelligible was picked up, it can go idle again without touching the clipboard at all, leaving whatever was there *before* dictation started (confirmed live: an old copied URL got inserted this way). `_finish_speechnote_dictation()` now compares the post-completion clipboard text against `_dictation_prior_clipboard` and only treats it as real dictated output if it's both non-empty *and* actually different — otherwise reports "no text was captured," same as a genuinely empty result.
- **Deliberately out of scope**: continuous/multi-utterance dictation (one click = one utterance, relying on Speech Note's own voice-activity-detection auto-stop); a language-selection UI (uses whatever Speech Note itself is configured for); any text-to-speech counterpart.

### Code Editor

A separate internal editor for source code (JS/Python/HTML/CSS/PHP), reached via the viewer tab row's "Editor" tab (`column2_mode == "code"`). Built on [CodeMirror 6](https://codemirror.net/) by default, vendored the same way as Muya (a pre-built static bundle, `assets/codemirror/`) — its own container/session/toolbar, not sharing `self.webview`'s Muya multiplexing, since a code editor has no URL-bar relevance.

- **`basicSetup`** (the `codemirror` meta-package's bundled extension set) wires up find & replace (Ctrl+F), find-next/prev, select-all-matches (Ctrl+Shift+L), code folding, undo/redo, bracket matching/auto-close, and basic autocompletion (Ctrl+Space) — all for free.
- **Custom keybinding overrides**, deliberately shadowing three `basicSetup` defaults (`Prec.highest`, by direct request): **Ctrl+G** → go to line (frees Ctrl+G from CM6's own `Mod-Alt-g` default; this also shadows `Mod-g`/`Shift-Mod-g` find-next/prev, which move to **F3/Shift-F3 only**); **Ctrl+D** → copy current line down (`copyLineDown`; a confirmed tradeoff — shadows multi-cursor "select next occurrence", which loses its own shortcut); **Ctrl+K** → cut current line (nano-style kill-line; implemented as `selectLine` + native `document.execCommand("cut")`, since CM6's view has a built-in DOM `"cut"` handler that syncs the result back into its model for free).
- **No autosave** — a dirty-poll timer (`CodeEditorSession.dirty_poll_timer`, ~800ms) only ever refreshes the Save button's label; `_code_editor_save()` is the **only** method that writes to disk (toolbar Save or Ctrl+S). **Ctrl+S** is shared with a pre-existing, unrelated `toggle_edit_mode()` binding — `_on_global_ctrl_s()` prioritizes saving whatever document is actually open for editing (code/Notes/general-webview-markdown) over that toggle, and deliberately no longer *enters* edit mode via Ctrl+S.
- **Unsaved-changes guard** (`_confirm_discard_code_changes()`) on `closeEvent()`, `switch_to_config()`, and opening a *different* file while the current one is dirty.
- **`.html`/`.htm` open in the code editor by default** (reversed from an earlier opt-in design) — the rule is simply "local files open in the editor, URLs open in the web viewer." The one exception: a launcher item explicitly configured with `app="firefox"/"chrome"` still renders even for a local file, an explicit "view, don't edit" signal. The **"</> Edit Source"**/**"👁 Rendered"** toggle still flips a given file between the two views regardless of which one it opened in.
- **Extension routing**: `.py`/`.js`/`.css`/`.php`/`.html`/`.htm`/`.json`/`.txt`/`.nix` all route into the code editor by default — in Focus layout for launcher clicks, unconditionally for folder-browser clicks. `.json` maps to the `'js'` CodeMirror language (no dedicated JSON package is vendored; valid JSON tokenizes fine as JS object/array literals). `code_editor_extensions` (Settings tab, comma-separated, e.g. `vue,rs,go`) extends — not replaces — the built-in set; an added extension with no language mapping still opens as plain text with line numbers.
- **Line-wrap toggle** ("↩ Wrap", `code_wrap_btn`): CM6's `EditorView.lineWrapping` lives in its own `Compartment` so toggling it reconfigures the live editor in place (no lost undo history). Persisted per-machine as `code_editor_wrap` (default on).
- **"📂 Open"** button (`open_code_file()`) opens an arbitrary file not already referenced by the project.
- **Theming**: reuses the `__PF_BG__`/`__PF_FG__` placeholder pattern, plus a CM6 `EditorView.theme({...})` for chrome (gutter/selection/active-line, sourced from existing `themes.py` keys) and a small, hand-picked 3-color syntax palette per theme (`_code_editor_syntax_colors()`), independent of `themes.py` — the same reasoning as the Notes paper theme's hand-picked colors.

#### Monaco backend (alternative to CodeMirror 6)

A second, user-selectable backend — [Monaco Editor](https://microsoft.github.io/monaco-editor/) (the editor behind VS Code) — configurable via `code_editor_backend` (`"codemirror"` default / `"monaco"` / `"auto"`, same shape as `console_backend`): `resolve_code_editor_backend()` resolves `"auto"` to `"monaco"` only if the vendored assets are present, falling back to `"codemirror"` otherwise. Settings → Applications has a dropdown with a live "assets not found" warning, mirroring Terminal Backend's own pattern.

- **A shared six-function JS↔Python bridge contract** (`__initCodeEditor`/`__getCodeEditorContent`/`__codeEditorIsDirty`/`__codeEditorClearDirty`/`__getCodeEditorViewState`/`__setCodeEditorWrap`) is what makes this a drop-in alternative rather than a parallel feature — every Python-side caller (session/tabs/dirty-poll/save/wrap-toggle/discard-guard) is backend-agnostic; `_load_code_editor_shell()` is the **only** function that branches on backend (picking the matching shell HTML + asset base URL).
- **Vendoring**: `assets/monaco/vs/` is monaco-editor's official prebuilt AMD folder, committed unpruned (~24MB) — per-language pruning was investigated and rejected as only saving ~600KB without a proper webpack build.
- **Boots via the classic AMD `require()` sequence** (not a single global-exposing script like the CodeMirror bundle); one persistent `monaco.editor.create()` instance swaps in a fresh model per tab (`createModel()`/dispose-previous) rather than destroying/recreating the editor.
- **Web Workers do work from a `file://`-origin page in this QtWebEngine build** (confirmed via a live spike — PDF.js's closest precedent falls back to a synchronous "fake worker" when this fails, but here real `Worker` instances spawned with no errors). This enabled a middle scope: JS/TS hover/autocomplete/signature-help stay on; CSS/JSON validation stays on; **JS/TS semantic error-squiggle validation is explicitly disabled** (`noSemanticValidation`/`noSyntaxValidation`), since each tab is a standalone file with no project/`node_modules`/tsconfig context and would otherwise produce noisy, incorrect "Cannot find module" errors.
- **The same four keybinding overrides** are reimplemented via `editor.addCommand(...)` — Mod-K needed a from-scratch implementation, since Monaco has no `clipboardCutAction` and even a trusted native `execCommand('cut')` doesn't sync back into Monaco's own document model the way CM6's view does; the working version selects the line, copies via the Clipboard API, then deletes the range via `editor.executeEdits()`.
- **Theming** mirrors the CodeMirror shell's placeholder set via `monaco.editor.defineTheme()`.
- Everything else (multi-tab open/close/switch, the dirty-poll Save button, wrap toggle, theme-toggle reload, the HTML rendered/source toggle, the external-editor footer button, the discard-guard) is unaffected by backend choice, confirmed via direct end-to-end testing with both backends.

*(Extensive debugging narratives behind the keybinding/clipboard investigation and the worker/diagnostics scoping decision are recorded in `ai/CLAUDE_ARCHIVE.md` → "Code Editor".)*
### Multi-Instance PDF, Image, Web, Notes, Editor & Terminal Tabs

The PDF, Image, Web, Notes, Editor, and Terminal viewers each support multiple simultaneously-open items as tabs.

- **PDF/Image** (`PdfTabState`/`ImageTabState`, top-level classes alongside `MuyaSession`/`CodeEditorSession`): cheap, in-process resources with no shared-renderer constraint, so **every open tab keeps its loaded resource for the tab's lifetime** — no cap, no lazy-loading. `self.pdf_tabs`/`self.image_tabs` (lists) + `*_active_index` are the source of truth; the pre-existing scalar attributes (`pdf_doc`, `pdf_path`, `image_pixmap`, etc.) remain as **active-tab proxies**, always mirroring the active tab, so every pre-existing render/zoom/page-nav/pin method keeps working completely unchanged. `_activate_pdf_tab(index)`/`_activate_image_tab(index)` flush the outgoing tab's live state, sync the proxies, and re-render/re-fit. Opening is always-new-tab (`_open_pdf_tab()`/`_open_image_tab()`), never a replace — even for a file already open elsewhere.
- **Tab strip UI**: a row of label+close pairs between each viewer's toolbar and content, built once per `build_main_content()` rebuild, repopulated afterward without a full rebuild. An "X Close All" button appears once more than one tab is open, built on that type's own single-tab close method in a loop — most types (PDF/Image/Web/Terminal) can always reach zero tabs this way; Notes deliberately never reaches zero (it re-appends a fresh project-note tab), so its Close All closes down to exactly one tab then closes that one too; Editor's close can be *refused* (a dirty tab's discard-confirmation, "No"), so its Close All stops as soon as the list stops shrinking rather than looping.
- **Persistence**: `save_notes()` writes `pdf_tabs`/`image_tabs` (lists) and `*_active_tab` (index) into the project's JSON; the pre-existing single-dict `pdf_state`/`image_state` keys are kept as a mirror of the active tab for backward compatibility. `load_notes()` prefers the list keys, migrating the old single-dict shape into a one-item list on read.
- **Web** (`WebTabState`, `kind`: `"url"`/`"html_file"`/`"markdown"`): a `QWebEngineView` is a real Chromium renderer process, so **only one is ever kept live** (the app's existing persistent `self.webview`) — switching Web tabs re-navigates that single shared webview rather than creating N of them. `_open_web_tab(kind, value)` ("open" actions — launcher clicks, preview buttons) always creates a new tab; `_navigate_active_web_tab(kind, value)` (the URL bar's Enter / Home button) navigates the *current* tab in place, matching real browser address-bar behavior. `WEB_TAB_CAP = 8` is a tidiness cap only (closes the oldest tab past it) — not a resource constraint, since there's only ever one real renderer regardless of tab count.
- **Web-tab restoration is lazy**: `_ensure_web_tabs_loaded()` activates the remembered tab **at most once per project**, only once the Web viewer tab is actually entered — not unconditionally on every app launch regardless of active viewer, as it originally was. Fixed after a remembered external URL triggered a fatal QtWebEngine GPU-compositor crash (`SIGILL`, a runaway "Reduced surface width" resize loop) purely from being eagerly rendered in the background on one machine with a degraded GPU stack.
- **Right-click "Open link in new tab/window" now works** (and JS `window.open()`), via a custom `LinkOpeningWebPage.createWindow()` override — `QWebEnginePage.createWindow()` returns `None` by default, which is why this silently did nothing before; the override hands Chromium a throwaway, unparented page purely to capture the destination URL, then opens it as a real new Web tab and discards the throwaway page (with a 5s safety-net cleanup timer in case no real navigation ever arrives).
- **Cookie/session persistence**: `self.webview`/`self.notes_webview` are backed by a **named** `QWebEngineProfile("projectflow")`, created before either webview — `QWebEngineProfile.defaultProfile()` is **permanently off-the-record** in this Qt/PyQt6 build (confirmed empirically), silently ignoring persistent-storage settings, so a named profile is the only way logins/cookies survive a restart. Every terminal tab's own webview, plus the code editor and Help viewer, deliberately stay on the default profile, since none of them load content that needs cookies to survive a restart.
- **Notes tabs** (Focus layout only — Standard layout's Notes column is a fixed pane, structurally incapable of showing anything but the project's own note): the same one-shared-webview pattern as Web. `NotesTabState` holds just `path` (`None` = the project's own note). `_open_note_in_notes_tab()`/`_open_notes_tab()` **reuses** an already-open tab for the same file rather than duplicating — a note's whole document is always shown at once, so a second tab on the same file has no purpose, unlike PDF/Web. Never truly empty — closing the last Notes tab recreates a fresh project-note tab. Caret/scroll position is restored across tab switches via Muya's `getCursorOffset()`/`setCursorByOffset()` (a public API that round-trips through the markdown text itself, surviving the full document rebuild a tab switch does). An open arbitrary note now survives an app restart (a genuinely new persistence behavior, since a `NotesTabState` is cheap to rebuild from disk). **Re-activating the tab already on screen is a no-op** (`self._notes_tab_content_loaded_index` guard) — needed because Muya's `setContent()` unconditionally clears undo history, so without this guard, clicking a launcher/Folder-Browser item or the "Project Note" button that resolved to the already-open tab silently wiped undo/redo on every click, a real bug reported as "sometimes Ctrl+Z just doesn't work."
- **Editor tabs** (`CodeTabState`: `path`/`language`/session-only `pending_unsaved_content`/`dirty`/`view_state`) — the highest-risk type, since the Code Editor has a deliberate no-autosave policy. `_open_code_tab()` reuses an already-open tab by path rather than duplicating (a real user-reported bug: switching projects and back used to silently open a *second* tab on a file already restored among the project's `code_tabs`). Tab labels disambiguate same-named files from different folders by prefixing the parent folder name. **Switching tabs must never force a save or a discard**: `_activate_code_tab(index)` is async — it first pulls the live editor's content via `__getCodeEditorContent()` and caches it on the *previously*-active tab's own `CodeTabState` before loading the target tab, so a background tab's edits are flushed, not destroyed; this also means opening a *different* file no longer needs a discard-guard at all (that guard now only covers closing the app, switching projects, and the HTML rendered↔source toggle, where content genuinely would be lost). Cursor/scroll position is likewise restored per tab (`CodeTabState.view_state`).
- **Terminal tabs** (`TerminalTabState`: `cwd`/`webview`/`proc`/`port`/`ready`) are the one type that does **not** follow the "at most one instance of the expensive resource" rule every other type here uses — a terminal tab's whole point is a real, independently-running shell, so re-navigating one shared webview (the Web-tab model) would mean killing whatever's running in it on every tab switch. Instead it follows PDF/Image's "keep every open tab's resource alive" model, except the resource (a real OS subprocess + port) is genuinely expensive, hence **`TERMINAL_TAB_CAP = 5`** — `_open_terminal_tab()` **refuses outright** past the cap (status-bar warning, no silent eviction, since a background tab can have a real process running). Reuse-by-cwd (`_find_terminal_tab_for_cwd()`), not always-new-tab. Only `cwd` is ever persisted across restarts (a running shell can't be resumed); a restored tab is **lazy-spawned** — only the active tab's process starts immediately, every other restored tab waits until actually clicked. `_teardown_terminal_tabs()` (process cleanup only, no `save_notes()` call) is used specifically from `load_config()` on a project switch, to avoid writing the *new* project's partially-loaded state back over its own config file — `_close_all_terminal_tabs()` (which does call `save_notes()` per tab) is used everywhere else. `closeEvent()` stops every open terminal tab's process.

*(A long history of real, specific concurrency/timing bugs found while building this feature — async-index races causing crashes when a tab list shrinks mid-callback, several rounds of `column2_mode`/`active_viewer` reload-gate regressions, autosave-on-tab-switch races losing the last few seconds of edits, a Code Editor Save button that silently stopped clearing the per-tab dirty flag, and more — is recorded in full in `ai/CLAUDE_ARCHIVE.md` → "Multi-Instance Tabs".)*
### Group-by-Type Launcher View

A "🗂️ Group" toggle in the launcher column header (Standard layout only — Focus layout uses the Docs/Resources tabs instead) splits launchers into **Docs** and **Resources**, both the project's real categories, shown under their own real names — an item's category membership (wherever it's physically filed) is the only classification; there is no auto-pooling by file extension (an earlier version did this and was removed as more machinery than it was worth).

- **Docs** is backed by one real category, canonically **"Documentation"** (a literal `"Docs"` category name from before this was settled on is still recognized as a legacy alias) — plus two things that are *also* shown there but aren't real categories: **AI** (see below, always above Docs) and a synthetic, non-editable **pinned project-notes entry** (`"{Project Name} project notes"`, path = the project's notes file, app `"default"` — opens the Notes tab in Focus layout per the Markdown Editor's notes/webview consolidation).
- `_ensure_documentation_category()` is the one place "Documentation" gets created — lazily, only when something is actually about to be filed there (the Docs header's "+ Add Launcher", "Move to category" → Documentation, Scan for Docs), never eagerly, and persisted immediately (required since `handle_item_move_to_category()` re-reads the config from disk).
- **Drag-and-drop** works fully for real Documentation/Resources items; only the AI/pinned-notes rows (no real category backing — a sentinel `(None, None)` origin) are excluded, along with inline rename/delete on the Docs bucket's header.
- **Editing while in this view**: Docs and Resources both stay on the grouped view regardless of `self.edit_mode` — both are real, fully editable categories. Only Files/Apps fall back to the raw ungrouped `self.COLUMN_1` list while editing.
- **👁 Hide toggle**: AI items only now (personal, machine-local `ai_hidden_paths` in `.projectflow_settings.json`, never written to the project file) — real Documentation/Resources items have no hide state, only delete or "Move to category."
- **"📁 Move to category"** always offers "📄 Documentation (docs)" first (auto-creating it via `_ensure_documentation_category()` if it doesn't exist yet) — the primary way an item gets promoted into Docs, by physically relocating it.
- **Per-project persistence**: `group_by_type` in the project's own config (`_save_group_by_type_to_config()`); falls back to the layout-linked default (on for Focus, off for Standard) when unset.
- **Automatic AI category**: if the project's `config_folder_path` contains an `ai/` subfolder, `_get_ai_category_items()` surfaces every non-dotfile inside it plus any root `CLAUDE.md`/`AGENTS.md`/`CHANGELOG.md`/`Specification.md`/`SPEC.md` — live/dynamic, computed fresh every render, nothing written to the project JSON, absent entirely for a project with no `ai/` folder. An authored item whose path matches one already surfaced in AI is hidden from Resources so it doesn't appear twice. Falls back through `_resolve_existing_path()`'s path-mapping tier if the folder isn't directly reachable (safe here, since AI items are never persisted — the mapped path is only ever used for that one render), flagged via a pale-blue mapped-path style identical to Documentation/Resources items' own per-item styling.
- **Open Project Folder footer**: a `_make_viewer_footer()` strip below the Docs category's item list, whenever `config_folder_path` is set and not in edit mode — a shortcut to the pinned project folder, not to wherever any given document actually lives.
### Theme System

The app supports three themes — light, dark, and a third "modern" theme — defined in `themes.py`. The footer 🌙/☀️ button remains a strict light/dark toggle; "modern" is reachable only from Settings → Themes tab for now.

**Theme settings:** `"system"` (default, follows desktop preference) / `"light"` / `"dark"` (navy panels on off-black) / `"modern"` (a third, visually distinct light theme).

**Theme architecture:**
- `themes.py`: `THEMES` dict with `"light"`/`"dark"`/`"modern"` color schemes, all three defining the same ~70 keys (any theme missing a key would silently fall back to a magenta placeholder).
- `init_theme()` / `t(key)` / `toggle_theme()` are the standard access points — `toggle_theme()` is deliberately a strict binary light/dark swap with no third-theme awareness (clicking it while on "modern" lands on "light," by design, documented both in the method's docstring and the Themes tab's hint label).

**Key theme color keys**: `bg_primary`/`bg_secondary` (backgrounds), `bg_panel` (section headers), `bg_button`/`bg_button_hover` (toolbar), `bg_category`/`bg_category_hover` (category headers), `bg_navy`/`bg_green_1..4` (bottom action buttons + the viewer tab row gradient — `update_viewer_tab_styling()`/`build_main_content()`'s `tab_btn_style`/`active_tab_style`), `fg_primary`/`fg_secondary`/`fg_on_dark` (text), `border`/`border_dark`/`border_light`, `bg_viewer`, `bg_help`/`fg_help_*`, `bg_code_inline`/`border_help_*`.

- **Active-tab indicator — background-brightness contrast only, no border** — both the viewer tab row (green) and the Launcher Tab Bar (blue) rely purely on the active tab's fill being distinctly *brighter* than resting, in the *same direction* in both themes. The viewer row reuses `bg_green_1` (resting, darkest) → `bg_green_3` (active, brightest). The launcher row uses a **dedicated** `tab_launcher_resting`/`tab_launcher_active` pair — not the general `bg_category`/`bg_category_hover`, reused ~30 places elsewhere — specifically because which literal color is "the brighter one" flips between light and dark theme (light theme's plain `bg_category` is already the brighter one; dark theme's plain `bg_category` is already the dimmer one), so each theme bakes the correct literal color into its own data under role-based names rather than assuming one shared key means the same thing in both themes. Several alternative designs (a white border, a `fg_secondary` border, an orange accent border, a same-hue-darker-fill) were tried and dropped in favor of this brightness-only approach — see `ai/CLAUDE_ARCHIVE.md` for the history.

**The "modern" theme** (added 2026-10-22): an airy off-white light theme with a clean, user-adjustable blue/green accent pair and pale-background status badges, loosely inspired by two reference screenshots for color/shape sense only. **Settings-only for now** — added to the Themes tab's theme dropdown but not wired into the footer toggle; every other theme-selection code path already treats any non-`"system"` string as a literal theme name, so no further wiring was needed, and the ~22 scattered `current_theme == "dark"`/`"light"` binary checks elsewhere in the file all degrade safely into the implicit "light-ish" branch.

- **Bundled Lato font** (`assets/fonts/Lato-{Regular,Bold}.ttf`, SIL OFL): loaded via `QFontDatabase.addApplicationFont()` at startup and applied to native Qt widgets (`QApplication.setFont()` in `apply_global_styles()`, which also captures/restores the true pre-Lato system default for light/dark) and to the Help viewer (a `@font-face` block substituted into `help/shell.html`'s placeholders). **Not** applied to the Notes/To-Do Muya webview — an attempt was made and reverted the same day after it made the editor barely responsive (typing not registering, slow scrolling); not re-attempted without first profiling actual font-load timing inside the live webview.
- **Structural polish — curated, not exhaustive**: two new theme-keyed tokens, `radius_card` and `shadow_card_*`, default to light/dark's existing flat/no-shadow values (so neither theme changes visually) and only differ for "modern" (14px radius + a soft drop shadow via `_apply_card_effect()`/`QGraphicsDropShadowEffect`), applied to four anchor points: `launcher_widget`, category header buttons, the footer bar, and one Settings-dialog "card" (Muya Heading Colors) — chosen to distinguish persistent chrome (stays flat) from content cards (gets the lift). **`column2_widget`/`notepad_column_widget` are deliberately excluded** from the shadow effect — a `QGraphicsEffect` on any ancestor of a `QWebEngineView` forces that webview into slow software-composited rendering, a severe, real performance regression (20-40s to open a note) found live and fixed by dropping both the shadow and the rounded-corner styling from those two panels entirely.
  - A real, confirmed Qt quirk underlies several rounds of follow-up fixes: a themed `QPushButton` with `border-radius` set but no genuine `border: <n>px solid <color>` (a bare `border: none;` isn't sufficient — it's itself a second signal telling Qt's style engine "no border styling here") silently falls back to square native chrome. **And** even with a correct border, `border-radius` is silently ignored (zero rounding, no clamping the way browsers do) whenever it exceeds half the widget's actual rendered height/width — confirmed via a live `QT_QPA_PLATFORM=xcb` + `QWidget.grab()` screenshot sweep after several rounds of CSS-content-only fixes failed to resolve a real, reported square-corner bug. The eventual fix lowered the "modern" radius for several button rows (`_pf_btn_radius`, `_pf_footer_btn_radius`) to a smaller, size-safe `10-12px` rather than reusing `radius_card` (14px) everywhere, plus explicit `setMinimumHeight()`/width floors on a few icon-only buttons that were otherwise too small for even that safer radius.
- **Accent-color picker** (Settings → Themes tab → "Modern Theme Colors"): 4 user-settable colors (`MODERN_ACCENT_DEFAULTS` — Accent Blue / Accent Blue Offset / Accent Green / Accent Green Offset) drive 16 "modern"-only theme keys via `derive_modern_overrides(accent_colors)`; `get_theme("modern", accent_colors)` merges them onto a **copy** of the base theme, never mutating `THEMES` itself. The viewer-tab-row's 4-stop green gradient is auto-derived from just the 2 green picks (RGB-interpolated/lightened via `_lerp_rgb()`/`_lighten_rgb()`) rather than being 2 more separate knobs, matching this app's standing "don't let a brightness ramp go non-monotonic" caution.
- **Font picker** (Settings → Themes tab → "Modern Theme Font"): originally 5 curated bundled fonts; widened 2026-10-24 to **any font installed on the system** (`_discover_system_fonts()` via `QFontDatabase.families()`), on direct request, since a `QWebEngineView`'s Chromium renderer can't see a font that's only registered for native Qt widgets, and vice versa — but Chromium can resolve any installed system font via fontconfig with no embedding needed, the same way any Linux browser does. `_resolve_modern_font()` returns `(family, bundled_entry_or_None)`; only a bundled font gets a real `@font-face` emitted for the Help viewer, everything else is referenced by name and relies on the system/fontconfig lookup. A freshly-installed font (e.g. via Nix) needs an app restart to appear (fontconfig cache timing) — no live detection attempted.

**Viewer dark mode**: PDF viewer inverts colors; Image viewer uses the theme background; Help viewer has full theme support; the general webview uses Qt's `ForceDarkMode` setting.

**Design Principles**: compact layout, minimal vertical space; clear visual hierarchy through color and size; a consistent cool palette (greys/blues/greens in light, navy/purple in dark); current selection indicated by size/border rather than drastically different colors.

*(The "modern" theme's multi-round border-radius/padding/height debugging saga — several dead-end fixes, including two that looked correct in an isolated string-level test but still failed live, before the real root cause (radius vs. widget size) was found via a real rendered screenshot — is recorded in full in `ai/CLAUDE_ARCHIVE.md` → "Theme System". The lesson that stylesheet correctness isn't provable from the string alone for this class of Qt bug is worth re-reading before debugging a similar "why doesn't this QSS render" issue.)*
### Project Settings Viewer

Project-specific settings are a regular viewer, `column2_mode == "settings"`. There is no separate "Project Details" dialog — the title-bar "✏️ Edit Project" button (`toggle_edit_mode()`) opens it directly: entering edit mode and opening the Settings viewer are one continuous action.

- **Persistent form**: `self.settings_form` is built once in `__init__` (`_build_settings_form()`), unlike every other viewer's container, which is recreated fresh on every rebuild — so an unrelated `refresh_projects()` elsewhere (e.g. reordering a launcher while this viewer happens to be open) never wipes in-progress edits.
- **Populate-on-entry, not populate-on-rebuild**: fields load from `self.config_*` via `_populate_settings_form()` only when entering the viewer for a *different* project (`self._settings_loaded_for`) — navigating to another viewer tab and back preserves unsaved edits.
- **Two Save buttons**, both calling `_save_project_and_exit_edit_mode()`: the title-bar one, and a second at the bottom of the (potentially long) form (`self._settings_bottom_save_btn`). Every field's change signal marks the form dirty (`_mark_settings_form_dirty()`), shown as an "(unsaved changes)" suffix on both buttons until the next populate or save.
- **Fields**: Project Name, Project Color (+ Clear), Scan for Documents (button), Kickstart (button), Layout ("Use three columns view" checkbox), Default Launcher Tab, Default Viewer Tab, PDF File, Web URL, Image File, Terminal Path (label-only rename of Console Path — the setting key/attribute stay `console_path`/`config_console_path`), Folder Start Path, then an **Integrations** section: Kimai Project ID, a "Tag files in this project with Baloo tag..." button (`_tag_current_project_files_baloo()` — deliberately a richer scope than the global bulk-tag button in Settings → Integrations, sweeping this project's notes file *and* every local file/folder its launchers reference, not just the notes file), and Desktop Menu Entry (`regenerate_desktop_file()`).
- **Settings shortcut icon** in the viewer tab row (a cog, just before the pin button) is a second entry point into this viewer: enters edit mode if not already editing (same as the title-bar button), or just jumps back to this viewer if already editing — so clicking over to another tab mid-edit and back doesn't also exit/save the session.
- **No per-project path-mapping toggle anymore** — an earlier checkbox (`path_mapping`) that unconditionally preferred a globally-mapped path whenever enabled was removed after it was found to permanently corrupt a portable path when the resolved (mapped) value got read back and re-saved into the config. Replaced by the always-fallback-only `_resolve_existing_path()` (see Folder browser above), which never persists its resolution.
- **No unsaved-changes guard**: navigating away from this viewer with unsaved edits discards them silently — considered acceptable for form fields, unlike the Code Editor's whole-file discard-guard.
### Kickstart / Project Finder

A reviewable "intelligent-add" dialog (`_show_kickstart_dialog()`) that suggests documentation, dev shortcuts, package-manager commands, a project alias, and an optional website launcher for a project's base folder — usable both retroactively on any existing project and automatically right after creating a new folder-based one.

- **Entry points**: the Project Settings Viewer's "🚀 Kickstart" button (works on any project, folder-based or not); automatically right after "Make Project" creates a new bare `.projectflow` (every detected suggestion listed but **unchecked**); optionally after the footer's "📄 New Project" flow, if the user opts in to linking a base folder (the template's own generic defaults are wiped in memory first, so they don't sit alongside whatever Kickstart adds).
- **Detection** (`_detect_project_indicators(folder_path)`, shared by both entry points): npm/yarn/pnpm, Python, Rust, Go, Composer, Makefile, Docker Compose, Git, README. Uses **absolute** paths (a deliberate departure from the old `.projectflow`-only relative-path convention, since the retrofit entry point must work on plain `projects/*.json` configs too).
- **Dev Shortcuts**: a radio choice between one combined `directorydev` launcher (default) or three separate editor/terminal/file-manager items.
- **Documentation**: reuses `_scan_for_docs()` verbatim, filing selections through `_ensure_documentation_category()` on Apply — identical behavior to the standalone Scan for Documents dialog, just folded into the same review screen.
- **AI**: shown only as an informational, non-checkable line — never written to the config, since the AI bucket is already fully dynamic.
- **Project Alias**: a checkbox + editable slugified name field — writes both a real shell alias (`_write_alias_to_file()`) and a matching `alias`-type launcher item. A debounced (~400ms) shell-builtin shadow-name warning (`_classify_shell_name()`, e.g. naming an alias `cd`) appears live as you type, backed by a real `bash -c 'type -t <name>'` check rather than a static command list.
- **Website**: a URL field, a separate display-title field, and two independent checkboxes — add an "Open Website" launcher, and/or set it as the pinned Web URL. The pin checkbox **replaces `self.web_tabs` outright** (not just the fallback scalar `config_webview_url`) — the fallback is only ever consulted when no tabs are open, and a template's own default web tab would otherwise keep winning on every later load even after the pin was set.
- **Checkbox defaults are opt-in, not opt-out** — every suggestion checkbox starts unchecked regardless of detection confidence.
- **Dedup across re-runs**: an exact path match against an existing item disables that checkbox (with an "Already in this project" tooltip), so re-running Kickstart on an already-kickstarted project has nothing left to accidentally re-add.
- **Apply** (`_apply_kickstart_selections()`): pins `config_folder_path`, appends every checked item (creating categories as needed), and saves via `_save_project_config()` — plus an explicit `save_notes()` when the website-pin checkbox replaced `web_tabs`, so the fix reaches disk before the dialog's own `refresh_projects()` can reload the still-stale value.
### Settings Dialog

Access via the ⚙️ button in the footer — global, machine-wide settings only; per-project settings live in the Project Settings Viewer above. Seven tabs:

- **Themes Tab**: Theme dropdown (system/light/dark/modern — the footer 🌙/☀️ button remains the fast light/dark toggle, see Theme System above for why "modern" is Settings-only); Muya Heading Colors (one hue-or-custom-hex dropdown per H2–H6, with color-swatch icons); **UI Text Size** (`ui_font_size_index`, a 5-step array `[10,11,12,13,14]`px driving launcher items, category headers, and both tab rows — multi-instance per-file tab strips always render one step smaller via `_ui_font_size(smaller=True)`); Projects Section Layout (per-row count/spacing, `projects_per_row`/`projects_spacing`).
- **Integrations Tab**: Kimai (Server URL, API Token, CSV Import Folder); Joplin (API Token); **Speech Note** — the `speechnote_enabled` checkbox (see UI Features → Voice Dictation), with a live "flatpak not found" warning and a static hint about Speech Note's own separate "action invocation" setting it also requires; **Baloo File Tags** — the `enable_baloo_tags` checkbox plus a "Create Baloo tags for all projects" bulk button (`_bulk_create_baloo_tags()`, notes-file-only across every project — a fast, predictable sweep, deliberately narrower in scope than the Project Settings Viewer's own per-project tag button, which also sweeps every launcher-referenced file); **Path Mappings** (From/To table feeding `_resolve_existing_path()`'s fallback tier — see Folder browser above).
- **Icon Preferences Tab**: manage `icon_preferences.json` entries (Add/Edit/Delete, with icon preview).
- **Launch Handlers Tab**: manage `launch_handlers_custom.json` entries — type badges [Custom]/[Built-in]/[Python]; Add/Edit/Delete (built-in/Python handlers are read-only, but can be "Copy as Custom" to override).
- **Features Tab**: per-checkbox visibility for each Launcher Tab (Docs/Resources can't both be hidden — hiding one disables the other's checkbox) and each Viewer Tab (at least one must stay enabled); plus one "Open in New Virtual Desktop" checkbox (`enable_virtual_desktop_feature`, greyed out on non-KDE or KDE-without-`qdbus` systems, with an explanatory tooltip).
- **Settings Tab**: Relocatable Data Folders (Project Data Folder / Advanced per-folder overrides / "📋 Copy Existing Data to New Location(s)" — see the dedicated Relocatable Data Folders section above); PDF Viewer; Note Editor; Terminal; Editor; File Manager (all auto-detected if left empty).
- **Button workflow**: Apply (save, keep open) / Cancel (discard, close) / OK (save, close). The dialog is theme-aware and restyles live on a theme change.
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
├── assets/codemirror/           # Vendored CodeMirror 6 bundle, default Code Editor backend
├── assets/monaco/               # Vendored Monaco Editor (VS Code's editor), alt. Code Editor backend
│   ├── editor.html              # AMD-boot shell page (see Code Editor's Monaco backend section)
│   └── vs/                      # Unpruned prebuilt monaco-editor min/vs folder (~24MB, committed as-is)
├── help/                        # File-based Help viewer content (see Help viewer)
│   ├── shell.html                # Master page: shared CSS + theme placeholders
│   ├── tabs/                     # One body-inner fragment per tab, auto-discovered
│   └── images/                   # Screenshots referenced from tab fragments
├── examples/                   # Tracked template source, copied into projects/notes/ on first run
│   ├── projectflow.json          # Template default project (see create_default_project())
│   └── projectflow.md            # Template default notes file
├── projects/                   # Project files (synced via Nextcloud) — gitignored, not tracked
│   └── [project].json          # User-specific projects
├── notes/                      # Markdown notes (synced via Nextcloud) — gitignored, not tracked
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
- The tracked template source in `examples/` (copied into `projects/`/the notes folder on first run by `setup_first_run()`) — **not** `projects/` itself, which is gitignored (see below)
- Configuration affecting all users (`.gitignore`)

**Files to exclude (in `.gitignore`):**
- `.projectflow_settings.json` - Per-machine user preferences (auto-generated)
- `projects/`, `notes/` - actual project/notes content (synced via Nextcloud/Syncthing instead, personal/client-specific)
- `ai/`, `docs/` - human/AI-shared working notes and local dev/planning docs, not meant for the public repo
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
    │   │   ├── Setup.svelte            # First-run wrapper around SettingsForm (full-screen chrome)
    │   │   ├── Settings.svelte         # Revisit-settings modal wrapper around SettingsForm
    │   │   ├── SettingsForm.svelte     # Shared connection/paths/Nextcloud-Locations form (Setup + Settings)
    │   │   ├── Main.svelte             # Project bar (pinned+recent) + ≡ picker + ⚙ settings + tab layout
    │   │   ├── ProjectPicker.svelte    # All-projects alphabetical grid with per-project pin toggle
    │   │   ├── Launchers.svelte        # Filtered launcher list + Links (viewers) section + NC↗ items
    │   │   ├── Notes.svelte            # Markdown viewer/editor
    │   │   ├── ShareTarget.svelte      # Share/Paste project-picker + preview dialog
    │   │   ├── PasteText.svelte        # In-app clipboard-paste alternative to Android share sheet
    │   │   ├── Viewers.svelte          # Unused (kept for reference; features merged into Launchers)
    │   │   └── QrScanner.svelte        # Camera overlay for Nextcloud QR scan
    │   └── lib/
    │       ├── store.js                # Svelte stores + async actions + pinned/recent ordering
    │       ├── webdav.js               # WebDAV client + Nextcloud path resolver + file-ID lookup
    │       └── cache.js                # Local offline read-through cache (Capacitor Filesystem, Directory.Data)
    ├── android/
    │   └── app/src/main/java/eu/ruadesign/projectflow/
    │       ├── MainActivity.java       # Registers WebDavPlugin/ShareReceiverPlugin/NextcloudAppPlugin
    │       ├── WebDavPlugin.java       # Custom OkHttp plugin for PROPFIND + binary (bodyBase64) uploads
    │       ├── ShareReceiverPlugin.java # Android ACTION_SEND share-sheet receiver (text/link + file shares)
    │       └── NextcloudAppPlugin.java # Explicit-package ACTION_VIEW launcher for com.nextcloud.client (needs a <queries> entry in AndroidManifest.xml)
    └── capacitor.config.json
```

### Key Technical Decisions

- **Custom `WebDavPlugin.java`**: Capacitor's built-in `CapacitorHttp` rejects `PROPFIND` (non-standard HTTP method), so a custom OkHttp-based plugin wraps arbitrary methods. `webdav.js` routes through it on Android, falling back to `fetch` in the browser.
- **Share-to-app (Android `ACTION_SEND`)**: a second manifest intent-filter makes the app appear in Android's share sheet for text/links (`text/plain`) and arbitrary files (`*/*`, separate filter). `ShareReceiverPlugin.java` exposes `getSharedData()` (reads and consumes `EXTRA_TEXT`/`EXTRA_SUBJECT`/`EXTRA_STREAM` off the current intent) plus a `shareReceived` event for the app-already-open case. A shared bare URL is appended as a new launcher item in a chosen project's "Added Resources" category; plain text is prepended to that project's note with a timestamped separator; a shared **file** is uploaded into the project's `documents/<slug>/` folder (via a new `bodyBase64` param on `WebDavPlugin`, since a JS string can't round-trip arbitrary binary bytes) and either noted or filed as a "Project Files" launcher item — mobile deliberately never invents a collision-safe slug or creates the documents folder itself; it uploads into what desktop has already set up, erroring with a clear message otherwise. File shares are never queued for offline retry (unlike link/text shares), since a base64 file body would blow past the small localStorage-backed retry queue's intended size.
- **CORS in browser testing**: `proxy.py` forwards WebDAV requests to Nextcloud with CORS headers added, for testing in a desktop browser instead of only on-device.
- **Settings screen (revisit setup)**: `SettingsForm.svelte` is shared between first-run `Setup.svelte` and a later-reachable `Settings.svelte` modal (⚙ button in the bottom nav bar), so the connection/paths/Nextcloud-Locations field set and test-before-save logic exist in exactly one place.
- **QR code setup**: scans Nextcloud's `nc://login/server:...&user:...&password:...` QR code via `jsqr` (pure JS, no native plugin) to auto-fill credentials.
- **No Viewers tab**: removed — a project's `webview_url` appears as a "Links (viewers)" section at the bottom of the Resources tab instead.
- **Nextcloud path resolution** (`webdav.js: resolveToNextcloudRelPath`): a launcher path containing `/Nextcloud/` is detected automatically; `config.nextcloudLocations` (a repeatable `{local, remote}` list, replacing an older single-alias pair) additionally handles symlinked paths that don't literally contain "Nextcloud" (e.g. desktop's `documents/`/`images/` folders), matching the **longest** `local` prefix. A detected item shows **NC↗**; opening one looks up the file's `oc:fileid` via a targeted `PROPFIND` and opens Nextcloud's file-scoped web URL directly, falling back to the plain folder URL if the lookup fails.
- **"Open in Nextcloud app"** (`config.openMethod`, experimental): builds the file's direct link (`{server}/f/{fileid}`) and hands it to `NextcloudAppPlugin.java`, which targets `com.nextcloud.client` explicitly via `Intent.setPackage()` + `queryIntentActivities()` (not `resolveActivity()`, which hardcodes a `MATCH_DEFAULT_ONLY` restriction real App Links don't satisfy) and a manifest `<queries>` declaration (required for Android 11+ package visibility) — falls straight through to the browser-open path on any failure at any step, which is what makes it safe to ship.
- **Project ordering**: pinned projects first, then recent (up to 8 total), via localStorage; the `≡` button opens an alphabetical grid with per-item pin toggle.
- **App icon**: `resources/icon.svg` is the master source; the deploy script regenerates all mipmap sizes via `@capacitor/assets`.
- **Responsive sizing**: fluid `clamp()`-based root font size, with `@media (min-width: 550px)` overrides for tablets/e-ink readers.
- **Theme system**: full light/dark CSS-variable system, with high-brightness dark-mode text for e-ink readability; persisted to localStorage.
- **Offline read cache** (`lib/cache.js`, `@capacitor/filesystem`): network-first, cache-as-fallback — `cacheProject()`/`getCachedProject()`/`cacheNote()`/`getCachedNote()` write/read a `{cachedAt, data}` envelope per project/note under app-private `Directory.Data` storage (needs no manifest permissions). Only falls back to the cache on a network error that looks offline-ish; a real 404/401 still surfaces normally. A "📦 Showing cached copy" banner shows whenever a stale fallback is in use. `precacheAllProjects()` (Settings → Advanced) is a manual bulk "get ready to go offline" action. Deliberately scoped to project configs + notes only for this first pass, not arbitrary NC↗ document/image content.
- **Notes path is separate** from the projects path — both configured independently in the Setup screen.

*(The real device-testing journey behind "Open in Nextcloud app" — an `nc://`-scheme theory ruled out via `dumpsys`, then a `resolveActivity()` vs. `queryIntentActivities()` gap, then an Android 11+ package-visibility gap, each found via a real `adb`-level comparison rather than guessed — is recorded in full in `ai/CLAUDE_ARCHIVE.md` → "Mobile App — Key Technical Decisions".)*

### Building the APK (NixOS)

Use the top-level `deploy_mobile.sh` script — it handles all steps automatically:

```bash
./deploy_mobile.sh
```

Steps: check ADB + Java → build web assets (`npm run build`) → regenerate Android icons from `resources/icon.svg` → sync to Android project (`cap sync android`) → build APK (Gradle) → install via ADB.

APK is at `mobile/app/android/app/build/outputs/apk/debug/app-debug.apk`.

### Setup Screen Configuration

Reachable both on first run and any time after, via the `⚙` button in `Main.svelte`'s header (see Settings screen above).

| Field | Example value | Notes |
|---|---|---|
| Server URL | `https://your-nextcloud.example.com` | |
| Username | `youruser` | |
| App Password | `xxxx-xxxx-xxxx-xxxx` | Nextcloud → Settings → Security → App passwords |
| Projects folder | `ProjectFlow` | Folder containing `.json` project files |
| Notes folder | `Notes/@Project Notes` | Folder containing `.md` notes files |
| Nextcloud Locations (Advanced) | `/home/user/Nextcloud` → *(blank)*, `/home/user/Nextcloud/ProjectFlowDocuments` → `ProjectFlowDocuments` | Optional, repeatable — local folders synced into Nextcloud, each paired with the Nextcloud-relative path it maps to |
| File opening method (Advanced) | `Browser` / `Nextcloud App` | Optional, experimental — see Nextcloud path resolution above |

Each Nextcloud Locations row handles one symlinked/synced directory. For example, if `~/Projects` is a symlink to `~/Nextcloud/Projects`, a row of `~/Projects` → `Projects` lets the app detect launcher entries pointing to `~/Projects/cop/guide.pdf` as Nextcloud-accessible. Unlike the old single-alias field this replaces, any number of rows can be registered at once — e.g. the main Nextcloud folder plus a separately-symlinked documents/images folder.
