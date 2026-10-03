"""Per-step feature extraction.

Only reads what is observable in the trace: steps, their inputs and outputs.
Ground-truth labels on the run row are never touched here.

Each step gets a flat dict of numeric features plus a ``details`` dict (which values were
ungrounded, which observation a note contradicts, ...) that the explainer turns into
human-readable evidence.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

TOOL_NAMES = ["search_customer", "get_order", "list_orders", "retrieve_policy", "calculate",
              "issue_refund", "update_address", "cancel_order", "read_email", "send_email"]
NAMES = TOOL_NAMES + ["llm", "plan", "finish"]
KINDS = ["plan", "llm", "tool", "retrieval", "final"]
SIDE_EFFECT_TOOLS = {"issue_refund", "update_address", "cancel_order", "send_email"}

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RE_MONEY = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)")
RE_IDENT = re.compile(r"\b(?:[A-Z]{1,4}-)+[A-Z0-9]{2,}\b")
RE_NUM = re.compile(r"(?<![\w.#-])#?(\d+(?:\.\d+)?)(?![\w-]|\.\d)")
INSTRUCTION_PATTERNS = [
    r"ignore (?:all )?previous", r"system instruction", r"\byou must\b",
    r"no need to mention", r"do not (?:mention|tell|ask)", r"note for the (?:support )?assistant",
    r"\bassistant\b", r"as approved by", r"\bimportant\b", r"for verification",
]
RE_INSTR = [re.compile(p, re.I) for p in INSTRUCTION_PATTERNS]
RE_IMPERATIVE = re.compile(r"(?:^|[.!?]\s+|:\s+)(issue|forward|send|cancel|refund|transfer|"
                           r"ignore|delete|wire|share)\b", re.I)
# memory keys that restate something a tool reported -> (tool, field)
OBSERVED_FIELDS = {
    "order_amount": ("get_order", "amount"),
    "order_status": ("get_order", "status"),
    "order_id": ("get_order", "order_id"),
    "customer_tier": ("search_customer", "tier"),
    "customer_email": ("read_email", "from"),
    "subtotal": ("calculate", "result"),
}
IGNORED_NUMBERS = {"0", "1", "100"}


# ----------------------------------------------------------------- entities


def norm_num(text: str) -> str | None:
    try:
        x = float(str(text).replace(",", ""))
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")


def _leaves(obj: Any, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v, key)
    else:
        yield key, obj


def entities(obj: Any) -> set[str]:
    """Numbers, money, ids, emails and dates mentioned anywhere in a JSON value."""
    out: set[str] = set()
    for key, v in _leaves(obj):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            n = norm_num(v)
            if n is not None:
                out.add(n)
            continue
        text = str(v)
        if key.endswith("_id") and text.strip().lstrip("#").isdigit():
            out.add(text.strip().lstrip("#"))
            continue
        for e in RE_EMAIL.findall(text):
            out.add(e.lower())
        text = RE_EMAIL.sub(" ", text)
        for d in RE_DATE.findall(text):
            out.add(d)
        text = RE_DATE.sub(" ", text)
        for m in RE_MONEY.findall(text):
            n = norm_num(m)
            if n:
                out.add(n)
        text = RE_MONEY.sub(" ", text)
        for ident in RE_IDENT.findall(text):
            out.add(ident)
        text = RE_IDENT.sub(" ", text)
        for m in RE_NUM.findall(text):
            n = norm_num(m)
            if n:
                out.add(n)
    return out


RE_ORDER_REF = re.compile(r"(?:#|order\s+#?)(\d{3,6})\b", re.I)


def order_ids_in(obj: Any) -> set[str]:
    """Order ids mentioned in a value: ``order_id`` fields, ``order_ids`` lists, ``#1043``."""
    out: set[str] = set()
    for key, v in _leaves(obj):
        if v is None or isinstance(v, bool):
            continue
        if key in ("order_id", "order_ids"):
            out.add(str(v).strip().lstrip("#"))
        elif isinstance(v, str):
            out.update(RE_ORDER_REF.findall(v))
    return out


def emails_in(obj: Any) -> set[str]:
    return {e.lower() for _, v in _leaves(obj) if isinstance(v, str) for e in RE_EMAIL.findall(v)}


def ownership(run: dict, steps: list[dict]) -> tuple[set[str], set[str]]:
    """Order ids and email addresses that legitimately belong to this request: the
    requester's address, the order the email is about, the requester's own order list,
    and anything the task text or the policy documents mention."""
    requester, cust_id = None, None
    orders = order_ids_in(run.get("task_text", ""))
    emails = emails_in(run.get("task_text", ""))
    for s in steps:
        out = s.get("output") if isinstance(s.get("output"), dict) else None
        if not out or s.get("error"):
            continue
        if s["name"] == "read_email" and requester is None:
            requester = str(out.get("from", "")).lower()
            emails.add(requester)
            orders |= order_ids_in(out.get("subject", ""))
        elif s["name"] == "search_customer" and str(out.get("email", "")).lower() == requester:
            cust_id = out.get("customer_id")
            orders |= {str(o) for o in out.get("order_ids", [])}
        elif s["name"] == "list_orders" and cust_id and out.get("customer_id") == cust_id:
            orders |= {str(o.get("order_id")) for o in out.get("orders", [])}
        elif s["kind"] == "retrieval":
            emails |= emails_in(out)
    return orders, emails


def text_of(obj: Any) -> str:
    return " ".join(str(v) for _, v in _leaves(obj) if isinstance(v, str))


def token_of(step: dict) -> str:
    """Transition token: tool name, or the llm instruction's first words."""
    if step["kind"] == "llm":
        instr = str((step.get("input") or {}).get("instruction", ""))
        return "llm:" + " ".join(instr.lower().split()[:3])
    return step["name"]


def sig_of(step: dict) -> str:
    return step["name"] + json.dumps(step.get("input"), sort_keys=True, ensure_ascii=False)


# --------------------------------------------------------- transition model


@dataclass
class TransitionModel:
    """Bigram model of step tokens, fit on successful runs only."""

    counts: dict = field(default_factory=dict)
    totals: dict = field(default_factory=dict)
    vocab: int = 1

    @classmethod
    def fit(cls, runs: Iterable[dict]) -> "TransitionModel":
        counts: dict = defaultdict(Counter)
        vocab = set()
        for r in runs:
            prev = "<start>"
            for s in r["steps"]:
                t = token_of(s)
                counts[prev][t] += 1
                vocab.add(t)
                prev = t
            counts[prev]["<end>"] += 1
        return cls({k: dict(v) for k, v in counts.items()},
                   {k: sum(v.values()) for k, v in counts.items()}, len(vocab) + 2)

    def surprisal(self, prev: str, cur: str) -> float:
        c = self.counts.get(prev, {}).get(cur, 0)
        total = self.totals.get(prev, 0)
        return -math.log((c + 0.1) / (total + 0.1 * self.vocab))

    def to_json(self) -> dict:
        return {"counts": self.counts, "vocab": self.vocab}

    @classmethod
    def from_json(cls, d: dict) -> "TransitionModel":
        counts = d["counts"]
        return cls(counts, {k: sum(v.values()) for k, v in counts.items()}, d["vocab"])


# ------------------------------------------------------------------ features


def _z(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mu = sum(values) / len(values)
    sd = math.sqrt(sum((v - mu) ** 2 for v in values) / len(values)) or 1.0
    return [(v - mu) / sd for v in values]


def _instruction_score(text: str) -> tuple[int, int]:
    return sum(1 for p in RE_INSTR if p.search(text)), len(RE_IMPERATIVE.findall(text))


def step_features(run: dict, tm: TransitionModel | None = None) -> list[dict]:
    """Return ``[{"f": {name: value}, "details": {...}}, ...]`` for each step of a run."""
    steps = sorted(run["steps"], key=lambda s: s["idx"])
    n = len(steps)
    task_ents = entities(run.get("task_text", ""))

    in_ents = [entities(s.get("input")) for s in steps]
    out_ents = [entities(s.get("output")) if not s.get("error") else set() for s in steps]
    sigs = [sig_of(s) for s in steps]
    tokens = [token_of(s) for s in steps]
    lat_z = _z([float(s.get("latency_ms") or 0) for s in steps])
    tok_z = _z([float((s.get("tokens_in") or 0) + (s.get("tokens_out") or 0)) for s in steps])
    side_ok = [s["name"] in SIDE_EFFECT_TOOLS and not s.get("error") and s["kind"] == "tool"
               for s in steps]

    own_orders, own_emails = ownership(run, steps)
    foreign_args: list[set[str]] = []
    for s in steps:
        a = s.get("input") or {}
        if s["name"] in SIDE_EFFECT_TOOLS and s["kind"] == "tool":
            fa = {o for o in order_ids_in(a) if o not in own_orders}
            fa |= {e for e in emails_in(a) if e not in own_emails}
        else:
            fa = set()
        foreign_args.append(fa)
    seen_refs: set[str] = set()

    grounded = set(task_ents)  # task text + tool/retrieval observations
    context = set(task_ents)  # + everything the agent itself wrote
    memory: dict[str, str] = {}
    latest_obs: dict[tuple, Any] = {}
    introduced: list[set[str]] = []
    rows: list[dict] = []

    for i, s in enumerate(steps):
        f: dict[str, float] = {}
        det: dict[str, Any] = {}
        kind, name = s["kind"], s["name"]
        out = s.get("output") if isinstance(s.get("output"), dict) else {}
        err = s.get("error")

        for k in KINDS:
            f[f"kind_{k}"] = float(kind == k)
        for nm in NAMES:
            f[f"name_{nm}"] = float(name == nm)
        f["pos_rel"] = i / max(1, n - 1)
        f["steps_to_end"] = float(n - 1 - i)
        f["idx"] = float(i)
        f["n_steps"] = float(n)

        # -- provenance of the arguments
        args = {k: v for k, v in (s.get("input") or {}).items() if k not in ("instruction", "task",
                                                                             "memory_keys")}
        arg_ents = entities(args)
        ungrounded_args = sorted(e for e in arg_ents if e not in grounded and e not in context
                                 and e not in IGNORED_NUMBERS)
        weak_args = sorted(e for e in arg_ents if e not in grounded and e not in IGNORED_NUMBERS)
        if kind in ("tool", "retrieval", "final") and arg_ents:
            f["arg_provenance"] = 1 - len(ungrounded_args) / len(arg_ents)
            f["arg_observed_frac"] = 1 - len(weak_args) / len(arg_ents)
        else:
            f["arg_provenance"] = 1.0
            f["arg_observed_frac"] = 1.0
        f["arg_ungrounded"] = float(len(ungrounded_args) if kind != "llm" else 0)
        det["ungrounded_args"] = ungrounded_args if kind != "llm" else []

        # -- novelty of what the step produced
        novel = sorted(e for e in out_ents[i] if e not in context and e not in IGNORED_NUMBERS)
        f["novel_entities"] = float(len(novel))
        det["novel"] = novel[:6]
        mu = out.get("memory_update") or {} if kind == "llm" else {}
        mu_ents = entities({k: v for k, v in mu.items() if k != "recheck"})
        llm_ungrounded = sorted(e for e in mu_ents if e not in grounded and e not in IGNORED_NUMBERS)
        f["llm_ungrounded"] = float(len(llm_ungrounded))
        det["llm_ungrounded"] = llm_ungrounded
        f["memory_update_size"] = float(len(mu))
        f["llm_extra_actions"] = float(len(out.get("extra_actions") or [])) if kind == "llm" else 0.0

        # -- memory overwrites and contradictions with what tools reported
        overwrites, contradictions = [], []
        for k, v in mu.items():
            if k == "recheck" and isinstance(v, dict):
                obs = latest_obs.get(("get_order", v.get("field")))
                if obs is not None and str(v.get("expect")) != str(obs):
                    contradictions.append({"key": f"recheck.{v.get('field')}",
                                           "value": v.get("expect"), "observed": obs})
                continue
            nv = json.dumps(v, sort_keys=True)
            if k in memory and memory[k] != nv:
                overwrites.append({"key": k, "old": json.loads(memory[k]), "new": v})
            if k in OBSERVED_FIELDS:
                obs = latest_obs.get(OBSERVED_FIELDS[k])
                if obs is not None and _norm(obs) != _norm(v):
                    contradictions.append({"key": k, "value": v, "observed": obs})
        f["memory_overwrite"] = float(len(overwrites))
        f["memory_contradiction"] = float(len(contradictions))
        det["overwrites"], det["contradictions"] = overwrites, contradictions

        # -- errors
        f["error_present"] = float(bool(err))
        nxt = steps[i + 1] if i + 1 < n else None
        retried = bool(err) and nxt is not None and sigs[i + 1] == sigs[i]
        f["error_retried"] = float(retried)
        f["error_then_continue"] = float(bool(err) and not retried)
        f["prior_errors"] = float(sum(1 for p in steps[:i] if p.get("error")))

        # -- retrieval
        if kind == "retrieval" and out:
            q = set(re.findall(r"[a-z0-9]+", str(args.get("query", "")).lower()))
            d = set(re.findall(r"[a-z0-9]+", f"{out.get('title', '')} {out.get('topic', '')}".lower()))
            f["retrieval_score"] = float(out.get("score") or 0)
            f["retrieval_doc_current"] = float(out.get("status") == "current")
            f["retrieval_doc_archived"] = float(out.get("status") == "archived")
            f["query_doc_overlap"] = len(q & d) / max(1, len(q | d))
            later = [j for j in range(i + 1, min(n, i + 3)) if steps[j]["kind"] == "retrieval"]
            f["retrieval_requeried"] = float(bool(later))
            det["doc"] = {k: out.get(k) for k in ("doc_id", "version", "status", "updated")}
        else:
            f["retrieval_score"] = 0.0
            f["retrieval_doc_current"] = 0.0
            f["retrieval_doc_archived"] = 0.0
            f["query_doc_overlap"] = 0.0
            f["retrieval_requeried"] = 0.0

        # -- calculation consistency
        if name == "calculate":
            nums = [norm_num(x) for x in re.findall(r"\d+(?:\.\d+)?", str(args.get("expression", "")))]
            nums = [x for x in nums if x and x not in IGNORED_NUMBERS]
            bad = sorted({x for x in nums if x not in grounded and x not in context})
            f["calc_consistency"] = 1 - len(bad) / max(1, len(nums))
            det["calc_unexplained"] = bad
        else:
            f["calc_consistency"] = 1.0

        # -- repetition and progress
        f["repeat_count"] = float(sum(1 for j in range(i) if sigs[j] == sigs[i]))
        f["future_repeats"] = float(sum(1 for j in range(i + 1, n) if sigs[j] == sigs[i]))
        prev_same = [j for j in range(i) if sigs[j] == sigs[i]]
        same_out = bool(prev_same) and steps[prev_same[-1]].get("output") == s.get("output")
        f["no_progress_repeat"] = float(same_out)
        f["progress_delta"] = float(len(novel))

        # -- instruction-like text in what the agent read
        instr, imper = _instruction_score(text_of(s.get("output"))) if kind in ("tool", "retrieval") else (0, 0)
        f["instruction_likeness"] = float(instr)
        f["imperatives"] = float(imper)
        det["instruction_hits"] = instr

        # -- plan claims vs. what actually follows
        remaining = (out.get("plan_update") or {}).get("remaining") if kind == "llm" else None
        f["claims_progress"] = float(remaining is not None)
        f["claimed_remaining"] = float(len(remaining)) if remaining is not None else -1.0
        f["side_effects_after"] = float(sum(side_ok[i + 1:]))
        f["side_effects_before"] = float(sum(side_ok[:i]))
        f["skips"] = float(len(out.get("skip") or [])) if kind == "llm" else 0.0

        # -- transitions vs. successful runs
        if tm is not None:
            f["transition_surprisal"] = tm.surprisal(tokens[i - 1] if i else "<start>", tokens[i])
            f["next_surprisal"] = tm.surprisal(tokens[i], tokens[i + 1] if i + 1 < n else "<end>")
        else:
            f["transition_surprisal"] = 0.0
            f["next_surprisal"] = 0.0

        f["latency_z"] = lat_z[i]
        f["tokens_z"] = tok_z[i]

        # -- foreign ids/addresses: where did they enter, where are they acted on
        refs = order_ids_in(s.get("input")) | emails_in(s.get("input"))
        if not err:
            refs |= order_ids_in(s.get("output")) | emails_in(s.get("output"))
        new_refs = refs - seen_refs
        seen_refs |= refs
        later_foreign = set().union(*foreign_args[i:]) if i < n else set()
        entered = sorted(new_refs & later_foreign)
        f["foreign_introduced"] = float(len(entered))
        f["foreign_in_args"] = float(len(foreign_args[i]))
        det["foreign_introduced"] = entered
        det["foreign_in_args"] = sorted(foreign_args[i])

        # what this step brought into the context for the first time
        intro = (out_ents[i] | (mu_ents if kind == "llm" else set()) | arg_ents) - context
        intro -= IGNORED_NUMBERS
        introduced.append(intro)
        rows.append({"f": f, "details": det})

        # -- update running context
        context |= in_ents[i] | out_ents[i]
        if kind in ("tool", "retrieval") and not err:
            grounded |= out_ents[i]
            if isinstance(s.get("output"), dict):
                for k, v in s["output"].items():
                    if not isinstance(v, (dict, list)):
                        latest_obs[(name, k)] = v
        for k, v in mu.items():
            if k != "recheck":
                memory[k] = json.dumps(v, sort_keys=True)

    # -- how much later work depends on values introduced at each step
    for i, row in enumerate(rows):
        intro = introduced[i]
        users = [j for j in range(i + 1, n) if intro & in_ents[j]]
        row["f"]["downstream_dependence"] = float(len(users))
        row["f"]["downstream_side_effects"] = float(sum(1 for j in users if side_ok[j]))
        row["f"]["introduced"] = float(len(intro))
        row["details"]["used_by"] = users[:6]
    return rows


def _norm(v: Any) -> str:
    n = norm_num(v) if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"[\d.,]+", v or "")) else None
    return n if n is not None else str(v).strip().lower().lstrip("#")


def feature_names(tm_present: bool = True) -> list[str]:
    demo = {"task_text": "", "steps": [{"idx": 0, "kind": "plan", "name": "plan", "input": {},
                                        "output": {}}]}
    return list(step_features(demo, TransitionModel() if tm_present else None)[0]["f"].keys())


def run_matrix(run: dict, tm: TransitionModel | None, names: list[str]) -> tuple[list[list[float]], list[dict]]:
    rows = step_features(run, tm)
    return [[r["f"][k] for k in names] for r in rows], rows


RUN_AGG = ["arg_ungrounded", "llm_ungrounded", "memory_overwrite", "memory_contradiction",
           "error_present", "error_then_continue", "retrieval_doc_archived", "retrieval_requeried",
           "repeat_count", "no_progress_repeat", "instruction_likeness", "llm_extra_actions",
           "transition_surprisal", "next_surprisal", "claims_progress", "novel_entities",
           "downstream_side_effects"]


def run_features(run: dict, tm: TransitionModel | None) -> dict:
    """Run-level aggregates for the failure classifier."""
    rows = step_features(run, tm)
    steps = run["steps"]
    out = {"n_steps": float(len(steps)),
           "finished": float(any(s["kind"] == "final" for s in steps)),
           "n_side_effects": float(sum(1 for s in steps if s["name"] in SIDE_EFFECT_TOOLS
                                       and not s.get("error"))),
           "n_llm": float(sum(1 for s in steps if s["kind"] == "llm")),
           "n_retrievals": float(sum(1 for s in steps if s["kind"] == "retrieval"))}
    for k in RUN_AGG:
        vals = [r["f"][k] for r in rows]
        out[f"max_{k}"] = max(vals)
        out[f"sum_{k}"] = sum(vals)
    # archived doc that was *not* followed by a re-query
    out["stale_doc_kept"] = float(any(r["f"]["retrieval_doc_archived"] and not r["f"]["retrieval_requeried"]
                                      for r in rows))
    return out
