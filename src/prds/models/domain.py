try:
    from enum import StrEnum
except ImportError:  # Python < 3.11
    from enum import Enum

    class StrEnum(str, Enum):
        pass

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
    RESEARCH = "research"
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
    domain_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Domain-specific metrics (reserved for future domain extensions)",
    )


class ResourceDelta(BaseModel):
    """Resource changes from an action; deltas may be negative."""

    cash: float = 0.0
    team_size: int = 0
    users: int = 0
    revenue: float = 0.0
    product_maturity: float = 0.0
    brand_awareness: float = 0.0
    market_share: float = 0.0


class CurrentState(BaseModel):
    background: str = Field(description="Background context and narrative")
    resources: ResourceSnapshot = Field(default_factory=ResourceSnapshot)
    constraints: list[str] = Field(default_factory=list)
    organization: dict[str, Any] = Field(default_factory=dict)
    personnel: list[dict[str, Any]] = Field(default_factory=list)
    financials: dict[str, Any] = Field(default_factory=dict)
    market_info: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class TargetGoal(BaseModel):
    description: str
    success_metrics: dict[str, float] = Field(default_factory=dict)
    baseline_snapshot: ResourceSnapshot | None = Field(
        default=None,
        description="Starting resources; goal progress is measured from this baseline",
    )


class SimulationConfig(BaseModel):
    domain_id: str = Field(default="startup", description="Domain profile (currently startup only)")
    agent_count: int = Field(default=50, ge=1, le=500)
    max_events: int = Field(default=24, ge=1, le=100, description="Upper bound on report-planned exogenous events")
    seed: int | None = None
    replications: int = Field(
        default=1, ge=1, le=10, description="Re-run the whole sim with different seeds for uncertainty"
    )
    param_overrides: dict[str, float] = Field(
        default_factory=dict, description="Override domain rule-engine parameters"
    )
    llm_model: str | None = None
    llm_model_analysis: str | None = None


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


class KnowledgeGraphData(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorldState(BaseModel):
    event_index: int = 0
    total_events: int = 0
    environment: EnvironmentParams = Field(default_factory=EnvironmentParams)
    external_market: dict[str, float] = Field(default_factory=dict)
    competition: dict[str, float] = Field(default_factory=dict)
    policy: dict[str, float] = Field(default_factory=dict)
    technology: dict[str, float] = Field(default_factory=dict)
    recent_events: list[Event] = Field(default_factory=list)
    narrative_summary: str = ""
    world_background_summary: str = ""
    graph_entity_hints: list[str] = Field(default_factory=list)
    domain_brief: list[str] = Field(
        default_factory=list, description="Key domain findings for agent reasoning"
    )
    domain_facts: list[str] = Field(
        default_factory=list, description="Compact graph relationship facts for agent context"
    )
    # Live knowledge-graph snapshot for per-agent subgraph retrieval (not sent to LLM).
    knowledge_graph: KnowledgeGraphData | None = Field(default=None, exclude=True)


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
    action: str
    action_params: dict[str, Any] = Field(default_factory=dict)


class ActionFinancials(BaseModel):
    """Cash flow breakdown for one decision step."""

    action_expense: float = Field(default=0.0, ge=0.0, description="Cash spent on the chosen action")
    action_income: float = Field(default=0.0, ge=0.0, description="Cash inflow from action (fundraise, savings, etc.)")
    operating_burn: float = Field(default=0.0, ge=0.0, description="Team operating burn for the step")
    operating_revenue: float = Field(default=0.0, ge=0.0, description="Operating revenue recognized this step")
    total_expense: float = Field(default=0.0, ge=0.0)
    total_revenue: float = Field(default=0.0, ge=0.0)
    net_cash_flow: float = Field(default=0.0, description="Net change in cash this step")


class GoalStatus(BaseModel):
    """Distance to the simulation goal after a decision step."""

    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall goal completion ratio")
    distance: float = Field(default=1.0, ge=0.0, le=1.0, description="1 - progress")
    metric_progress: dict[str, float] = Field(default_factory=dict)
    metric_gaps: dict[str, float] = Field(default_factory=dict, description="Remaining amount per metric")


class ActionResult(BaseModel):
    reward: float = 0.0
    penalty: float = 0.0
    resource_change: ResourceDelta = Field(default_factory=ResourceDelta)
    financials: ActionFinancials = Field(default_factory=ActionFinancials)
    action_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Domain-specific step breakdown, e.g. subjects studied",
    )
    narrative: str = ""
    success: bool = True


class DecisionLogEntry(BaseModel):
    event_index: int
    trigger_event_id: str = ""
    world_state: WorldState
    thought: str = ""
    reasoning: str = ""
    decision: str = ""
    action: str = "hold"
    action_params: dict[str, Any] = Field(default_factory=dict)
    result: ActionResult = Field(default_factory=ActionResult)
    events: list[Event] = Field(default_factory=list)
    resources_after: ResourceSnapshot | None = None
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


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
    timeline: list[DecisionLogEntry] = Field(default_factory=list)


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


class ResearchCitation(BaseModel):
    title: str = ""
    url: str = ""


class BackgroundReport(BaseModel):
    """Industry/domain background report produced in step ②."""

    query: str = ""
    report: str = Field(default="", description="Full markdown report body")
    key_findings: list[str] = Field(default_factory=list)
    citations: list[ResearchCitation] = Field(default_factory=list)
    provider: str = "fallback"  # deep_research|grounded|fallback|off
    model: str = ""
    grounded: bool = False


class WorldBackground(BaseModel):
    summary: str = ""
    community_summaries: list[str] = Field(default_factory=list)
    entity_reports: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    graph_source: str = "graphrag"
    neo4j_persisted: bool = False
    research_provider: str = "off"
    research_report: str = Field(default="", description="Background report markdown (step ②)")
    research_citations: list[ResearchCitation] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    event_index: int
    trigger_event_id: str = ""
    world_state: WorldState
    agent_thought: str
    decision: str
    action: str
    result: ActionResult
    resources_after: ResourceSnapshot | None = None
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class DecisionStep(BaseModel):
    event_index: int
    trigger_event_id: str = ""
    world_summary: str = ""
    events: list[str] = Field(default_factory=list)
    action: str = "hold"
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True
    financials: ActionFinancials = Field(default_factory=ActionFinancials)
    action_summary: dict[str, Any] = Field(default_factory=dict)
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class AgentDecisionPath(BaseModel):
    agent_id: str
    rank: int = 0
    total_score: float = 0.0
    eliminated: bool = False
    elimination_reason: str | None = None
    steps: list[DecisionStep] = Field(default_factory=list)


class EventAgentDecision(BaseModel):
    agent_id: str
    rank: int = 0
    action: str = "hold"
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True
    financials: ActionFinancials = Field(default_factory=ActionFinancials)
    action_summary: dict[str, Any] = Field(default_factory=dict)
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class EventSummary(BaseModel):
    event_type: str
    description: str = ""
    impact: float = 0.0


class EventComparison(BaseModel):
    event_index: int
    event_id: str = ""
    event_label: str = ""
    world_summary: str = ""
    events: list[str] = Field(default_factory=list)
    event_summaries: list[EventSummary] = Field(default_factory=list)
    agents: list[EventAgentDecision] = Field(default_factory=list)


class CounterfactualComparison(BaseModel):
    event_index: int
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


class MetricBand(BaseModel):
    """Percentile band for a metric across many parallel agents/seeds."""

    metric: str
    label: str = ""
    p10: float = 0.0
    p25: float = 0.0
    median: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    mean: float = 0.0


class EventProgressBand(BaseModel):
    event_index: int
    p25: float = 0.0
    median: float = 0.0
    p75: float = 0.0


class ParamAssumption(BaseModel):
    key: str
    label: str
    value: float
    min: float = 0.0
    max: float = 1.0
    group: str = "general"


class OutcomeDistribution(BaseModel):
    """Honest uncertainty view: distribution across all parallel paths/seeds."""

    sample_size: int = 0
    replications: int = 1
    success_threshold: float = 0.9
    success_rate: float = 0.0
    near_success_rate: float = 0.0
    achieved_rate: float = 0.0
    elimination_rate: float = 0.0
    goal_progress: MetricBand = Field(default_factory=lambda: MetricBand(metric="goal_progress"))
    metric_bands: list[MetricBand] = Field(default_factory=list)
    progress_trajectory: list[EventProgressBand] = Field(default_factory=list)
    elimination_reasons: dict[str, int] = Field(default_factory=dict)
    param_assumptions: list[ParamAssumption] = Field(default_factory=list)
    disclaimer: str = (
        "本结果基于一组未经真实数据校准的假设参数与随机事件，"
        "展示的是多条平行路径的分布区间，而非精确预测。请将其作为情景探索而非确定性建议。"
    )


class SimulationResult(BaseModel):
    simulation_id: str
    domain_id: str = "startup"
    agent_count: int
    events_simulated: int
    ontology: OntologyGraph
    knowledge_graph: KnowledgeGraphData
    top_agents: list[AgentScore]
    champion_agent_id: str
    champion_strategy: StrategyType
    champion_timeline: list[TimelineEntry]
    agent_paths: list[AgentDecisionPath] = Field(default_factory=list)
    event_comparisons: list[EventComparison] = Field(default_factory=list)
    planned_events: list[Event] = Field(default_factory=list)
    world_background: WorldBackground = Field(default_factory=WorldBackground)
    counterfactuals: list[CounterfactualComparison]
    synthesis: StrategySynthesis
    outcome_distribution: OutcomeDistribution = Field(default_factory=OutcomeDistribution)


class SimulationProgress(BaseModel):
    simulation_id: str
    status: SimulationStatus
    phase: SimulationPhase
    current_event_index: int
    total_events: int
    alive_agents: int
    total_agents: int
    progress_pct: float
    error: str | None = None
    pause_pending: bool = False
    pending_user_events: int = 0
