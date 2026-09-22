#!/usr/bin/env bash
#
# ProjectFlow Service Menu Installer
#
# Installs the three Dolphin/KIO service menu actions (Add to ProjectFlow, Upload
# to ProjectFlow Docs, Open Directory in ProjectFlow) with their Exec= lines
# rewritten to THIS checkout's real absolute path. The tracked
# projectflow-servicemenu.desktop deliberately ships with bare script names (no
# machine-specific path baked into the repo, per CLAUDE.md's Code Cleanup
# Guidelines) — that only works if utilities/ happens to be on $PATH, which it
# normally isn't, producing a "could not find the program" error from Dolphin. This
# script does the "edit the Exec lines" step the tracked file's own comment asks
# for, automatically.
#
# Safe to re-run any time (e.g. after `git pull` brings in a new/changed template,
# or if the installed copy gets overwritten by a fresh manual `cp`) — it always
# regenerates the installed file fresh from the tracked template, so a re-run never
# needs its own separate "already installed" handling.
#
# Usage: ./utilities/install-servicemenu.sh

set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SRC_FILE="$SCRIPT_DIR/projectflow-servicemenu.desktop"
DEST_DIR="$HOME/.local/share/kio/servicemenus"
DEST_FILE="$DEST_DIR/projectflow-servicemenu.desktop"

if [ ! -f "$SRC_FILE" ]; then
    echo "Error: $SRC_FILE not found" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

# Rewrite each bare "Exec=<script>.sh %F" line to that script's absolute path in
# THIS checkout. Matches only a plain filename right after "Exec=" (not anything
# already-absolute), so running this against a hand-edited or previously-installed
# file as the source would leave an already-correct line untouched too.
sed -E "s|^Exec=([A-Za-z0-9_.-]+\.sh)( .*)?\$|Exec=$SCRIPT_DIR/\1\2|" "$SRC_FILE" > "$DEST_FILE"

chmod +x "$SCRIPT_DIR/add-projectflow-servicemenu.sh" \
         "$SCRIPT_DIR/upload-to-projectflow-docs.sh" \
         "$SCRIPT_DIR/open-directory-in-projectflow.sh"

echo "Installed service menu to $DEST_FILE"
echo "Exec lines point to: $SCRIPT_DIR"
echo "Right-click a file or folder in Dolphin to see the new actions — no restart needed."
