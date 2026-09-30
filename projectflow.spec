# projectflow.spec — PyInstaller spec for a Windows --onedir build.
#
# PyInstaller cannot cross-compile — this MUST be run on Windows itself:
#   pyinstaller projectflow.spec --clean
#
# NOTE: don't pass --contents-directory on the command line — once a .spec
# file is given, PyInstaller rejects it ("makespec options not valid when a
# .spec file is given", confirmed via a real build). The equivalent is set
# below via EXE(..., contents_directory='.'), which keeps bundled data flat
# next to ProjectFlow.exe instead of PyInstaller >= 6.0's default nested
# _internal/ folder — required for _get_script_dir()'s onedir resolution
# (os.path.dirname(sys.executable)) to find anything.
#
# Output: dist/ProjectFlow/ProjectFlow.exe + its supporting files, all flat
# in that one folder.

import os

# NOTE: __file__ is NOT defined here — PyInstaller executes .spec files via
# exec(), not a normal module import, so there's no __file__ to derive a path
# from (confirmed via a real build: NameError: name '__file__' is not
# defined). PyInstaller injects SPECPATH into the spec's exec namespace
# specifically for this — it's already the absolute path to this spec
# file's own directory.
ROOT = SPECPATH

a = Analysis(
    ['projectflow.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ('assets', 'assets'),          # includes assets/muya, assets/codemirror,
                                        # assets/monaco (~24MB, unpruned by design —
                                        # see CLAUDE.md's vendoring rationale)
        ('help', 'help'),
        ('examples', 'examples'),
        ('icon_preferences.json', '.'),
        ('launch_handlers.py', '.'),   # loaded at runtime via
                                        # importlib.util.spec_from_file_location(),
                                        # NOT a normal `import` — PyInstaller's static
                                        # analysis will not auto-bundle this file
        # themes.py: a normal top-level `from themes import ...` in projectflow.py —
        # PyInstaller's static analysis should already compile it into the bundle
        # automatically. Deliberately NOT listed here; verify this assumption during
        # the first build rather than trusting it blind.
    ],
    hiddenimports=[
        # Safety net only — PyQt6's sip binding module is occasionally missed by
        # static analysis on some PyInstaller/PyQt6 version combinations. Leave
        # commented out unless the build log or a runtime ModuleNotFoundError says
        # otherwise:
        # 'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir: binaries/data go to COLLECT(), not baked into the exe
    name='ProjectFlow',
    contents_directory='.', # spec-file equivalent of the CLI --contents-directory flag —
                             # that flag is a "makespec" option and isn't accepted on the
                             # command line once a .spec file is given (confirmed via a
                             # real build: "ERROR: option(s) not allowed: --contents-directory
                             # / makespec options not valid when a .spec file is given").
                             # '.' keeps bundled data flat next to ProjectFlow.exe, matching
                             # what _get_script_dir()'s onedir branch expects, instead of the
                             # nested _internal/ folder PyInstaller >= 6.0 defaults to.
    debug=False,
    strip=False,
    upx=False,               # leave UPX off for this first spike — UPX-compressed
                              # QtWebEngine binaries have a documented history of AV
                              # false positives; revisit only if bundle size becomes a
                              # real complaint later
    console=False,           # GUI app, no console window
    icon=os.path.join(ROOT, 'assets', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='ProjectFlow',
)

# --- Deliberately NOT added in this first pass ---
# Manual QtWebEngine resource hooks (icudtl.dat, qtwebengine_resources.pak, locale
# .pak files, QtWebEngineProcess.exe). PyInstaller ships a bundled hook for
# PyQt6.QtWebEngineWidgets/QtWebEngineCore that's supposed to handle this
# automatically — this is the actual go/no-go question this whole spike exists to
# answer, not something to pre-guess a workaround for. If a QWebEngineView panel
# renders blank/white in the frozen build, inspect dist/ProjectFlow/PyQt6/Qt6/ for
# whichever of resources/, translations/qtwebengine_locales/, or
# QtWebEngineProcess.exe the hook missed, and add explicit datas/binaries entries
# for that specific piece then.
