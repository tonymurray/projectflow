# Installing and Running ProjectFlow on Windows

ProjectFlow's Windows support is **experimental** (see `README.md` and `ai/mac_windows.md`)
but has been validated on real Windows 11 hardware — the core app, launcher system, and all
built-in viewers (Notes/Web/Editor/Help) work. There are three ways to get it running, in
order of how much you want to deal with Python:

- **Option A — Download the prebuilt release.** No Python, no command line. Best for most
  people just wanting to run the app.
- **Option B — Run from source.** Needs Python, but means you're always on the exact latest
  code via `git pull`, and can read/modify it. Best if you want to tinker or help develop it.
- **Option C — Build the `.exe` yourself.** For contributors testing changes to the packaging
  itself (`projectflow.spec`). Most people don't need this — Option A already gives you a
  built `.exe`, built by GitHub's own servers instead of yours.

The app also checks GitHub once a day at startup for a newer release and will mention it in
the status bar if one exists (see "Checking for updates" near the end of this doc) — so once
you've picked an option below, staying current doesn't need you to keep checking by hand.

## What's different on Windows

Some KDE/Linux-only integrations aren't available and fall back gracefully:

- **Terminal viewer** uses the qtconsole backend instead of the ttyd real-terminal backend
  (ttyd is a Linux binary with no Windows build in this project's pipeline).
- **Baloo file tags** ("Tagged Files" category) don't exist on Windows — nothing to enable.
- **Dolphin service menus** (right-click "Add to ProjectFlow" etc.) are KDE/Dolphin-specific
  and have no Windows equivalent yet.
- Everything else — projects, launchers, Notes/Markdown editor, Code Editor, PDF/Image/Web
  viewers, Settings — works the same as on Linux.

## Option A — Download the prebuilt release

1. Go to the [Releases page](https://github.com/tonymurray/projectflow/releases) and download
   the latest `ProjectFlow-win-vYYYY.MM.DD.zip`.
2. Extract it anywhere you have write access — e.g. `Documents\ProjectFlow` or a `Programs`
   folder under your user profile. Avoid `C:\Program Files\...` (needs admin rights for no
   benefit here).
3. Run `ProjectFlow.exe` from inside the extracted folder.

That's it — no Python, no pip, no venv. The whole folder is self-contained (PyQt6, QtWebEngine,
and the app's own `assets\`/`help\`/`examples\` are all bundled inside it already).

**Upgrading**: download the newer zip from the same Releases page, extract it over the old
folder (or to a new folder, then copy your `projects\`/`notes\` subfolders and
`.projectflow_settings.json` across if you used a new folder). Nothing else to do — there's no
installer, no uninstall step, just files in a folder.

If you'd rather build this `.exe` yourself instead of downloading one GitHub already built, see
Option C.

## Option B — Run from source

### 1. Prerequisites

#### Python

Install **Python 3.11 or newer** (64-bit) from [python.org/downloads](https://www.python.org/downloads/windows/)
or the Microsoft Store.

- During the python.org installer, check **"Add python.exe to PATH"** on the first screen —
  this is unchecked by default and is the single most common reason `python`/`pip` "aren't
  recognized" afterward.
- Verify it worked by opening a new PowerShell window and running:

  ```powershell
  python --version
  ```

#### Git for Windows (recommended, not required)

Needed to clone the repository and to pull updates later. Download from
[git-scm.com/download/win](https://git-scm.com/download/win) and install with default options.
If you'd rather not install Git, see the "without Git" option in step 2.

### 2. Get the code

Pick a folder to keep the app in — anywhere you have write access works, e.g. a `Programs`
folder under your user profile. Avoid `C:\Program Files\...` (requires admin rights for no
benefit here).

#### With Git (recommended — makes upgrading a one-line command)

```powershell
cd $HOME\Programs
git clone https://github.com/tonymurray/projectflow.git
cd projectflow
```

#### Without Git

Download the ZIP from the GitHub repository's green "Code" → "Download ZIP" button, then
extract it to e.g. `C:\Users\<you>\Programs\projectflow`. Upgrading later means re-downloading
and re-extracting the ZIP (see step 4 below). This is the *source* ZIP from the green "Code"
button — not the same as the prebuilt release zip from Option A.

### 3. Set up a virtual environment and install dependencies

From inside the `projectflow` folder, in PowerShell:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-windows.txt
```

Notes:

- `venv\Scripts\activate` only affects the *current* PowerShell window — you'll run it again
  every time you open a new terminal to work with this app (see "Run it" below).
- If PowerShell refuses to run the activation script with an error about execution policies
  (e.g. *"...venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on
  this system..."*), run this once (per user, not per project) and try again:

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

  This is a default Windows security setting that blocks PowerShell *scripts* (`.ps1` files,
  which is what `venv\Scripts\activate` actually is) while still allowing ordinary commands —
  it's not specific to this project, and `-Scope CurrentUser` only loosens it for your own
  Windows account, not system-wide. If you'd rather not change this setting at all, you can
  skip activation entirely and call the venv's Python directly instead, e.g.:

  ```powershell
  venv\Scripts\python.exe projectflow.py
  venv\Scripts\pip.exe install -r requirements-windows.txt
  ```
- `requirements-windows.txt` installs PyQt6, PyQt6-WebEngine, PyMuPDF, qtconsole, ipykernel,
  and `platformdirs` (used for Windows-appropriate app-data paths). This is a few hundred MB —
  PyQt6-WebEngine (the embedded Chromium-based browser engine used by Notes/Web/Help/Editor) is
  the bulk of it.

### 4. Run it

With the virtual environment active (step 3's `venv\Scripts\activate`):

```powershell
python projectflow.py
```

To open a specific project directly:

```powershell
python projectflow.py projects\myproject.json
```

#### Running it again later (new terminal session)

Each new PowerShell window starts without the venv active. From the `projectflow` folder:

```powershell
venv\Scripts\activate
python projectflow.py
```

If you want a one-click launcher, create a `run.bat` in the `projectflow` folder with:

```bat
@echo off
call venv\Scripts\activate.bat
python projectflow.py
```

Double-clicking `run.bat` then activates the venv and starts the app in one step.

### 5. Upgrading to a newer version

#### If you cloned with Git

```powershell
cd $HOME\Programs\projectflow
git pull
venv\Scripts\activate
pip install -r requirements-windows.txt --upgrade
```

The `pip install --upgrade` step is only strictly necessary when a change to
`requirements-windows.txt` itself shows up in the pull (check `git log -p requirements-windows.txt`
if unsure) — otherwise your existing venv already has everything it needs. Running it anyway is
harmless, just a bit slower.

#### If you downloaded the source ZIP

1. Download the latest ZIP from GitHub the same way as step 2.
2. Extract it over the old folder (or to a new folder, then copy your `projects\` and `notes\`
   subfolders — and `.projectflow_settings.json` — across if you used a new folder).
3. Re-run step 3's `pip install -r requirements-windows.txt` inside the existing `venv` (no
   need to delete/recreate the venv unless something seems broken).

## Option C — Build the `.exe` yourself

For contributors testing changes to `projectflow.spec` itself, or anyone who'd rather build
their own copy than download the one from Releases. This is the same build GitHub's Actions
workflow runs automatically on every tagged release (see
`.github/workflows/windows-build.yml`) — running it yourself just does that one build locally
instead of on GitHub's servers.

This needs Option B's setup first (Python + the source code + a venv with
`requirements-windows.txt` installed) — PyInstaller can't cross-compile, so this **must** be
run on Windows itself; there's no way to produce a Windows `.exe` from Linux/Mac.

With the venv active (or using `venv\Scripts\pip.exe`/`pyinstaller.exe` directly, if you're
avoiding `activate` as above):

```powershell
pip install pyinstaller
pyinstaller projectflow.spec --clean
```

This produces `dist\ProjectFlow\ProjectFlow.exe` plus its supporting files, all in one folder
(an "onedir" build — PyQt6, QtWebEngine, and the app's own `assets\`/`help\`/`examples\` are all
bundled in there, so the whole `dist\ProjectFlow` folder is self-contained and can be copied
elsewhere, e.g. to `Documents\ProjectFlow`, and run without Python or the venv present — this is
exactly what Option A's downloaded zip already is, just built by you instead of by GitHub).

Notes:

- First build can take a few minutes — PyInstaller is scanning and copying everything PyQt6/
  QtWebEngine needs.
- `projects\`, `notes\`, and `.projectflow_settings.json` are created next to wherever
  `ProjectFlow.exe` is actually run from — not inside `dist\` as part of the build itself.
- Re-run `pyinstaller projectflow.spec --clean` any time you want a fresh build after pulling
  updates; it doesn't update itself in place. The `--clean` flag clears PyInstaller's cache from
  any previous build, which avoids a few real build failures seen during initial development
  (stale cached data from an older spec).
- This is a newer, less-exercised path than running from source — if something behaves
  differently in a packaged `.exe` versus `python projectflow.py`, that's worth reporting.

## Checking for updates

The app pings GitHub's public Releases API once per calendar day at startup and compares the
latest tagged release against its own `VERSION` file — if a newer one exists, it shows a plain
status-bar note with a link, never a popup. This is on by default; toggle it off in
**Settings → Settings tab → "Check for Updates"** if you'd rather not. It fails silently if
you're offline — it never blocks startup or shows an error for a failed check.

This only ever *tells* you a newer version exists — it doesn't download or install anything
automatically. Which upgrade steps to actually run depends on which Option above you used (see
each Option's own "Upgrading" instructions).

## Where your data lives

- **Settings**: `.projectflow_settings.json` next to `ProjectFlow.exe`/`projectflow.py`.
- **Projects**: the `projects\` subfolder (created on first run).
- **Notes**: the `notes\` subfolder by default (configurable in Settings).
- **App-internal data** (e.g. the embedded browser's cookie/session storage): `%LOCALAPPDATA%\ProjectFlow`.

None of these are touched by an upgrade (re-extracting a release zip, `git pull`, or
re-extracting a source ZIP into the same folder) — only the application code itself changes.

## Troubleshooting

- **"python is not recognized..."** — Python wasn't added to PATH during install. Re-run the
  python.org installer, choose "Modify", and enable "Add python.exe to PATH", or reinstall with
  that box checked. (Only applies to Options B/C — Option A needs no Python at all.)
- **pip install fails on PyQt6-WebEngine** — make sure you're on 64-bit Python 3.11+; there is
  no 32-bit wheel for recent PyQt6-WebEngine versions.
- **Window opens but looks broken / fonts tiny or huge** — a high-DPI display scaling quirk;
  not yet specifically tuned for Windows. Report it with your display's scaling percentage
  (Settings → System → Display) if you hit this.
- **Terminal viewer looks different from the Linux screenshots** — expected; Windows falls back
  to the qtconsole backend (see "What's different on Windows" above), which doesn't support
  interactive full-screen programs like `nano`/`vim`/`htop`.
