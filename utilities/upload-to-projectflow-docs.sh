#!/usr/bin/env bash
#
# ProjectFlow Service Menu Handler — Upload to Docs
# Copies the selected file(s) INTO a project's own documents/<slug>/ folder
# (unlike add-projectflow-servicemenu.sh, which just references the file at its
# original location) and files each as a launcher item under that project's
# "Project Files" category — the external, Dolphin-triggered counterpart to the
# app's own "⬆ Upload File" launcher-header button (upload_file_to_project() in
# projectflow.py), reimplemented standalone here since a KDE service menu spawns a
# fresh process independent of whether ProjectFlow is currently running.
#
# Installation:
# 1. Copy projectflow-servicemenu.desktop to ~/.local/share/kio/servicemenus/
# 2. Edit the .desktop file's Exec= lines to point to where you installed both scripts
# 3. Make this script executable: chmod +x upload-to-projectflow-docs.sh
#
# The script auto-detects the projects/documents directories relative to its location,
# same convention as add-projectflow-servicemenu.sh.
#

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
APP_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECTS_DIR="$APP_ROOT/projects"
DOCUMENTS_DIR="$APP_ROOT/documents"

FILES=("$@")

if [ ${#FILES[@]} -eq 0 ]; then
    kdialog --error "No files selected"
    exit 1
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

selected=$(kdialog --combobox "Upload to which project's Documents folder?" "${projects[@]}")

if [ -z "$selected" ]; then
    exit 0
fi

PROJECT_FILE="$PROJECTS_DIR/${selected}.json"

if [ ! -f "$PROJECT_FILE" ]; then
    kdialog --error "Config file not found: $PROJECT_FILE"
    exit 1
fi

FILES_PYTHON="["
for f in "${FILES[@]}"; do
    escaped=$(printf '%s' "$f" | sed 's/\\/\\\\/g; s/"/\\"/g')
    FILES_PYTHON+="\"$escaped\","
done
FILES_PYTHON+="]"

python3 << EOF
import json
import os
import re
import shutil
import sys

config_path = "$PROJECT_FILE"
documents_dir = "$DOCUMENTS_DIR"
files_to_upload = $FILES_PYTHON

try:
    with open(config_path, 'r') as f:
        data = json.load(f)
except Exception as e:
    print(f"Error reading config: {e}", file=sys.stderr)
    sys.exit(1)

# --- Resolve (and persist) this project's documents_subfolder slug, replicating
# _slugify_project_name()/_get_or_create_project_documents_folder() exactly (see
# projectflow.py) so a slug computed here matches what the live app would compute/
# reuse for the same project, whether or not ProjectFlow is currently running. ---
slug = data.get('documents_subfolder')
if not slug:
    project_name = data.get('project_name') or os.path.splitext(os.path.basename(config_path))[0]
    candidate = re.sub(r'[\s-]+', '_', project_name.strip().lower())
    candidate = re.sub(r'[^\w]', '', candidate) or "project"
    slug = candidate
    n = 2
    while os.path.isdir(os.path.join(documents_dir, slug)):
        slug = f"{candidate}_{n}"
        n += 1
    data['documents_subfolder'] = slug

docs_folder = os.path.join(documents_dir, slug)
os.makedirs(docs_folder, exist_ok=True)

# Ensure columns exist
if 'columns' not in data or not data['columns']:
    data['columns'] = [[]]
column1 = data['columns'][0]

# Find or create "Project Files" category — same category new_code_file()'s own
# _ensure_project_files_category() uses, per the app's own convention that a
# file-manager/Resources upload files under Resources, not Documentation.
project_files = None
for category_dict in column1:
    if isinstance(category_dict, dict) and "Project Files" in category_dict:
        project_files = category_dict["Project Files"]
        break
if project_files is None:
    project_files = []
    column1.append({"Project Files": project_files})

existing_paths = {item[1] for item in project_files if len(item) > 1}

def titleize_stem(stem):
    # Mirrors _titleize_stem() in projectflow.py: underscore/hyphen -> space, title-case.
    return re.sub(r'[_-]+', ' ', stem).strip().title() or stem

uploaded = 0
skipped = 0
for src in files_to_upload:
    filename = os.path.basename(src)
    target = os.path.join(docs_folder, filename)
    if target in existing_paths or os.path.exists(target):
        skipped += 1
        continue
    try:
        shutil.copy2(src, target)
    except OSError as e:
        print(f"Error copying {src}: {e}", file=sys.stderr)
        skipped += 1
        continue
    stem = os.path.splitext(filename)[0]
    project_files.append([titleize_stem(stem), target, "default"])
    existing_paths.add(target)
    uploaded += 1

try:
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)
except Exception as e:
    print(f"Error writing config: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Uploaded {uploaded} file(s), skipped {skipped} (already present), to {config_path}")
EOF

result=$?

if [ $result -eq 0 ]; then
    kdialog --passivepopup "Uploaded to ${selected}'s Documents folder" 3
else
    kdialog --error "Failed to upload files to project"
fi
