#!/usr/bin/env python3
"""Populate a SQLite database with Odyssey demo / test data.

Usage:
  cd backend
  python scripts/seed_test_db.py
  python scripts/seed_test_db.py --output ./data/odyssey_test.db
  PRDS_DATABASE_URL=sqlite+aiosqlite:///./data/odyssey_test.db python scripts/seed_test_db.py

Then point the backend at it, e.g. in backend/.env:
  PRDS_DATABASE_URL=sqlite+aiosqlite:///./data/odyssey_test.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python scripts/seed_test_db.py` without installing the package.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from prds.config import get_settings
from prds.models.domain import (
    AgentDecisionPath,
    BranchSummary,
    CurrentState,
    DecisionStep,
    EventCategory,
    EventAgentDecision,
    EventComparison,
    EventSummary,
    GoalStatus,
    MetricBand,
    MetricReading,
    MetricSpec,
    OutcomeDistribution,
    Rationality,
    SimulationConfig,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    SimulationStatus,
    StrategySynthesis,
    TargetGoal,
    WorldBackground,
)
from prds.storage.models import AppSetting, ChatMessage, ChatSession, KbCategory, KbDocument, SimulationRun
from prds.storage.repository import SimulationRepository

# Stable ids so docs / manual tests can reference them.
RUN_COMPLETED = "demo-run-completed-001"
RUN_RUNNING = "demo-run-running-002"
CHAT_MATH = "demo-chat-math-001"
CHAT_PLAIN = "demo-chat-plain-002"
KB_MATH = "math_kb"
KB_NOTES = "notes_kb"


def _utc(days_ago: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _completed_input() -> SimulationInput:
    return SimulationInput(
        current_state=CurrentState(
            background="高三学生，数学月考 62 分，目标院校要求数学不低于 78 分。",
            constraints=["每天可用于数学的时间不超过 2 小时", "不能放弃其他科目复习"],
        ),
        goal=TargetGoal(description="把数学稳定提到 78 分以上，并维持到高考"),
        config=SimulationConfig(
            agent_count=4,
            max_events=4,
            seed=42,
            kb_category_ids=[KB_MATH, KB_NOTES],
        ),
    )


def _running_input() -> SimulationInput:
    return SimulationInput(
        current_state=CurrentState(
            background="早期 SaaS 团队，ARR 约 120 万，现金流紧张，需要在 6 个月内验证 PMF。",
        ),
        goal=TargetGoal(description="在预算有限的情况下找到可复制的获客路径"),
        config=SimulationConfig(
            agent_count=3,
            max_events=6,
            seed=7,
            kb_category_ids=[KB_NOTES],
        ),
    )


def _completed_result(run_id: str) -> SimulationResult:
    branches = [
        BranchSummary(
            branch_id="branch_01",
            label="稳扎稳打：错题本 + 专题突破",
            rationality=Rationality.RATIONAL,
            persona="优先补基础，再攻中档题",
            rank=1,
            final_progress=0.86,
            final_metrics={"数学成绩": 79.0, "错题覆盖率": 0.82},
            final_narrative="通过系统化错题复盘，中档题正确率显著提升。",
            workspaces=[f"sim_{run_id[:18]}_b01_{KB_MATH}"],
        ),
        BranchSummary(
            branch_id="branch_02",
            label="题海战术：限时刷卷",
            rationality=Rationality.RATIONAL,
            persona="以量换分，强调速度",
            rank=2,
            final_progress=0.74,
            final_metrics={"数学成绩": 76.0, "错题覆盖率": 0.55},
            final_narrative="题量上去了，但基础漏洞仍在，波动较大。",
            workspaces=[f"sim_{run_id[:18]}_b02_{KB_MATH}"],
        ),
        BranchSummary(
            branch_id="branch_03",
            label="只攻压轴题",
            rationality=Rationality.IRRATIONAL,
            persona="忽视基础，赌难题拉分",
            rank=3,
            final_progress=0.52,
            final_metrics={"数学成绩": 68.0, "错题覆盖率": 0.21},
            final_narrative="难题得分有限，基础题失分反而增加。",
            workspaces=[f"sim_{run_id[:18]}_b03_{KB_MATH}"],
        ),
        BranchSummary(
            branch_id="branch_04",
            label="跟班 + 1v1 混合",
            rationality=Rationality.RATIONAL,
            persona="课内同步，周末专项",
            rank=4,
            final_progress=0.80,
            final_metrics={"数学成绩": 77.5, "错题覆盖率": 0.71},
            final_narrative="节奏稳定，但时间成本较高。",
            workspaces=[f"sim_{run_id[:18]}_b04_{KB_MATH}"],
        ),
    ]

    agent_paths = [
        AgentDecisionPath(
            agent_id=b.branch_id,
            rank=b.rank,
            total_score=b.final_progress,
            label=b.label,
            rationality=b.rationality,
            steps=[
                DecisionStep(
                    event_index=i,
                    trigger_event_id=f"evt_{i:02d}",
                    world_summary=f"第 {i} 轮：模拟考试难度波动",
                    action=b.label.split("：", 1)[0],
                    decision=f"执行策略：{b.label}",
                    reasoning="依据知识库中的学习规律与过往错题分布做调整。",
                    outcome=b.final_narrative if i == 4 else "阶段性指标小幅改善。",
                    success=True,
                    goal_status=GoalStatus(progress=min(1.0, b.final_progress * i / 4)),
                )
                for i in range(1, 5)
            ],
        )
        for b in branches
    ]

    event_comparisons = [
        EventComparison(
            event_index=i,
            event_id=f"evt_{i:02d}",
            event_label=f"事件 {i}",
            world_summary="月考/周测带来压力，需调整复习重心。",
            events=[f"模拟事件 {i}"],
            event_summaries=[
                EventSummary(
                    event_type="exam_pressure",
                    description="阶段性测评暴露薄弱章节",
                    impact=0.2,
                )
            ],
            agents=[
                EventAgentDecision(
                    agent_id=b.branch_id,
                    rank=b.rank,
                    action=b.label.split("：", 1)[0],
                    decision=b.label,
                    reasoning=b.persona,
                    outcome="指标更新",
                    success=True,
                    label=b.label,
                    rationality=b.rationality,
                    metrics=[
                        MetricReading(
                            name="数学成绩",
                            value=62 + i * 4,
                            previous=62 + (i - 1) * 4,
                            unit="分",
                        )
                    ],
                    goal_status=GoalStatus(progress=min(1.0, b.final_progress * i / 4)),
                )
                for b in branches
            ],
        )
        for i in range(1, 5)
    ]

    return SimulationResult(
        simulation_id=run_id,
        agent_count=4,
        events_simulated=4,
        champion_agent_id="branch_01",
        branches=branches,
        agent_paths=agent_paths,
        event_comparisons=event_comparisons,
        metric_specs=[
            MetricSpec(name="数学成绩", unit="分", baseline=62, target=78),
            MetricSpec(name="错题覆盖率", unit="", baseline=0.3, target=0.85),
        ],
        world_background=WorldBackground(
            summary="基于知识库中的学习策略与考试规律生成推演背景。",
            research_report="输入目标：数学 62 → 78；约束：每日 2 小时。",
        ),
        synthesis=StrategySynthesis(
            principles=["先补基础再提速", "错题复盘优先于盲目刷题"],
            recommended_roadmap=[
                "第 1-2 周：梳理知识图谱，建立错题本",
                "第 3-4 周：专题突破中档题",
                "第 5-6 周：限时模拟 + 回归基础",
            ],
        ),
        outcome_distribution=OutcomeDistribution(
            sample_size=4,
            success_rate=0.5,
            near_success_rate=0.75,
            goal_progress=MetricBand(metric="goal_progress", median=0.78, mean=0.73),
        ),
    )


async def seed(output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise SystemExit(f"Refusing to overwrite existing file: {output}\nUse --force to replace it.")

    output.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{output.resolve()}"
    os.environ["PRDS_DATABASE_URL"] = db_url
    get_settings.cache_clear()

    repo = SimulationRepository()
    await repo.init_db()

    now = _utc(0)
    yesterday = _utc(1)
    week_ago = _utc(5)

    async with repo.session_factory() as session:
        # --- Knowledge base metadata (LightRAG workspaces are separate) ---
        session.add_all(
            [
                KbCategory(
                    id=KB_MATH,
                    name="数学学习资料",
                    description="公式、题型与复习策略",
                    created_at=week_ago,
                    updated_at=week_ago,
                ),
                KbCategory(
                    id=KB_NOTES,
                    name="项目笔记",
                    description="SaaS 增长与产品笔记",
                    created_at=week_ago,
                    updated_at=yesterday,
                ),
            ]
        )
        session.add_all(
            [
                KbDocument(
                    id="doc-math-outline",
                    category_id=KB_MATH,
                    filename="math_review_outline.md",
                    status="processed",
                    size=2048,
                    created_at=week_ago,
                    updated_at=week_ago,
                ),
                KbDocument(
                    id="doc-notes-growth",
                    category_id=KB_NOTES,
                    filename="saas_growth_notes.txt",
                    status="processed",
                    size=1024,
                    created_at=yesterday,
                    updated_at=yesterday,
                ),
            ]
        )

        # --- Completed simulation ---
        completed_input = _completed_input()
        completed_result = _completed_result(RUN_COMPLETED)
        session.add(
            SimulationRun(
                id=RUN_COMPLETED,
                status=SimulationStatus.COMPLETED.value,
                phase=SimulationPhase.COMPLETED.value,
                current_event_index=4,
                total_events=4,
                alive_agents=4,
                total_agents=4,
                progress_pct=100.0,
                input_json=completed_input.model_dump_json(),
                result_json=completed_result.model_dump_json(),
                created_at=week_ago,
                updated_at=yesterday,
            )
        )

        # --- In-progress simulation ---
        running_input = _running_input()
        session.add(
            SimulationRun(
                id=RUN_RUNNING,
                status=SimulationStatus.RUNNING.value,
                phase=SimulationPhase.BRANCH_SIM.value,
                current_event_index=2,
                total_events=6,
                alive_agents=3,
                total_agents=3,
                progress_pct=42.0,
                input_json=running_input.model_dump_json(),
                created_at=yesterday,
                updated_at=now,
            )
        )

        # --- Chat sessions ---
        session.add_all(
            [
                ChatSession(
                    id=CHAT_MATH,
                    title="二次函数顶点公式",
                    model_id="demo-model",
                    created_at=yesterday,
                    updated_at=now,
                ),
                ChatSession(
                    id=CHAT_PLAIN,
                    title="Markdown 渲染测试",
                    model_id="demo-model",
                    created_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=2),
                ),
            ]
        )
        session.add_all(
            [
                ChatMessage(
                    id="msg-m1",
                    session_id=CHAT_MATH,
                    role="user",
                    content="请解释二次函数 $y=ax^2+bx+c$ 的顶点坐标公式。",
                    created_at=yesterday,
                ),
                ChatMessage(
                    id="msg-m2",
                    session_id=CHAT_MATH,
                    role="assistant",
                    content=(
                        "二次函数顶点坐标为：\n\n"
                        "$$\\left(-\\frac{b}{2a},\\; \\frac{4ac-b^2}{4a}\\right)$$\n\n"
                        "**推导思路**\n"
                        "1. 配方：$y=a\\left(x+\\frac{b}{2a}\\right)^2+\\frac{4ac-b^2}{4a}$\n"
                        "2. 当 $x=-\\frac{b}{2a}$ 时取得最值。"
                    ),
                    model="demo-model/gpt-4o-mini",
                    created_at=now,
                ),
                ChatMessage(
                    id="msg-p1",
                    session_id=CHAT_PLAIN,
                    role="user",
                    content="用 Markdown 列三个学习建议",
                    created_at=now - timedelta(hours=3),
                ),
                ChatMessage(
                    id="msg-p2",
                    session_id=CHAT_PLAIN,
                    role="assistant",
                    content=(
                        "## 学习建议\n\n"
                        "- **固定时段**：每天同一时间复习 45 分钟\n"
                        "- **错题优先**：先复盘再刷新题\n"
                        "- **周测反馈**：每周做一次限时小测\n\n"
                        "> 坚持比单次强度更重要。"
                    ),
                    model="demo-model/gpt-4o-mini",
                    created_at=now - timedelta(hours=2),
                ),
            ]
        )

        # --- Demo LLM model catalog (no real API key) ---
        session.add(
            AppSetting(
                key="llm_models",
                value_json=json.dumps(
                    {
                        "models": [
                            {
                                "id": "demo-model",
                                "name": "Demo Model",
                                "provider": "openai",
                                "model": "gpt-4o-mini",
                                "api_base": "",
                                "model_analysis": "gpt-4o-mini",
                                "api_key": "sk-demo-not-real",
                                "created_at": now.isoformat(),
                            }
                        ],
                        "default_model_id": "demo-model",
                    },
                    ensure_ascii=False,
                ),
                updated_at=now,
            )
        )

        await session.commit()

    await repo.engine.dispose()

    print(f"Test database written: {output.resolve()}")
    print()
    print("Sample ids:")
    print(f"  completed simulation : {RUN_COMPLETED}")
    print(f"  running simulation   : {RUN_RUNNING}")
    print(f"  chat (math)          : {CHAT_MATH}")
    print(f"  chat (markdown)      : {CHAT_PLAIN}")
    print(f"  kb categories        : {KB_MATH}, {KB_NOTES}")
    print()
    print("Use it with:")
    print(f"  PRDS_DATABASE_URL=sqlite+aiosqlite:///{output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Odyssey test SQLite database")
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_ROOT / "data" / "odyssey_test.db",
        help="Output SQLite file path (default: backend/data/odyssey_test.db)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing database file",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.output, args.force))


if __name__ == "__main__":
    main()
