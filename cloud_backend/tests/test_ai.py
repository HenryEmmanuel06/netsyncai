"""AI planner tests — validation is offline; endpoint uses a stubbed plan."""

import pytest

from app.ai.planner import (
    Plan,
    PlanError,
    PlanStep,
    needs_confirmation,
    validate_steps,
)

# ── validation ───────────────────────────────────────────────────────────────

def test_valid_plan_passes():
    validate_steps([
        PlanStep(tool="browse_folder", args={"path": "C:\\x"}),
        PlanStep(tool="search_files", args={"query": "q", "limit": 5}),
    ])


def test_unknown_tool_rejected():
    with pytest.raises(PlanError, match="unknown tool"):
        validate_steps([PlanStep(tool="run_shell", args={})])


def test_owner_only_tools_never_plannable():
    for tool in ("add_folder", "remove_folder", "list_local_dirs", "set_folder_access"):
        with pytest.raises(PlanError, match="unknown tool"):
            validate_steps([PlanStep(tool=tool, args={})])


def test_unknown_arg_rejected():
    with pytest.raises(PlanError, match="no arg"):
        validate_steps([
            PlanStep(tool="search_files", args={"query": "x", "evil": 1})
        ])


def test_missing_required_arg():
    with pytest.raises(PlanError, match="missing"):
        validate_steps([PlanStep(tool="rename_file", args={"path": "x"})])


def test_wrong_arg_type():
    with pytest.raises(PlanError, match="must be"):
        validate_steps([
            PlanStep(tool="search_files", args={"query": 1})
        ])


def test_confirmation_detection():
    assert needs_confirmation(Plan(steps=[PlanStep(tool="delete_file", args={"path": "x"})]))
    assert not needs_confirmation(Plan(steps=[PlanStep(tool="browse_folder", args={"path": "x"})]))


# ── endpoint ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_without_key_422(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.ai.planner.settings.gemini_api_key", "")
    r = await client.post("/api/v1/ai/task",
                          json={"prompt": "list files"}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_destructive_plan_needs_confirm(client, auth_headers, monkeypatch):
    from app.ai.planner import Plan, PlanStep

    async def fake_plan(prompt, devices):
        return Plan(steps=[
            PlanStep(device="PC", tool="delete_file", args={"path": "C:\\x"})
        ], summary="delete it")

    monkeypatch.setattr("app.api.ai.generate_plan", fake_plan)
    await client.post("/api/v1/devices", json={"name": "PC"}, headers=auth_headers)

    r = await client.post("/api/v1/ai/task",
                          json={"prompt": "delete x"}, headers=auth_headers)
    assert r.json()["needs_confirmation"] is True
    assert r.json()["executed"] is False

    r = await client.post("/api/v1/ai/task",
                          json={"prompt": "delete x", "confirm": True},
                          headers=auth_headers)
    assert r.json()["executed"] is True
    # device is offline → step fails gracefully, not a 500
    assert r.json()["steps"][0]["ok"] is False


@pytest.mark.asyncio
async def test_readonly_plan_executes_immediately(client, auth_headers, monkeypatch):
    from app.ai.planner import Plan, PlanStep

    async def fake_plan(prompt, devices):
        return Plan(steps=[
            PlanStep(device="PC", tool="browse_folder", args={"path": ""})
        ])

    monkeypatch.setattr("app.api.ai.generate_plan", fake_plan)
    await client.post("/api/v1/devices", json={"name": "PC"}, headers=auth_headers)

    r = await client.post("/api/v1/ai/task",
                          json={"prompt": "list my roots"}, headers=auth_headers)
    assert r.json()["needs_confirmation"] is False
    assert r.json()["steps"][0]["ok"] is False  # offline, but executed
