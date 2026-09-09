try:
    from enum import StrEnum
except ImportError:  # Python < 3.11
    from enum import Enum

    class StrEnum(str, Enum):
        pass

from typing import Any

from pydantic import BaseModel, Field


class EventCategory(StrEnum):
    MACRO = "macro"
    MARKET = "market"
    ORG = "org"
    RESOURCE = "resource"


class Rationality(StrEnum):
    """How disciplined a branch's response to an event is."""

    RATIONAL = "rational"
    IRRATIONAL = "irrational"


class SimulationPhase(StrEnum):
    PENDING = "pending"
    INTAKE = "intake"
    KB_SNAPSHOT = "kb_snapshot"
    EVENT_PLAN = "event_plan"
    BRANCH_FORK = "branch_fork"
    BRANCH_SIM = "branch_sim"
    SCORING = "scoring"
    SYNTHESIS = "synthesis"
    CLEANUP = "cleanup"
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


class MetricSpec(BaseModel):
    """One measurable dimension of the goal, derived from goal + knowledge base."""

    name: str
    unit: str = ""
    direction: str = Field(default="up", description="up: higher is better, down: lower is better")
    baseline: float = 0.0
    target: float = 0.0

    def progress(self, value: float) -> float:
        """Completion ratio of this metric for a predicted value."""
        span = self.target - self.baseline
        if abs(span) < 1e-9:
            return 1.0 if abs(value - self.target) < 1e-9 else 0.0
        ratio = (value - self.baseline) / span
        return max(0.0, min(1.0, ratio))


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
    domain_id: str = Field(default="startup", description="Domain profile label (display only)")
    agent_count: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Number of response strategies explored in parallel (one KB branch each)",
    )
    max_events: int = Field(
        default=6, ge=1, le=60, description="Number of grounded events to plan from the knowledge base"
    )
    seed: int | None = None
    kb_category_ids: list[str] = Field(
        default_factory=list,
        description="LightRAG workspace / KB category ids the simulation is grounded in",
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
    evidence: list[str] = Field(
        default_factory=list, description="Knowledge-base facts this event was derived from"
    )
    is_black_swan: bool = Field(
        default=False, description="Rare, high-impact shock injected into long timelines"
    )


class UserEventInput(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    category: EventCategory = EventCategory.MARKET
    impact: float = Field(default=0.0, ge=-1.0, le=1.0)
    severity: float = Field(default=0.6, ge=0.1, le=1.0)


class KnowledgeGraphData(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class GoalStatus(BaseModel):
    """Distance to the simulation goal after a decision step."""

    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall goal completion ratio")
    distance: float = Field(default=1.0, ge=0.0, le=1.0, description="1 - progress")
    metric_progress: dict[str, float] = Field(default_factory=dict)
    metric_gaps: dict[str, float] = Field(default_factory=dict, description="Remaining amount per metric")


class BranchProfile(BaseModel):
    """A parallel world: one response strategy line with its own KB copy."""

    branch_id: str
    label: str = ""
    index: int = 0
    rationality: Rationality = Rationality.RATIONAL
    persona: str = Field(default="", description="Short description of how this branch decides")
    workspaces: list[str] = Field(
        default_factory=list, description="Branch-owned LightRAG workspaces (copies of the source KBs)"
    )
    primary_workspace: str = Field(
        default="", description="Workspace that receives the evolving state snapshot"
    )
    read_only_workspaces: list[str] = Field(
        default_factory=list,
        description="Shared source workspaces read directly when forking was skipped",
    )


class StrategyOption(BaseModel):
    """One branch's response to one event."""

    branch_id: str
    title: str = ""
    action_label: str = Field(default="", description="Short chip label shown in the UI")
    detail: str = ""
    rationale: str = ""
    rationality: Rationality = Rationality.RATIONAL


class MetricReading(BaseModel):
    name: str
    value: float = 0.0
    previous: float = 0.0
    unit: str = ""
    reason: str = ""


class BranchStateUpdate(BaseModel):
    """Predicted state of one branch after applying a strategy to an event."""

    branch_id: str
    narrative: str = ""
    metrics: list[MetricReading] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    success: bool = True
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class StateTraceEntry(BaseModel):
    """Full record of one (event, branch) step: what happened, what was done, what followed."""

    event_index: int
    event_id: str = ""
    branch_id: str
    strategy: StrategyOption
    state: BranchStateUpdate


class BranchSummary(BaseModel):
    branch_id: str
    label: str = ""
    rationality: Rationality = Rationality.RATIONAL
    persona: str = ""
    rank: int = 0
    final_progress: float = 0.0
    final_metrics: dict[str, float] = Field(default_factory=dict)
    final_narrative: str = ""
    workspaces: list[str] = Field(default_factory=list)


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


class WorldBackground(BaseModel):
    summary: str = ""
    community_summaries: list[str] = Field(default_factory=list)
    entity_reports: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    graph_source: str = "lightrag"
    research_provider: str = "knowledge_base"
    research_report: str = Field(default="", description="Intake notes for the run")
    research_citations: list[ResearchCitation] = Field(default_factory=list)


class DecisionStep(BaseModel):
    event_index: int
    trigger_event_id: str = ""
    world_summary: str = ""
    events: list[str] = Field(default_factory=list)
    action: str = ""
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True
    action_summary: dict[str, Any] = Field(default_factory=dict)
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class AgentDecisionPath(BaseModel):
    agent_id: str
    rank: int = 0
    total_score: float = 0.0
    label: str = ""
    rationality: Rationality = Rationality.RATIONAL
    steps: list[DecisionStep] = Field(default_factory=list)


class EventAgentDecision(BaseModel):
    agent_id: str
    rank: int = 0
    action: str = ""
    decision: str = ""
    reasoning: str = ""
    outcome: str = ""
    success: bool = True
    label: str = ""
    rationality: Rationality = Rationality.RATIONAL
    metrics: list[MetricReading] = Field(default_factory=list)
    action_summary: dict[str, Any] = Field(default_factory=dict)
    goal_status: GoalStatus = Field(default_factory=GoalStatus)


class EventSummary(BaseModel):
    event_type: str
    description: str = ""
    impact: float = 0.0
    is_black_swan: bool = False
    evidence: list[str] = Field(default_factory=list)


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
    principles: list[str] = Field(default_factory=list)
    key_turning_points: list[str] = Field(default_factory=list)
    success_factors: list[str] = Field(default_factory=list)
    failure_avoidance_factors: list[str] = Field(default_factory=list)
    recommended_roadmap: list[str] = Field(default_factory=list)
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


class OutcomeDistribution(BaseModel):
    """Spread of outcomes across the parallel strategy branches."""

    sample_size: int = 0
    success_threshold: float = 0.9
    success_rate: float = 0.0
    near_success_rate: float = 0.0
    goal_progress: MetricBand = Field(default_factory=lambda: MetricBand(metric="goal_progress"))
    metric_bands: list[MetricBand] = Field(default_factory=list)
    disclaimer: str = (
        "本结果由知识库检索增强生成的推演产生，展示的是多条平行策略路径的分布区间，"
        "而非精确预测。请将其作为情景探索而非确定性建议。"
    )


class SimulationResult(BaseModel):
    simulation_id: str
    domain_id: str = "startup"
    agent_count: int = 0
    events_simulated: int = 0
    ontology: OntologyGraph = Field(default_factory=OntologyGraph)
    knowledge_graph: KnowledgeGraphData = Field(default_factory=KnowledgeGraphData)
    champion_agent_id: str = ""
    agent_paths: list[AgentDecisionPath] = Field(default_factory=list)
    event_comparisons: list[EventComparison] = Field(default_factory=list)
    planned_events: list[Event] = Field(default_factory=list)
    world_background: WorldBackground = Field(default_factory=WorldBackground)
    counterfactuals: list[CounterfactualComparison] = Field(default_factory=list)
    synthesis: StrategySynthesis = Field(default_factory=StrategySynthesis)
    outcome_distribution: OutcomeDistribution = Field(default_factory=OutcomeDistribution)
    branches: list[BranchSummary] = Field(default_factory=list)
    metric_specs: list[MetricSpec] = Field(default_factory=list)
    state_trace: list[StateTraceEntry] = Field(default_factory=list)


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
