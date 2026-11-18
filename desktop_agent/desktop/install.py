"""Per-user self-installation for the packaged exe (no admin rights).

Running the downloaded netsync-agent.exe the first time:
  1. copies itself to %LOCALAPPDATA%\\Programs\\NetSyncAI\\netsync-agent.exe
  2. registers: start with Windows, the netsync:// link handler, a Start
     menu shortcut, and an entry in Settings â†’ Apps (for uninstall)
  3. relaunches from the installed location

All registry writes are under HKCU. Nothing here runs unless the agent is
frozen (PyInstaller) â€” `python main.py` never touches the registry.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agent_config import AGENT_VERSION

log = logging.getLogger("netsync.install")

APP_NAME = "NetSync AI"
EXE_NAME = "netsync-agent.exe"
PROTOCOL = "netsync"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NetSyncAI"
PROTOCOL_KEY = rf"Software\Classes\{PROTOCOL}"


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / "NetSyncAI"


def installed_exe() -> Path:
    return install_dir() / EXE_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def running_from_install_dir() -> bool:
    return Path(sys.executable).resolve() == installed_exe().resolve()


def _shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"


def _hidden() -> dict:
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def register(exe: Path) -> None:
    """Idempotent: (re)point every Windows integration at `exe`."""
    if os.name != "nt":
        return  # macOS/Linux integration (launchd, .desktop) not implemented
    import winreg

    quoted = f'"{exe}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, "NetSyncAI", 0, winreg.REG_SZ, f"{quoted} --background")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:NetSync AI")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY + r"\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{quoted},0")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY + r"\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'{quoted} "%1"')

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in {
            "DisplayName": APP_NAME,
            "DisplayVersion": AGENT_VERSION,
            "Publisher": APP_NAME,
            "DisplayIcon": f"{quoted},0",
            "InstallLocation": str(exe.parent),
            "UninstallString": f"{quoted} --uninstall",
        }.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)

    _make_shortcut(exe)


def _make_shortcut(exe: Path) -> None:
    lnk = _shortcut_path()
    if lnk.exists():
        return  # target path is stable (install dir), nothing to update
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:NS_LNK);"
        "$s.TargetPath=$env:NS_EXE;$s.WorkingDirectory=$env:NS_DIR;"
        "$s.IconLocation=$env:NS_EXE+',0';$s.Description='NetSync AI';$s.Save()"
    )
    env = {**os.environ, "NS_LNK": str(lnk), "NS_EXE": str(exe), "NS_DIR": str(exe.parent)}
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       env=env, timeout=20, check=False, **_hidden())
    except (OSError, subprocess.SubprocessError):
        log.warning("could not create Start menu shortcut")


def unregister() -> None:
    if os.name != "nt":
        return
    import winreg

    def _delete_tree(root, path):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    _delete_tree(root, f"{path}\\{child}")
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "NetSyncAI")
    except FileNotFoundError:
        pass
    _delete_tree(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY)
    _delete_tree(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    _shortcut_path().unlink(missing_ok=True)


def self_install(argv: list[str]) -> bool:
    """If running a downloaded copy, install it and relaunch. Returns True
    when the caller should exit (the installed copy takes over)."""
    from desktop.instance import send_to_running

    if os.name != "nt" or not is_frozen() or running_from_install_dir():
        return False  # Windows-only install flow; other OSes run in place

    target = installed_exe()
    target.parent.mkdir(parents=True, exist_ok=True)
    send_to_running("quit")          # stop an older installed copy, if any
    for _ in range(20):
        try:
            shutil.copy2(sys.executable, target)
            break
        except PermissionError:
            time.sleep(0.5)          # old process still exiting
    else:
        raise RuntimeError(f"could not write {target} â€” close NetSync AI and retry")

    # wait for the old process to release the single-instance port before
    # relaunching — otherwise the new copy fails to acquire it and exits,
    # leaving NOTHING running (device stays offline until a manual launch)
    for _ in range(40):
        if not send_to_running("quit"):
            break                  # port released — old instance is gone
        time.sleep(0.25)

    register(target)
    subprocess.Popen([str(target), *argv], close_fds=True, **_hidden())
    log.info("installed to %s", target)
    return True


def schedule_self_delete() -> None:
    """The running exe can't delete itself â€” hand off to a short-lived cmd."""
    if os.name != "nt":
        return
    exe = installed_exe()
    cmd = f'ping -n 3 127.0.0.1 >nul & del /f /q "{exe}" & rmdir "{exe.parent}"'
    subprocess.Popen(["cmd", "/c", cmd], close_fds=True, **_hidden())
