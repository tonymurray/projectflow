#!/usr/bin/env python3
"""
Generate .desktop files for each ProjectFlow project
This allows KDE to distinguish different projects as separate applications
"""

import os
import glob

# Choose appropriate icon based on desktop environment
de = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
if 'gnome' in de:
    icon = "text-x-script"
else:
    icon = "preferences-desktop-icons"

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)  # Go up from utilities/

# Get absolute path to projectflow.py
projectflow_path = os.path.join(project_dir, "projectflow.py")

# Directory for desktop files
desktop_dir = os.path.expanduser("~/.local/share/applications")
os.makedirs(desktop_dir, exist_ok=True)

# Find all project files
projects_dir = os.path.join(project_dir, "projects")
project_files = glob.glob(os.path.join(projects_dir, "*.json"))

print(f"Found {len(project_files)} project files:")

for project_file in project_files:
    project_name = os.path.basename(project_file)

    # Create identifier from filename
    project_identifier = project_name.replace('.json', '')

    # Desktop file path
    desktop_file = os.path.join(desktop_dir, f"projectflow-{project_identifier}.desktop")

    # Desktop file content
    desktop_content = f"""[Desktop Entry]
Type=Application
Name=ProjectFlow ({project_identifier})
Comment=Quick launcher for {project_identifier}
Exec={projectflow_path} {project_file}
Icon={icon}
Terminal=false
Categories=Utility;Development;
StartupWMClass=ProjectFlow-{project_identifier}
"""

    # Write the desktop file
    with open(desktop_file, 'w') as f:
        f.write(desktop_content)

    # Make it executable
    os.chmod(desktop_file, 0o755)

    print(f"  Created: {desktop_file}")
    print(f"    - Name: ProjectFlow ({project_identifier})")
    print(f"    - WM Class: ProjectFlow-{project_identifier}")

print(f"\nDone! Created {len(project_files)} .desktop files in {desktop_dir}")
print("\nYou can now:")
print("1. Search for 'ProjectFlow' in KDE's application launcher")
print("2. See separate entries for each project")
print("3. Pin each one to different Activities panels")
print("\nNote: Run 'kbuildsycoca6' (or kbuildsycoca5 for KDE 5) to refresh menus immediately")
