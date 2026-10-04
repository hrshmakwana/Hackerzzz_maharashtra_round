"""/diagnose endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..services import diagnosis_service, review_service

router = APIRouter(tags=["diagnose"])


@router.post("/runs/{run_id}/diagnose")
def diagnose(run_id: str, report: bool = False, refresh: bool = False,
             session: Session = Depends(get_session)) -> dict:
    return diagnosis_service.diagnose(session, run_id, with_report=report, refresh=refresh)


@router.get("/runs/{run_id}/diagnosis")
def get_diagnosis(run_id: str, session: Session = Depends(get_session)) -> dict:
    hit = diagnosis_service.cached(session, run_id)
    if hit is None:
        raise HTTPException(404, "not diagnosed yet")
    return hit


@router.post("/runs/{run_id}/review")
def review(run_id: str, session: Session = Depends(get_session)) -> dict:
    """Ask independent AIs whether they agree with the diagnosis."""
    return review_service.review(session, run_id)
