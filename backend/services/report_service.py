"""Narrate a diagnosis as an incident report (Gemini, optional).

The narrator only gets the model's ranking, the evidence strings and the blamed step's
content. It is told not to second-guess the ranking; without a key a template is used.
"""

from __future__ import annotations

import json

from agent_sim.llm import GeminiClient, LLMUnavailable, gemini_available

SYSTEM = (
    "You write short incident reports for an AI-agent flight recorder. Use ONLY the facts "
    "given. The diagnosis model has already chosen the root-cause step; never pick a "
    "different step and never invent evidence. Plain, direct English. Markdown."
)


def template_report(run: dict, diag: dict, fix: dict | None = None) -> str:
    top = diag["ranking"][0]
    others = diag["ranking"][1:3]
    lines = [
        f"### Incident report — run `{run['id'][:8]}`",
        "",
        f"**What happened:** the agent was asked to handle a `{run['task_family']}` request and "
        f"the run **failed**: {run.get('outcome_detail', '')}.",
        "",
        f"**Canon Event:** step {top['idx']} (`{top['name']}`), blamed with probability "
        f"{top['prob']:.2f}.",
    ]
    if top["evidence"]:
        lines += ["", "**Evidence from the trace:**"] + [f"- {e}" for e in top["evidence"]]
    if others:
        lines += ["", "**Other suspects:** " + ", ".join(
            f"step {o['idx']} `{o['name']}` ({o['prob']:.2f})" for o in others)]
    if fix:
        lines += ["", f"**Suggested fix:** {fix['explanation']} Fork the run at step "
                      f"{top['idx']} with this edit to prove it."]
    return "\n".join(lines)


def narrate(run: dict, diag: dict, fix: dict | None = None) -> tuple[str, str]:
    """Returns ``(markdown, source)`` where source is "gemini" or "template"."""
    if not gemini_available():
        return template_report(run, diag, fix), "template"
    top = diag["ranking"][0]
    step = next(s for s in run["steps"] if s["idx"] == top["idx"])
    facts = {
        "task": run.get("task_text"),
        "outcome": run.get("outcome_detail"),
        "final_answer": run.get("final_answer"),
        "canon_event": {"step": top["idx"], "name": top["name"], "probability": top["prob"],
                        "input": step.get("input"), "output": step.get("output"),
                        "error": step.get("error"), "evidence": top["evidence"],
                        "top_signals": [s["label"] for s in top["shap"][:4]]},
        "other_suspects": [{"step": r["idx"], "name": r["name"], "probability": r["prob"]}
                           for r in diag["ranking"][1:3]],
        "suggested_fix": fix["explanation"] if fix else None,
    }
    prompt = (
        "Write an incident report with these sections: **What happened** (1-2 sentences), "
        "**Canon Event** (the given step and why, citing the evidence), **Why it surfaced "
        "later** (one sentence), **Suggested fix** (only if one is given). Max 170 words.\n\n"
        f"Facts:\n{json.dumps(facts, ensure_ascii=False, default=str)[:6000]}"
    )
    try:
        text = GeminiClient().text(prompt, system=SYSTEM)
        if text:
            return text, "gemini"
    except (LLMUnavailable, Exception):  # noqa: BLE001 - fall back to the template
        pass
    return template_report(run, diag, fix), "template"
