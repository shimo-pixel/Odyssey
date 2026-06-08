import pytest

from prds.intake.refine import RefineRequest, refine_user_input
from prds.llm.client import LLMClient


@pytest.mark.asyncio
async def test_refine_user_input_expands_and_structures():
    llm = LLMClient()
    req = RefineRequest(
        background="我想在北京开一家小面馆",
        goal="年底回本并净赚 5 万",
        constraints=["每月追加投入上限 5000 元"],
    )
    proposal = await refine_user_input(llm, req)

    assert proposal.background.strip()
    assert proposal.goal.strip()
    assert proposal.constraints
    assert proposal.risks
    assert proposal.assumptions
    assert proposal.success_metrics


@pytest.mark.asyncio
async def test_refine_falls_back_to_user_text_when_blank():
    llm = LLMClient()
    req = RefineRequest(background="原始现状", goal="原始目标")
    proposal = await refine_user_input(llm, req)
    assert proposal.background
    assert proposal.goal
