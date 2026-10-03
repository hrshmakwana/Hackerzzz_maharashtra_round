"""Rank steps, attach evidence and SHAP, cache Diagnosis rows."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from agent_sim.repair import propose_fix
from ml.common import load_models, models_available
from ml.features import step_features

from ..models import Diagnosis
from ..store import load_checkpoint, load_run
from . import report_service


def require_run(session: Session, run_id: str, finished: bool = True) -> dict:
    run = load_run(session, run_id)
    if run is None:
        raise HTTPException(404, f"run {run_id} not found")
    if finished and run["status"] == "running":
        raise HTTPException(409, "run is still running")
    if not run["steps"]:
        raise HTTPException(422, "run has no steps")
    return run


def cached(session: Session, run_id: str) -> Optional[dict]:
    if not models_available():
        return None
    version = load_models().version
    row = session.exec(select(Diagnosis).where(Diagnosis.run_id == run_id,
                                               Diagnosis.model_version == version)
                       .order_by(Diagnosis.id.desc())).first()
    if row is None:
        return None
    out = dict(row.ranking)
    out["report_md"] = row.report_md
    return out


def diagnose(session: Session, run_id: str, with_report: bool = False,
             refresh: bool = False) -> dict:
    if not models_available():
        raise HTTPException(503, "no trained model found - run `make train`")
    run = require_run(session, run_id)
    if run["status"] == "success" and not refresh:
        pass  # successful runs can be diagnosed too; the ranking just shows least-trusted steps
    hit = None if refresh else cached(session, run_id)
    if hit and (not with_report or hit.get("report_md")):
        return hit

    if hit:
        diag = {k: v for k, v in hit.items() if k != "report_md"}
    else:
        from ml.explain import diagnose as run_diagnosis

        diag = run_diagnosis(run)
        diag["run_status"] = run["status"]
        if run.get("fault_type"):
            # Ground truth is shown next to the prediction for evaluation only.
            diag["ground_truth"] = {"step": run.get("fault_step"), "type": run.get("fault_type")}

        rows = step_features(run)
        loader = lambda cid: load_checkpoint(session, cid)  # noqa: E731
        fix = propose_fix(run, diag["canon_event"]["idx"], rows, load_checkpoint=loader)
        diag["suggested_fix"] = fix

    report_md = None
    if with_report:
        report_md, source = report_service.narrate(run, diag, diag.get("suggested_fix"))
        diag["report_source"] = source

    session.add(Diagnosis(run_id=run_id, model_version=diag["model_version"], ranking=diag,
                          report_md=report_md))
    session.commit()
    diag["report_md"] = report_md
    return diag
