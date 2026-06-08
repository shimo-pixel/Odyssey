"""Step ②: produce an industry/domain background report.

Pluggable providers, chosen by config + key availability:
- deep_research : Gemini Deep Research agent (async Interactions API, polled)
- grounded      : Gemini generateContent with Google Search grounding
- fallback      : in-house LLM writes a report from domain knowledge (no web)
- off           : skip research entirely

Any provider failure degrades gracefully to the fallback, so the pipeline never
hard-fails on a missing/expired key or transient network error.
"""

import asyncio
import json
import logging

import httpx
from pydantic import BaseModel

from prds.config import Settings, get_settings
from prds.llm.client import LLMClient
from prds.models.domain import BackgroundReport, ResearchCitation
from prds.research.prompts import (
    FALLBACK_SYSTEM,
    GROUNDED_SYSTEM,
    build_research_query,
)

logger = logging.getLogger(__name__)

_GENAI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class _FallbackReport(BaseModel):
    report: str = ""
    key_findings: list[str] = []


async def generate_background_report(
    llm: LLMClient,
    *,
    background: str,
    goal: str,
    constraints: list[str],
    domain_id: str = "startup",
    settings: Settings | None = None,
) -> BackgroundReport:
    settings = settings or get_settings()
    provider = settings.resolved_research_provider()
    query = build_research_query(background, goal, constraints, domain_id)

    if provider == "off":
        return BackgroundReport(query=query, provider="off")

    try:
        if provider == "deep_research":
            return await _deep_research(settings, llm, query)
        if provider == "grounded":
            return await _grounded(settings, llm, query)
    except Exception as exc:
        logger.warning("Research provider '%s' failed, falling back: %s", provider, exc)

    return await _fallback(llm, query)


async def _fallback(llm: LLMClient, query: str) -> BackgroundReport:
    result = await llm.structured_complete(
        FALLBACK_SYSTEM, query, _FallbackReport, model=llm.analysis_model
    )
    return BackgroundReport(
        query=query,
        report=result.report,
        key_findings=result.key_findings,
        provider="fallback",
        model=llm.analysis_model,
        grounded=False,
    )


async def _extract_findings(llm: LLMClient, report: str) -> list[str]:
    if not report.strip():
        return []
    try:
        class _F(BaseModel):
            key_findings: list[str] = []

        out = await llm.structured_complete(
            "Extract 3-6 concise key findings from the report. Same language as the report. JSON only.",
            report[:6000],
            _F,
            model=llm.analysis_model,
        )
        return out.key_findings
    except Exception as exc:
        logger.debug("Key-finding extraction failed: %s", exc)
        return []


async def _grounded(settings: Settings, llm: LLMClient, query: str) -> BackgroundReport:
    model = settings.prds_research_grounded_model
    url = f"{_GENAI_BASE}/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": GROUNDED_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    async with httpx.AsyncClient(timeout=settings.prds_research_timeout_s) as client:
        resp = await client.post(
            url, headers={"x-goog-api-key": settings.gemini_api_key}, json=body
        )
        resp.raise_for_status()
        data = resp.json()

    report, citations = _parse_genai_candidate(data)
    if not report.strip():
        raise ValueError("Grounded Gemini returned empty report")
    return BackgroundReport(
        query=query,
        report=report,
        key_findings=await _extract_findings(llm, report),
        citations=citations,
        provider="grounded",
        model=model,
        grounded=True,
    )


async def _deep_research(settings: Settings, llm: LLMClient, query: str) -> BackgroundReport:
    model = settings.prds_research_model
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Api-Revision": "2026-05-20",
        "Content-Type": "application/json",
    }
    create_body = {
        "agent": model,
        "input": query,
        "tools": [{"type": "google_search"}],
        "background": True,
        "store": True,
    }
    async with httpx.AsyncClient(timeout=settings.prds_research_timeout_s) as client:
        resp = await client.post(f"{_GENAI_BASE}/interactions", headers=headers, json=create_body)
        resp.raise_for_status()
        created = resp.json()
        interaction_id = created.get("id") or created.get("name")
        if not interaction_id:
            raise ValueError(f"Deep Research create returned no id: {created}")

        deadline = settings.prds_research_timeout_s
        waited = 0
        poll = max(2, settings.prds_research_poll_interval_s)
        while waited < deadline:
            await asyncio.sleep(poll)
            waited += poll
            g = await client.get(f"{_GENAI_BASE}/interactions/{interaction_id}", headers=headers)
            g.raise_for_status()
            interaction = g.json()
            status = interaction.get("status")
            if status == "completed":
                report = interaction.get("output_text") or _join_output(interaction)
                citations = _parse_interaction_citations(interaction)
                if not report.strip():
                    raise ValueError("Deep Research completed with empty output")
                return BackgroundReport(
                    query=query,
                    report=report,
                    key_findings=await _extract_findings(llm, report),
                    citations=citations,
                    provider="deep_research",
                    model=model,
                    grounded=True,
                )
            if status == "failed":
                raise ValueError(f"Deep Research failed: {interaction.get('error')}")

    raise TimeoutError("Deep Research timed out")


def _parse_genai_candidate(data: dict) -> tuple[str, list[ResearchCitation]]:
    candidates = data.get("candidates") or []
    if not candidates:
        return "", []
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "\n".join(p.get("text", "") for p in parts if p.get("text"))

    citations: list[ResearchCitation] = []
    grounding = candidate.get("groundingMetadata") or {}
    for chunk in grounding.get("groundingChunks") or []:
        web = chunk.get("web") or {}
        if web.get("uri"):
            citations.append(ResearchCitation(title=web.get("title", ""), url=web["uri"]))
    return text, citations


def _join_output(interaction: dict) -> str:
    output = interaction.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        texts = []
        for item in output:
            if isinstance(item, dict):
                texts.append(item.get("text") or json.dumps(item, ensure_ascii=False))
            else:
                texts.append(str(item))
        return "\n".join(texts)
    return ""


def _parse_interaction_citations(interaction: dict) -> list[ResearchCitation]:
    citations: list[ResearchCitation] = []
    for c in interaction.get("citations") or []:
        if isinstance(c, dict) and (c.get("url") or c.get("uri")):
            citations.append(
                ResearchCitation(title=c.get("title", ""), url=c.get("url") or c.get("uri"))
            )
    return citations
