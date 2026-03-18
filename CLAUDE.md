# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProjectFlow (formerly "Folder Opener") is a PyQt6-based KDE Plasma application that provides a graphical launcher for quickly opening projects, files, and folders in various applications. It uses JSON configuration files to define categorized shortcuts. The app displays a three-panel layout: Shortcuts (left), Viewer (center), and Notepad (right).

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
- `recent_projects`: List of up to 10 recently used projects (for quick-access bar)
- `pinned_projects`: List of projects pinned to the front of the quick-access bar (drag to reorder/pin, ↺ to reset)
- `theme`: Color theme - `"light"`, `"dark"`, or `"system"` (default: `"system"` - follows desktop preference)
- `joplin_token`: Joplin Web Clipper API token (enables manual sync button in notepad toolbar)
- `notes_folder`: Path where notes are stored as markdown files (default: `notes/` in project dir). Set to `"~/Nextcloud/Notes/ProjectFlow/"` for Nextcloud sync
- `pdfviewer`: Path to an external PDF viewer application (e.g., `"~/Programs/notesviewer/notesviewer.py"`). When set, adds an "External" button to the PDF toolbar that opens the current PDF in this viewer. Omit this setting to hide the button.
- `open_note_external`: External markdown editor command (e.g., `"zettlr"`, `"code"`, `"kate"`). When set, adds a 📝 button to the notepad toolbar that opens the current note's markdown file in this editor.
- `enable_baloo_tags`: Enable/disable Baloo tag querying for tagged files (default: `true`). Set to `false` on non-KDE systems.
- `terminal`: External terminal application (default: auto-detected based on desktop environment). Used by terminal-related handlers and the Console viewer's "External" button. Leave empty for auto-detection.

### Per-Config Options

These options can be set in individual config JSON files:
- `pdf_file`: Default PDF file to load for this config
- `webview_url`: Default URL to load in web viewer for this config
- `image_file`: Default image file to load for this config
- `console_path`: Default directory for the embedded console
- `column2_default`: Which viewer to show by default - `"pdf"`, `"webview"`, `"image"`, `"help"`, or `"console"`
- `terminal`: Terminal emulator override for this config (e.g., `"gnome-terminal"`, `"alacritty"`). Overrides global terminal setting.

These options can also be set via the 📌 button in each viewer toolbar:
- Load a PDF, webpage, or image in the central viewer
- Click 📌 to save it as the default AND set that viewer as `column2_default`
- To change default viewer type: switch to the desired viewer, load content, click 📌

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
- Notes auto-save on every change
- Markdown format enables sync with Nextcloud Notes or any markdown-compatible tool
- Legacy HTML notes in JSON projects are automatically migrated to markdown files

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

### `SettingsDialog` (settings dialog in projectflow.py)

- `__init__(parent)`: Creates tabbed dialog with Settings and Icon Preferences tabs
- `create_settings_tab()`: Builds form for `.projectflow_settings.json` options
- `create_icon_preferences_tab()`: Builds list view for `icon_preferences.json` management
- `load_icon_preferences()`: Populates icon list from JSON file
- `add_icon_preference()` / `edit_icon_preference()` / `delete_icon_preference()`: CRUD operations for icon mappings
- `apply_settings()`: Saves both settings and icon preferences to their respective files
- `update_theme()`: Refreshes dialog styling when theme changes

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
- `tail_log` - Tail debug.log in terminal
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

`directorydev` - Open full dev environment (Dolphin + terminal + VSCode, optionally npm):
```python
("My Project", "~/projects/myapp", "directorydev")           # Opens 3 apps (no npm)
("My Project", "~/projects/myapp dev", "directorydev")       # Also runs npm run dev
("My Project", "~/projects/myapp build", "directorydev")     # Also runs npm run build
("My Project", "~/projects/myapp test", "directorydev")      # Also runs npm test
```

The main button opens all apps at once. Individual icon buttons (🗄️ $_ 💠) to the right of the main button allow opening each app separately. The npm button (⚡) only appears if a recognized command is specified: start, dev, build, test, install, run.

## UI Features

- **Three-panel layout**: Shortcuts (left) | Viewer (center) | Notepad (right)
- **Shortcuts panel**: Single column of categorized launchers with "Open All" buttons per category
- **Central viewer**: Toggles between PDF viewer, web browser, image viewer, help, and console (cycles PDF → Web → Image → Help → Console). Each viewer has an "External" button to open in a standalone application.
- **Embedded console**: IPython/qtconsole for quick Python and shell commands (`!ls`, `!git status`). Limitations: no interactive programs (nano, vim) - use External button for full terminal.
  - **Why qtconsole**: Well-established Jupyter project with strong community support. Alternatives considered:
    - `termqt` - Pure Python terminal (supports nano/vim), but small community (61 stars), single maintainer
    - `pyqtermwidget` / `qtermwidget` - C++ based, requires compilation, complex bindings
    - `QProcess + QTextEdit` - Simple but no colors, no terminal features
  - Current approach: qtconsole + External button provides best balance of features and reliability
- **Preview buttons**: Web links (firefox/chrome) show 🌐 button to preview in webview; images (gwenview/gimp/krita) show 🖼️ button to preview in image viewer
- **Projects section**: Unified project switcher with two modes toggled by 🕐 button:
  - **Recent mode** (default): Shows pinned + recent projects (up to 10) with drag-drop reordering. Pinned projects shown with underline. ↺ button resets pinned order. Backfills from available projects if some are missing/renamed.
  - **Alphabetical mode**: Shows all projects in rows of 10, sorted alphabetically. Full rows stretch to fill width; last incomplete row is left-aligned.
- **Panel headers**: Grey headers at top of each panel (#5a5a5a)
- **Category headers**: Clickable "Open All" buttons for each category (light blue #3498db)
- **Item buttons**: Individual launchers with application icons. Drag to reorder within category (saves to config).
- **Edit mode**: Toggle to enable editing - shows "Add Entry" buttons per category and "Add Category" button at bottom

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

**Project Items Tab** - Edit categories and items for the current config:
- Tree-based editor showing all shortcuts
- Drag-drop reordering for categories and items
- Double-click to edit categories or items
- Add/Delete buttons in edit dialogs
- Application selector populated from icon_preferences.json

**Project Defaults Tab** - Configure viewer defaults for the current config:
- Default Viewer: Select which viewer opens by default (pdf, webview, image, help, console)
- PDF File: Path to default PDF file with browse button
- Web URL: Default URL for webview
- Image File: Path to default image with browse button
- Console Path: Working directory for embedded console with browse button

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
- **Terminal**: Terminal application for console external button
- **Notes Folder**: Path where markdown notes are stored
- **Enable Baloo Tags**: Checkbox to enable/disable KDE Baloo tag integration
- **Joplin Token**: API token for Joplin Web Clipper sync

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

## Potential Improvements

### Make File Manager Agnostic (like terminal)

Similar to the terminal-agnostic changes, the app currently has hardcoded "dolphin" references that should be made configurable:

1. **Add `detect_default_file_manager()`**: Auto-detect based on desktop environment (KDE→dolphin, GNOME→nautilus, XFCE→thunar, etc.)
2. **Add `file_manager` setting**: Allow users to configure their preferred file manager
3. **Update handlers**: `dolphin_tabs`, `directorydev` action for "dolphin"
4. **Config migration needed**: Once-off find/replace in config files for:
   - Handler/app names: `"dolphin"` → `"file_manager"`
   - Display labels containing "Dolphin" → more generic names

### Config Migration Tasks

After handler renames, existing config files may need updating:
- `"konsoles"` → `"ssh_session"` or `"ssh_cd_npm"`
- `"konsolelog"` → `"tail_log"`
- `"konsolersync"` → `"rsync_backup"`
- Display labels referencing "Konsole" → "Terminal"
