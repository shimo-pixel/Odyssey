"""Externalized, tunable simulation parameters.

All previously hard-coded "magic constants" live here so that:
- assumptions are explicit and inspectable by users,
- they can be overridden per simulation via SimulationConfig.param_overrides,
- per-agent strategy diversity can scale them (see apply_agent_diversity).
"""

from pydantic import BaseModel, Field

from prds.models.domain import AgentAttributes


class ParamSpec(BaseModel):
    """Metadata describing a tunable parameter (for UI / transparency)."""

    key: str
    label: str
    value: float
    min: float
    max: float
    group: str = "general"


class StartupParams(BaseModel):
    """Startup / investment rule-engine parameters (all tunable)."""

    monthly_burn_per_head: float = Field(default=2.0, ge=0.1, le=20.0)
    hire_cost_months: float = Field(default=3.0, ge=1.0, le=12.0)
    hire_min_post_runway: float = Field(default=2.0, ge=0.0, le=12.0)
    layoff_severance_months: float = Field(default=2.0, ge=0.0, le=12.0)

    fundraise_base_prob: float = Field(default=0.06, ge=0.0, le=1.0)
    fundraise_climate_weight: float = Field(default=0.22, ge=0.0, le=1.0)
    fundraise_info_weight: float = Field(default=0.12, ge=0.0, le=1.0)
    fundraise_max_prob: float = Field(default=0.42, ge=0.0, le=1.0)
    fundraise_yield_base: float = Field(default=0.45, ge=0.0, le=2.0)
    fundraise_yield_climate: float = Field(default=0.35, ge=0.0, le=2.0)

    product_dev_efficiency: float = Field(default=0.01, ge=0.0, le=0.2)
    marketing_efficiency: float = Field(default=0.006, ge=0.0, le=0.2)
    marketing_min_maturity: float = Field(default=0.12, ge=0.0, le=1.0)

    revenue_per_user: float = Field(default=0.00035, ge=0.0, le=0.01)
    organic_growth_weight: float = Field(default=0.25, ge=0.0, le=2.0)

    acquisition_success_prob: float = Field(default=0.55, ge=0.0, le=1.0)
    acquisition_min_maturity: float = Field(default=0.35, ge=0.0, le=1.0)
    acquisition_min_runway: float = Field(default=4.0, ge=0.0, le=24.0)

    _LABELS = {
        "monthly_burn_per_head": ("每人月度消耗", "经济"),
        "hire_cost_months": ("招聘前置成本(月)", "经济"),
        "hire_min_post_runway": ("招聘后最低 runway(月)", "约束"),
        "layoff_severance_months": ("裁员遣散(月)", "经济"),
        "fundraise_base_prob": ("融资基础成功率", "融资"),
        "fundraise_climate_weight": ("融资-资本环境权重", "融资"),
        "fundraise_info_weight": ("融资-信息质量权重", "融资"),
        "fundraise_max_prob": ("融资成功率上限", "融资"),
        "fundraise_yield_base": ("融资到账基数", "融资"),
        "fundraise_yield_climate": ("融资到账-环境权重", "融资"),
        "product_dev_efficiency": ("产品研发效率", "产品"),
        "marketing_efficiency": ("营销效率", "市场"),
        "marketing_min_maturity": ("营销最低产品成熟度", "市场"),
        "revenue_per_user": ("单用户营收系数", "营收"),
        "organic_growth_weight": ("自然增长权重", "市场"),
        "acquisition_success_prob": ("并购成功率", "资本运作"),
        "acquisition_min_maturity": ("并购最低成熟度", "资本运作"),
        "acquisition_min_runway": ("并购最低 runway(月)", "资本运作"),
    }

    def specs(self) -> list[ParamSpec]:
        return _specs_for(self, self._LABELS)


def _specs_for(model: BaseModel, labels: dict) -> list[ParamSpec]:
    specs: list[ParamSpec] = []
    fields = type(model).model_fields
    for key, value in model.model_dump().items():
        field = fields[key]
        label, group = labels.get(key, (key, "general"))
        lo = _meta_ge(field)
        hi = _meta_le(field)
        specs.append(
            ParamSpec(
                key=key,
                label=label,
                value=float(value),
                min=float(lo if lo is not None else 0.0),
                max=float(hi if hi is not None else (value * 4 or 1.0)),
                group=group,
            )
        )
    return specs


def _meta_ge(field) -> float | None:
    for m in getattr(field, "metadata", []) or []:
        if hasattr(m, "ge"):
            return m.ge
    return None


def _meta_le(field) -> float | None:
    for m in getattr(field, "metadata", []) or []:
        if hasattr(m, "le"):
            return m.le
    return None


def resolve_params(base: BaseModel, overrides: dict | None) -> BaseModel:
    """Apply user overrides onto a base parameter set (ignoring unknown keys)."""
    if not overrides:
        return base.model_copy()
    valid = {k: v for k, v in overrides.items() if k in type(base).model_fields}
    return base.model_copy(update=valid)


def apply_agent_diversity(params: BaseModel, attrs: AgentAttributes) -> BaseModel:
    """Let an agent's traits genuinely reshape rule parameters, not just prompts.

    This is what makes "parallel worlds" actually diverge in the rule engine.
    """
    if isinstance(params, StartupParams):
        risk = attrs.risk_preference  # 0..1
        info = attrs.information_quality
        execu = attrs.execution_power
        return params.model_copy(
            update={
                # Risk-tolerant agents keep less runway buffer before hiring.
                "hire_min_post_runway": _clamp(params.hire_min_post_runway * (1.6 - risk), 0.0, 12.0),
                # High-conviction (risk) agents pitch harder, slightly better odds.
                "fundraise_base_prob": _clamp(params.fundraise_base_prob * (0.7 + risk * 0.8), 0.0, 1.0),
                "fundraise_max_prob": _clamp(params.fundraise_max_prob * (0.85 + risk * 0.4), 0.0, 1.0),
                # Better information => more capital-efficient product/marketing.
                "product_dev_efficiency": params.product_dev_efficiency * (0.7 + info * 0.6),
                "marketing_efficiency": params.marketing_efficiency * (0.7 + info * 0.6),
                # Strong operators close acquisitions more reliably.
                "acquisition_success_prob": _clamp(
                    params.acquisition_success_prob * (0.7 + execu * 0.6), 0.0, 1.0
                ),
            }
        )
    return params.model_copy()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
