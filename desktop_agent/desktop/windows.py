"""tkinter windows for app mode. All functions must run on the Tk thread."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

BG = "#0f0f14"
SURFACE = "#17171f"
BORDER = "#2a2a38"
TEXT = "#ececf1"
DIM = "#9b9bab"
PRIMARY = "#8b5cf6"
PRIMARY_HOVER = "#7c4dff"
DANGER = "#f87171"
FONT = "Segoe UI"


def _center(win: tk.Toplevel, w: int, h: int) -> None:
    win.update_idletasks()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"{w}x{h}+{x}+{y}")


def _window(root: tk.Tk, title: str, w: int, h: int, icon=None) -> tk.Toplevel:
    win = tk.Toplevel(root, bg=BG)
    win.title(title)
    win.resizable(False, False)
    if icon is not None:
        win.iconphoto(False, icon)
    _center(win, w, h)
    win.attributes("-topmost", True)
    win.after(400, lambda: win.attributes("-topmost", False))
    win.focus_force()
    return win


def _button(parent, text: str, command: Callable, primary: bool = True) -> tk.Button:
    bg = PRIMARY if primary else SURFACE
    hover = PRIMARY_HOVER if primary else BORDER
    b = tk.Button(
        parent, text=text, command=command, bg=bg, fg="white" if primary else TEXT,
        activebackground=hover, activeforeground="white", relief="flat",
        bd=0, padx=18, pady=9, font=(FONT, 10, "bold"), cursor="hand2",
        highlightthickness=1 if not primary else 0, highlightbackground=BORDER,
    )
    b.bind("<Enter>", lambda _: b.configure(bg=hover))
    b.bind("<Leave>", lambda _: b.configure(bg=bg))
    return b


def _header(win, icon, title: str, subtitle: str) -> None:
    head = tk.Frame(win, bg=BG)
    head.pack(fill="x", padx=28, pady=(26, 8))
    if icon is not None:
        tk.Label(head, image=icon, bg=BG).pack(side="left", padx=(0, 14))
    text = tk.Frame(head, bg=BG)
    text.pack(side="left", fill="x")
    tk.Label(text, text=title, bg=BG, fg=TEXT, font=(FONT, 15, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(text, text=subtitle, bg=BG, fg=DIM, font=(FONT, 9), anchor="w",
             justify="left", wraplength=330).pack(fill="x")


class WelcomeWindow:
    """Shown when this computer isn't connected to an account yet."""

    def __init__(self, root: tk.Tk, icon, *, reason: str | None,
                 on_open_dashboard: Callable[[], None],
                 on_submit_code: Callable[[str], None]):
        self.win = _window(root, "NetSync AI", 470, 420 if reason else 380, icon)
        _header(self.win, icon, "Connect this computer",
                "Link this PC to your NetSync AI account to browse, share and "
                "sync its folders from the web dashboard.")
        if reason:
            tk.Label(self.win, text=reason, bg="#2a1414", fg=DANGER, font=(FONT, 9),
                     wraplength=410, justify="left", padx=12, pady=8
                     ).pack(fill="x", padx=28, pady=(6, 0))

        steps = tk.Frame(self.win, bg=SURFACE, highlightthickness=1,
                         highlightbackground=BORDER)
        steps.pack(fill="x", padx=28, pady=14)
        for n, line in enumerate((
            "Open the dashboard and sign in",
            "Go to Devices → Add this computer",
            "Approve the request in the window that appears",
        ), 1):
            row = tk.Frame(steps, bg=SURFACE)
            row.pack(fill="x", padx=14, pady=(10 if n == 1 else 2, 10 if n == 3 else 2))
            tk.Label(row, text=str(n), bg=PRIMARY, fg="white", width=2,
                     font=(FONT, 9, "bold")).pack(side="left")
            tk.Label(row, text=line, bg=SURFACE, fg=TEXT, font=(FONT, 10)
                     ).pack(side="left", padx=10)

        _button(self.win, "Open dashboard", on_open_dashboard).pack(
            padx=28, fill="x")

        tk.Label(self.win, text="Have a pairing code instead?", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(anchor="w", padx=28, pady=(16, 4))
        row = tk.Frame(self.win, bg=BG)
        row.pack(fill="x", padx=28)
        self.code = tk.StringVar()
        entry = tk.Entry(row, textvariable=self.code, bg=SURFACE, fg=TEXT,
                         insertbackground=TEXT, relief="flat",
                         font=("Consolas", 13), highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=PRIMARY)
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.bind("<Return>", lambda _: self._submit(on_submit_code))
        _button(row, "Connect", lambda: self._submit(on_submit_code),
                primary=False).pack(side="left", padx=(8, 0))
        self.status = tk.Label(self.win, text="", bg=BG, fg=DIM, font=(FONT, 9))
        self.status.pack(anchor="w", padx=28, pady=(8, 0))

    def _submit(self, cb):
        code = self.code.get().strip().upper().replace("-", "").replace(" ", "")
        if len(code) != 8:
            self.set_status("Codes are 8 characters long.", error=True)
            return
        self.set_status("Checking code…")
        cb(code)

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, fg=DANGER if error else DIM)

    def close(self) -> None:
        self.win.destroy()


class ConfirmPairWindow:
    """Explicit local consent before this PC is linked to an account."""

    def __init__(self, root: tk.Tk, icon, *, owner_email: str, device_name: str,
                 replacing: str | None, on_confirm: Callable[[], None],
                 on_cancel: Callable[[], None]):
        self.win = _window(root, "NetSync AI — Connect this computer", 470, 400, icon)
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)
        self._on_cancel = on_cancel
        _header(self.win, icon, "Connect this computer?",
                "A NetSync AI account is asking to link this PC.")

        card = tk.Frame(self.win, bg=SURFACE, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="x", padx=28, pady=12)
        for label, value in (("Account", owner_email or "unknown"),
                             ("Device name", device_name)):
            row = tk.Frame(card, bg=SURFACE)
            row.pack(fill="x", padx=14, pady=6)
            tk.Label(row, text=label, bg=SURFACE, fg=DIM, font=(FONT, 9),
                     width=12, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=SURFACE, fg=TEXT,
                     font=(FONT, 10, "bold"), anchor="w").pack(side="left")

        note = ("Only continue if you started this from your own dashboard. "
                "That account will be able to manage which folders on this PC "
                "are shared. System folders are always protected.")
        if replacing:
            note = (f"This PC is currently connected as “{replacing}”. "
                    "Continuing moves it to the account above. ") + note
        tk.Label(self.win, text=note, bg=BG, fg=DIM, font=(FONT, 9),
                 wraplength=410, justify="left").pack(fill="x", padx=28)

        btns = tk.Frame(self.win, bg=BG)
        btns.pack(fill="x", padx=28, pady=(18, 0))
        self.connect_btn = _button(btns, "Connect", on_confirm)
        self.connect_btn.pack(side="right")
        _button(btns, "Cancel", self._cancel, primary=False).pack(side="right", padx=8)
        self.status = tk.Label(self.win, text="", bg=BG, fg=DIM, font=(FONT, 9))
        self.status.pack(anchor="w", padx=28, pady=(10, 0))

    def _cancel(self):
        self._on_cancel()
        self.win.destroy()

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, fg=DANGER if error else DIM)

    def busy(self) -> None:
        self.connect_btn.configure(state="disabled", text="Connecting…")

    def close(self) -> None:
        self.win.destroy()


class InfoWindow:
    def __init__(self, root: tk.Tk, icon, title: str, body: str,
                 action: tuple[str, Callable[[], None]] | None = None):
        self.win = _window(root, "NetSync AI", 440, 250, icon)
        _header(self.win, icon, title, body)
        btns = tk.Frame(self.win, bg=BG)
        btns.pack(fill="x", padx=28, pady=(20, 0))
        _button(btns, "Close", self.win.destroy, primary=action is None).pack(side="right")
        if action:
            label, cb = action
            _button(btns, label, lambda: (cb(), self.win.destroy())).pack(side="right", padx=8)

    def close(self) -> None:
        self.win.destroy()
