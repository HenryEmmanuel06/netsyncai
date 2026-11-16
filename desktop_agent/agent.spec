# PyInstaller spec — builds the single-file Windows app.
# Build: pyinstaller --noconfirm agent.spec
# Never embed secrets: the agent must contain no API keys or credentials.
# The backend/dashboard URLs come from build_config.json (see docs/DEPLOYMENT.md).

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
        "watchdog.observers.winapi",
        "pystray._win32",
        "PIL.ImageTk",
        "desktop.agent_app",
        "file_operations.folders",
        "synchronization.sync_engine",
    ],
    hookspath=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="netsync-agent",
    console=False,                      # windowed app; CLI reattaches to the parent terminal
    icon="assets/netsync.ico",
)
