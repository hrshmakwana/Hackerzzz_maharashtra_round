"""/compare endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..services import compare_service
from ..store import load_run

router = APIRouter(tags=["compare"])


@router.get("/compare")
def compare(a: str, b: str, session: Session = Depends(get_session)) -> dict:
    ra, rb = load_run(session, a), load_run(session, b)
    if ra is None or rb is None:
        raise HTTPException(404, "run not found")
    if rb.get("parent_run_id") != a and ra.get("parent_run_id") == b:
        ra, rb = rb, ra  # always show the original on the left
    result = compare_service.align(ra, rb)
    result["steps_a"] = ra["steps"]
    result["steps_b"] = rb["steps"]
    return result
