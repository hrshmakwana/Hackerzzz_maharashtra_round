"""Fork-and-fix experiments: does auto-fix at the blamed step flip fail -> success?"""

from __future__ import annotations

import random
from statistics import mean

import numpy as np

from agent_sim.repair import propose_fix
from agent_sim.replay import fork_run, savings
from agent_sim.runner import run_agent

from .common import Models

SAMPLE = 150
SPLITS = ["test", "heldout_type", "heldout_family"]


def rerecord(run: dict):
    """Re-simulate a dataset run with checkpoints kept in memory (traces are deterministic)."""
    fault = {"type": run["fault_type"], "step": run["fault_step"]} if run.get("fault_type") else None
    out = run_agent(run["task_family"], run["seed"], run.get("policy", "sim"), fault,
                    run_id=run["id"], split=run["split"])
    rec = out.record.model_dump(mode="json")
    rec["fault_meta"] = run.get("fault_meta")
    return rec, out.checkpoints


def try_fix(run: dict, checkpoints: dict, k: int, rows) -> tuple[bool | None, dict | None]:
    load = lambda cid: (lambda cp: cp.model_dump() if cp else None)(checkpoints.get(cid))  # noqa: E731
    fix = propose_fix(run, k, rows, load_checkpoint=load)
    if fix is None:
        return None, None
    out = fork_run(run, k, [fix["edit"]], load_checkpoint=load)
    fork = out.record.model_dump(mode="json")
    return out.success, savings(run, fork)


def replay_stats(runs: list[dict], models: Models, sample: int = SAMPLE) -> dict:
    result = {"n": sample, "splits": {}}
    for split in SPLITS:
        pool = [r for r in runs if r["split"] == split and r["status"] == "fail" and r.get("fault_type")]
        random.Random(f"replay:{split}").shuffle(pool)
        flips1, flips_sweep, fixable, reused, tokens, time_ms, at_true = [], [], [], [], [], [], []
        confirmed_true = []
        for run in pool[:sample]:
            rec, cps = rerecord(run)
            scores, rows, _ = models.score_steps(rec)
            order = [int(i) for i in np.argsort(-scores, kind="stable")]
            ok1, sv = try_fix(rec, cps, order[0], rows)
            flips1.append(bool(ok1))
            fixable.append(ok1 is not None)
            if sv:
                reused.append(sv["reused_frac"])
                tokens.append(sv["tokens_saved"])
                time_ms.append(sv["time_saved_ms"])
            flipped = [order[0]] if ok1 else []
            for k in order[1:3]:
                okk, _ = try_fix(rec, cps, k, rows)
                if okk:
                    flipped.append(k)
            flips_sweep.append(bool(flipped))
            if flipped:
                # the sweep confirms the earliest step whose fix flips the outcome
                confirmed_true.append(min(flipped) == run["fault_step"])
            ok_true, _ = try_fix(rec, cps, run["fault_step"], rows)
            at_true.append(bool(ok_true))
        n = len(flips1)
        result["splits"][split] = {
            "n": n,
            "flip_rate_top1": round(mean(flips1), 4) if n else None,
            "flip_rate_sweep": round(mean(flips_sweep), 4) if n else None,
            "flip_rate_at_true_step": round(mean(at_true), 4) if n else None,
            "fix_proposed_rate": round(mean(fixable), 4) if n else None,
            "confirmed_precision": round(mean(confirmed_true), 4) if confirmed_true else None,
            "avg_reused_frac": round(mean(reused), 4) if reused else 0.0,
            "avg_tokens_saved": round(mean(tokens), 1) if tokens else 0.0,
            "avg_time_saved_ms": round(mean(time_ms), 1) if time_ms else 0.0,
        }
    return result
