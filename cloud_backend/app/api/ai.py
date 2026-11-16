"""AI task endpoint: prompt → validated plan → (optionally) executed.

Two-call flow for destructive plans: first call returns the plan with
needs_confirmation=true; the client re-submits with confirm=true to run
it. Read-only plans execute immediately.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.ai.planner import PlanError, generate_plan, needs_confirmation
from app.api.deps import current_auth, get_device_store
from app.errors import http_409, http_422
from app.orchestration.dispatcher import (
    CommandFailed,
    CommandTimeout,
    DeviceOffline,
    dispatch,
)
from app.schemas.ai import PlanStepOut, TaskRequest, TaskResponse
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceStore

log = logging.getLogger("netsync.ai")
router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/task", response_model=TaskResponse)
async def run_task(
    req: TaskRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    devices = [d for d in await store.list_devices(auth.user_id) if not d.revoked_at]
    by_name = {d.name.lower(): d.id for d in devices}

    try:
        plan = await generate_plan(req.prompt, list(by_name))
    except PlanError as exc:
        raise http_422(str(exc))

    destructive = needs_confirmation(plan)
    execute = not destructive or req.confirm
    if destructive and not req.confirm:
        return TaskResponse(
            summary=plan.summary, needs_confirmation=True, executed=False,
            steps=[PlanStepOut(device=s.device, tool=s.tool, args=s.args,
                               description=s.description) for s in plan.steps],
        )

    out: list[PlanStepOut] = []
    for step in plan.steps:
        device_id = (
            by_name.get(step.device.lower()) if step.device
            else (devices[0].id if devices else None)
        )
        entry = PlanStepOut(device=step.device, tool=step.tool,
                            args=step.args, description=step.description)
        if device_id is None:
            entry.ok, entry.error = False, "no matching device"
            out.append(entry)
            break
        try:
            entry.result = await dispatch(device_id, step.tool, step.args, timeout=60)
            entry.ok = True
        except (DeviceOffline, CommandTimeout, CommandFailed) as exc:
            entry.ok = False
            entry.error = getattr(exc, "error", str(exc))
            out.append(entry)
            break  # stop the chain on first failure
        out.append(entry)

    await log_activity(store, auth.user_id, "ai.task", target=req.prompt[:200],
                       metadata={"steps": len(out),
                                 "ok": all(s.ok for s in out) if out else False})
    return TaskResponse(
        summary=plan.summary,
        needs_confirmation=destructive,
        executed=execute,
        steps=out,
    )
