"""Keep cloud share records in sync with what agents actually share.

A share record only means something while its root exists in the agent's
indexed folders. If the owner removes the folder outside this API (older
app version, agent-side tooling), the cloud record becomes a ghost —
collaborators would keep seeing a share that always fails. Whenever a
device is reachable we prune those records; offline devices can't be
verified, so their shares are kept.
"""

from __future__ import annotations

import logging

from app.orchestration.dispatcher import dispatch
from app.services.device_registry import DeviceStore

log = logging.getLogger("netsync.reconcile")


def _norm(path: str) -> str:
    return path.replace("/", "\\").lower().rstrip("\\")


async def prune_ghost_shares(
    store: DeviceStore, shares: list[dict]
) -> list[dict]:
    """Drop shares whose root the owning agent no longer reports."""
    by_device: dict[str, list[dict]] = {}
    for s in shares:
        by_device.setdefault(s["device_id"], []).append(s)
    keep: list[dict] = []
    for device_id, rows in by_device.items():
        try:
            res = await dispatch(device_id, "list_folders", {}, timeout=10)
        except Exception:
            keep.extend(rows)  # unreachable — can't verify, keep as-is
            continue
        live = {_norm(f.get("path", "")) for f in res.get("folders", [])}
        for s in rows:
            if _norm(s.get("root_path", "")) in live:
                keep.append(s)
                continue
            try:
                n = await store.delete_shares_for_root(
                    s["owner_id"], s["device_id"], s["root_path"])
                log.info("pruned %d ghost share(s) at %s on device %s",
                         n, s["root_path"], device_id)
            except Exception:
                log.warning("failed to prune ghost share %s", s.get("id"))
    return keep
