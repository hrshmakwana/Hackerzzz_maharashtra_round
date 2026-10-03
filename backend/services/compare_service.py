"""Align two runs and find the divergence point."""

from __future__ import annotations

from difflib import SequenceMatcher

from agent_sim.replay import savings
from blackbox_sdk import canonical_json


def _token(s: dict) -> str:
    return canonical_json([s["kind"], s["name"], s.get("input")])


def align(a: dict, b: dict) -> dict:
    sa = sorted(a["steps"], key=lambda s: s["idx"])
    sb = sorted(b["steps"], key=lambda s: s["idx"])
    sm = SequenceMatcher(None, [_token(s) for s in sa], [_token(s) for s in sb], autojunk=False)
    pairs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                same = canonical_json([sa[i].get("output"), sa[i].get("error")]) == \
                    canonical_json([sb[j].get("output"), sb[j].get("error")])
                pairs.append({"a": sa[i]["idx"], "b": sb[j]["idx"],
                              "op": "equal" if same else "output_changed",
                              "reused": bool(sb[j].get("reused"))})
        else:
            n = max(i2 - i1, j2 - j1)
            for t in range(n):
                i, j = i1 + t, j1 + t
                pairs.append({"a": sa[i]["idx"] if i < i2 else None,
                              "b": sb[j]["idx"] if j < j2 else None,
                              "op": op if (i < i2 and j < j2) else ("delete" if i < i2 else "insert"),
                              "reused": bool(sb[j].get("reused")) if j < j2 else False})

    divergence = next((p for p in pairs if p["op"] != "equal"), None)
    is_fork = b.get("parent_run_id") == a["id"]
    result = {
        "a": _summary(a),
        "b": _summary(b),
        "pairs": pairs,
        "divergence": {"a": divergence["a"], "b": divergence["b"]} if divergence else None,
        "fork_step": b.get("fork_step_idx") if is_fork else None,
        "is_fork": is_fork,
        "outcome": {"a": a["status"], "b": b["status"],
                    "flipped": a["status"] == "fail" and b["status"] == "success",
                    "regressed": a["status"] == "success" and b["status"] == "fail"},
        "edits": b.get("edits") if is_fork else None,
        "similarity": round(sm.ratio(), 4),
    }
    if is_fork:
        result["savings"] = savings(a, b)
    return result


def _summary(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "status", "outcome_detail", "final_answer", "task_family",
                                  "task_text", "policy", "parent_run_id", "fork_step_idx",
                                  "steps_reused", "steps_rerun", "tokens_total",
                                  "latency_total_ms", "split")} | {"n_steps": len(r["steps"])}
