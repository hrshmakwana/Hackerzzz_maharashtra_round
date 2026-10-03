"""Recompute and verify a run's hash chain."""

from __future__ import annotations

from blackbox_sdk import verify_chain


def verify(run: dict) -> dict:
    result = verify_chain(run["id"], run["steps"])
    head = run["steps"][-1]["hash"] if run["steps"] else None
    result["chain_head"] = run.get("chain_head")
    result["head_matches"] = bool(head == run.get("chain_head")) if run.get("status") != "running" else None
    if result["valid"] and result["head_matches"] is False:
        result["valid"] = False
        result["broken_at"] = run["steps"][-1]["idx"] if run["steps"] else None
    result["steps_checked"] = len(run["steps"])
    return result
