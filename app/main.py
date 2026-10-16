"""Sessions and rate limits are per process. Behind a proxy, start uvicorn with --proxy-headers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import audit, checks, config, metrics, ratelimit, sop
from .sessions import SessionStore

_WEB = Path(__file__).parent.parent / "web"
_STORE = SessionStore(config.SESSION_TTL_S, config.MAX_SESSIONS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.validate()
    yield


app = FastAPI(title="Creator Submission Review Agent", lifespan=lifespan)


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(default="", max_length=2000)


class ChatOut(BaseModel):
    session_id: str
    reply: str
    phase: str
    verified: bool
    memory: dict


def _too_many(detail: str, retry_after: float) -> HTTPException:
    return HTTPException(status_code=429, detail=detail,
                         headers={"Retry-After": str(int(retry_after) + 1)})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_WEB / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "provider": config.LLM_PROVIDER, "model": config.LLM_MODEL,
            "sessions": len(_STORE), "extraction_health": metrics.snapshot()}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, request: Request) -> ChatOut:
    ip = request.client.host if request.client else "unknown"
    try:
        ratelimit.check(f"ip:{ip}", *config.IP_RATE_LIMIT)
        if body.session_id:
            ratelimit.check(f"session:{body.session_id}", *config.SESSION_RATE_LIMIT)
    except ratelimit.RateLimitExceeded as e:
        audit.rate_limited(body.session_id, f"ip:{ip}")
        raise _too_many("Too many requests. Please slow down.", e.retry_after)

    wait = ratelimit.blocked(f"vfail:{ip}", *config.IP_VERIFY_FAIL_LIMIT)
    if wait:
        audit.rate_limited(body.session_id, f"vfail:{ip}")
        raise _too_many("Too many failed identity checks from this address.", wait)

    # Unknown or expired id gets a new session.
    state = _STORE.get(body.session_id) or _STORE.create()

    # One turn at a time per session.
    with state.lock:
        failures_before = state.failed_verifications
        reply = sop.handle_turn(state, body.message)
        for _ in range(state.failed_verifications - failures_before):
            ratelimit.record(f"vfail:{ip}", config.IP_VERIFY_FAIL_LIMIT[1])

        memory = state.client_snapshot()
        if state.verified_creator_id and state.review:
            view = checks.creator_view(state.review)
            memory["review"] = view
        return ChatOut(session_id=state.session_id, reply=reply, phase=state.phase.value,
                       verified=state.verified_creator_id is not None, memory=memory)


@app.post("/reset")
def reset(body: ChatIn) -> dict:
    _STORE.drop(body.session_id)
    return {"ok": True}
