"""run_agent(): executes a task with a policy, optionally from a checkpoint with edits.

    python -m agent_sim.runner --family refund --seed 7
    python -m agent_sim.runner --family refund --seed 7 --fault bad_retrieval
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from blackbox_sdk import Edit, Recorder, RunRecord, canonical_json
from blackbox_sdk.schema import sha256

from . import faults
from .checker import check
from .faults import FaultSpec
from .tasks import Task, make_task
from .tools import SIDE_EFFECT_TOOLS, TRANSIENT_ERRORS, ToolError, execute, swap_doc_output
from .world import World

MAX_STEPS = 25
TRANSIENT_P = {"tool": 0.06, "retrieval": 0.03}
_MISSING = object()


@dataclass
class RunOutcome:
    record: RunRecord
    tags: list[str] = field(default_factory=list)
    world: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    task: Optional[Task] = None

    @property
    def success(self) -> bool:
        return self.record.status == "success"


def get_policy(name: str):
    if name == "sim":
        from .policy_sim import SimPolicy

        return SimPolicy()
    if name == "gemini":
        from .policy_gemini import GeminiPolicy

        return GeminiPolicy()
    raise ValueError(f"unknown policy {name}")


def _rng(seed: int, idx: int, salt: str) -> random.Random:
    return random.Random(int(sha256(f"{salt}:{seed}:{idx}")[:16], 16))


def sim_cost(action: dict, output: Any, idx: int, seed: int) -> dict:
    """Plausible latency/token numbers for simulated steps (deterministic)."""
    r = _rng(seed, idx, "cost:" + action["name"])
    kind = action["kind"]
    size = len(canonical_json(output)) if output is not None else 0
    if kind == "llm":
        tin = 380 + 55 * idx + r.randint(0, 60)
        tout = max(18, size // 4)
        return {"latency_ms": 420 + tout * 9 + r.randint(0, 600), "tokens_in": tin, "tokens_out": tout}
    if kind == "plan":
        return {"latency_ms": 500 + r.randint(0, 400), "tokens_in": 310 + r.randint(0, 40),
                "tokens_out": max(30, size // 4)}
    if kind == "retrieval":
        return {"latency_ms": 90 + r.randint(0, 230), "tokens_in": 0, "tokens_out": 0}
    if kind == "final":
        return {"latency_ms": 5 + r.randint(0, 20), "tokens_in": 0, "tokens_out": 0}
    return {"latency_ms": 35 + r.randint(0, 220), "tokens_in": 0, "tokens_out": 0}


def run_agent(family: str, seed: int, policy: str | Any = "sim", fault: Any = None, *,
              start: Optional[dict] = None, edits: Optional[list] = None, sink: Any = None,
              run_id: Optional[str] = None, split: str = "live",
              parent_run_id: Optional[str] = None, max_steps: int = MAX_STEPS,
              keep_checkpoints: bool = True, step_delay: float = 0.0,
              recorder: Optional[Recorder] = None) -> RunOutcome:
    """Run one episode.

    ``start`` resumes a fork: ``{"prefix": [step dicts 0..k-1], "agent_state": ...,
    "world_state": ..., "tags": [...]}``. The prefix steps are copied with ``reused=True``
    and never re-executed; the episode continues live from step k with the same seed.
    """
    task, world0 = make_task(family, seed)
    pol = get_policy(policy) if isinstance(policy, str) else policy
    fault_spec = FaultSpec.parse(fault)
    edit_objs = [e if isinstance(e, Edit) else Edit(**e) for e in (edits or [])]
    prefix = (start or {}).get("prefix", [])
    fork_idx = len(prefix) if start else None
    for e in edit_objs:
        if e.step is None:
            e.step = fork_idx if fork_idx is not None else 0

    rec = recorder or Recorder(
        run_id=run_id, sink=sink, keep_checkpoints=keep_checkpoints,
        task_family=family, task_id=task.task_id, task_text=task.text, seed=seed,
        policy=pol.name, split=split, parent_run_id=parent_run_id, fork_step_idx=fork_idx,
        edits=[e.model_dump(exclude_none=True) for e in edit_objs] or None,
        fault_type=fault_spec.type if fault_spec else None,
        fault_step=fault_spec.step if fault_spec else None,
    )

    tags: list[str] = []
    if start:
        world = World.from_snapshot(start["world_state"])
        state = copy.deepcopy(start["agent_state"])
        tags = list(start.get("tags", []))
        for s in prefix:
            rec.record(s["kind"], s["name"], s.get("input"), s.get("output"), s.get("error"),
                       latency_ms=s.get("latency_ms", 0), tokens_in=s.get("tokens_in", 0),
                       tokens_out=s.get("tokens_out", 0), parent_idx=s.get("parent_idx"),
                       reused=True, checkpoint_id=s.get("checkpoint_id"))
    else:
        world = World(world0)
        state = pol.init_state(task)

    by_step: dict[int, list[Edit]] = {}
    for e in edit_objs:
        by_step.setdefault(e.step, []).append(e)

    idx = len(prefix)
    finished, final_answer = False, None
    while idx < max_steps:
        step_edits = by_step.get(idx, [])
        for e in step_edits:
            if e.type == "patch_prompt" and e.prompt:
                state["system_prompt"] = state["system_prompt"] + "\n" + e.prompt
        content_edit = next((e for e in step_edits if e.type != "patch_prompt"), None)

        action = pol.decide(task, state, idx, seed)
        fault_live = fault_spec is not None and fault_spec.step == idx
        ctx = None
        if fault_live:
            ctx = faults.Ctx(task=task, world=world, state=state, seed=seed, idx=idx, policy=pol,
                             redecide=lambda view, _i=idx: pol.decide(task, view, _i, seed))
            action = faults.pre(fault_spec, action, ctx)

        override = _MISSING
        if content_edit is not None:
            if content_edit.type == "override_args" and content_edit.args is not None:
                action = {**action, "input": dict(content_edit.args)}
            elif content_edit.type in ("override_output", "override_decision"):
                override = content_edit.output
            elif content_edit.type == "swap_document":
                override = swap_doc_output(content_edit.doc_id or "",
                                           action["input"].get("query", ""))

        output, error, flags = None, None, {}
        kind = action["kind"]
        if kind in ("llm", "plan"):
            output = action.get("output") if override is _MISSING else override
        elif kind == "final":
            finished = True
            final_answer = str(action["input"].get("answer", ""))
            output = {"status": "submitted"}
        elif override is not _MISSING:
            output = override
        else:
            intercepted = None
            if fault_live and content_edit is None:
                intercepted = faults.intercept(fault_spec, action, ctx)
            if intercepted is not None:
                output, error, flags = intercepted
            else:
                transient = None
                if content_edit is None and not action.get("is_retry"):
                    r = _rng(seed, idx, "transient")
                    if r.random() < TRANSIENT_P.get(kind, 0):
                        transient = r.choice(TRANSIENT_ERRORS)
                if transient:
                    error = transient
                else:
                    try:
                        output = execute(world, action["name"], dict(action["input"]))
                    except ToolError as exc:
                        error = str(exc)
                reexec_ok = content_edit is None or (
                    content_edit.type == "override_args" and fault_spec.type in faults.PERSISTENT
                    if fault_spec else False)
                if fault_live and reexec_ok and not transient:
                    output, error, flags = faults.post(fault_spec, action, output, error, ctx)

        cost = sim_cost(action, output, idx, seed) if pol.name == "sim" else \
            action.get("cost") or sim_cost(action, output, idx, seed)
        rec.record(kind, action["name"], action["input"], output, error,
                   latency_ms=cost["latency_ms"], tokens_in=cost["tokens_in"],
                   tokens_out=cost["tokens_out"])
        tags.append(action.get("tag", ""))
        pol.observe(task, state, action, output, error, flags)
        rec.checkpoint(state, world.data)
        idx += 1
        if step_delay:
            time.sleep(step_delay)
        if finished:
            break

    ok, detail = check(task, world.data, final_answer, finished)
    meta = dict(fault_spec.meta) if fault_spec else None
    record = rec.finish(
        "success" if ok else "fail", detail, final_answer or "",
        fault_meta=meta, steps_reused=len(prefix), steps_rerun=len(rec.steps) - len(prefix),
    )
    return RunOutcome(record=record, tags=tags, world=world.data, state=state, task=task)


def side_effects(steps: list) -> list[tuple[int, str]]:
    """(idx, signature) for every step that changes the outside world."""
    out = []
    for s in steps:
        s = s if isinstance(s, dict) else s.model_dump()
        if (s["name"] in SIDE_EFFECT_TOOLS and not s.get("error")) or s["kind"] == "final":
            out.append((s["idx"], s["name"] + canonical_json(s["input"])))
    return out


def manifest_step(clean_steps: list, faulty_steps: list, fault_step: int) -> int:
    """First step at or after the fault whose side effect never happens in the clean run
    (or the last step, when the damage is an omission)."""
    clean = {sig for _, sig in side_effects(clean_steps)}
    for idx, sig in side_effects(faulty_steps):
        if idx >= fault_step and sig not in clean:
            return idx
    last = faulty_steps[-1]
    return last["idx"] if isinstance(last, dict) else last.idx


# ---------------------------------------------------------------------------- CLI


def _print_trace(rec: RunRecord) -> None:
    for s in rec.steps:
        mark = "!" if s.error else " "
        body = s.error or json.dumps(s.output, ensure_ascii=False)
        if len(body) > 110:
            body = body[:107] + "..."
        args = json.dumps(s.input, ensure_ascii=False)
        if len(args) > 70:
            args = args[:67] + "..."
        print(f"{s.idx:>2}{mark} {s.kind:<9} {s.name:<16} {args}")
        print(f"      -> {body}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one ShopOps episode with the sim agent.")
    ap.add_argument("--family", default="refund")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--policy", default="sim")
    ap.add_argument("--fault", default=None, help="fault type; step is picked automatically")
    ap.add_argument("--fault-step", type=int, default=None)
    args = ap.parse_args()

    fault = None
    if args.fault:
        clean = run_agent(args.family, args.seed, args.policy, keep_checkpoints=False)
        cands = faults.candidate_steps(args.fault, [s.model_dump() for s in clean.record.steps],
                                       clean.tags)
        step = args.fault_step if args.fault_step is not None else (cands[0] if cands else 1)
        fault = {"type": args.fault, "step": step}

    out = run_agent(args.family, args.seed, args.policy, fault, keep_checkpoints=False)
    rec = out.record
    print(f"task: {rec.task_text}\n")
    _print_trace(rec)
    print(f"\nanswer:  {rec.final_answer}")
    print(f"outcome: {rec.status.upper()} - {rec.outcome_detail}")
    if fault:
        print(f"fault:   {rec.fault_type} at step {rec.fault_step} {rec.fault_meta}")


if __name__ == "__main__":
    main()
