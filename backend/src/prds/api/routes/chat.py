"""Direct LLM chat / quick-answer API with session history."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from prds.kb.settings_store import get_model_entry, settings_from_model_entry
from prds.llm.model_config import configure_litellm, normalize_litellm_model
from prds.storage.repository import SimulationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

ANSWER_MAX_TOKENS = 8192

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question clearly and accurately. "
    "Use the full context the user provides; do not ask them to shorten long inputs. "
    "Format answers in GitHub-flavored Markdown (headings, lists, tables, bold/italic, "
    "fenced code blocks when showing code). "
    "When your answer includes mathematical formulas, write them in MathType-compatible LaTeX: "
    "use $...$ for inline formulas and $$...$$ for display (block) formulas. "
    "Use standard LaTeX math commands (e.g. \\frac, \\sqrt, \\sum, \\int). "
    "Do not put formulas inside markdown code fences or show raw TeX as plain code — "
    "the chat UI renders Markdown and these math delimiters as formatted content."
)

_repo: SimulationRepository | None = None


def get_repo() -> SimulationRepository:
    global _repo
    if _repo is None:
        _repo = SimulationRepository()
    return _repo


class ChatMessagePublic(BaseModel):
    id: str
    role: str
    content: str
    model: str | None = None
    created_at: str | None = None


class ChatSessionSummary(BaseModel):
    id: str
    title: str = ""
    model_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int = 0


class ChatSessionDetail(BaseModel):
    id: str
    title: str = ""
    model_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    messages: list[ChatMessagePublic] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    title: str = ""
    model_id: str | None = None


class ChatAnswerRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model_id: str | None = None
    session_id: str | None = None


class ChatAnswerResponse(BaseModel):
    answer: str
    model: str
    model_id: str | None = None
    session_id: str


def _session_summary(session, message_count: int = 0) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=session.id,
        title=session.title or "",
        model_id=session.model_id,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        message_count=message_count,
    )


def _message_public(msg) -> ChatMessagePublic:
    return ChatMessagePublic(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        model=msg.model,
        created_at=msg.created_at.isoformat() if msg.created_at else None,
    )


@router.get("/sessions", response_model=dict)
async def list_chat_sessions(limit: int = Query(50, ge=1, le=200)) -> dict:
    repo = get_repo()
    sessions = await repo.list_chat_sessions(limit=limit)
    items = []
    for s in sessions:
        msgs = await repo.list_chat_messages(s.id)
        items.append(_session_summary(s, len(msgs)).model_dump())
    return {"sessions": items}


@router.post("/sessions", response_model=ChatSessionDetail)
async def create_chat_session(payload: ChatSessionCreate) -> ChatSessionDetail:
    repo = get_repo()
    session = await repo.create_chat_session(
        title=payload.title,
        model_id=payload.model_id,
    )
    return ChatSessionDetail(
        id=session.id,
        title=session.title or "",
        model_id=session.model_id,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        messages=[],
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_chat_session(session_id: str) -> ChatSessionDetail:
    repo = get_repo()
    session = await repo.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    msgs = await repo.list_chat_messages(session_id)
    return ChatSessionDetail(
        id=session.id,
        title=session.title or "",
        model_id=session.model_id,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        messages=[_message_public(m) for m in msgs],
    )


@router.delete("/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> dict:
    repo = get_repo()
    deleted = await repo.delete_chat_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"session_id": session_id, "deleted": True}


class _PreparedChatTurn:
    __slots__ = (
        "repo",
        "session_id",
        "model_name",
        "model_id",
        "llm_kwargs",
    )

    def __init__(
        self,
        *,
        repo: SimulationRepository,
        session_id: str,
        model_name: str,
        model_id: str | None,
        llm_kwargs: dict[str, Any],
    ) -> None:
        self.repo = repo
        self.session_id = session_id
        self.model_name = model_name
        self.model_id = model_id
        self.llm_kwargs = llm_kwargs


def _answer_text(message: Any) -> str:
    content = getattr(message, "content", None) or ""
    return str(content)


async def _prepare_chat_turn(payload: ChatAnswerRequest) -> _PreparedChatTurn:
    message = payload.message
    if not message.strip():
        raise HTTPException(status_code=422, detail="message required")

    repo = get_repo()
    session_id = (payload.session_id or "").strip() or None
    session = await repo.get_chat_session(session_id) if session_id else None
    if session_id and not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    model_id = payload.model_id or (session.model_id if session else None)
    entry = await get_model_entry(model_id)
    if entry is None or not (entry.get("api_key") and entry.get("model")):
        raise HTTPException(
            status_code=400,
            detail="No LLM model configured. Add a model in Settings.",
        )

    if not session:
        session = await repo.create_chat_session(
            title=message.strip()[:256],
            model_id=str(entry.get("id") or "") or model_id,
        )
        session_id = session.id

    prior = await repo.list_chat_messages(session_id)
    await repo.append_chat_message(session_id, role="user", content=message)

    settings = settings_from_model_entry(entry)
    configure_litellm(settings)
    model = normalize_litellm_model(entry["model"], settings)

    llm_messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in prior:
        if msg.role in ("user", "assistant"):
            llm_messages.append({"role": msg.role, "content": msg.content})
    llm_messages.append({"role": "user", "content": message})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": llm_messages,
        "max_tokens": ANSWER_MAX_TOKENS,
        "api_key": entry.get("api_key") or None,
    }
    api_base = (entry.get("api_base") or "").strip()
    if api_base:
        kwargs["api_base"] = api_base.rstrip("/")

    model_name = str(entry.get("model") or model)
    return _PreparedChatTurn(
        repo=repo,
        session_id=session_id,
        model_name=model_name,
        model_id=str(entry.get("id") or "") or None,
        llm_kwargs=kwargs,
    )


def _ndjson_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


@router.post("/answer", response_model=ChatAnswerResponse)
async def chat_answer(payload: ChatAnswerRequest) -> ChatAnswerResponse:
    prepared = await _prepare_chat_turn(payload)
    try:
        response = await litellm.acompletion(**prepared.llm_kwargs)
        choice = response.choices[0]
        content = _answer_text(choice.message)
        if not content.strip():
            raise HTTPException(status_code=502, detail="LLM returned empty content")
        await prepared.repo.append_chat_message(
            prepared.session_id,
            role="assistant",
            content=content,
            model=prepared.model_name,
        )
        return ChatAnswerResponse(
            answer=content,
            model=prepared.model_name,
            model_id=prepared.model_id,
            session_id=prepared.session_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("chat/answer failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc


@router.post("/answer/stream")
async def chat_answer_stream(payload: ChatAnswerRequest) -> StreamingResponse:
    prepared = await _prepare_chat_turn(payload)

    async def generate() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        yield _ndjson_line(
            {
                "type": "meta",
                "session_id": prepared.session_id,
                "model": prepared.model_name,
                "model_id": prepared.model_id,
            }
        )
        try:
            stream = await litellm.acompletion(**prepared.llm_kwargs, stream=True)
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                content = _answer_text(delta)
                if not content:
                    continue
                answer_parts.append(content)
                yield _ndjson_line({"type": "delta", "content": content})

            answer = "".join(answer_parts).strip()
            if not answer:
                yield _ndjson_line({"type": "error", "detail": "LLM returned empty content"})
                return

            await prepared.repo.append_chat_message(
                prepared.session_id,
                role="assistant",
                content=answer,
                model=prepared.model_name,
            )
            yield _ndjson_line(
                {
                    "type": "done",
                    "answer": answer,
                    "model": prepared.model_name,
                    "model_id": prepared.model_id,
                    "session_id": prepared.session_id,
                }
            )
        except Exception as exc:
            logger.exception("chat/answer/stream failed")
            yield _ndjson_line({"type": "error", "detail": f"LLM request failed: {exc}"})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-ndjson",
            "X-Accel-Buffering": "no",
        },
    )
