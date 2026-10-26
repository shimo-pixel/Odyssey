"""Simulation API surface after the branch-pipeline switch."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from prds.config import get_settings
from prds.models.domain import (
    BranchSummary,
    Rationality,
    SimulationPhase,
    SimulationResult,
    SimulationStatus,
)


@pytest.fixture
async def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PRDS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    get_settings.cache_clear()

    from prds.api.routes import simulations as sim_routes
    from prds.main import app
    from prds.storage.repository import SimulationRepository

    repo = SimulationRepository()
    await repo.init_db()
    sim_routes._repo = repo

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, repo

    # The engine holds an aiosqlite thread bound to this test's event loop.
    await repo.engine.dispose()
    sim_routes._repo = None


def _payload(agent_count: int = 4, max_events: int = 6) -> dict:
    return {
        "current_state": {"background": "数学 62 分"},
        "goal": {"description": "把数学提到 78 分"},
        "config": {
            "agent_count": agent_count,
            "max_events": max_events,
            "kb_category_ids": ["math_kb"],
        },
    }


async def test_refine_route_is_gone(api):
    """Input structuring happens silently inside the run now, not via an endpoint."""
    client, _ = api
    from prds.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/simulations/refine" not in paths

    r = await client.post("/api/simulations/refine", json=_payload())
    assert r.status_code in (404, 405)


async def test_create_rejects_runs_beyond_the_step_cap(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("PRDS_KBSIM_MAX_STEPS", "20")
    get_settings.cache_clear()

    r = await client.post("/api/simulations", json=_payload(agent_count=8, max_events=10))

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "80" in detail and "20" in detail


async def test_create_requires_a_goal(api):
    client, _ = api
    payload = _payload()
    payload["goal"]["description"] = "   "

    r = await client.post("/api/simulations", json=payload)

    assert r.status_code == 422


async def test_config_endpoint_reports_branch_pipeline_limits(api):
    client, _ = api

    body = (await client.get("/api/config")).json()

    assert "max_steps" in body
    assert "default_agent_count" in body
    assert "default_max_events" in body
    assert "graphrag_enabled" not in body
    assert "neo4j_configured" not in body


async def test_knowledge_graph_returns_browsable_branch_workspaces(api):
    client, repo = api
    from prds.models.domain import (
        CurrentState,
        SimulationConfig,
        SimulationInput,
        TargetGoal,
    )

    run_id = await repo.create_run(
        SimulationInput(
            current_state=CurrentState(background="数学 62 分"),
            goal=TargetGoal(description="把数学提到 78 分"),
            config=SimulationConfig(agent_count=2, max_events=2),
        )
    )
    await repo.save_result(
        run_id,
        SimulationResult(
            simulation_id=run_id,
            agent_count=2,
            events_simulated=2,
            branches=[
                BranchSummary(
                    branch_id="branch_01",
                    label="策略 1",
                    rationality=Rationality.RATIONAL,
                    rank=1,
                    workspaces=[f"sim_{run_id[:18]}_b01_math_kb"],
                ),
                BranchSummary(
                    branch_id="branch_02",
                    label="策略 2",
                    rationality=Rationality.IRRATIONAL,
                    rank=2,
                    workspaces=[f"sim_{run_id[:18]}_b02_math_kb"],
                ),
            ],
        ),
    )

    r = await client.get(f"/api/simulations/{run_id}/knowledge-graph")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["graph_source"] == "lightrag"
    assert [b["branch_id"] for b in body["branches"]] == ["branch_01", "branch_02"]
    assert [b["rationality"] for b in body["branches"]] == ["rational", "irrational"]
    assert all(b["workspaces"] for b in body["branches"])


async def test_knowledge_graph_requires_a_completed_run(api):
    client, repo = api
    from prds.models.domain import (
        CurrentState,
        SimulationConfig,
        SimulationInput,
        TargetGoal,
    )

    run_id = await repo.create_run(
        SimulationInput(
            current_state=CurrentState(background=""),
            goal=TargetGoal(description="目标"),
            config=SimulationConfig(),
        )
    )

    r = await client.get(f"/api/simulations/{run_id}/knowledge-graph")
    assert r.status_code == 409

    missing = await client.get("/api/simulations/does-not-exist/knowledge-graph")
    assert missing.status_code == 404


async def test_pause_is_limited_to_the_branch_simulation_phase(api):
    client, repo = api
    from prds.models.domain import (
        CurrentState,
        SimulationConfig,
        SimulationInput,
        TargetGoal,
    )

    run_id = await repo.create_run(
        SimulationInput(
            current_state=CurrentState(background=""),
            goal=TargetGoal(description="目标"),
            config=SimulationConfig(),
        )
    )
    await repo.update_progress(
        run_id, status=SimulationStatus.RUNNING, phase=SimulationPhase.EVENT_PLAN
    )

    too_early = await client.post(f"/api/simulations/{run_id}/pause")
    assert too_early.status_code == 409

    await repo.update_progress(run_id, phase=SimulationPhase.BRANCH_SIM)
    from prds.simulation.control import get_control
    get_control().set_can_pause(run_id, True)
    ok = await client.post(f"/api/simulations/{run_id}/pause")
    assert ok.status_code == 200
    assert ok.json()["status"] == "pause_requested"
