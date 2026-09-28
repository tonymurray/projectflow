"""
OS Integration — the one module allowed to know about sys.platform.

Every Linux-specific external-process/filesystem convention this app relies on
(xdg-open, desktop-environment detection, terminal/editor/file-manager
auto-detection, terminal command-line conventions, per-OS app-data storage
paths, and menu-entry generation) is collected here so projectflow.py and
launch_handlers.py never branch on platform themselves — they call through
this module instead.

Each function's Linux branch is a verbatim relocation of code that already
existed at its old call site, not a rewrite — the goal of this module is that
importing it and calling through it changes nothing about how the app behaves
on Linux. Windows branches are additive and never execute there.

See ai/mac_windows.md for the original portability assessment and
~/.claude/plans/can-you-now-revisit-sequential-pie.md for the extraction plan
this module implements.
"""

import os
import shlex
import shutil
import subprocess
import sys

PLATFORM = "windows" if sys.platform == "win32" else "linux"


def open_path_default(path):
    """Open a file/folder/URL with whatever the OS considers its default
    handler for it. Linux: xdg-open (fire-and-forget, detached from this
    process). Windows: os.startfile(), the OS-native equivalent."""
    if PLATFORM == "windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path], start_new_session=True)


def detect_desktop_environment():
    """Detect the current desktop environment.

    Returns one of: 'kde', 'gnome', 'xfce', 'cosmic', 'mate', 'cinnamon',
    'lxqt', 'lxde', 'windows', or 'unknown'.
    """
    if PLATFORM == "windows":
        return 'windows'

    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()

    if 'kde' in desktop or 'plasma' in desktop:
        return 'kde'
    elif 'gnome' in desktop or 'ubuntu' in desktop:
        return 'gnome'
    elif 'xfce' in desktop:
        return 'xfce'
    elif 'cosmic' in desktop:
        return 'cosmic'
    elif 'mate' in desktop:
        return 'mate'
    elif 'cinnamon' in desktop:
        return 'cinnamon'
    elif 'lxqt' in desktop:
        return 'lxqt'
    elif 'lxde' in desktop:
        return 'lxde'
    return 'unknown'


def detect_default_browser():
    """Detect the system default browser. Returns a friendly name like 'firefox'."""
    if PLATFORM == "windows":
        return 'browser'  # no Windows-specific detection yet; caller only uses this for display

    try:
        result = subprocess.run(
            ['xdg-settings', 'get', 'default-web-browser'],
            capture_output=True, text=True, timeout=2
        )
        desktop = result.stdout.strip().lower()
        for name in ('firefox', 'chromium', 'chrome', 'epiphany', 'opera', 'brave', 'vivaldi', 'konqueror'):
            if name in desktop:
                return name
    except Exception:
        pass
    if shutil.which('firefox'):
        return 'firefox'
    if shutil.which('chromium'):
        return 'chromium'
    return 'browser'


def detect_default_terminal(de):
    """Detect the appropriate terminal for desktop environment `de` (as
    returned by detect_desktop_environment())."""
    if PLATFORM == "windows":
        if shutil.which('wt'):
            return 'wt'
        if shutil.which('powershell'):
            return 'powershell'
        return 'cmd'

    # Prefer xdg-terminal-exec if available (freedesktop standard, respects user's default)
    if shutil.which('xdg-terminal-exec'):
        return 'xdg-terminal-exec'

    terminal_map = {
        'kde': 'konsole',
        'gnome': 'gnome-terminal',
        'xfce': 'xfce4-terminal',
        'cosmic': 'cosmic-term',
        'mate': 'mate-terminal',
        'cinnamon': 'gnome-terminal',
        'lxqt': 'qterminal',
        'lxde': 'lxterminal',
    }

    if de in terminal_map:
        return terminal_map[de]

    # Fallback: check what's installed
    for term in ['konsole', 'gnome-terminal', 'xfce4-terminal', 'alacritty', 'kitty', 'xterm']:
        if shutil.which(term):
            return term

    return 'xterm'  # Ultimate fallback


def detect_default_editor(de):
    """Detect the appropriate editor for desktop environment `de`."""
    if PLATFORM == "windows":
        return 'notepad'

    editor_map = {
        'kde': 'kate',
        'gnome': 'gedit',
        'xfce': 'mousepad',
        'cosmic': 'cosmic-edit',
        'mate': 'pluma',
        'cinnamon': 'xed',
        'lxqt': 'featherpad',
        'lxde': 'leafpad',
    }

    if de in editor_map and shutil.which(editor_map[de]):
        return editor_map[de]

    # Fallback: check what's installed
    for editor in ['code', 'kate', 'gedit', 'nano']:
        if shutil.which(editor):
            return editor

    return 'xdg-open'  # Ultimate fallback — open_path_default() knows how to run this value too


def detect_default_file_manager(de):
    """Detect the appropriate file manager for desktop environment `de`."""
    if PLATFORM == "windows":
        return 'explorer'

    fm_map = {
        'kde': 'dolphin',
        'gnome': 'nautilus',
        'xfce': 'thunar',
        'cosmic': 'cosmic-files',
        'mate': 'caja',
        'cinnamon': 'nemo',
        'lxqt': 'pcmanfm-qt',
        'lxde': 'pcmanfm',
    }

    if de in fm_map and shutil.which(fm_map[de]):
        return fm_map[de]

    # Fallback: check what's installed
    for fm in ['dolphin', 'nautilus', 'thunar', 'pcmanfm']:
        if shutil.which(fm):
            return fm

    return 'xdg-open'  # Ultimate fallback


def build_terminal_shell_cmd(terminal, shell_cmd, hold=False, interactive=False):
    """Build a command list that opens `terminal` and runs `shell_cmd` in it,
    using that terminal's own CLI argument conventions. `terminal` is
    whatever get_configured_terminal()/detect_default_terminal() resolved to.
    """
    if PLATFORM == "windows":
        # NOTE: not yet verified on real Windows hardware (no Windows machine
        # available in this dev environment — see Phase 0/2 of the port plan).
        # /K keeps the window open after the command runs (Windows' rough
        # equivalent of a terminal's "hold" flag); /C runs then closes.
        if terminal == "wt":
            flag = "/K" if hold else "/C"
            return ["wt", "cmd", flag, shell_cmd]
        elif terminal == "powershell":
            args = ["powershell"]
            if hold:
                args.append("-NoExit")
            args.extend(["-Command", shell_cmd])
            return args
        else:  # cmd (or anything unrecognized)
            flag = "/K" if hold else "/C"
            return ["cmd", flag, shell_cmd]

    # Terminal-specific argument patterns
    # Format: (hold_flag, execute_separator, needs_shell_wrapper)
    terminal_configs = {
        "xdg-terminal-exec": (None, [], True),  # command passed directly as args
        "konsole": ("--hold", ["-e"], True),
        "gnome-terminal": (None, ["--"], True),  # gnome-terminal doesn't have hold
        "xfce4-terminal": ("--hold", ["-e"], True),
        "terminator": ("--hold", ["-e"], True),
        "tilix": ("--hold", ["-e"], True),
        "alacritty": ("--hold", ["-e"], True),
        "kitty": ("--hold", [], True),  # kitty just appends command
        "wezterm": (None, ["start", "--"], True),  # wezterm start -- cmd
        "foot": ("--hold", [], True),  # foot just appends command
        "xterm": ("-hold", ["-e"], True),
        "urxvt": ("-hold", ["-e"], True),
        "ghostty": (None, ["-e"], True),
        "hyper": (None, ["-e"], True),
        "tabby": (None, ["run"], True),
        "guake": (None, ["-e"], True),
        "tilda": (None, ["-c"], True),
        "warp-terminal": (None, [], True),
    }

    config = terminal_configs.get(terminal, ("--hold", ["-e"], True))
    hold_flag, exec_sep, needs_shell = config

    terminal_cmd = [terminal]

    # Add hold flag if requested and supported
    if hold and hold_flag:
        terminal_cmd.append(hold_flag)

    # Add execute separator
    terminal_cmd.extend(exec_sep)

    # Add the shell command
    if needs_shell:
        bash_flags = ["-i", "-c"] if interactive else ["-c"]
        terminal_cmd.extend(["bash"] + bash_flags + [shell_cmd])
    else:
        terminal_cmd.append(shell_cmd)

    return terminal_cmd


def build_terminal_workdir_cmd(terminal, path):
    """Build a command list that opens `terminal` at directory `path`."""
    if PLATFORM == "windows":
        # NOTE: not yet verified on real Windows hardware — see the note in
        # build_terminal_shell_cmd() above.
        if terminal == "wt":
            return ["wt", "-d", path]
        elif terminal == "powershell":
            return ["powershell", "-NoExit", "-Command", f"cd '{path}'"]
        else:  # cmd
            return ["cmd", "/K", "cd", "/d", path]

    # Terminal-specific workdir argument patterns
    workdir_args = {
        "xdg-terminal-exec": ["bash", "-c", "cd " + shlex.quote(path) + " && exec $SHELL"],
        "konsole": ["--workdir", path],
        "gnome-terminal": ["--working-directory=" + path],
        "xfce4-terminal": ["--working-directory=" + path],
        "terminator": ["--working-directory=" + path],
        "tilix": ["--working-directory=" + path],
        "alacritty": ["--working-directory", path],
        "kitty": ["--directory", path],
        "wezterm": ["start", "--cwd", path],
        "foot": ["--working-directory=" + path],
        "xterm": ["-e", "cd " + shlex.quote(path) + " && exec $SHELL"],
        "urxvt": ["-cd", path],
        "ghostty": ["--working-directory=" + path],
        "cosmic-term": ["--working-directory", path],
        "mate-terminal": ["--working-directory=" + path],
        "qterminal": ["--workdir", path],
        "lxterminal": ["--working-directory=" + path],
    }

    args = workdir_args.get(terminal, ["--workdir", path])
    return [terminal] + args


def app_data_dir(app_name):
    """Return the base directory for this app's own persistent data (e.g.
    the QtWebEngine profile storage). Linux: ~/.local/share/<app_name>,
    matching the XDG convention this app has always used. Windows:
    %LOCALAPPDATA%\\<app_name> via `platformdirs` — a Windows-only
    dependency, imported lazily here so Linux never needs it installed.

    Callers must keep using a *named* QWebEngineProfile pointed at a path
    under this directory, not QWebEngineProfile.defaultProfile() — see the
    comment at this function's call site in projectflow.py's __init__ for
    why (defaultProfile() is permanently off-the-record in this Qt build
    and silently ignores any storage path set on it).
    """
    if PLATFORM == "windows":
        import platformdirs
        return platformdirs.user_data_dir(app_name)
    return os.path.expanduser(f"~/.local/share/{app_name}")


def applications_dir():
    """Base directory where this user's desktop launcher entries live.
    Linux: ~/.local/share/applications (freedesktop .desktop convention).
    Windows: the current user's Start Menu Programs folder.

    NOTE: only the directory resolution is cross-platform so far. The
    actual entry-writing logic (ensure_desktop_file_installed()/
    regenerate_desktop_file() in projectflow.py) still only knows how to
    write freedesktop .desktop files — a genuinely different format from
    a Windows .lnk shortcut, not just a different path. Building and
    verifying a pywin32-based .lnk writer is real Phase 2/3 work that
    needs actual Windows hardware to test against (see the port plan);
    deliberately not attempted blind in this pass.
    """
    if PLATFORM == "windows":
        return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
    return os.path.expanduser("~/.local/share/applications")


# App/handler names that only make sense as *suggestions* on Linux — KDE-specific
# apps (dolphin, kate, konsole, okular) and Linux/macOS-only mechanisms (rsync).
# Filtered out of the launcher "Application" dropdown's suggestions on Windows via
# filter_unsupported_app_names() below. The dropdown is a free-text combobox
# regardless, so typing one of these by hand still works if it happens to be
# installed (Kate and Okular do ship real Windows builds) — this only narrows
# what's *suggested*, it never blocks a launcher from using them.
LINUX_ONLY_APP_NAMES = {"dolphin", "dolphin_tabs", "kate", "konsole", "okular", "rsync_backup"}


def filter_unsupported_app_names(names):
    """Remove app/handler names not worth suggesting on this platform from an
    iterable of names, returning a list. Linux returns them unchanged — this
    function only ever narrows the Windows list, never the Linux one."""
    if PLATFORM == "windows":
        return [n for n in names if n not in LINUX_ONLY_APP_NAMES]
    return list(names)


def set_windows_taskbar_identity(app_id):
    """Tell Windows Explorer this process is its own distinct application,
    not just another python.exe. Without this, a PyQt app launched via
    `python script.py` (rather than a frozen, icon-bearing .exe) commonly
    shows the taskbar button/icon for python.exe itself instead of the
    window's own QIcon — Windows taskbar grouping keys off the Application
    User Model ID, which defaults to the host interpreter's own identity if
    the app never sets one. Must be called before QApplication() is
    constructed. No-op on Linux, which has no such concept (window/taskbar
    icons there already just follow the QIcon set via setWindowIcon())."""
    if PLATFORM != "windows":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass  # best-effort — a missing/failed call just means the old fallback icon shows
