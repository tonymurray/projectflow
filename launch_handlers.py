"""
Launch Handlers for ProjectFlow

This file defines custom application launchers that extend ProjectFlow's
built-in launch capabilities. You can add your own handlers here.

Built-in handlers (always available, cannot be overridden):
  - "browser"      : Opens URLs in your default browser (xdg-open)
  - "file_manager" : Opens folders in your default file manager (xdg-open)
  - "editor"       : Opens files in your default editor (xdg-open)
  - "default"      : Lets the system decide how to open the path (xdg-open)

Handler types:
  1. Simple handlers (LAUNCH_HANDLERS): Define a command template
  2. Complex handlers (COMPLEX_HANDLERS): Python functions for advanced logic
"""

import subprocess
import shlex
import shutil
import os

# =============================================================================
# TERMINAL CONFIGURATION
# =============================================================================
# This will be set by projectflow.py at runtime with the configured terminal

_terminal_config = {
    "terminal": "konsole",  # Will be overwritten by projectflow.py
    "workdir_command_builder": None,  # Function to build workdir command
    "shell_command_builder": None,  # Function to build shell command
}

# Editor and file manager configuration (set by projectflow.py at runtime)
_editor_config = None
_file_manager_config = None


def set_terminal_config(terminal, workdir_builder, shell_builder):
    """Set the terminal configuration. Called by projectflow.py at startup."""
    _terminal_config["terminal"] = terminal
    _terminal_config["workdir_command_builder"] = workdir_builder
    _terminal_config["shell_command_builder"] = shell_builder


def set_editor_config(editor):
    """Set the editor configuration. Called by projectflow.py at startup."""
    global _editor_config
    _editor_config = editor


def set_file_manager_config(file_manager):
    """Set the file manager configuration. Called by projectflow.py at startup."""
    global _file_manager_config
    _file_manager_config = file_manager


def _get_editor():
    """Get the configured editor name."""
    return _editor_config or "code"


def _get_file_manager():
    """Get the configured file manager name."""
    return _file_manager_config or "dolphin"


def _get_terminal():
    """Get the configured terminal name."""
    return _terminal_config["terminal"]


def _build_terminal_workdir_cmd(path):
    """Build command to open terminal at specified directory."""
    builder = _terminal_config["workdir_command_builder"]
    if builder:
        return builder(path)
    # Fallback if not configured (shouldn't happen in normal use)
    terminal = _get_terminal()
    return [terminal, "--workdir", path]


def _build_terminal_shell_cmd(shell_cmd, hold=False):
    """Build command to run shell command in terminal."""
    builder = _terminal_config["shell_command_builder"]
    if builder:
        return builder(shell_cmd, hold)
    # Fallback if not configured
    terminal = _get_terminal()
    cmd = [terminal]
    if hold:
        cmd.append("--hold")
    cmd.extend(["-e", "bash", "-c", shell_cmd])
    return cmd


# =============================================================================
# SIMPLE HANDLERS
# =============================================================================
# Each handler defines a command to execute. Use {path} as placeholder for the
# expanded file/folder path.
#
# Options:
#   "command"     : List of command arguments, or string for shell commands
#   "type"        : "exec" (default) or "shell" (runs through bash -c)
#   "terminal"    : True to run in terminal
#   "hold"        : True to keep terminal open after command finishes
#   "description" : Human-readable description (for documentation)

LAUNCH_HANDLERS = {
    # Note: "terminal" handler is now handled dynamically in projectflow.py
    # to use the configured terminal emulator

    # Tail a debug.log file in terminal
    "tail_log": {
        "type": "shell",
        "command": "cd {path} && tail -n 500 -f debug.log",
        "terminal": True,
        "hold": True,
        "description": "Tail debug.log in terminal",
        "example": "~/projects/myapp"
    },

    # Tail a debug.log file in kitty (--hold keeps window open after Ctrl+C)
    "kitty_tail": {
        "command": ["kitty", "--directory", "{path}", "--hold", "tail", "-n", "500", "-f", "debug.log"],
        "description": "Tail debug.log in kitty",
        "example": "~/projects/myapp"
    },

    # Note: rsync_backup is now a complex handler with safety checks (see COMPLEX_HANDLERS)

    # Firefox: Open in a new window
    "firefox": {
        "command": ["firefox", "--new-window", "{path}"],
        "description": "Open URL in a new Firefox window",
        "example": "https://wikipedia.org"
    },

    # Chrome: Open via Flatpak in a new window
    "chrome": {
        "command": ["flatpak", "run", "--command=/app/bin/chrome",
                    "com.google.Chrome", "--new-window", "{path}"],
        "description": "Open URL in Chrome via Flatpak",
        "example": "https://wikipedia.org"
    },
}


# =============================================================================
# COMPLEX HANDLERS
# =============================================================================
# For handlers that need Python logic beyond simple command templates.
# Each function receives (path, expanded_path) and should return a status message.

def handle_ssh_session(path, expanded_path):
    """
    SSH session handler with optional path and command.

    Usage in config:
        ["Server SSH", "user@host /path command args", "ssh_session"]

    If second part starts with /, ~, or . it's treated as a path to cd to.
    Otherwise, everything after user@host is treated as a command.

    Examples:
        "user@server"                    -> SSH to server, run bash
        "user@server /var/www"           -> SSH, cd to /var/www, run bash
        "user@server /app ./go.sh"       -> SSH, cd to /app, run ./go.sh
        "user@server npm start"          -> SSH, run npm start in home dir
    """
    parts = expanded_path.split()
    remote_user, remote_host = parts[0].split("@")

    remote_dir = "~"
    remote_command = ""

    if len(parts) > 1:
        second_part = parts[1]
        # If second part looks like a path, treat it as directory
        if second_part.startswith(('/','~', '.')):
            remote_dir = second_part
            remote_command = " ".join(parts[2:])
        else:
            # Otherwise treat everything as a command (no cd)
            remote_command = " ".join(parts[1:])

    if not remote_command:
        remote_command = "bash"

    # Build the remote command safely
    remote_command_quoted = shlex.quote(f"cd {remote_dir} && {remote_command}")

    # Build shell command that keeps terminal open after SSH exits
    shell_cmd = f'ssh -t {remote_user}@{remote_host} {remote_command_quoted}; exec bash'
    cmd = _build_terminal_shell_cmd(shell_cmd, hold=False)  # exec bash keeps it open
    subprocess.Popen(cmd, start_new_session=True)

    return f"SSH connection to {remote_user}@{remote_host}"


def handle_terminal_npm(path, expanded_path):
    """
    Run npm start in terminal (legacy handler).

    Usage in config:
        ["My App", "~/projects/myapp", "terminal_npm"]
    """
    shell_cmd = f'cd {shlex.quote(expanded_path)} && npm start'
    cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    subprocess.Popen(cmd, start_new_session=True)
    return f"npm start in {expanded_path}"


def handle_npm(path, expanded_path):
    """
    Run npm commands in terminal.

    Usage in config:
        ["My App", "~/projects/myapp", "npm"]           -> npm start
        ["My App", "~/projects/myapp dev", "npm"]       -> npm run dev
        ["My App", "~/projects/myapp build", "npm"]     -> npm run build
        ["My App", "~/projects/myapp test", "npm"]      -> npm test
        ["My App", "~/projects/myapp install", "npm"]   -> npm install

    The command is appended after the path, separated by space.
    """
    parts = expanded_path.split()
    project_path = os.path.expanduser(parts[0])
    npm_cmd = parts[1] if len(parts) > 1 else "start"

    # Map common commands to their npm equivalents
    if npm_cmd in ("start", "test", "install"):
        shell_cmd = f'cd {shlex.quote(project_path)} && npm {npm_cmd}'
    else:
        shell_cmd = f'cd {shlex.quote(project_path)} && npm run {npm_cmd}'

    cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    subprocess.Popen(cmd, start_new_session=True)
    return f"npm {npm_cmd} in {project_path}"


def handle_terminal_cmd(path, expanded_path):
    """
    Open terminal at a directory with optional command.

    Usage in config:
        ["My Project", "~/project command args", "terminal_cmd"]

    Examples:
        "~/project"              -> cd ~/project, open bash
        "~/project ./go.sh"      -> cd ~/project && ./go.sh
        "~/project npm run dev"  -> cd ~/project && npm run dev
    """
    parts = expanded_path.split()
    project_path = os.path.expanduser(parts[0])
    command = " ".join(parts[1:]) if len(parts) > 1 else ""

    if command:
        shell_cmd = f'cd {shlex.quote(project_path)} && {command}'
        cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    else:
        # Just open terminal at directory
        cmd = _build_terminal_workdir_cmd(project_path)

    subprocess.Popen(cmd, start_new_session=True)
    return f"Terminal at {project_path}" + (f" running {command}" if command else "")


def handle_directorydev_action(expanded_path, action):
    """
    Execute a single directorydev action.

    Args:
        expanded_path: The path (possibly with npm command appended)
        action: One of "file_manager", "terminal", "editor", "npm"
                (legacy names "dolphin" and "code" are also accepted)
    """
    parts = expanded_path.split()
    project_path = os.path.expanduser(parts[0])
    npm_cmd = parts[1] if len(parts) > 1 else "dev"

    if action in ("dolphin", "file_manager"):
        subprocess.Popen([_get_file_manager(), project_path], start_new_session=True)
    elif action == "terminal":
        cmd = _build_terminal_workdir_cmd(project_path)
        subprocess.Popen(cmd, start_new_session=True)
    elif action in ("code", "editor"):
        subprocess.Popen([_get_editor(), project_path], start_new_session=True)
    elif action == "npm":
        if npm_cmd in ("start", "test", "install"):
            shell_cmd = f'cd {shlex.quote(project_path)} && npm {npm_cmd}'
        else:
            shell_cmd = f'cd {shlex.quote(project_path)} && npm run {npm_cmd}'
        cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
        subprocess.Popen(cmd, start_new_session=True)


def handle_directorydev(path, expanded_path):
    """
    Open a full dev environment: editor, terminal, file manager, and optionally npm.

    Uses the configured editor (default: code) and file manager (default: dolphin).

    Usage in config:
        ["My Project", "~/projects/myapp", "directorydev"]           -> Opens 3 apps (no npm)
        ["My Project", "~/projects/myapp dev", "directorydev"]       -> npm run dev
        ["My Project", "~/projects/myapp build", "directorydev"]     -> npm run build
        ["My Project", "~/projects/myapp test", "directorydev"]      -> npm test

    The npm command is appended after the path, separated by space.
    npm only runs if a recognized command is specified: start, dev, build, test, install, run
    """
    parts = expanded_path.split()
    project_path = os.path.expanduser(parts[0])
    npm_cmd = parts[1] if len(parts) > 1 else None
    npm_commands = ("start", "dev", "build", "test", "install", "run")
    has_npm_cmd = npm_cmd in npm_commands

    # Always open these 3
    for action in ["editor", "terminal", "file_manager"]:
        handle_directorydev_action(expanded_path, action)

    # Only run npm if a command is specified
    if has_npm_cmd:
        handle_directorydev_action(expanded_path, "npm")

    return f"Opened dev environment at {project_path}"


def handle_dolphin_tabs(path, expanded_path):
    """
    Open multiple folders in the configured file manager as tabs.

    Usage in config:
    ["My Folders", "~/Documents ~/Projects ~/Pictures", "dolphin_tabs"]

    Paths are space-separated. Each path will open as a tab (if the file manager supports it).
    """
    # Split by spaces and expand each path
    paths = expanded_path.split()
    expanded_paths = [os.path.expanduser(p) for p in paths]

    # Run file manager with all paths as arguments
    file_manager = _get_file_manager()
    subprocess.Popen([file_manager] + expanded_paths, start_new_session=True)

    return f"Opened {len(expanded_paths)} folders in {file_manager}"


# =============================================================================
# RSYNC SAFETY HELPERS
# =============================================================================

def _validate_rsync_source(source):
    """
    Check rsync source path for dangerous patterns.

    With --delete, a trailing slash means "copy contents" which can lead to
    unintended deletion of files in the destination directory.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if source.rstrip('/') != source:
        return (False,
            f"BLOCKED: Source path ends with '/'\n\n"
            f"Path: {source}\n\n"
            f"With --delete, this would copy CONTENTS and may delete "
            f"all other files in the destination directory.\n\n"
            f"Remove the trailing slash to sync the directory itself.")
    return (True, None)


def _get_rsync_backup_dir(source):
    """
    Generate backup directory path for rsync --backup-dir.

    Creates a timestamped directory under ~/.rsync_backups/ where
    files deleted by --delete will be moved instead of being
    permanently removed.

    Returns:
        str: Expanded path like ~/.rsync_backups/myproject_20240315_143025
    """
    from datetime import datetime
    source_name = os.path.basename(source.rstrip('/'))
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.expanduser(f"~/.rsync_backups/{source_name}_{timestamp}")


def _show_rsync_error(error_message):
    """Show rsync validation error in a dialog (requires PyQt6)."""
    try:
        from PyQt6.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance()
        if app:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Rsync Safety Check")
            msg.setText(error_message)
            msg.exec()
    except ImportError:
        # Fall back to console output if PyQt6 not available
        print(f"ERROR: {error_message}")


def handle_rsync_backup(path, expanded_path):
    """
    Run rsync with common excludes and safety checks.

    Usage in config:
        ["Backup", "~/source ~/destination", "rsync_backup"]

    Path format: source destination

    Safety features:
    - Blocks trailing slashes on source (dangerous with --delete)
    - Backs up deleted files to ~/.rsync_backups/
    """
    parts = expanded_path.split()
    if len(parts) < 2:
        return "Error: rsync_backup requires: source destination"

    source = os.path.expanduser(parts[0])
    destination = parts[1]
    # Expand ~ for local paths (remote paths use user@host: format)
    if destination.startswith('~'):
        destination = os.path.expanduser(destination)

    # Safety check for trailing slash
    is_valid, error_msg = _validate_rsync_source(source)
    if not is_valid:
        _show_rsync_error(error_msg)
        return f"Blocked: {error_msg.split(chr(10))[0]}"

    # Generate backup directory for deleted files
    backup_dir = _get_rsync_backup_dir(source)

    shell_cmd = (
        f"rsync -avz --delete "
        f"--backup --backup-dir={shlex.quote(backup_dir)} "
        f"--exclude='.git/' --exclude='build/' --exclude='node_modules/' "
        f"{shlex.quote(source)} {shlex.quote(destination)}"
    )
    cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    subprocess.Popen(cmd, start_new_session=True)

    return f"rsync to {destination} (backups in {backup_dir})"


def handle_rsync_backup_id(path, expanded_path):
    """
    Run rsync with SSH identity file and safety checks.

    Usage in config:
        ["Backup to Server", "~/.ssh/my_key ~/local/path user@server:/remote/path", "rsync_backup_id"]

    Path format: identity_file source destination
    The identity file is passed to SSH via -e "ssh -i identity_file"

    Safety features:
    - Blocks trailing slashes on source (dangerous with --delete)
    - Backs up deleted files to ~/.rsync_backups/
    """
    parts = expanded_path.split()
    if len(parts) < 3:
        return "Error: rsync_backup_id requires: identity_file source destination"

    identity_file = os.path.expanduser(parts[0])
    source = os.path.expanduser(parts[1])
    destination = parts[2]
    # Expand ~ for local paths (remote paths use user@host: format)
    if destination.startswith('~'):
        destination = os.path.expanduser(destination)

    # Safety check for trailing slash
    is_valid, error_msg = _validate_rsync_source(source)
    if not is_valid:
        _show_rsync_error(error_msg)
        return f"Blocked: {error_msg.split(chr(10))[0]}"

    # Generate backup directory for deleted files
    backup_dir = _get_rsync_backup_dir(source)

    shell_cmd = (
        f'rsync -avz -e "ssh -i {shlex.quote(identity_file)}" '
        f"--delete --backup --backup-dir={shlex.quote(backup_dir)} "
        f"--exclude='.git/' --exclude='build/' --exclude='node_modules/' "
        f"{shlex.quote(source)} {shlex.quote(destination)}"
    )
    cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    subprocess.Popen(cmd, start_new_session=True)

    return f"rsync with identity to {destination} (backups in {backup_dir})"


def handle_rsync_backup_id_port(path, expanded_path):
    """
    Run rsync with SSH identity file, custom port, and safety checks.

    Usage in config:
        ["Backup to Server", "~/.ssh/my_key 65 ~/local/path user@server:/remote/path", "rsync_backup_id_port"]

    Path format: identity_file port source destination
    The identity file and port are passed to SSH via -e "ssh -i identity_file -p port"

    Safety features:
    - Blocks trailing slashes on source (dangerous with --delete)
    - Backs up deleted files to ~/.rsync_backups/
    """
    parts = expanded_path.split()
    if len(parts) < 4:
        return "Error: rsync_backup_id_port requires: identity_file port source destination"

    identity_file = os.path.expanduser(parts[0])
    port = parts[1]
    source = os.path.expanduser(parts[2])
    destination = parts[3]
    # Expand ~ for local paths (remote paths use user@host: format)
    if destination.startswith('~'):
        destination = os.path.expanduser(destination)

    # Safety check for trailing slash
    is_valid, error_msg = _validate_rsync_source(source)
    if not is_valid:
        _show_rsync_error(error_msg)
        return f"Blocked: {error_msg.split(chr(10))[0]}"

    # Generate backup directory for deleted files
    backup_dir = _get_rsync_backup_dir(source)

    shell_cmd = (
        f'rsync -avz -e "ssh -i {shlex.quote(identity_file)} -p {port}" '
        f"--delete --backup --backup-dir={shlex.quote(backup_dir)} "
        f"--exclude='.git/' --exclude='build/' --exclude='node_modules/' "
        f"{shlex.quote(source)} {shlex.quote(destination)}"
    )
    cmd = _build_terminal_shell_cmd(shell_cmd, hold=True)
    subprocess.Popen(cmd, start_new_session=True)

    return f"rsync with identity (port {port}) to {destination} (backups in {backup_dir})"


# =============================================================================
# COMPLEX HANDLER INFO
# =============================================================================
# Metadata for complex handlers (descriptions and examples for the UI)

COMPLEX_HANDLER_INFO = {
    "ssh_session": {
        "description": "SSH with optional path and command",
        "example": "user@host /var/www ./go.sh"
    },
    "ssh_cd_npm": {
        "description": "SSH with optional path and command (alias)",
        "example": "user@host /app npm start"
    },
    "terminal_cmd": {
        "description": "Terminal at path with optional command",
        "example": "~/project ./go.sh"
    },
    "terminal_npm": {
        "description": "Run npm start in terminal (legacy)",
        "example": "~/projects/myapp"
    },
    "npm": {
        "description": "Run npm commands in terminal",
        "example": "~/projects/myapp dev"
    },
    "directorydev": {
        "description": "Open editor + terminal + file manager",
        "example": "~/projects/myapp dev"
    },
    "dolphin_tabs": {
        "description": "Open folders as file manager tabs",
        "example": "~/Documents ~/Projects ~/Pictures"
    },
    "rsync_backup": {
        "description": "Rsync with safety checks",
        "example": "~/source ~/destination"
    },
    "rsync_backup_id": {
        "description": "Rsync with SSH identity file",
        "example": "~/.ssh/key ~/local user@server:/remote"
    },
    "rsync_backup_id_port": {
        "description": "Rsync with identity + custom port",
        "example": "~/.ssh/key 2222 ~/local user@server:/remote"
    },
}


# Register complex handlers
COMPLEX_HANDLERS = {
    "ssh_session": handle_ssh_session,
    "ssh_cd_npm": handle_ssh_session,  # Alias - describes the SSH + cd + npm functionality
    "terminal_cmd": handle_terminal_cmd,
    "terminal_npm": handle_terminal_npm,  # Legacy, use "npm" instead
    "npm": handle_npm,
    "directorydev": handle_directorydev,
    "dolphin_tabs": handle_dolphin_tabs,
    "rsync_backup": handle_rsync_backup,
    "rsync_backup_id": handle_rsync_backup_id,
    "rsync_backup_id_port": handle_rsync_backup_id_port,
}
