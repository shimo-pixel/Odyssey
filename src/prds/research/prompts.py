"""Prompts for industry background research (step ②)."""


def build_research_query(background: str, goal: str, constraints: list[str], domain_id: str) -> str:
    parts = [
        "为下述决策情景撰写一份「行业/领域背景研究报告」，用于驱动一个多智能体平行推演系统。",
        "",
        f"【领域】{domain_id}",
        f"【当前现状】\n{background}",
        f"【最终目标】\n{goal}",
    ]
    if constraints:
        parts.append("【环境约束】\n" + "\n".join(f"- {c}" for c in constraints))
    parts.extend(
        [
            "",
            "报告需覆盖：",
            "1. 行业结构与关键参与者（上下游、竞争者、监管/平台方）；",
            "2. 该领域真实的成本结构、单位经济与典型经营节奏；",
            "3. 常见的、高概率发生的外部事件与周期性波动（不是罕见黑天鹅，而是该领域大概率会遇到的事件）；",
            "4. 该领域内成熟从业者通常如何决策、常见的成功/失败模式；",
            "5. 与目标相关的关键风险、机会与可量化基准（典型转化率、毛利、获客成本、达标周期等）。",
            "尽量给出具体数字区间与现实依据，避免空泛乐观。使用与输入相同的语言（中文输入则用中文）。",
        ]
    )
    return "\n".join(parts)


FALLBACK_SYSTEM = """You are a domain research analyst. Without live web access, write a
realistic, concrete industry background report for the given decision scenario, drawing on
general domain knowledge. Be specific with typical cost structures, unit economics, common
high-probability events, and how experienced practitioners actually decide. Avoid optimism bias.
Use the same language as the input. Return JSON only with keys:
{
  "report": "full markdown report",
  "key_findings": ["concise finding", ...]
}"""


GROUNDED_SYSTEM = """You are a domain research analyst with web search grounding.
Research the scenario's industry and write a concrete, cited background report covering industry
structure, real cost/unit economics, common high-probability events, typical practitioner
decision patterns, and quantified benchmarks/risks/opportunities. Avoid optimism bias.
Use the same language as the input."""
