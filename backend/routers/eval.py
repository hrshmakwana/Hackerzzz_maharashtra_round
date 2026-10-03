"""/eval, /stats, /meta and /demo endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from agent_sim.faults import FAULT_TYPES, HELDOUT_FAULT_TYPES
from agent_sim.hero import HERO_RUNS
from agent_sim.llm import gemini_available
from agent_sim.tasks import FAMILIES, HELDOUT_FAMILY
from ml.common import ARTIFACTS, load_models, models_available

from ..db import get_session
from ..models import Run

router = APIRouter(tags=["eval"])


def _read(name: str) -> dict | None:
    p = ARTIFACTS / name
    return json.loads(p.read_text()) if p.exists() else None


@router.get("/eval")
def eval_metrics() -> dict:
    metrics = _read("metrics.json")
    if metrics is None:
        raise HTTPException(404, "no metrics yet - run `make eval`")
    info = _read("train_info.json") or {}
    metrics["feature_importance_full"] = info.get("feature_importance", [])
    return metrics


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    def group(col, *conds):
        stmt = select(col, func.count()).select_from(Run)
        for c in conds:
            stmt = stmt.where(c)
        return {str(k): v for k, v in session.exec(stmt.group_by(col)).all()}

    originals = Run.parent_run_id.is_(None)
    total = session.exec(select(func.count()).select_from(Run).where(originals)).one()
    by_status = group(Run.status, originals)
    forks = session.exec(select(Run).where(Run.parent_run_id.is_not(None))).all()
    parent_status = {}
    if forks:
        ids = list({f.parent_run_id for f in forks})
        for pid, st in session.exec(select(Run.id, Run.status).where(Run.id.in_(ids))).all():
            parent_status[pid] = st
    flips = sum(1 for f in forks if f.status == "success" and parent_status.get(f.parent_run_id) == "fail")
    reused = [f.steps_reused / max(1, f.n_steps) for f in forks]
    metrics = _read("metrics.json") or {}
    test = (metrics.get("splits", {}).get("test", {}).get("methods", {}).get("model", {}))
    replay = (metrics.get("replay", {}).get("splits", {}).get("test", {}))
    finished = by_status.get("success", 0) + by_status.get("fail", 0)
    return {
        "runs": total,
        "by_status": by_status,
        "fail_rate": round(by_status.get("fail", 0) / finished, 4) if finished else None,
        "by_family": group(Run.task_family, originals),
        "by_fault_type": group(Run.fault_type, originals, Run.status == "fail"),
        "by_split": group(Run.split, originals),
        "by_policy": group(Run.policy, originals),
        "forks": len(forks),
        "fork_flips": flips,
        "avg_steps_reused": round(sum(reused) / len(reused), 4) if reused else replay.get("avg_reused_frac"),
        "top1_test": test.get("top1"),
        "top3_test": test.get("top3"),
        "dataset_runs": (metrics.get("dataset") or {}).get("runs"),
        "model_version": metrics.get("model_version"),
    }


@router.get("/meta")
def meta() -> dict:
    return {
        "families": FAMILIES,
        "heldout_family": HELDOUT_FAMILY,
        "fault_types": FAULT_TYPES,
        "heldout_fault_types": HELDOUT_FAULT_TYPES,
        "edit_types": ["override_args", "override_output", "override_decision", "swap_document",
                       "patch_prompt"],
        "policies": {"sim": True, "gemini": gemini_available()},
        "model": {"available": models_available(),
                  "version": load_models().version if models_available() else None},
    }


@router.get("/demo")
def demo(session: Session = Depends(get_session)) -> dict:
    out = []
    for hero in HERO_RUNS:
        run = session.get(Run, hero["id"])
        out.append({**{k: hero[k] for k in ("id", "title", "story", "family", "fault")},
                    "available": run is not None,
                    "status": run.status if run else None})
    return {"runs": out}
