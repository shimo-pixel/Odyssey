import random
import uuid

from prds.models.domain import AgentAttributes, AgentState, ResourceSnapshot, StrategyType
from prds.simulation.actions import randomize_attributes


ALL_STRATEGIES = list(StrategyType)


def create_agents(
    count: int,
    initial_resources: ResourceSnapshot,
    seed: int | None = None,
) -> list[AgentState]:
    rng = random.Random(seed)
    agents: list[AgentState] = []

    for i in range(count):
        strategy = ALL_STRATEGIES[i % len(ALL_STRATEGIES)]
        attrs = randomize_attributes(rng, strategy.value)
        agents.append(
            AgentState(
                agent_id=f"agent_{i:04d}_{uuid.uuid4().hex[:6]}",
                strategy_type=strategy,
                attributes=attrs,
                resources=initial_resources.model_copy(),
            )
        )
    return agents
