#!/usr/bin/env bash
#
# ProjectFlow Service Menu Handler — Open Directory in ProjectFlow
# Prompts which existing project to open, then launches ProjectFlow for that
# project with its Folder viewer pointed straight at the selected directory (or,
# if a file was right-clicked instead, that file's containing directory) — via the
# --folder CLI flag (see main()/ProjectFlowApp.__init__ in projectflow.py). This is
# purely a launch-time convenience: it never creates a new project (unlike
# "Make Project"/folder_make_project_at()) and never writes anything to the chosen
# project's own config — config_folder_path/folder_path stays whatever it already
# was.
#
# Deliberately does NOT try to detect/reuse an already-open ProjectFlow window —
# there's no IPC between separate ProjectFlow processes, and window-focus detection
# is unreliable on a Wayland session running ProjectFlow through XWayland. Always
# spawns a fresh instance instead, the same "just open it" precedent
# open_config_in_new_window()/"Add to ProjectFlow" already use — opening the same
# project twice is a pre-existing, already-supported situation, not a new one.
#
# Installation:
# 1. Copy projectflow-servicemenu.desktop to ~/.local/share/kio/servicemenus/
# 2. Edit the .desktop file's Exec= lines to point to where you installed all three scripts
# 3. Make this script executable: chmod +x open-directory-in-projectflow.sh
#

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
APP_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECTS_DIR="$APP_ROOT/projects"
# Prefer the nix-shell wrapper when Nix is actually available: a Dolphin-spawned
# service menu process has no PyQt6 on its plain `python3`/PATH the way a terminal
# that's already sourced nix-shell does. open_config_in_new_window() (the in-app
# "open in new window" action) can call projectflow.py directly because it's spawned
# FROM an already-running, already-nix-shell'd ProjectFlow process and inherits that
# environment — this script has no such parent to inherit from, so it needs the
# wrapper itself on a Nix system. projectflow-nix's own `exec ... "$@"` passes the
# --folder flag through unchanged. On a non-Nix install (uv/pip, per the three setup
# paths in CLAUDE.md's "Running the Application"), there's no `nix-shell` to wrap
# with — dependencies already live in whatever environment python3 itself resolves
# to there, so projectflow.py directly is the correct (and only working) choice.
if [ -x "$APP_ROOT/projectflow-nix" ] && command -v nix-shell >/dev/null 2>&1; then
    APP_SCRIPT="$APP_ROOT/projectflow-nix"
else
    APP_SCRIPT="$APP_ROOT/projectflow.py"
fi

# Only the first selected item is used — opening one directory in one Folder viewer
# is the whole point; a multi-selection here has no single sensible target.
TARGET="$1"

if [ -z "$TARGET" ]; then
    kdialog --error "No file or folder selected"
    exit 1
fi

if [ -d "$TARGET" ]; then
    DIR="$TARGET"
else
    DIR="$(dirname "$TARGET")"
fi

projects=()
for file in "$PROJECTS_DIR"/*.json; do
    if [ -f "$file" ]; then
        basename="${file##*/}"
        name="${basename%.json}"
        projects+=("$name")
    fi
done

if [ ${#projects[@]} -eq 0 ]; then
    kdialog --error "No project files found in $PROJECTS_DIR"
    exit 1
fi

selected=$(kdialog --combobox "Open this directory in which project?" "${projects[@]}")

if [ -z "$selected" ]; then
    exit 0
fi

PROJECT_FILE="$PROJECTS_DIR/${selected}.json"

if [ ! -f "$PROJECT_FILE" ]; then
    kdialog --error "Config file not found: $PROJECT_FILE"
    exit 1
fi

setsid "$APP_SCRIPT" "$PROJECT_FILE" --folder "$DIR" >/dev/null 2>&1 &
disown
