"""NetSync AI desktop app: the resident agent with a tray icon.

Threads:
  main    — tkinter (windows) + a queue pump; ALL UI work happens here
  tray    — pystray icon (callbacks post work to the main thread)
  agent   — asyncio loop running the coordinator connection
  ipc     — single-instance listener (deep links from the browser)
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import httpx

from agent_config import AGENT_VERSION, dashboard_url, default_coordinator
from database.db import connect, get_setting, set_setting
from networking.coordinator import (
    CredentialRejected,
    PairingFailed,
    redeem_pairing,
    run_forever,
)

log = logging.getLogger("netsync.app")

DEVICE_KEYS = ("device_id", "device_credential", "device_name", "coordinator_url")


def setup_file_logging(data_dir: Path) -> Path:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logs / "agent.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logs


def parse_pair_link(message: str) -> str | None:
    """netsync://pair?code=ABCD2345 → 'ABCD2345' (None if not a pair link)."""
    if not message.lower().startswith("netsync://"):
        return None
    u = urlparse(message)
    target = (u.netloc or u.path.lstrip("/")).lower().rstrip("/")
    if target != "pair":
        return None
    code = (parse_qs(u.query).get("code") or [""])[0].strip().upper()
    return code if len(code) == 8 and code.isalnum() else None


def fetch_pairing_preview(coordinator: str, code: str) -> dict:
    r = httpx.get(f"{coordinator.rstrip('/')}/api/v1/pairing/preview",
                  params={"code": code}, timeout=20)
    if r.status_code != 200:
        try:
            msg = r.json()["detail"]["error"]
        except Exception:
            msg = f"server returned {r.status_code}"
        raise PairingFailed(msg)
    return r.json()


STATUS_TEXT = {
    "unpaired": "Not connected",
    "connecting": "Connecting…",
    "online": "Online",
    "offline": "Offline — reconnecting",
    "rejected": "Removed from account",
}


class AgentApp:
    def __init__(self, data_dir: Path, initial_message: str | None, background: bool):
        self.data_dir = data_dir
        self.initial_message = initial_message
        self.background = background
        self.ui: queue.Queue[Callable[[], None]] = queue.Queue()
        self.state = "unpaired"
        self.agent_future = None
        self.windows: dict[str, object] = {}
        self.pairing_busy = False
        self.device_name: str | None = None

    # ── plumbing ──────────────────────────────────────────────────────────

    def post(self, fn: Callable[[], None]) -> None:
        """Run fn on the Tk thread (safe from any thread)."""
        self.ui.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self.ui.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("ui task failed")
        self.root.after(120, self._pump)

    def _settings(self) -> dict:
        return {k: get_setting(self.conn, k) for k in DEVICE_KEYS}

    def _paired(self) -> bool:
        s = self._settings()
        return bool(s["device_id"] and s["device_credential"])

    # ── lifecycle ─────────────────────────────────────────────────────────

    def run(self) -> int:
        from desktop.instance import InstanceServer, send_to_running

        setup_file_logging(self.data_dir)
        self.ipc = InstanceServer(lambda m: self.post(lambda: self.handle_message(m)))
        # the just-updated copy can race a still-dying predecessor for the
        # port — retry briefly before deciding another instance owns it
        acquired = False
        for _ in range(20):
            if self.ipc.try_acquire():
                acquired = True
                break
            time.sleep(0.25)
        if not acquired:
            send_to_running(self.initial_message or "show")
            return 0

        log.info("NetSync AI %s starting (data: %s)", AGENT_VERSION, self.data_dir)
        self.conn = connect(self.data_dir)
        self.device_name = get_setting(self.conn, "device_name")
        self.root = tk.Tk()
        self.root.withdraw()
        self._load_images()

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, name="agent", daemon=True).start()
        self._start_tray()

        if self._paired():
            self.start_agent()
            if not self.background and not self.initial_message:
                self.show_status()
        else:
            self.set_state("unpaired")
            if not self.background and not self.initial_message:
                self.show_welcome()
            elif self.background:
                self.notify("Not connected yet — click the tray icon to connect.")
        if self.initial_message:
            self.handle_message(self.initial_message)

        self.root.after(120, self._pump)
        self.root.mainloop()
        return 0

    def quit(self) -> None:
        log.info("quitting")
        self.stop_agent()
        try:
            self.tray.stop()
        except Exception:
            pass
        self.ipc.close()
        self.root.after(200, self.root.destroy)

    # ── images / tray ─────────────────────────────────────────────────────

    def _load_images(self) -> None:
        from PIL import ImageTk
        from desktop.icon import make_icon
        self.window_icon = ImageTk.PhotoImage(make_icon(48), master=self.root)
        self.root.iconphoto(True, self.window_icon)

    def _start_tray(self) -> None:
        import pystray
        from desktop.icon import make_icon

        item = pystray.MenuItem
        menu = pystray.Menu(
            item(lambda _: f"NetSync AI — {self.status_line()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Open dashboard", lambda: self.post(self.open_dashboard), default=True),
            item("Connect this computer…", lambda: self.post(self.show_welcome),
                 visible=lambda _: self.state in ("unpaired", "rejected")),
            item("Open log folder", lambda: self.post(self.open_logs)),
            pystray.Menu.SEPARATOR,
            item("Quit NetSync AI", lambda: self.post(self.quit)),
        )
        self.tray = pystray.Icon("NetSyncAI", make_icon(64, "unpaired"),
                                 "NetSync AI", menu)
        self.tray.run_detached()

    def status_line(self) -> str:
        # called from the tray thread — use the cached name, never sqlite
        if self.state == "online" and self.device_name:
            return f"Online as {self.device_name}"
        return STATUS_TEXT.get(self.state, self.state)

    def set_state(self, state: str, detail: str | None = None) -> None:
        from desktop.icon import make_icon
        prev, self.state = self.state, state
        try:
            self.tray.icon = make_icon(64, state)
            self.tray.title = f"NetSync AI — {STATUS_TEXT.get(state, state)}"
            self.tray.update_menu()
        except Exception:
            pass
        if state == "online" and prev != "online":
            log.info("online")
        if state == "rejected":
            self._forget_device()
            self.show_welcome(reason="This computer was removed from your NetSync "
                                     "account. Connect it again to keep using it.")

    def notify(self, message: str) -> None:
        try:
            self.tray.notify(message, "NetSync AI")
        except Exception:
            pass

    # ── agent loop ────────────────────────────────────────────────────────

    def start_agent(self) -> None:
        self.stop_agent()
        s = self._settings()
        coordinator = s["coordinator_url"] or default_coordinator()
        data_dir = self.data_dir

        def on_status(state, detail=None):
            self.post(lambda: self.set_state(state, detail))

        async def runner():
            conn = connect(data_dir)  # sqlite: one connection per thread
            from desktop.machine_id import machine_id
            try:
                await run_forever(coordinator, s["device_id"], s["device_credential"],
                                  AGENT_VERSION, conn=conn, on_status=on_status,
                                  machine_id=machine_id(conn))
            except CredentialRejected:
                pass  # already reported through on_status
            finally:
                conn.close()

        self.set_state("connecting")
        self.agent_future = asyncio.run_coroutine_threadsafe(runner(), self.loop)

    def stop_agent(self) -> None:
        if self.agent_future is not None:
            self.loop.call_soon_threadsafe(self.agent_future.cancel)
            self.agent_future = None

    def _forget_device(self) -> None:
        self.stop_agent()
        self.conn.execute(
            f"DELETE FROM agent_settings WHERE key IN ({','.join('?' * len(DEVICE_KEYS))})",
            DEVICE_KEYS,
        )
        self.conn.commit()
        self.device_name = None

    # ── messages (IPC / deep links) ───────────────────────────────────────

    def handle_message(self, message: str) -> None:
        log.info("message: %s", message.split("?")[0])
        if message == "quit":
            self.quit()
        elif code := parse_pair_link(message):
            self.begin_pairing(code)
        elif message.lower().startswith("netsync://") or message == "show":
            if self.state in ("unpaired", "rejected"):
                self.show_welcome()
            else:
                self.show_status()

    # ── windows ───────────────────────────────────────────────────────────

    def _close(self, key: str) -> None:
        w = self.windows.pop(key, None)
        if w is not None:
            try:
                w.close()
            except tk.TclError:
                pass

    def show_welcome(self, reason: str | None = None) -> None:
        from desktop.windows import WelcomeWindow
        self._close("welcome")
        self.windows["welcome"] = WelcomeWindow(
            self.root, self.window_icon, reason=reason,
            on_open_dashboard=lambda: self.open_dashboard("/devices?connect=1"),
            on_submit_code=self.begin_pairing,
        )

    def open_dashboard(self, path: str = "") -> None:
        webbrowser.open(dashboard_url().rstrip("/") + (path or "/dashboard"))

    def open_logs(self) -> None:
        os.startfile(self.data_dir / "logs")  # type: ignore[attr-defined]

    def show_status(self) -> None:
        """Reassure a manual (double-click) launcher that the app is alive —
        without a window, a paired agent looks like 'nothing happened'."""
        from desktop.windows import InfoWindow
        self._close("status")
        self.windows["status"] = InfoWindow(
            self.root, self.window_icon,
            f"NetSync AI — {STATUS_TEXT.get(self.state, self.state)}",
            f"This computer is connected as “{self.device_name or '—'}” and "
            "keeps running in the background (system tray icon). Manage shared "
            "folders and people from the dashboard.",
            action=("Open dashboard", lambda: self.open_dashboard("")),
        )

    # ── pairing ───────────────────────────────────────────────────────────

    def _welcome_status(self, text: str, error: bool = False) -> None:
        w = self.windows.get("welcome")
        if w is not None:
            try:
                w.set_status(text, error)
            except tk.TclError:
                pass

    def begin_pairing(self, code: str) -> None:
        if self.pairing_busy:
            return
        self.pairing_busy = True
        coordinator = default_coordinator()

        def work():
            try:
                preview = fetch_pairing_preview(coordinator, code)
                self.post(lambda: self._confirm_pairing(coordinator, code, preview))
            except Exception as exc:  # never leak pairing_busy — a stuck flag
                # silently ignores every later Connect click
                msg = str(exc) if isinstance(exc, PairingFailed) else \
                    "Can't reach NetSync AI. Check your internet connection."
                def fail():
                    self.pairing_busy = False
                    if "welcome" in self.windows:
                        self._welcome_status(msg, error=True)
                    else:
                        self.show_welcome(reason=f"Pairing failed: {msg}")
                self.post(fail)

        threading.Thread(target=work, daemon=True).start()

    def _confirm_pairing(self, coordinator: str, code: str, preview: dict) -> None:
        from desktop.windows import ConfirmPairWindow
        self._close("confirm")
        replacing = get_setting(self.conn, "device_name") if self._paired() else None

        def cancel():
            self.pairing_busy = False
            self.windows.pop("confirm", None)

        def confirm():
            win.busy()
            from desktop.machine_id import machine_id
            mid = machine_id(self.conn)  # main thread — sqlite isn't shared

            def work():
                try:
                    result = asyncio.run(redeem_pairing(
                        coordinator, code, AGENT_VERSION, machine_id=mid))
                    self.post(lambda: self._paired_ok(coordinator, result))
                except Exception as exc:  # network errors, bad bodies, anything
                    def fail():
                        self.pairing_busy = False
                        msg = str(exc) or "pairing failed — try again"
                        try:
                            win.set_status(msg, error=True)
                            win.connect_btn.configure(state="normal", text="Connect")
                        except tk.TclError:
                            pass
                    self.post(fail)

            threading.Thread(target=work, daemon=True).start()

        win = ConfirmPairWindow(
            self.root, self.window_icon,
            owner_email=preview.get("owner_email") or "",
            device_name=preview.get("device_name") or "This computer",
            replacing=replacing, on_confirm=confirm, on_cancel=cancel,
        )
        self.windows["confirm"] = win
        self._close("welcome")

    def _paired_ok(self, coordinator: str, result: dict) -> None:
        self.pairing_busy = False
        self.stop_agent()
        set_setting(self.conn, "device_id", result["device_id"])
        set_setting(self.conn, "device_credential", result["device_credential"])
        set_setting(self.conn, "device_name", result["device_name"])
        set_setting(self.conn, "coordinator_url", coordinator)
        self.device_name = result["device_name"]
        log.info("paired as %s (%s)", result["device_name"], result["device_id"])
        self._close("confirm")
        self.start_agent()
        self.notify(f"Connected as {result['device_name']}. Manage shared folders "
                    "from the dashboard.")


# ── uninstall ────────────────────────────────────────────────────────────────

def run_uninstall(data_dir: Path) -> int:
    from tkinter import messagebox

    from desktop.install import schedule_self_delete, unregister
    from desktop.instance import send_to_running

    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(
        "Uninstall NetSync AI",
        "Remove NetSync AI from this computer?\n\nThe computer will stop "
        "syncing and disappear from your dashboard once you remove it there.",
    ):
        return 0
    send_to_running("quit")
    unregister()
    if messagebox.askyesno(
        "Uninstall NetSync AI",
        "Also delete NetSync AI's local data (file index, sync history and "
        "this computer's connection)?\n\nYour own files are never deleted.",
    ):
        shutil.rmtree(data_dir, ignore_errors=True)
    schedule_self_delete()
    messagebox.showinfo("NetSync AI", "NetSync AI has been removed.")
    return 0


def run_app(data_dir: Path, argv: list[str]) -> int:
    message = next((a for a in argv if a.lower().startswith("netsync://")), None)
    background = "--background" in argv
    if "--uninstall" in argv:
        return run_uninstall(data_dir)

    from desktop.install import is_frozen, register, running_from_install_dir, self_install
    if self_install(argv):
        return 0
    if is_frozen() and running_from_install_dir():
        try:
            register(Path(sys.executable))  # repair paths after updates
        except OSError:
            log.warning("could not refresh Windows integration")
    try:
        return AgentApp(data_dir, message, background).run()
    except Exception:
        log.exception("fatal app error")
        # a windowed exe dies silently otherwise — show the user something
        try:
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            log_dir = data_dir / "logs"
            messagebox.showerror(
                "NetSync AI",
                f"NetSync AI could not start.\n\nDetails were written to:\n{log_dir}",
            )
        except Exception:
            pass
        return 1
