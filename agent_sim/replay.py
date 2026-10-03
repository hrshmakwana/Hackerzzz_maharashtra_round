"""Fork a recorded run at step k: reuse steps 0..k-1, resume from the checkpoint after
step k-1, apply edits at step k and re-execute only the suffix."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .runner import RunOutcome, run_agent

CheckpointLoader = Callable[[str], Optional[dict]]


def fork_run(parent: dict, k: int, edits: Optional[list] = None, *,
             load_checkpoint: CheckpointLoader, sink: Any = None,
             run_id: Optional[str] = None, split: str = "fork",
             step_delay: float = 0.0) -> RunOutcome:
    steps = sorted(parent["steps"], key=lambda s: s["idx"])
    if not 0 <= k < len(steps) + 1:
        raise ValueError(f"step {k} is outside the run (0..{len(steps)})")
    fault = None
    if parent.get("fault_type") and parent.get("fault_step") is not None:
        # The environment of the original run is replayed as-is: if the fork starts before
        # the faulty step, the same thing will happen again unless an edit prevents it.
        fault = {"type": parent["fault_type"], "step": parent["fault_step"]}

    start = None
    if k > 0:
        cp_id = steps[k - 1].get("checkpoint_id")
        cp = load_checkpoint(cp_id) if cp_id else None
        if cp is None or cp.get("world_state") is None:
            raise LookupError(f"no checkpoint stored after step {k - 1}")
        start = {"prefix": steps[:k], "agent_state": cp["agent_state"],
                 "world_state": cp["world_state"]}
    out = run_agent(parent["task_family"], parent["seed"], parent.get("policy", "sim"), fault,
                    start=start, edits=edits, sink=sink, run_id=run_id, split=split,
                    parent_run_id=parent["id"], fork_step_idx=k, step_delay=step_delay)
    return out


def savings(parent: dict, fork: dict) -> dict:
    """What the fork did not have to redo."""
    reused = [s for s in fork["steps"] if s.get("reused")]
    return {
        "steps_reused": len(reused),
        "steps_rerun": len(fork["steps"]) - len(reused),
        "tokens_saved": sum((s.get("tokens_in") or 0) + (s.get("tokens_out") or 0) for s in reused),
        "time_saved_ms": sum(s.get("latency_ms") or 0 for s in reused),
        "reused_frac": round(len(reused) / max(1, len(parent["steps"])), 4),
    }
