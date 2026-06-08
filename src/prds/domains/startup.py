from prds.agents.prompts import build_agent_system_prompt
from prds.domains.registry import DomainProfile
from prds.models.domain import AgentState, GoalStatus, ResourceSnapshot, TargetGoal, WorldState
from prds.simulation import actions as startup_actions
from prds.simulation import elimination as startup_elimination
from prds.simulation import realism as startup_realism
from prds.analysis import scoring as startup_scoring


PROFILE = DomainProfile(
    id="startup",
    label="创业 / 投资",
    description="组织经营、融资、产品与市场决策推演",
    default_resources={
        "cash": 100,
        "team_size": 5,
        "users": 0,
        "revenue": 0,
        "product_maturity": 0.3,
        "brand_awareness": 0.2,
        "market_share": 0.05,
        "domain_metrics": {},
    },
    default_success_metrics={
        "revenue": 100.0,
        "users": 100_000.0,
        "market_share": 0.2,
        "product_maturity": 1.0,
    },
    default_market_info={
        "tam": 1000,
        "competition_intensity": 0.5,
        "user_growth_rate": 0.05,
    },
    execute_action=startup_actions._execute_startup_action,
    compute_goal_status=startup_elimination.compute_goal_status,
    should_eliminate=startup_elimination.should_eliminate,
    build_decision_context=startup_realism.build_decision_context,
    score_resource_efficiency=startup_scoring.resource_efficiency,
    build_system_prompt=build_agent_system_prompt,
)
