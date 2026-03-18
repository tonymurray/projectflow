# ProjectFlow - Build Specification

This document is a reverse-engineered specification that could be used to rebuild ProjectFlow from scratch, or as a template for similar applications.

## 1. Project Overview

### Purpose
A KDE Plasma launcher application for power users who manage many projects, files, and URLs. Provides quick access to open items in specific applications without navigating file managers or remembering paths.

### Problem Statement
Developers and power users often have:
- Multiple projects across different directories
- Frequently accessed files that should open in specific apps
- URLs for dashboards, documentation, admin panels
- SSH connections to various servers
- Need for quick context switching between project sets

### Target Users
- Developers with multiple active projects
- System administrators managing multiple servers
- Users who prefer keyboard/click efficiency over file browsing

## 2. Tech Stack

### Runtime
- **Language**: Python 3.13+
- **GUI Framework**: PyQt6
- **Dependency Management**: nix-shell (shebang-based, no manual install)
- **Platform**: Linux (KDE Plasma optimized, but works on other DEs)

### File Formats
- **Configurations**: JSON files (Python-executable for advanced use cases)
- **Settings**: JSON (machine-specific, not version controlled)
- **Notes**: Markdown files (external sync friendly)

### External Dependencies
- `xdg-open` for default application handling
- `konsole` for terminal operations
- `flatpak` for sandboxed applications (optional)

## 3. Data Model

### 3.1 Configuration File Schema

```python
# Each config defines three columns of categorized items

COLUMN_1 = [
    {
        "Category Name": [
            ("Display Name", "/path/to/item", "application"),
            ("Website", "https://example.com", "firefox"),
        ]
    },
    {
        "Another Category": [
            ("Item", "~/Documents/file.txt", "kate"),
        ]
    }
]

COLUMN_2 = [...]  # Same structure
COLUMN_3 = [...]  # Same structure

# Application metadata for icons and display names
APP_INFO = {
    "kate": {"icon": "kate", "name": "Kate"},
    "firefox": {"icon": "firefox", "name": "Firefox"},
    "konsole": {"icon": "utilities-terminal", "name": "Terminal"},
}

# Column headers displayed above each column
COLUMN_HEADERS = ["Development", "Documents", "Utilities"]
```

### 3.2 Settings File Schema

```json
{
  "default_config": "configs/main_config.json",
  "last_used_config": "configs/work_config.json",
  "recent_configs": [
    "configs/work_config.json",
    "configs/personal_config.json"
  ],
  "configs_directory": "configs",
  "notes_folder": "notes/",
  "joplin_token": null
}
```

**Field Descriptions:**
- `default_config`: Config loaded on startup (set via UI button)
- `last_used_config`: Auto-updated when switching configs
- `recent_configs`: Up to 8 most recently used configs (for quick-access bar)
- `configs_directory`: Subdirectory to scan for available configs
- `notes_folder`: Where per-config markdown notes are stored
- `joplin_token`: Optional API token for Joplin sync integration

### 3.3 Notes Storage

- Each config gets a corresponding markdown file
- Filename derived from config: `work_config.json` → `work.md`
- Auto-save on every change (no save button needed)
- Plain markdown enables sync with Nextcloud Notes, Obsidian, etc.

## 4. UI Layout

### 4.1 Window Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ RECENT CONFIGS BAR                                              │
│ Recent: [1 Main] [2 Work] [3 Personal] [4 Server] ...          │
├─────────────────────────────────────────────────────────────────┤
│ NOTEPAD TOOLBAR                                                 │
│ [Toggle Notepad]                              [Joplin Sync]     │
├─────────────────────────────────────────────────────────────────┤
│ MAIN CONTENT AREA (scrollable)                                  │
│ ┌───────────────────┬───────────────────┬───────────────────┐   │
│ │ COLUMN HEADER 1   │ COLUMN HEADER 2   │ COLUMN HEADER 3   │   │
│ ├───────────────────┼───────────────────┼───────────────────┤   │
│ │ [Category    All] │ [Category    All] │ [Category    All] │   │
│ │  [Item] [Item]    │  [Item] [Item]    │  [Item]           │   │
│ │  [Item]           │  [Item]           │                   │   │
│ │                   │                   │                   │   │
│ │ [Category    All] │ [Category    All] │ [Category    All] │   │
│ │  [Item] [Item]    │  [Item]           │  [Item] [Item]    │   │
│ └───────────────────┴───────────────────┴───────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│ ACTION BUTTONS                                                  │
│ [Load Config] [Edit Config] [Refresh] [Set as Default]         │
├─────────────────────────────────────────────────────────────────┤
│ NOTEPAD (collapsible)                                           │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Markdown editor - per-config notes                          │ │
│ │ Auto-saves on change                                        │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Specifications

**Recent Configs Bar:**
- Horizontal row of numbered buttons (1-8)
- Current config: larger (32px height, bold, white border)
- Other configs: smaller (26px height)
- Click to switch configs instantly

**Column Headers:**
- Grey background (#5a5a5a), white text
- Spans full width of column
- Text from config's COLUMN_HEADERS list

**Category Groups:**
- Header button with category name + "Open All" functionality
- Light blue background (#3498db)
- Click header to open all items in category
- Items arranged in flow layout below header

**Item Buttons:**
- Icon (from APP_INFO or system theme) + display name
- Hover effect for feedback
- Click to launch item in specified application

**Action Buttons:**
- Four buttons in logical workflow order
- Dark-to-light green gradient left-to-right
- Load Config (#094d2e) → Edit (#0d5f3a) → Refresh (#168a5f) → Set Default (#27ae60)

**Notepad:**
- Collapsible via toggle button
- QTextEdit with markdown content
- Auto-saves to notes_folder/[config-name].md
- Optional Joplin sync button (visible only if token configured)

## 5. Application Logic

### 5.1 Startup Sequence

1. Load settings from `.projectflow_settings.json`
2. Determine config to use (priority order):
   a. Default config (if set and exists)
   b. Last used config (if exists)
   c. Standard default: `projectflow_config.json` or `configs/projectflow_config.json`
3. Load and execute config file
4. Build UI from config data
5. Load notes for current config
6. Display window

### 5.2 Config Switching

1. User selects new config (recent bar or Load button)
2. Save current notes (auto-save)
3. Update `last_used_config` in settings
4. Add to `recent_configs` (max 8, no duplicates)
5. Clear and rebuild entire UI
6. Load notes for new config

### 5.3 Launch Logic

When user clicks an item button, determine launch method:

```
1. Check COMPLEX_HANDLERS in launch_handlers.py
   → If match, call handler function

2. Check LAUNCH_HANDLERS in launch_handlers.py
   → If match, execute command template

3. Check for terminal command patterns (&&, ||, ;, starts with cd/npm)
   → Launch in Konsole with hold

4. Check for Flatpak app (starts with "com.")
   → Launch via `flatpak run`

5. Default
   → Launch via subprocess.Popen([app, path])
```

Path handling:
- Expand `~` to home directory
- Support URLs (http://, https://)
- Support absolute and relative paths

### 5.4 Launch Handlers

**Simple Handlers** (command templates):
```python
LAUNCH_HANDLERS = {
    "firefox": {
        "command": ["firefox", "--new-window", "{path}"],
        "description": "Open in Firefox (new window)"
    },
    "terminal": {
        "command": ["konsole", "--workdir", "{path}"],
        "description": "Open folder in terminal"
    },
}
```

**Complex Handlers** (Python functions):
```python
def handle_npm(path, expanded_path):
    """Parse path for npm command, launch in Konsole"""
    # "~/project dev" → npm run dev in ~/project
    pass

COMPLEX_HANDLERS = {
    "npm": handle_npm,
}
```

## 6. Color Scheme

### Primary Colors

| Element | Color | Hex |
|---------|-------|-----|
| Recent bar background | Dark blue | #1e5a8e |
| Recent bar hover | Light blue | #2570a8 |
| Column headers | Medium grey | #5a5a5a |
| Category headers | Light blue | #3498db |
| Load Config button | Dark green | #094d2e |
| Edit Config button | Green | #0d5f3a |
| Refresh button | Medium green | #168a5f |
| Set Default button | Light green | #27ae60 |

### Design Principles

- Cool color palette (greys, blues, greens)
- Visual hierarchy through color intensity
- Current/selected items indicated by size and border, not color change
- Compact layout minimizing wasted vertical space
- Consistent hover feedback on interactive elements

## 7. File Structure

```
projectflow/
├── projectflow.py              # Main application (single file)
├── launch_handlers.py          # Custom launch handlers
├── icon_preferences.json       # App icon/name mappings
├── CLAUDE.md                   # Development reference
├── .gitignore
├── .projectflow_settings.json  # User settings (not in git)
├── configs/                    # Configuration files
│   ├── main_config.json
│   └── work_config.json
├── notes/                      # Per-config markdown notes
│   ├── main.md
│   └── work.md
└── extras/                     # Utility scripts
    ├── build_specification.md  # This file
    └── migrate_configs.py
```

## 8. Key Implementation Details

### 8.1 Dynamic UI Generation

The UI is generated dynamically from config data, not hardcoded:
- `build_main_content()` iterates through COLUMN_1/2/3
- Creates category groups with flow layouts
- Buttons created from item tuples

On refresh, the entire main content is destroyed and rebuilt:
```python
def refresh_projects(self):
    # Clear existing content
    self.clear_layout(self.main_layout)
    # Reload config
    self.load_config()
    # Rebuild UI
    self.build_main_content()
```

### 8.2 Settings Persistence

Settings are loaded at startup and saved after every change:
```python
def save_settings(self):
    with open(self.settings_file, 'w') as f:
        json.dump(self.settings, f, indent=2)
```

### 8.3 Notes Auto-Save

Notes save on every text change with a short debounce:
```python
self.notepad.textChanged.connect(self.save_notes)
```

### 8.4 Icon Resolution

Icons are resolved in order:
1. Explicit icon in APP_INFO
2. Application name as icon name (system theme lookup)
3. Fallback generic icon

## 9. Extension Points

### Adding New Launch Handlers

1. **Simple handler**: Add to LAUNCH_HANDLERS dict with command template
2. **Complex handler**: Write Python function, add to COMPLEX_HANDLERS dict

### Adding New Config Fields

1. Add field to config file
2. Extract in `load_config()` method
3. Use in `build_main_content()` or other UI methods

### Theming

Colors are defined inline in the code. To theme:
1. Extract colors to a theme dict
2. Apply via setStyleSheet with f-string interpolation

## 10. Future Considerations

### Potential Enhancements
- Keyboard navigation (arrow keys, number shortcuts)
- Search/filter across all items
- Drag-and-drop config editing
- Import from existing launchers (KDE, GNOME)
- Multiple windows for different contexts

### Alternative Implementations
- **Rust + Slint/GTK**: Single binary, faster startup
- **Electron/Tauri**: Web UI, cross-platform
- **QML**: More fluid animations, same Qt ecosystem

---

*This specification is reverse-engineered from the working ProjectFlow application. It serves as both documentation of design decisions and a template for building similar applications.*
