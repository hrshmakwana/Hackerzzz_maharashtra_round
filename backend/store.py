"""Reading and writing runs, steps and checkpoints."""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from blackbox_sdk.schema import CheckpointRecord, RunRecord, StepRecord

from .models import Checkpoint, Run, Step, WorldSnapshot

RUN_FIELDS = [
    "id", "task_family", "task_id", "task_text", "seed", "policy", "status", "outcome_detail",
    "final_answer", "parent_run_id", "fork_step_idx", "edits", "fault_type", "fault_step",
    "fault_meta", "split", "chain_head", "steps_reused", "steps_rerun", "tokens_total",
    "latency_total_ms", "created_at",
]
STEP_FIELDS = [
    "idx", "parent_idx", "kind", "name", "input", "output", "error", "latency_ms", "tokens_in",
    "tokens_out", "checkpoint_id", "prev_hash", "hash", "reused",
]


def run_row(run: RunRecord) -> dict:
    row = {k: getattr(run, k) for k in RUN_FIELDS}
    row["n_steps"] = len(run.steps)
    return row


def step_row(run_id: str, step: StepRecord) -> dict:
    row = {k: getattr(step, k) for k in STEP_FIELDS}
    row["run_id"] = run_id
    return row


def _insert_ignore(session: Session, model, rows: list[dict]) -> None:
    if rows:
        session.execute(sqlite_insert(model).on_conflict_do_nothing(), rows)


def _checkpoint_rows(checkpoints: Iterable[CheckpointRecord]) -> tuple[list[dict], list[dict]]:
    cps, worlds, seen = [], [], set()
    for cp in checkpoints:
        cps.append({"id": cp.id, "agent_state": cp.agent_state, "world_id": cp.world_id})
        if cp.world_id not in seen:
            seen.add(cp.world_id)
            worlds.append({"id": cp.world_id, "state": cp.world_state})
    return cps, worlds


def save_runs(engine: Engine, items: list[tuple[RunRecord, dict]]) -> None:
    """Bulk write ``(run, checkpoints)`` pairs in one transaction."""
    runs, steps, cps = [], [], []
    for run, checkpoints in items:
        runs.append(run_row(run))
        steps += [step_row(run.id, s) for s in run.steps]
        cps += list(checkpoints.values())
    cp_rows, world_rows = _checkpoint_rows(cps)
    with Session(engine) as s:
        _insert_ignore(s, WorldSnapshot, world_rows)
        _insert_ignore(s, Checkpoint, cp_rows)
        _insert_ignore(s, Run, runs)
        if steps:
            s.execute(sqlite_insert(Step), steps)
        s.commit()


def save_run(engine: Engine, run: RunRecord, checkpoints: dict) -> None:
    save_runs(engine, [(run, checkpoints)])


# -- streaming writes (live runs) --------------------------------------------------


def save_run_header(engine: Engine, run: RunRecord) -> None:
    with Session(engine) as s:
        s.merge(Run(**run_row(run)))
        s.commit()


def update_run_header(engine: Engine, run: RunRecord) -> None:
    save_run_header(engine, run)


def save_step(engine: Engine, run_id: str, step: StepRecord) -> None:
    with Session(engine) as s:
        s.add(Step(**step_row(run_id, step)))
        s.commit()


def save_checkpoint(engine: Engine, run_id: str, step: StepRecord, cp: CheckpointRecord) -> None:
    cp_rows, world_rows = _checkpoint_rows([cp])
    with Session(engine) as s:
        _insert_ignore(s, WorldSnapshot, world_rows)
        _insert_ignore(s, Checkpoint, cp_rows)
        row = s.exec(select(Step).where(Step.run_id == run_id, Step.idx == step.idx)).first()
        if row is not None:
            row.checkpoint_id = cp.id
            s.add(row)
        s.commit()


# -- reads -------------------------------------------------------------------------


def run_dict(run: Run) -> dict:
    d = run.model_dump()
    d["created_at"] = run.created_at.isoformat() if run.created_at else None
    return d


def step_dict(step: Step) -> dict:
    d = step.model_dump()
    d.pop("id", None)
    d.pop("run_id", None)
    return d


def load_run(session: Session, run_id: str) -> Optional[dict]:
    run = session.get(Run, run_id)
    if run is None:
        return None
    steps = session.exec(select(Step).where(Step.run_id == run_id).order_by(Step.idx)).all()
    d = run_dict(run)
    d["steps"] = [step_dict(s) for s in steps]
    return d


def load_checkpoint(session: Session, checkpoint_id: str) -> Optional[dict]:
    cp = session.get(Checkpoint, checkpoint_id)
    if cp is None:
        return None
    world = session.get(WorldSnapshot, cp.world_id)
    return {"id": cp.id, "agent_state": cp.agent_state,
            "world_state": world.state if world else None}
