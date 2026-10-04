"""Fork a run from a checkpoint, apply edits, re-run the suffix; auto-fix and sweep."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session

from agent_sim.repair import propose_fix
from agent_sim.replay import fork_run, savings
from blackbox_sdk import Edit
from blackbox_sdk.recorder import SQLiteSink
from ml.features import step_features

from ..db import get_engine
from ..models import ForkJob
from ..store import load_checkpoint, load_run
from .diagnosis_service import diagnose, require_run


def _loader(session: Session):
    return lambda cid: load_checkpoint(session, cid)


def _summary(parent: dict, child: dict) -> dict:
    return {
        "id": child["id"],
        "parent_run_id": parent["id"],
        "fork_step_idx": child.get("fork_step_idx"),
        "status": child["status"],
        "outcome_detail": child.get("outcome_detail"),
        "final_answer": child.get("final_answer"),
        "parent_status": parent["status"],
        "flipped": parent["status"] == "fail" and child["status"] == "success",
        "savings": savings(parent, child),
        "edits": child.get("edits"),
    }


def fork(session: Session, run_id: str, step: int, edits: Optional[list] = None,
         kind: str = "fork") -> dict:
    parent = require_run(session, run_id)
    if not 0 <= step < len(parent["steps"]):
        raise HTTPException(422, f"step must be between 0 and {len(parent['steps']) - 1}")
    if parent.get("policy") != "sim":
        raise HTTPException(422, "forking live Gemini runs is not supported yet")
    try:
        edit_objs = [e if isinstance(e, Edit) else Edit(**e) for e in (edits or [])]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid edit: {exc}") from exc
    try:
        out = fork_run(parent, step, edit_objs, load_checkpoint=_loader(session),
                       sink=SQLiteSink(), run_id=uuid.uuid4().hex)
    except LookupError as exc:
        raise HTTPException(422, str(exc)) from exc
    child = out.record.model_dump(mode="json")
    summary = _summary(parent, child)
    session.add(ForkJob(parent_run_id=run_id, kind=kind,
                        request={"step": step, "edits": [e.model_dump(exclude_none=True) for e in edit_objs]},
                        result={k: summary[k] for k in ("id", "status", "flipped")}))
    session.commit()
    return summary


def suggest(session: Session, run_id: str, step: int) -> Optional[dict]:
    run = require_run(session, run_id)
    if not 0 <= step < len(run["steps"]):
        raise HTTPException(422, "step out of range")
    return propose_fix(run, step, step_features(run), load_checkpoint=_loader(session))


def autofix(session: Session, run_id: str, step: Optional[int] = None) -> dict:
    if step is None:
        step = diagnose(session, run_id)["canon_event"]["idx"]
    fix = suggest(session, run_id, step)
    if fix is None:
        raise HTTPException(422, f"no repair found for step {step}: nothing in the trace "
                                 f"points at a concrete problem there")
    result = fork(session, run_id, step, [fix["edit"]], kind="autofix")
    result["fix"] = fix
    return result


def sweep(session: Session, run_id: str, top_k: int = 3) -> dict:
    diag = diagnose(session, run_id)
    run = require_run(session, run_id)
    rows = step_features(run)
    universes = []
    for rank, r in enumerate(diag["ranking"][: max(1, min(top_k, 8))]):
        k = r["idx"]
        fix = propose_fix(run, k, rows, load_checkpoint=_loader(session))
        entry = {"rank": rank + 1, "step": k, "name": r["name"], "prob": r["prob"], "fix": fix}
        if fix is None:
            # nothing to repair here: replay this universe unchanged to show the ending holds
            res = fork(session, run_id, k, [], kind="sweep")
            entry.update({"status": res["status"], "flipped": res["flipped"], "fork_id": res["id"],
                          "savings": res["savings"], "replayed_unchanged": True,
                          "note": "no visible problem at this step, replayed as it was"})
        else:
            res = fork(session, run_id, k, [fix["edit"]], kind="sweep")
            entry.update({"status": res["status"], "flipped": res["flipped"], "fork_id": res["id"],
                          "savings": res["savings"]})
        universes.append(entry)
    flips = [u["step"] for u in universes if u["flipped"]]
    confirmed = min(flips) if flips else None
    return {"run_id": run_id, "universes": universes, "confirmed_step": confirmed,
            "confirmed_fork": next((u["fork_id"] for u in universes if u["step"] == confirmed), None),
            "model_top1": diag["canon_event"]["idx"]}


def replay_from(session: Session, run_id: str, step: int) -> dict:
    """Re-execute from step k with no changes (should reproduce the run)."""
    return fork(session, run_id, step, [], kind="replay")


def state_at(session: Session, run_id: str, idx: int) -> dict:
    run = load_run(session, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    steps = {s["idx"]: s for s in run["steps"]}
    if idx not in steps:
        raise HTTPException(404, "step not found")
    after = load_checkpoint(session, steps[idx]["checkpoint_id"]) if steps[idx].get("checkpoint_id") else None
    before = None
    if idx > 0 and steps.get(idx - 1, {}).get("checkpoint_id"):
        before = load_checkpoint(session, steps[idx - 1]["checkpoint_id"])
    return {"idx": idx, "checkpoint_id": steps[idx].get("checkpoint_id"),
            "after": after, "diff": diff_states(before, after)}


def diff_states(before: Optional[dict], after: Optional[dict], limit: int = 40) -> list[dict]:
    if after is None:
        return []
    a = _flatten({"agent": (before or {}).get("agent_state") or {},
                  "world": (before or {}).get("world_state") or {}})
    b = _flatten({"agent": after.get("agent_state") or {}, "world": after.get("world_state") or {}})
    out = []
    for key in sorted(set(a) | set(b)):
        if key.startswith("agent.messages") or key.startswith("world.counters"):
            continue
        if a.get(key) != b.get(key):
            op = "added" if key not in a else ("removed" if key not in b else "changed")
            out.append({"path": key, "op": op, "before": a.get(key), "after": b.get(key)})
        if len(out) >= limit:
            break
    return out


def _flatten(obj, prefix: str = "") -> dict:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj) and len(obj) <= 30:
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


__all__ = ["fork", "autofix", "sweep", "suggest", "replay_from", "state_at", "get_engine"]
