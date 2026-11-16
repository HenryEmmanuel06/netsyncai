"""Best-effort activity logging — an audit write must never fail a request."""

from __future__ import annotations

import logging

log = logging.getLogger("netsync.activity")


async def log_activity(
    store, actor_id: str | None, action: str, *, device_id: str | None = None,
    target: str | None = None, metadata: dict | None = None,
) -> None:
    try:
        await store.record_activity(
            actor_id, action, device_id=device_id, target=target, metadata=metadata
        )
    except Exception:
        log.warning("could not record activity %s", action, exc_info=True)
