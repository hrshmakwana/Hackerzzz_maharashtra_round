"""Pydantic models for runs and steps, shared by the SDK, simulator and API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

StepKind = Literal["plan", "llm", "tool", "retrieval", "final"]
RunStatus = Literal["success", "fail", "running"]
EditType = Literal[
    "override_args", "override_output", "override_decision", "swap_document", "patch_prompt"
]


def canonical_json(obj: Any) -> str:
    """Stable JSON used for hashing: sorted keys, no whitespace, utf-8 kept as-is."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def genesis_hash(run_id: str) -> str:
    return sha256(run_id)


def step_hash(prev_hash: str, *, kind: str, name: str, input: Any, output: Any,
              error: Optional[str], idx: int) -> str:
    payload = canonical_json(
        {"kind": kind, "name": name, "input": input, "output": output, "error": error, "idx": idx}
    )
    return sha256(prev_hash + payload)


def world_id(world_state: dict) -> str:
    return sha256(canonical_json(world_state))


def checkpoint_id(agent_state: dict, world_state_id: str) -> str:
    return sha256(canonical_json({"agent": agent_state, "world": world_state_id}))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StepRecord(BaseModel):
    idx: int
    parent_idx: Optional[int] = None
    kind: StepKind
    name: str
    input: dict = Field(default_factory=dict)
    output: Any = None
    error: Optional[str] = None
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    checkpoint_id: Optional[str] = None
    prev_hash: str = ""
    hash: str = ""
    reused: bool = False


class CheckpointRecord(BaseModel):
    id: str
    agent_state: dict
    world_id: str
    world_state: dict


class Edit(BaseModel):
    """A change applied when forking a run at step k."""

    type: EditType
    step: Optional[int] = None  # defaults to the fork step
    args: Optional[dict] = None  # override_args
    output: Any = None  # override_output / override_decision
    doc_id: Optional[str] = None  # swap_document
    prompt: Optional[str] = None  # patch_prompt
    note: Optional[str] = None  # human-readable reason, shown in the UI


class RunRecord(BaseModel):
    id: str
    task_family: str = ""
    task_id: str = ""
    task_text: str = ""
    seed: int = 0
    policy: str = "sim"
    status: RunStatus = "running"
    outcome_detail: str = ""
    final_answer: str = ""
    parent_run_id: Optional[str] = None
    fork_step_idx: Optional[int] = None
    edits: Optional[list[dict]] = None
    fault_type: Optional[str] = None
    fault_step: Optional[int] = None
    fault_meta: Optional[dict] = None
    split: str = "live"
    chain_head: str = ""
    steps_reused: int = 0
    steps_rerun: int = 0
    tokens_total: int = 0
    latency_total_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    steps: list[StepRecord] = Field(default_factory=list)
