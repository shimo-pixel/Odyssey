import pytest

from prds.llm.client import LLMClient
from prds.models.domain import (
    CurrentState,
    ResourceSnapshot,
    SimulationConfig,
    SimulationInput,
    TargetGoal,
)
from prds.simulation.orchestrator import SimulationOrchestrator


@pytest.mark.asyncio
async def test_full_simulation_smoke():
    llm = LLMClient()
    orchestrator = SimulationOrchestrator(llm)

    simulation_input = SimulationInput(
        current_state=CurrentState(
            background="Early-stage startup building a productivity app.",
            resources=ResourceSnapshot(cash=50, team_size=3, users=50),
            constraints=["limited budget"],
            risks=["competition"],
            opportunities=["remote work trend"],
        ),
        goal=TargetGoal(
            description="Reach 1000 users in 3 months",
            success_metrics={"users": 1000},
        ),
        config=SimulationConfig(agent_count=5, max_events=3, seed=42),
    )

    result = await orchestrator.run("test-run-id", simulation_input)

    assert result.simulation_id == "test-run-id"
    assert result.agent_count == 5
    assert len(result.top_agents) <= 10
    assert result.champion_agent_id
    assert result.champion_timeline
    assert result.synthesis.principles
    assert "平行世界" in result.synthesis.disclaimer
    assert result.knowledge_graph.nodes
