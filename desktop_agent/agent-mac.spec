# PyInstaller spec — builds the single-file macOS agent.
# Build (on a Mac or the macos CI runner): pyinstaller --noconfirm agent-mac.spec
# Console binary: `netsync-agent-macos pair <code>` then `netsync-agent-macos run`.
# Launching it with no arguments opens the desktop app windows (tkinter) —
# there is no menu-bar tray on macOS yet, so keep the Terminal window open.

import pathlib

ROOT = pathlib.Path.cwd()

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ("database/schema.sql", "database"),
        ("build_config.json", "."),
    ],
    hiddenimports=[
        "watchdog.observers.fsevents",
        "watchdog.observers.kqueue",
        "PIL.ImageTk",
        "desktop.agent_app",
        "file_operations.folders",
        "synchronization.sync_engine",
    ],
    hookspath=[],
    excludes=["winreg", "pystray._win32"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="netsync-agent-macos",
    console=True,                       # CLI-first; windows attach when launched bare
)
