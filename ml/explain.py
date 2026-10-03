"""SHAP contributions and trace evidence for a ranked step.

``diagnose(run)`` returns the full ranking: for every step its score, softmax probability
within the run, the top SHAP contributions and human-readable evidence sentences built
from the feature details (never from labels).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from .common import Models, load_models, softmax

FEATURE_LABELS = {
    "transition_surprisal": "unusual step order",
    "next_surprisal": "unusual next step",
    "arg_ungrounded": "arguments never observed",
    "arg_provenance": "argument provenance",
    "arg_observed_frac": "arguments seen in tool output",
    "llm_ungrounded": "asserted values never observed",
    "novel_entities": "new values in output",
    "memory_contradiction": "contradicts a tool result",
    "memory_overwrite": "overwrites a remembered value",
    "error_then_continue": "error ignored",
    "error_present": "tool error",
    "error_retried": "error retried",
    "retrieval_doc_archived": "archived document",
    "retrieval_doc_current": "current document",
    "retrieval_requeried": "re-queried afterwards",
    "retrieval_score": "retrieval score",
    "calc_consistency": "calculation consistency",
    "repeat_count": "repeated call",
    "future_repeats": "repeated later",
    "no_progress_repeat": "repeat without progress",
    "instruction_likeness": "instruction-like content",
    "llm_extra_actions": "extra actions scheduled",
    "claims_progress": "progress claim",
    "claimed_remaining": "work claimed remaining",
    "side_effects_after": "actions after this step",
    "side_effects_before": "actions before this step",
    "downstream_dependence": "later steps depend on it",
    "downstream_side_effects": "later actions depend on it",
    "foreign_introduced": "brings in foreign ids",
    "foreign_in_args": "acts on foreign ids",
    "introduced": "new values introduced",
    "pos_rel": "position in run",
    "steps_to_end": "steps until the end",
}


@lru_cache(maxsize=1)
def _explainer():
    import shap

    return shap.TreeExplainer(load_models().ranker)


def shap_values(X: np.ndarray) -> np.ndarray:
    vals = _explainer().shap_values(X)
    return np.asarray(vals[0] if isinstance(vals, list) else vals)


def _fmt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def evidence_for(step: dict, row: dict) -> list[str]:
    f, d = row["f"], row["details"]
    name = step["name"]
    ev: list[str] = []
    out = step.get("output") if isinstance(step.get("output"), dict) else {}

    if f.get("error_then_continue"):
        ev.append(f"{name} failed ({str(step.get('error')).split(':')[0]}) and the agent carried "
                  f"on without retrying")
    if f.get("retrieval_doc_archived") and not f.get("retrieval_requeried"):
        doc = d.get("doc") or {}
        ev.append(f"retrieved {doc.get('doc_id')} — marked {doc.get('status')} (version "
                  f"{doc.get('version')}, updated {doc.get('updated')}) — and used it without "
                  f"looking for the current version")
    if d.get("foreign_introduced"):
        ev.append(f"brings in {', '.join(d['foreign_introduced'])}, which do not belong to this "
                  f"customer's request, and later actions use them")
    if d.get("ungrounded_args"):
        args = step.get("input") or {}
        named = []
        for v in d["ungrounded_args"][:3]:
            key = next((k for k, x in args.items() if v in str(x).replace(",", "")), None)
            named.append(f"{key} {v}" if key else v)
        ev.append(f"uses {', '.join(named)}, never seen in the task or any earlier tool output")
    for c in d.get("contradictions", [])[:2]:
        ev.append(f"writes {c['key']} = {_fmt(c['value'])}, but the tool reported "
                  f"{_fmt(c['observed'])}")
    for o in d.get("overwrites", [])[:2]:
        ev.append(f"overwrites {o['key']}: {_fmt(o['old'])} → {_fmt(o['new'])} with no tool "
                  f"result behind the change")
    if d.get("llm_ungrounded") and step["kind"] == "llm" and not d.get("contradictions"):
        ev.append(f"asserts {', '.join(d['llm_ungrounded'][:3])}, which no tool ever returned")
    if d.get("calc_unexplained"):
        ev.append(f"the expression uses {', '.join(d['calc_unexplained'])}, which matches nothing "
                  f"the agent had observed or noted")
    if f.get("claims_progress") and f.get("side_effects_after", 1) == 0:
        ev.append("declares the remaining work done; no further actions follow")
    if f.get("future_repeats", 0) >= 2:
        ev.append(f"the same call is repeated {int(f['future_repeats'])} more times without "
                  f"new information")
    if f.get("instruction_likeness", 0) >= 2:
        ev.append(f"the content contains text addressed to the assistant "
                  f"({int(f['instruction_likeness'])} instruction markers)")
    if f.get("llm_extra_actions"):
        acts = ", ".join(a.get("name", "?") for a in out.get("extra_actions", []))
        ev.append(f"schedules extra actions the task did not ask for ({acts})")
    if d.get("foreign_in_args") and not d.get("foreign_introduced"):
        ev.append(f"acts on {', '.join(d['foreign_in_args'])}, outside this customer's request")
    if f.get("transition_surprisal", 0) > 4:
        ev.append(f"step order rarely seen in successful runs (surprisal "
                  f"{f['transition_surprisal']:.1f})")
    if f.get("downstream_side_effects", 0) >= 1 and ev:
        ev.append(f"{int(f['downstream_dependence'])} later step(s) build on values introduced "
                  f"here")
    return ev


def step_label(step: dict) -> str:
    return {"llm": "LLM step", "plan": "planning step", "final": "final answer"}.get(
        step["kind"], step["name"])


def headline(step: dict, row: dict) -> str:
    ev = evidence_for(step, row)
    if not ev:
        return f"{step_label(step)} looks most responsible"
    return ev[0] if ev[0].startswith(step["name"]) else f"{step_label(step)} {ev[0]}"


def diagnose(run: dict, models: Models | None = None, top_shap: int = 6,
             with_shap: bool = True) -> dict:
    models = models or load_models()
    steps = sorted(run["steps"], key=lambda s: s["idx"])
    scores, rows, X = models.score_steps(run)
    probs = softmax(np.asarray(scores, dtype=float))
    sv = shap_values(X) if with_shap else np.zeros_like(X)
    ranking = []
    for i in np.argsort(-scores, kind="stable"):
        contrib = sorted(
            ({"feature": n, "label": FEATURE_LABELS.get(n, n.replace("_", " ")),
              "value": round(float(X[i, j]), 3), "contribution": round(float(sv[i, j]), 4)}
             for j, n in enumerate(models.names)),
            key=lambda c: -abs(c["contribution"]))[:top_shap]
        evidence = evidence_for(steps[i], rows[i])
        if not evidence:
            pos = [c["label"] for c in contrib if c["contribution"] > 0][:2]
            if pos and probs[i] >= 0.2:
                evidence = [f"strongest model signals: {', '.join(pos)}"]
        ranking.append({
            "idx": steps[i]["idx"],
            "name": steps[i]["name"],
            "kind": steps[i]["kind"],
            "score": round(float(scores[i]), 4),
            "prob": round(float(probs[i]), 4),
            "evidence": evidence,
            "shap": contrib,
        })
    risk = models.fail_risk(run)
    top = ranking[0]
    top_step = steps[[s["idx"] for s in steps].index(top["idx"])]
    top_row = rows[[s["idx"] for s in steps].index(top["idx"])]
    return {
        "model_version": models.version,
        "ranking": ranking,
        "fail_risk": round(risk, 4),
        "canon_event": {"idx": top["idx"], "name": top["name"], "prob": top["prob"],
                        "headline": headline(top_step, top_row)},
    }
