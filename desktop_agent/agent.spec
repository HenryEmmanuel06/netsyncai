# PyInstaller spec — Phase 6 will finalize (icon, tray deps, version info).
# Build: pyinstaller agent.spec
# Never embed secrets: the agent must contain no API keys or credentials.

import pathlib

ROOT = pathlib.Path.cwd()

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[("database/schema.sql", "database")],
    hiddenimports=["watchdog.observers.winapi"],
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
    console=True,          # Phase 6: console=False + tray app entrypoint
    icon=None,             # Phase 6: assets/netsync.ico
)
