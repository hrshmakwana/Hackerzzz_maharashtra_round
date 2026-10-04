"""Second opinions: independent AIs double-check the model's diagnosis.

The trained ranker still makes the call. Each reviewer reads the same recording and the
model's answer, and says whether it agrees (and, if not, which step it would blame).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session

from agent_sim.llm import reviewers

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


def build_prompt(run: dict, diag: dict) -> str:
    top = diag["ranking"][0]
    return (
        f"Task given to the agent: {run.get('task_text', '')}\n"
        f"How the run failed: {run.get('outcome_detail', '')}\n\n"
        f"Recording (step index in brackets):\n{_trace(run)}\n\n"
        f"A diagnosis model says the root cause is step [{top['idx']}] ({top['name']}). "
        f"Its evidence: {'; '.join(top['evidence']) or 'none given'}.\n\n"
        "Do you agree that this step is where the failure really started (not just where it "
        "became visible)? Reply with JSON only: "
        '{"agree": true or false, "root_cause_step": <the step index you would blame>, '
        '"reason": "<one short plain-English sentence, without step numbers>"}'
    )


def _ask(name: str, client, prompt: str) -> dict:
    try:
        data = client.json(prompt, system=SYSTEM)
        step = data.get("root_cause_step")
        return {
            "name": name,
            "model": client.model,
            "agree": bool(data.get("agree")),
            "step": int(step) if isinstance(step, (int, float)) or str(step).isdigit() else None,
            "reason": str(data.get("reason") or "").strip(),
        }
    except Exception as exc:  # noqa: BLE001 - one reviewer failing must not break the rest
        return {"name": name, "model": getattr(client, "model", ""), "agree": None, "step": None,
                "reason": "", "error": str(exc)[:200]}


def review(session: Session, run_id: str) -> dict:
    run = require_run(session, run_id)
    diag = diagnose(session, run_id)
    panel = reviewers()
    if not panel:
        return {"run_id": run_id, "model_step": diag["canon_event"]["idx"], "reviews": [],
                "agree": 0, "available": False}
    prompt = build_prompt(run, diag)
    with ThreadPoolExecutor(max_workers=len(panel)) as pool:
        reviews = list(pool.map(lambda p: _ask(p[0], p[1], prompt), panel))
    # a reviewer that names the same step agrees, whatever its yes/no flag says
    for r in reviews:
        if r.get("step") == diag["canon_event"]["idx"]:
            r["agree"] = True
    return {
        "run_id": run_id,
        "model_step": diag["canon_event"]["idx"],
        "reviews": reviews,
        "agree": sum(1 for r in reviews if r["agree"]),
        "available": True,
    }
