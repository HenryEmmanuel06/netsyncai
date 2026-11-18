"""NetSync AI desktop agent — entrypoint.

End users never use the CLI. Launching the exe with no subcommand (double-
click, Windows startup, or a netsync:// link from the dashboard) starts the
desktop app: tray icon, pairing window, background agent.

Developer CLI subcommands:
  init    create local database + settings
  pair    redeem a pairing code -> device credential (one-time)
  run     connect to the coordinator and stay resident (foreground)
  index   index a folder into local SQLite FTS5
  search  search the local index
  status  show agent state
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from agent_config import AGENT_VERSION, default_coordinator
from database.db import connect, default_data_dir, get_setting, set_setting
from indexing.indexer import index_folder, register_folder, search_files
from networking.coordinator import (
    CredentialRejected,
    PairingFailed,
    redeem_pairing,
    run_forever,
)

log = logging.getLogger("netsync-agent")
CLI_COMMANDS = {"init", "pair", "run", "index", "search", "status"}


def cmd_init(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    set_setting(conn, "agent_version", AGENT_VERSION)
    print(f"Initialized agent database at {args.data_dir}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    folder_path = Path(args.folder).resolve()
    if not folder_path.is_dir():
        print(f"not a directory: {folder_path}", file=sys.stderr)
        return 2
    folder_id = register_folder(conn, folder_path, label=args.label, access=args.access)
    stats = index_folder(conn, folder_id)
    print(
        f"indexed {folder_path}: +{stats.added} ~{stats.updated} "
        f"-{stats.deleted} (skipped {stats.skipped})"
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    results = search_files(conn, args.query, ext=args.ext, limit=args.limit)
    print(json.dumps(results, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    folders = conn.execute("SELECT path, label FROM indexed_folders").fetchall()
    device_id = get_setting(conn, "device_id")
    print(json.dumps({
        "agent_version": AGENT_VERSION,
        "device_id": device_id,
        "paired": device_id is not None,
        "coordinator_url": get_setting(conn, "coordinator_url") or default_coordinator(),
        "indexed_folders": [dict(f) for f in folders],
        "data_dir": str(args.data_dir),
    }, indent=2))
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    if get_setting(conn, "device_id") and not args.force:
        print("already paired (use --force to re-pair)", file=sys.stderr)
        return 2
    from desktop.machine_id import machine_id
    try:
        result = asyncio.run(
            redeem_pairing(args.coordinator, args.code, AGENT_VERSION,
                           machine_id=machine_id(conn))
        )
    except PairingFailed as exc:
        print(f"pairing failed: {exc}", file=sys.stderr)
        return 1
    set_setting(conn, "device_id", result["device_id"])
    set_setting(conn, "device_credential", result["device_credential"])
    set_setting(conn, "device_name", result["device_name"])
    set_setting(conn, "coordinator_url", args.coordinator)
    set_setting(conn, "owner_email", result.get("owner_email") or "")
    print(f"paired as {result['device_name']} ({result['device_id']})")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    conn = connect(args.data_dir)
    device_id = get_setting(conn, "device_id")
    credential = get_setting(conn, "device_credential")
    coordinator = (
        args.coordinator
        or get_setting(conn, "coordinator_url")
        or default_coordinator()
    )
    if not device_id or not credential:
        print("not paired — run `main.py pair <code>` first", file=sys.stderr)
        return 2
    if not coordinator:
        print("no coordinator URL — pass --coordinator", file=sys.stderr)
        return 2
    log.info("starting agent: device=%s coordinator=%s", device_id, coordinator)
    from desktop.machine_id import machine_id
    try:
        asyncio.run(
            run_forever(coordinator, device_id, credential, AGENT_VERSION,
                        conn=conn, machine_id=machine_id(conn))
        )
    except CredentialRejected as exc:
        print(f"this device is no longer accepted ({exc}) — pair again with "
              "`pair <code> --force`", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        log.info("shutting down")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netsync-agent")
    p.add_argument("--data-dir", type=Path, default=default_data_dir())
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    pp = sub.add_parser("pair")
    pp.add_argument("code", help="8-character code from the web dashboard")
    pp.add_argument("--coordinator", default=default_coordinator())
    pp.add_argument("--force", action="store_true")
    pp.set_defaults(fn=cmd_pair)

    pr = sub.add_parser("run")
    pr.add_argument("--coordinator", default=None,
                    help="override the saved/bundled coordinator URL")
    pr.set_defaults(fn=cmd_run)

    pi = sub.add_parser("index")
    pi.add_argument("folder")
    pi.add_argument("--label", default="")
    pi.add_argument(
        "--access", default="read", choices=["none", "read", "readwrite"],
        help="remote access level for this folder",
    )
    pi.set_defaults(fn=cmd_index)

    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--ext")
    ps.add_argument("--limit", type=int, default=50)
    ps.set_defaults(fn=cmd_search)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    return p


def _attach_parent_console() -> None:
    """The release exe is a windowed app (no console). When a developer runs
    a CLI subcommand from a terminal, reattach to that terminal for output."""
    if os.name != "nt" or not getattr(sys, "frozen", False) or sys.stdout is not None:
        return
    import ctypes
    if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", buffering=1)
        sys.stderr = open("CONOUT$", "w", buffering=1)


def is_cli(argv: list[str]) -> bool:
    return any(a in CLI_COMMANDS or a in ("-h", "--help") for a in argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not is_cli(argv):
        try:
            from desktop.agent_app import run_app
        except ImportError as exc:
            # no tkinter/pystray (headless build, minimal python) — the agent
            # still works fully through the CLI
            print(f"NetSync AI {AGENT_VERSION}\n"
                  f"the desktop app isn't available here ({exc}).\n"
                  "Use the CLI instead:\n"
                  "  netsync-agent pair <code>   link this computer\n"
                  "  netsync-agent run           stay connected (foreground)\n"
                  "  netsync-agent status        show pairing + folders",
                  file=sys.stderr)
            return 2
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--data-dir", type=Path, default=default_data_dir())
        known, rest = pre.parse_known_args(argv)
        return run_app(known.data_dir, rest)

    _attach_parent_console()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
