"""NetSync AI desktop agent — CLI entrypoint.

Phase 1: init local DB, register/index folders, local search.
Phase 2 adds: `run` — pairing + persistent WSS connection to coordinator.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from database.db import connect, default_data_dir, get_setting, set_setting
from indexing.indexer import index_folder, register_folder, search_files

log = logging.getLogger("netsync-agent")
AGENT_VERSION = "0.1.0"


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
    folder_id = register_folder(conn, folder_path, label=args.label)
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
        "indexed_folders": [dict(f) for f in folders],
        "data_dir": str(args.data_dir),
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netsync-agent")
    p.add_argument("--data-dir", type=Path, default=default_data_dir())
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    pi = sub.add_parser("index")
    pi.add_argument("folder")
    pi.add_argument("--label", default="")
    pi.set_defaults(fn=cmd_index)

    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--ext")
    ps.add_argument("--limit", type=int, default=50)
    ps.set_defaults(fn=cmd_search)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
