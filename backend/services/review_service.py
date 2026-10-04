"""Second opinions: independent AIs double-check the model's diagnosis.

The trained ranker still makes the call. Each reviewer reads the same recording *blind*
(it is not shown our answer), names the step it thinks caused the failure, and we compare.
Every answer is stored so accuracy can be tracked as more runs are tested.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, delete

from agent_sim.llm import MAKERS, reviewers

from ..models import AIReview

from .diagnosis_service import diagnose, require_run

SYSTEM = (
    "You are an independent reviewer auditing an AI customer-support agent that failed. "
    "Be strict and concise. Judge only from the recording you are given."
)


def _trace(run: dict) -> str:
    lines = []
    for s in run["steps"]:
        out = s.get("error") or json.dumps(s.get("output"), ensure_ascii=False)
        args = json.dumps(s.get("input"), ensure_ascii=False)
        lines.append(f"[{s['idx']}] {s['kind']} {s['name']} input={args[:300]} -> {out[:400]}")
    return "\n".join(lines)


def build_prompt(run: dict) -> str:
    return (
        f"Task given to the agent: {run.get('task_text', '')}\n"
        f"How the run failed: {run.get('outcome_detail', '')}\n\n"
        f"Recording (step index in brackets):\n{_trace(run)}\n\n"
        "Which single step is the root cause: the earliest step that, had it been done "
        "correctly, would have prevented the failure (not just where the failure became "
        "visible)? Reply with JSON only: "
        '{"root_cause_step": <step index>, '
        '"reason": "<one short plain-English sentence, without step numbers>"}'
    )


def _ask(name: str, client, prompt: str) -> dict:
    try:
        data = client.json(prompt, system=SYSTEM)
        step = data.get("root_cause_step")
        return {
            "name": name,
            "maker": MAKERS.get(name, ""),
            "model": client.model,
            "agree": None,
            "step": int(step) if isinstance(step, (int, float)) or str(step).isdigit() else None,
            "reason": str(data.get("reason") or "").strip(),
        }
    except Exception as exc:  # noqa: BLE001 - one reviewer failing must not break the rest
        return {"name": name, "maker": MAKERS.get(name, ""), "model": getattr(client, "model", ""),
                "agree": None, "step": None,
                "reason": "", "error": str(exc)[:200]}


def review(session: Session, run_id: str) -> dict:
    run = require_run(session, run_id)
    diag = diagnose(session, run_id)
    model_step = diag["canon_event"]["idx"]
    panel = reviewers()
    if not panel:
        return {"run_id": run_id, "model_step": model_step, "reviews": [], "agree": 0,
                "available": False}
    prompt = build_prompt(run)
    with ThreadPoolExecutor(max_workers=len(panel)) as pool:
        reviews = list(pool.map(lambda p: _ask(p[0], p[1], prompt), panel))
    for r in reviews:
        r["agree"] = None if r.get("error") else r.get("step") == model_step

    session.exec(delete(AIReview).where(AIReview.run_id == run_id))
    for r in reviews:
        if not r.get("error"):
            session.add(AIReview(run_id=run_id, reviewer=r["name"], model=r["model"],
                                 step=r.get("step"), reason=r.get("reason", "")))
    session.commit()
    return {
        "run_id": run_id,
        "model_step": model_step,
        "reviews": reviews,
        "agree": sum(1 for r in reviews if r["agree"]),
        "available": True,
    }
