"""/replay endpoints: fork, replay-from-here, suggested fix, auto-fix, multiverse sweep."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..services import replay_service

router = APIRouter(tags=["replay"])


class ForkBody(BaseModel):
    step: int = Field(ge=0)
    edits: list[dict] = []


@router.post("/runs/{run_id}/fork")
def fork(run_id: str, body: ForkBody, session: Session = Depends(get_session)) -> dict:
    return replay_service.fork(session, run_id, body.step, body.edits)


@router.post("/runs/{run_id}/replay")
def replay(run_id: str, step: int = Query(ge=0), session: Session = Depends(get_session)) -> dict:
    return replay_service.replay_from(session, run_id, step)


@router.get("/runs/{run_id}/fix")
def suggest_fix(run_id: str, step: int = Query(ge=0),
                session: Session = Depends(get_session)) -> dict:
    fix = replay_service.suggest(session, run_id, step)
    return {"step": step, "fix": fix}


@router.post("/runs/{run_id}/autofix")
def autofix(run_id: str, step: Optional[int] = Query(None, ge=0),
            session: Session = Depends(get_session)) -> dict:
    return replay_service.autofix(session, run_id, step)


@router.post("/runs/{run_id}/sweep")
def sweep(run_id: str, top_k: int = Query(3, ge=1, le=8),
          session: Session = Depends(get_session)) -> dict:
    return replay_service.sweep(session, run_id, top_k)
