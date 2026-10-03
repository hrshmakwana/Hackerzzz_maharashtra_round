"""Propose a fix for one step of a failed run, using only what the trace shows.

Rules, tried in order for the blamed step:
1. the call returned an error that nobody retried      -> retry it
2. the retrieved policy document is archived            -> swap in the current version
3. a tool output carries instructions for the assistant -> strip them
4. arguments contain values never observed / not owned  -> nearest observed value
5. a calculation uses unexplained numbers               -> nearest observed numbers
6. an llm step contradicts or overwrites observations   -> restore the observed values;
   premature "all done" claims and extra scheduled actions are dropped. When the step has
   such a problem, re-running the llm call from its checkpoint is tried first and kept
   only if the new answer agrees with the tool outputs.

No rule looks at labels: a step without a visible problem gets no fix.
"""

from __future__ import annotations

import copy
import math
import re
from difflib import SequenceMatcher
from typing import Any, Optional

from ml.features import (
    IGNORED_NUMBERS,
    RE_INSTR,
    emails_in,
    entities,
    norm_num,
    order_ids_in,
    ownership,
    step_features,
)

from .world import POLICY_DOCS, current_doc_for_topic


def _ratio_distance(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return abs(a - b)
    return abs(math.log(a / b))


def _closest_number(value: str, candidates: set[str]) -> Optional[str]:
    try:
        x = float(value)
    except ValueError:
        return None
    best, best_d = None, None
    for c in candidates:
        try:
            y = float(c)
        except ValueError:
            continue
        if c in IGNORED_NUMBERS or y == x:
            continue
        d = _ratio_distance(x, y) - 0.05 * SequenceMatcher(None, value, c).ratio()
        if best_d is None or d < best_d:
            best, best_d = c, d
    return best


def _closest_string(value: str, candidates: set[str]) -> Optional[str]:
    cands = [c for c in candidates if c != value]
    if not cands:
        return None
    return max(cands, key=lambda c: (SequenceMatcher(None, value, c).ratio(), c))


def _observed(steps: list[dict], upto: int, task_text: str) -> set[str]:
    seen = set(entities(task_text))
    for s in steps[:upto]:
        if s["kind"] in ("tool", "retrieval") and not s.get("error"):
            seen |= entities(s.get("output"))
    return seen


def _replace_value(args: Any, old: str, new: str) -> Any:
    """Replace ``old`` wherever it appears as a value (numbers keep their type)."""
    if isinstance(args, dict):
        return {k: _replace_value(v, old, new) for k, v in args.items()}
    if isinstance(args, list):
        return [_replace_value(v, old, new) for v in args]
    if isinstance(args, bool) or args is None:
        return args
    if isinstance(args, (int, float)):
        if norm_num(args) == old:
            try:
                return float(new) if "." in new or isinstance(args, float) else int(new)
            except ValueError:
                return args
        return args
    text = str(args)
    if text.strip().lstrip("#") == old:
        return text.replace(old, new)
    if "@" in old:
        return text.replace(old, new)
    return re.sub(rf"(?<![\d.]){re.escape(old)}(?![\d])", new, text)


def propose_fix(run: dict, k: int, rows: Optional[list[dict]] = None,
                load_checkpoint=None) -> Optional[dict]:
    """Return ``{"edit": {...}, "rule": str, "explanation": str}`` or None."""
    steps = sorted(run["steps"], key=lambda s: s["idx"])
    if not 0 <= k < len(steps):
        return None
    s = steps[k]
    rows = rows or step_features(run)
    det = rows[k]["details"]
    kind, name = s["kind"], s["name"]
    out = s.get("output") if isinstance(s.get("output"), dict) else {}
    args = s.get("input") or {}
    own_orders, own_emails = ownership(run, steps)
    requested = _requested_orders(run, steps)
    observed = _observed(steps, k, run.get("task_text", ""))

    # 1. an error that was not retried
    if kind in ("tool", "retrieval") and s.get("error"):
        nxt = steps[k + 1] if k + 1 < len(steps) else None
        retried = nxt is not None and nxt["name"] == name and nxt.get("input") == args
        if not retried:
            return _fix("override_args", {"args": copy.deepcopy(args)}, "retry",
                        f"Retry {name}: it failed ({s['error'].split(':')[0]}) and the agent "
                        f"carried on as if it had worked.")

    # 2. archived policy document that the agent kept using
    if kind == "retrieval" and out.get("status") == "archived" \
            and not rows[k]["f"].get("retrieval_requeried"):
        cur = current_doc_for_topic(out.get("topic", ""))
        if cur:
            return _fix("swap_document", {"doc_id": cur["doc_id"]}, "current_document",
                        f"Use the current {cur['title']} ({cur['version']}) instead of the "
                        f"archived {out.get('version')} from {out.get('updated')}.")

    # 3. instructions hidden in content the agent read
    if kind == "tool" and name == "read_email" and out.get("body"):
        body = out["body"]
        paras = re.split(r"\n\s*\n", body)
        keep = [p for p in paras if not any(rx.search(p) for rx in RE_INSTR)]
        if len(keep) < len(paras):
            clean = {**out, "body": "\n\n".join(keep)}
            return _fix("override_output", {"output": clean}, "strip_instructions",
                        "Remove the instructions addressed to the assistant from the email "
                        "before the agent reads it.")

    # 4. arguments with values that were never observed or do not belong to the request
    if kind in ("tool", "final") and name != "calculate":
        new_args = copy.deepcopy(args)
        changes = []
        for oid in sorted(order_ids_in(args)):
            off_request = len(requested) == 1 and oid not in requested
            if (oid not in own_orders and oid not in observed
                    or oid in det.get("foreign_introduced", []) or off_request):
                pool = requested if requested else own_orders
                rep = _closest_number(oid, pool) if pool else None
                if rep:
                    new_args = _replace_value(new_args, oid, rep)
                    changes.append(f"order {oid} -> {rep}")
        for em in sorted(emails_in(args)):
            if em not in own_emails and em not in {e for e in observed if "@" in e}:
                rep = _closest_string(em, own_emails)
                if rep:
                    new_args = _replace_value(new_args, em, rep)
                    changes.append(f"{em} -> {rep}")
        for val in det.get("ungrounded_args", []):
            if "@" in val or val in order_ids_in(args):
                continue
            rep = _closest_number(val, observed)
            if rep:
                new_args = _replace_value(new_args, val, rep)
                changes.append(f"{val} -> {rep}")
        if changes and new_args != args:
            return _fix("override_args", {"args": new_args}, "grounded_args",
                        "Use values the agent actually observed: " + ", ".join(changes) + ".")

    # 5. calculation with unexplained numbers
    if name == "calculate" and det.get("calc_unexplained"):
        expr = str(args.get("expression", ""))
        rebuilt = _subtotal_from_items(expr, steps, k)
        if rebuilt and rebuilt != expr:
            return _fix("override_args", {"args": {**args, "expression": rebuilt}}, "grounded_calc",
                        "Recompute the subtotal from the order lines get_order returned.")
        notes_vals = _llm_values(steps, k) - IGNORED_NUMBERS
        changes = []
        for val in det["calc_unexplained"]:
            rep = _closest_number(val, notes_vals)
            if rep is None or _ratio_distance(float(val), float(rep)) > 0.7:
                rep = _closest_number(val, observed - set(det["calc_unexplained"]))
            if rep:
                expr = re.sub(rf"(?<![\d.]){re.escape(val)}(?![\d.])", rep, expr, count=1)
                changes.append(f"{val} -> {rep}")
        if changes:
            return _fix("override_args", {"args": {**args, "expression": expr}}, "grounded_calc",
                        "Recompute with the numbers the agent had recorded: "
                        + ", ".join(changes) + ".")

    # 6. llm reasoning steps
    if kind == "llm" and out:
        problems = (det.get("contradictions") or det.get("llm_ungrounded")
                    or det.get("foreign_introduced"))
        if problems and load_checkpoint is not None:
            regen = _rerun_llm(run, k, load_checkpoint)
            if regen is not None and regen != out and _consistent(run, k, regen):
                return _fix("override_decision", {"output": regen}, "rerun_llm",
                            "Re-run this LLM call from its checkpoint; the new answer agrees "
                            "with the tool outputs.")
        new = copy.deepcopy(out)
        mu = new.get("memory_update") or {}
        notes = []
        for c in det.get("contradictions", []):
            key, obs = c["key"], c["observed"]
            if key.startswith("recheck.") and isinstance(mu.get("recheck"), dict):
                # waiting for a state the tools never reported: skip the re-check
                mu.pop("recheck")
                new["thought"] = "The order details are already known; no need to re-check."
                notes.append(f"drop the re-check waiting for {key.split('.', 1)[1]} "
                             f"'{c['value']}' (tools report '{obs}')")
            elif key in mu:
                mu[key] = _same_type(mu[key], obs)
                new["thought"] = _swap_text(new.get("thought", ""), c["value"], obs)
                notes.append(f"{key} = {obs} (as reported by the tool)")
        for o in det.get("overwrites", []):
            if o["key"] in mu and not any(c["key"] == o["key"] for c in det.get("contradictions", [])):
                ents = entities({"v": o["new"]})
                if ents and not ents <= observed:
                    mu[o["key"]] = o["old"]
                    new["thought"] = _swap_text(new.get("thought", ""), o["new"], o["old"])
                    notes.append(f"keep {o['key']} = {o['old']}")
        for val in det.get("llm_ungrounded", []):
            for key, v in list(mu.items()):
                if key == "recheck" or norm_num(v) != val and str(v).lstrip("#") != val:
                    continue
                pool = own_orders if key == "order_id" else observed
                rep = _closest_number(val, pool)
                if rep:
                    mu[key] = _same_type(v, rep)
                    new["thought"] = _swap_text(new.get("thought", ""), v, rep)
                    notes.append(f"{key} = {rep} (observed)")
            for key, v in list(mu.items()):
                if isinstance(v, str) and "@" in v and v not in own_emails:
                    rep = _closest_string(v, own_emails)
                    if rep:
                        mu[key] = rep
                        new["thought"] = _swap_text(new.get("thought", ""), v, rep)
                        notes.append(f"{key} = {rep}")
        if "plan_update" in new and rows[k]["f"].get("side_effects_after", 0) == 0:
            new.pop("plan_update")
            notes.append("ignore the premature 'all done' and continue the plan")
        if new.get("extra_actions"):
            foreign = []
            for a in new["extra_actions"]:
                refs = order_ids_in(a.get("args")) | emails_in(a.get("args"))
                if refs - own_orders - own_emails:
                    foreign.append(a)
            if foreign:
                new["extra_actions"] = [a for a in new["extra_actions"] if a not in foreign]
                if not new["extra_actions"]:
                    new.pop("extra_actions")
                notes.append("drop actions on orders/addresses outside this request")
        if new.get("memory_update") is not None:
            new["memory_update"] = mu
        if notes and new != out:
            return _fix("override_decision", {"output": new}, "grounded_decision",
                        "Correct the reasoning step: " + "; ".join(notes) + ".")
    return None


def _requested_orders(run: dict, steps: list[dict]) -> set[str]:
    """Orders the request is about: named in the task or in the first email's subject."""
    req = order_ids_in(run.get("task_text", ""))
    for s in steps:
        if s["name"] == "read_email" and isinstance(s.get("output"), dict) and not s.get("error"):
            req |= order_ids_in(s["output"].get("subject", ""))
            break
    return req


def _consistent(run: dict, k: int, output: dict) -> bool:
    """Would the replacement llm output still contradict what the tools reported?"""
    trial = copy.deepcopy(run)
    steps = sorted(trial["steps"], key=lambda s: s["idx"])
    steps[k]["output"] = output
    trial["steps"] = steps[: k + 1]
    d = step_features(trial)[k]["details"]
    return not d.get("contradictions") and not d.get("foreign_introduced")


def _fix(edit_type: str, payload: dict, rule: str, explanation: str) -> dict:
    return {"edit": {"type": edit_type, **payload, "note": explanation}, "rule": rule,
            "explanation": explanation}


def _same_type(old: Any, new: Any) -> Any:
    if isinstance(old, bool):
        return old
    if isinstance(old, (int, float)) and not isinstance(new, (int, float)):
        try:
            return float(new) if isinstance(old, float) else int(float(new))
        except (TypeError, ValueError):
            return new
    if isinstance(old, str) and not isinstance(new, str):
        return str(new)
    return new


def _swap_text(text: str, old: Any, new: Any) -> str:
    from .world import money

    out = text
    for a, b in ((old, new),):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) or \
                (norm_num(a) and norm_num(b)):
            try:
                out = out.replace(money(float(a)), money(float(b)))
            except (TypeError, ValueError):
                pass
        out = out.replace(f"#{a}", f"#{b}").replace(str(a), str(b))
    return out


def _subtotal_from_items(expr: str, steps: list[dict], upto: int) -> Optional[str]:
    """For ``price * qty + ...`` expressions, rebuild from the latest order lines."""
    if not re.fullmatch(r"\s*\d+(?:\.\d+)? \* \d+(?: \+ \d+(?:\.\d+)? \* \d+)*\s*", expr):
        return None
    for s in reversed(steps[:upto]):
        out = s.get("output") if isinstance(s.get("output"), dict) else None
        if s["name"] == "get_order" and out and out.get("items"):
            return " + ".join(f"{norm_num(i['price'])} * {i['qty']}" for i in out["items"])
    return None


def _llm_values(steps: list[dict], upto: int) -> set[str]:
    vals: set[str] = set()
    for s in steps[:upto]:
        if s["kind"] == "llm" and isinstance(s.get("output"), dict):
            vals |= entities(s["output"].get("memory_update") or {})
    return vals


def _rerun_llm(run: dict, k: int, load_checkpoint) -> Optional[dict]:
    """Ask the policy for step k again, starting from the checkpoint after step k-1."""
    from .runner import get_policy
    from .tasks import make_task

    steps = sorted(run["steps"], key=lambda s: s["idx"])
    if k == 0 or run.get("policy", "sim") != "sim":
        return None
    cp = load_checkpoint(steps[k - 1].get("checkpoint_id"))
    if not cp:
        return None
    task, _ = make_task(run["task_family"], run["seed"])
    action = get_policy("sim").decide(task, cp["agent_state"], k, run["seed"])
    if action.get("kind") != "llm":
        return None
    return action.get("output")


__all__ = ["propose_fix", "POLICY_DOCS"]
