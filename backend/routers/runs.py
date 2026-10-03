"""/runs endpoints: list, detail, integrity, per-step state, ingest."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from blackbox_sdk.schema import CheckpointRecord, RunRecord
from ml.features import step_features

from ..db import get_engine, get_session
from ..models import Run
from ..services import integrity, replay_service
from ..services.diagnosis_service import cached
from ..store import load_run, run_dict, save_run

router = APIRouter(tags=["runs"])

SUMMARY_FIELDS = ["id", "task_family", "task_id", "seed", "policy", "status", "outcome_detail",
                  "split", "parent_run_id", "fork_step_idx", "fault_type", "fault_step",
                  "n_steps", "steps_reused", "steps_rerun", "tokens_total", "latency_total_ms",
                  "created_at"]


def summary(run: Run) -> dict:
    d = run_dict(run)
    return {k: d.get(k) for k in SUMMARY_FIELDS}


@router.get("/runs")
def list_runs(status: Optional[str] = None, family: Optional[str] = None,
              split: Optional[str] = None, fault_type: Optional[str] = None,
              policy: Optional[str] = None, forks: Optional[bool] = None,
              q: Optional[str] = None, limit: int = Query(50, ge=1, le=500),
              offset: int = Query(0, ge=0), session: Session = Depends(get_session)) -> dict:
    stmt = select(Run)
    count = select(func.count()).select_from(Run)
    conds = []
    if status:
        conds.append(Run.status == status)
    if family:
        conds.append(Run.task_family == family)
    if split:
        conds.append(Run.split == split)
    if fault_type:
        conds.append(Run.fault_type == (None if fault_type == "none" else fault_type))
    if policy:
        conds.append(Run.policy == policy)
    if forks is not None:
        conds.append(Run.parent_run_id.is_not(None) if forks else Run.parent_run_id.is_(None))
    if q:
        conds.append(or_(Run.id.startswith(q), Run.task_text.contains(q),
                         Run.outcome_detail.contains(q)))
    for c in conds:
        stmt = stmt.where(c)
        count = count.where(c)
    rows = session.exec(stmt.order_by(Run.created_at.desc()).offset(offset).limit(limit)).all()
    total = session.exec(count).one()
    return {"items": [summary(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def graph_edges(run: dict) -> list[dict]:
    steps = sorted(run["steps"], key=lambda s: s["idx"])
    edges = [{"source": s["parent_idx"], "target": s["idx"], "kind": "seq"}
             for s in steps if s.get("parent_idx") is not None]
    if run["status"] != "running" and steps:
        seen = set()
        for s, row in zip(steps, step_features(run)):
            for j in row["details"].get("used_by", [])[:4]:
                if j != s["idx"] + 1 and (s["idx"], j) not in seen:
                    seen.add((s["idx"], j))
                    edges.append({"source": s["idx"], "target": j, "kind": "data"})
    return edges


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = load_run(session, run_id)
    if run is None:
        raise HTTPException(404, f"run {run_id} not found")
    run["edges"] = graph_edges(run)
    run["diagnosis"] = cached(session, run_id) if run["status"] != "running" else None
    children = session.exec(select(Run).where(Run.parent_run_id == run_id)
                            .order_by(Run.created_at.desc()).limit(20)).all()
    run["forks"] = [summary(c) for c in children]
    return run


@router.get("/runs/{run_id}/verify")
def verify_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = load_run(session, run_id)
    if run is None:
        raise HTTPException(404, f"run {run_id} not found")
    return integrity.verify(run)


@router.get("/runs/{run_id}/steps/{idx}/state")
def step_state(run_id: str, idx: int, session: Session = Depends(get_session)) -> dict:
    return replay_service.state_at(session, run_id, idx)


class IngestBody(BaseModel):
    run: dict
    checkpoints: list[dict] = []


@router.post("/ingest")
def ingest(body: IngestBody) -> dict:
    """Receive a run recorded elsewhere with the SDK's HttpSink."""
    run = RunRecord(**body.run)
    cps = {c["id"]: CheckpointRecord(**c) for c in body.checkpoints}
    save_run(get_engine(), run, cps)
    return {"id": run.id, "steps": len(run.steps)}
