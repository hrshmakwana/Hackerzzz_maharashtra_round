"""Tables: Run, Step, Checkpoint, WorldSnapshot, Diagnosis, ForkJob.

Checkpoints are content-addressed. The world part of a checkpoint is stored separately in
``WorldSnapshot`` because it only changes when a tool mutates something, so most steps of
a run point at the same world row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from blackbox_sdk.schema import utcnow


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    task_family: str = Field(default="", index=True)
    task_id: str = ""
    task_text: str = ""
    seed: int = 0
    policy: str = "sim"
    status: str = Field(default="running", index=True)
    outcome_detail: str = ""
    final_answer: str = ""
    parent_run_id: Optional[str] = Field(default=None, index=True)
    fork_step_idx: Optional[int] = None
    edits: Optional[list] = Field(default=None, sa_column=Column(JSON))
    fault_type: Optional[str] = Field(default=None, index=True)
    fault_step: Optional[int] = None
    fault_meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    split: str = Field(default="live", index=True)
    chain_head: str = ""
    steps_reused: int = 0
    steps_rerun: int = 0
    n_steps: int = 0
    tokens_total: int = 0
    latency_total_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Step(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, foreign_key="run.id")
    idx: int
    parent_idx: Optional[int] = None
    kind: str
    name: str
    input: Any = Field(default=None, sa_column=Column(JSON))
    output: Any = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    checkpoint_id: Optional[str] = None
    prev_hash: str = ""
    hash: str = ""
    reused: bool = False


class Checkpoint(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_state: Any = Field(default=None, sa_column=Column(JSON))
    world_id: str = Field(index=True)


class WorldSnapshot(SQLModel, table=True):
    id: str = Field(primary_key=True)
    state: Any = Field(default=None, sa_column=Column(JSON))


class Diagnosis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    model_version: str = ""
    ranking: Any = Field(default=None, sa_column=Column(JSON))
    report_md: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class ForkJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    parent_run_id: str = Field(index=True)
    kind: str = "fork"  # fork | autofix | sweep
    request: Any = Field(default=None, sa_column=Column(JSON))
    result: Any = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class AIReview(SQLModel, table=True):
    """One AI's independent pick for a run's root cause (kept for the live leaderboard)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    reviewer: str = Field(index=True)
    model: str = ""
    step: Optional[int] = None
    reason: str = ""
    created_at: datetime = Field(default_factory=utcnow)
