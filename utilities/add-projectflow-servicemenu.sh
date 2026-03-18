#!/usr/bin/env bash
#
# ProjectFlow Service Menu Handler
# Adds files/folders to a ProjectFlow project's "Added Resources" category
#
# Installation:
# 1. Copy projectflow-servicemenu.desktop to ~/.local/share/kio/servicemenus/
# 2. Edit the .desktop file to point Exec= to where you installed this script
# 3. Make this script executable: chmod +x add-projectflow-servicemenu.sh
#
# The script auto-detects the projects directory relative to its location.
#

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
PROJECTS_DIR="$(dirname "$SCRIPT_DIR")/projects"

# Get the file(s) to add - handle multiple selections
FILES=("$@")

if [ ${#FILES[@]} -eq 0 ]; then
    kdialog --error "No files selected"
    exit 1
fi

# Get list of project files (without path, without .json extension)
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

# Show selection dialog
selected=$(kdialog --combobox "Add to which project?" "${projects[@]}")

if [ -z "$selected" ]; then
    # User cancelled
    exit 0
fi

PROJECT_FILE="$PROJECTS_DIR/${selected}.json"

if [ ! -f "$PROJECT_FILE" ]; then
    kdialog --error "Config file not found: $PROJECT_FILE"
    exit 1
fi

# Build a Python list of files (properly quoted)
FILES_PYTHON="["
for f in "${FILES[@]}"; do
    # Escape backslashes and quotes for Python string
    escaped=$(printf '%s' "$f" | sed 's/\\/\\\\/g; s/"/\\"/g')
    FILES_PYTHON+="\"$escaped\","
done
FILES_PYTHON+="]"

# Add files to "Added Resources" category in COLUMN_1
python3 << EOF
import json
import sys
import os

config_path = "$PROJECT_FILE"
files_to_add = $FILES_PYTHON

try:
    with open(config_path, 'r') as f:
        data = json.load(f)
except Exception as e:
    print(f"Error reading config: {e}", file=sys.stderr)
    sys.exit(1)

# Ensure columns exist
if 'columns' not in data:
    data['columns'] = [[], [], []]
while len(data['columns']) < 3:
    data['columns'].append([])

column1 = data['columns'][0]

# Find or create "Added Resources" category
added_resources = None
for category_dict in column1:
    if "Added Resources" in category_dict:
        added_resources = category_dict["Added Resources"]
        break

if added_resources is None:
    # Create the category at the end of column 1
    added_resources = []
    column1.append({"Added Resources": added_resources})

# Add files that aren't already present
added = 0
existing_paths = [item[1] for item in added_resources]

for filepath in files_to_add:
    if filepath not in existing_paths:
        # Get display name from filename
        display_name = os.path.basename(filepath)
        # Determine app based on file type
        if os.path.isdir(filepath):
            app = "file_manager"
        else:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg'):
                app = "gwenview"
            else:
                app = "default"
        added_resources.append([display_name, filepath, app])
        added += 1

try:
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)
except Exception as e:
    print(f"Error writing config: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Added {added} item(s) to {config_path}")
EOF

result=$?

if [ $result -eq 0 ]; then
    if [ ${#FILES[@]} -eq 1 ]; then
        kdialog --passivepopup "Added to $selected" 3
    else
        kdialog --passivepopup "Added ${#FILES[@]} files to $selected" 3
    fi
else
    kdialog --error "Failed to add files to project"
fi
