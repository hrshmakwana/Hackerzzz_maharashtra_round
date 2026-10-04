"""/eval, /stats, /meta and /demo endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from agent_sim.faults import FAULT_TYPES, HELDOUT_FAULT_TYPES
from agent_sim.hero import HERO_RUNS
from agent_sim.llm import MAKERS, gemini_available, model_label, reviewers
from agent_sim.tasks import FAMILIES, HELDOUT_FAMILY
from agent_sim.world import POLICY_DOCS
from ml.common import ARTIFACTS, load_models, models_available

from ..db import get_session
from ..models import AIReview, Diagnosis, Run

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
        "reviewers": [{"name": n, "model": c.model} for n, c in reviewers()],
        "model": {"available": models_available(),
                  "version": load_models().version if models_available() else None},
        "documents": [{k: d[k] for k in ("doc_id", "title", "topic", "version", "status")}
                      for d in POLICY_DOCS],
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


BASIS = (
    "Every test run has one step we broke on purpose, so the right answer is known in advance. "
    "A method is counted correct only if its first pick is exactly that step. When a run is "
    "fixed in the app, replaying it confirms the answer: fixing the right step makes the run succeed."
)


@router.get("/leaderboard")
def leaderboard(session: Session = Depends(get_session)) -> dict:
    """Accuracy of our model and each AI: fixed benchmark plus every run tested in the app."""
    metrics = _read("metrics.json") or {}
    test = (metrics.get("splits", {}).get("test", {}) or {}).get("methods", {})
    judge_models = metrics.get("judge_models") or {}

    truth = {r.id: r.fault_step for r in session.exec(
        select(Run).where(Run.fault_step.is_not(None), Run.parent_run_id.is_(None))).all()}

    # our model: latest diagnosis per run with a known answer
    ours = {}
    for d in session.exec(select(Diagnosis).order_by(Diagnosis.id)).all():
        if d.run_id in truth and isinstance(d.ranking, dict):
            ours[d.run_id] = d.ranking.get("canon_event", {}).get("idx") == truth[d.run_id]
    live = {"Black Box": [sum(ours.values()), len(ours)]}
    for rv in session.exec(select(AIReview)).all():
        if rv.run_id in truth:
            c = live.setdefault(rv.reviewer, [0, 0])
            c[0] += int(rv.step == truth[rv.run_id])
            c[1] += 1

    rows = [{"key": "model", "name": "Black Box", "maker": "Our trained model"}]
    for key in ("llm_judge", "llm_judge2", "llm_judge3"):
        if judge_models.get(key):
            name = model_label(judge_models[key])
            rows.append({"key": key, "name": name, "maker": MAKERS.get(name, "")})
    for r in rows:
        b = test.get(r["key"], {})
        r["benchmark"] = {"top1": b.get("top1"), "n": b.get("n")} if b.get("n") else None
        c, t = live.get(r["name"], [0, 0])
        r["live"] = {"correct": c, "total": t, "rate": round(c / t, 4) if t else None}
    return {"basis": BASIS, "methods": rows}
