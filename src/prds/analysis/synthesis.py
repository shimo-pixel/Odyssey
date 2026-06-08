import json

from prds.llm.client import LLMClient
from prds.llm.schemas import SynthesisOutput
from prds.models.domain import AgentScore, AgentState, StrategySynthesis, TargetGoal


SYNTHESIS_SYSTEM = """You are a strategy synthesis engine for a multi-agent simulation.
From the champion agent's trajectory and top performers, extract actionable patterns.
Return JSON with: principles, key_turning_points, success_factors, failure_avoidance_factors, recommended_roadmap.
Do NOT give direct advice - frame everything as outcomes from parallel world simulation."""


async def synthesize_strategy(
    llm: LLMClient,
    champion: AgentState,
    top_agents: list[AgentScore],
    goal: TargetGoal,
    agent_count: int,
) -> StrategySynthesis:
    payload = {
        "goal": goal.model_dump(),
        "champion": {
            "strategy": champion.strategy_type.value,
            "timeline": [e.model_dump() for e in champion.timeline],
            "final_resources": champion.resources.model_dump(),
        },
        "top_agents": [a.model_dump() for a in top_agents],
        "agent_count": agent_count,
    }
    user = json.dumps(payload, ensure_ascii=False, indent=2)

    output = await llm.structured_complete(
        SYNTHESIS_SYSTEM,
        user,
        SynthesisOutput,
        model=llm.analysis_model,
    )
    return StrategySynthesis(
        **output.model_dump(),
        disclaimer=f"本路线图来自 {agent_count} 个平行世界推演结果，非直接建议。",
    )
