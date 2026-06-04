from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    HIRE = "hire"
    LAYOFF = "layoff"
    FUNDRAISE = "fundraise"
    PRODUCT_DEV = "product_dev"
    MARKETING = "marketing"
    STRATEGIC_PIVOT = "strategic_pivot"
    PARTNERSHIP = "partnership"
    ACQUISITION = "acquisition"
    COST_CUT = "cost_cut"
    HOLD = "hold"


class EventCategory(StrEnum):
    MACRO = "macro"
    MARKET = "market"
    ORG = "org"
    RESOURCE = "resource"


class StrategyType(StrEnum):
    CONSERVATIVE = "ConservativeAgent"
    AGGRESSIVE = "AggressiveAgent"
    DATA_DRIVEN = "DataDrivenAgent"
    MARKETING = "MarketingAgent"
    PRODUCT = "ProductAgent"
    FINANCIAL = "FinancialAgent"
    GROWTH = "GrowthAgent"
    BALANCED = "BalancedAgent"
    OPPORTUNISTIC = "OpportunisticAgent"
    SURVIVAL = "SurvivalAgent"


class SimulationPhase(StrEnum):
    PENDING = "pending"
    ONTOLOGY = "ontology"
    WORLD_INIT = "world_init"
    AGENT_SPAWN = "agent_spawn"
    SIMULATION = "simulation"
    SCORING = "scoring"
    TRAJECTORY = "trajectory"
    COUNTERFACTUAL = "counterfactual"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ResourceSnapshot(BaseModel):
    cash: float = Field(default=100.0, description="Cash in arbitrary units (e.g. 万)")
    team_size: int = Field(default=5)
    users: int = Field(default=0)
    revenue: float = Field(default=0.0)
    product_maturity: float = Field(default=0.1, ge=0.0, le=1.0)
    brand_awareness: float = Field(default=0.1, ge=0.0, le=1.0)
    market_share: float = Field(default=0.01, ge=0.0, le=1.0)


class CurrentState(BaseModel):
    background: str = Field(description="Background context and narrative")
    resources: ResourceSnapshot = Field(default_factory=ResourceSnapshot)
    constraints: list[str] = Field(default_factory=list)
    organization: dict[str, Any] = Field(default_factory=dict)
    personnel: list[dict[str, Any]] = Field(default_factory=list)
    financials: dict[str, Any] = Field(default_factory=dict)
    market_info: dict[str, Any] = Field(default_factory=dict)
    time_limit_periods: int | None = None
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class TargetGoal(BaseModel):
    description: str
    success_metrics: dict[str, float] = Field(default_factory=dict)
    deadline_periods: int | None = None


class SimulationConfig(BaseModel):
    agent_count: int = Field(default=50, ge=1, le=500)
    periods: int = Field(default=120, ge=1, le=360)
    period_time_unit: str = Field(default="month", description="day|week|month|quarter|year")
    period_time_length: int = Field(default=1, ge=1, le=52, description="Each period spans N units")
    simulation_start_date: str | None = Field(default=None, description="Optional start date YYYY-MM-DD")
    seed: int | None = None
    llm_model: str | None = None
    llm_model_analysis: str | None = None
    checkpoint_interval: int = Field(default=5, ge=1)


class SimulationInput(BaseModel):
    current_state: CurrentState
    goal: TargetGoal
    config: SimulationConfig = Field(default_factory=SimulationConfig)


class Event(BaseModel):
    event_id: str
    event_type: str
    category: EventCategory
    impact: float = Field(ge=-1.0, le=1.0)
    probability: float = Field(ge=0.0, le=1.0)
    severity: float = Field(ge=0.0, le=1.0)
    description: str = ""


class UserEventInput(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    category: EventCategory = EventCategory.MARKET
    impact: float = Field(default=0.0, ge=-1.0, le=1.0)
    severity: float = Field(default=0.6, ge=0.1, le=1.0)


class EnvironmentParams(BaseModel):
    economic_index: float = Field(default=1.0, ge=0.0, le=2.0)
    policy_support: float = Field(default=0.5, ge=0.0, le=1.0)
    tech_maturity: float = Field(default=0.5, ge=0.0, le=1.0)
    competition_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    user_growth_rate: float = Field(default=0.05, ge=-0.5, le=1.0)


class WorldState(BaseModel):
    period: int = 0
    total_periods: int = 120
    environment: EnvironmentParams = Field(default_factory=EnvironmentParams)
    external_market: dict[str, float] = Field(default_factory=dict)
    competition: dict[str, float] = Field(default_factory=dict)
    policy: dict[str, float] = Field(default_factory=dict)
    technology: dict[str, float] = Field(default_factory=dict)
    recent_events: list[Event] = Field(default_factory=list)
    narrative_summary: str = ""
    world_background_summary: str = ""
    graph_entity_hints: list[str] = Field(default_factory=list)


class AgentAttributes(BaseModel):
    risk_preference: float = Field(default=0.5, ge=0.0, le=1.0)
    learning_rate: float = Field(default=0.5, ge=0.0, le=1.0)
    execution_power: float = Field(default=0.5, ge=0.0, le=1.0)
    information_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    adaptability: float = Field(default=0.5, ge=0.0, le=1.0)


class AgentDecision(BaseModel):
    thought: str
    reasoning: str
    decision: str
    action: ActionType
    action_params: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    reward: float = 0.0
    penalty: float = 0.0
    resource_change: ResourceSnapshot = Field(default_factory=ResourceSnapshot)
    narrative: str = ""
    success: bool = True


class PeriodLogEntry(BaseModel):
    period: int
    world_state: WorldState
    thought: str = ""
    reasoning: str = ""
    decision: str = ""
    action: ActionType = ActionType.HOLD
    action_params: dict[str, Any] = Field(default_factory=dict)
    result: ActionResult = Field(default_factory=ActionResult)
    events: list[Event] = Field(default_factory=list)


class AgentState(BaseModel):
    agent_id: str
    strategy_type: StrategyType
    attributes: AgentAttributes
    resources: ResourceSnapshot
    eliminated: bool = False
    elimination_reason: str | None = None
    goal_progress: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_exposure: float = Field(default=0.0, ge=0.0, le=1.0)
    execution_score: float = Field(default=0.5, ge=0.0, le=1.0)
    adaptability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    timeline: list[PeriodLogEntry] = Field(default_factory=list)


class AgentScore(BaseModel):
    agent_id: str
    strategy_type: StrategyType
    total_score: float
    goal_achievement: float
    resource_efficiency: float
    risk_control: float
    execution_quality: float
    adaptability: float
    final_resources: ResourceSnapshot


class OntologyEntity(BaseModel):
    id: str
    entity_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class OntologyRelation(BaseModel):
    source_id: str
    target_id: str
    relation_type: str


class OntologyGraph(BaseModel):
    entities: list[OntologyEntity] = Field(default_factory=list)
    relations: list[OntologyRelation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)


class KnowledgeGraphData(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorldBackground(BaseModel):
    summary: str = ""
    community_summaries: list[str] = Field(default_factory=list)
    entity_reports: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    graph_source: str = "graphrag"
    neo4j_persisted: bool = False


class TimelineEntry(BaseModel):
    period: int
    world_state: WorldState
    agent_thought: str
    decision: str
    action: ActionType
    result: ActionResult


class DecisionStep(BaseModel):
    period: int
    world_summary: str = ""
    events: list[str] = Field(default_factory=list)
    action: ActionType = ActionType.HOLD
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True


class AgentDecisionPath(BaseModel):
    agent_id: str
    rank: int = 0
    total_score: float = 0.0
    eliminated: bool = False
    elimination_reason: str | None = None
    steps: list[DecisionStep] = Field(default_factory=list)


class PeriodAgentDecision(BaseModel):
    agent_id: str
    rank: int = 0
    action: ActionType = ActionType.HOLD
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True


class EventSummary(BaseModel):
    event_type: str
    description: str = ""
    impact: float = 0.0


class PeriodComparison(BaseModel):
    period: int
    period_label: str = ""
    world_summary: str = ""
    events: list[str] = Field(default_factory=list)
    event_summaries: list[EventSummary] = Field(default_factory=list)
    agents: list[PeriodAgentDecision] = Field(default_factory=list)


class CounterfactualComparison(BaseModel):
    period: int
    decision_a: str
    outcome_a: str
    decision_b: str
    outcome_b: str
    difference: str


class StrategySynthesis(BaseModel):
    principles: list[str]
    key_turning_points: list[str]
    success_factors: list[str]
    failure_avoidance_factors: list[str]
    recommended_roadmap: list[str]
    disclaimer: str = "本路线图来自多平行世界推演结果，非直接建议。"


class SimulationResult(BaseModel):
    simulation_id: str
    agent_count: int
    periods_simulated: int
    period_time_unit: str = "month"
    period_time_length: int = 1
    simulation_start_date: str | None = None
    ontology: OntologyGraph
    knowledge_graph: KnowledgeGraphData
    top_agents: list[AgentScore]
    champion_agent_id: str
    champion_strategy: StrategyType
    champion_timeline: list[TimelineEntry]
    agent_paths: list[AgentDecisionPath] = Field(default_factory=list)
    period_comparisons: list[PeriodComparison] = Field(default_factory=list)
    world_background: WorldBackground = Field(default_factory=WorldBackground)
    counterfactuals: list[CounterfactualComparison]
    synthesis: StrategySynthesis


class SimulationProgress(BaseModel):
    simulation_id: str
    status: SimulationStatus
    phase: SimulationPhase
    current_period: int
    total_periods: int
    alive_agents: int
    total_agents: int
    progress_pct: float
    error: str | None = None
    pause_pending: bool = False
    pending_user_events: int = 0
    period_time_unit: str = "month"
    period_time_length: int = 1
    simulation_start_date: str | None = None
