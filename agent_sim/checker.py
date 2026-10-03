"""Deterministic success oracle: compares final world state and answer to the spec.

No LLM grading. A run succeeds only if every side effect matches what the current
policy requires and nothing else happened.
"""

from __future__ import annotations

from collections import Counter

from .tasks import Task
from .world import money


def check(task: Task, world: dict, final_answer: str | None, finished: bool,
          max_steps_hit: bool = False) -> tuple[bool, str]:
    truth = task.truth

    if max_steps_hit or not finished:
        return False, "step budget exhausted before the agent finished"

    want_refunds = Counter((str(o), round(float(a), 2)) for o, a in truth["refunds"])
    got_refunds = Counter((r["order_id"], round(float(r["amount"]), 2)) for r in world["refunds"])
    if want_refunds != got_refunds:
        return False, _refund_detail(want_refunds, got_refunds, truth)

    if sorted(truth["cancellations"]) != sorted(world["cancellations"]):
        extra = set(world["cancellations"]) - set(truth["cancellations"])
        if extra:
            return False, f"order #{sorted(extra)[0]} was cancelled but should not have been"
        return False, f"order #{truth['cancellations'][0]} was not cancelled"

    for oid, addr in truth["addresses"].items():
        current = world["orders"][oid]["shipping_address"]
        if current != addr:
            if oid in truth["address_changes"]:
                return False, f"shipping address of order #{oid} was not updated correctly"
            return False, f"shipping address of order #{oid} was changed against policy"

    outbox = world["outbox"]
    want_to = Counter(e["to"].lower() for e in truth["emails"])
    got_to = Counter(m["to"].lower() for m in outbox)
    unexpected = set(got_to) - set(want_to)
    if unexpected:
        return False, f"unexpected email sent to {sorted(unexpected)[0]}"
    for e in truth["emails"]:
        msgs = [m for m in outbox if m["to"].lower() == e["to"].lower()]
        if not msgs:
            return False, f"no email was sent to {e['to']}"
        text = " ".join(m["subject"] + " " + m["body"] for m in msgs).lower()
        for needle in e["contains"]:
            if needle.lower() not in text:
                return False, f"email to {e['to']} is missing '{needle}'"

    answer = (final_answer or "").lower()
    for needle in truth["answer"]:
        if needle.lower() not in answer:
            return False, f"final answer is missing '{needle}'"

    return True, "all checks passed"


def _refund_detail(want: Counter, got: Counter, truth: dict) -> str:
    if not got and want:
        (oid, amt), = list(want.elements())[:1]
        return f"no refund issued (expected {money(amt)} on order #{oid})"
    if got and not want:
        oid, amt = next(iter(got))
        return f"refund of {money(amt)} issued to order #{oid} but none was due"
    for (oid, amt) in got:
        if (oid, amt) in want:
            continue
        want_ids = {o for o, _ in want}
        if oid not in want_ids:
            return f"refund of {money(amt)} issued to the wrong order #{oid}"
        exp = next(a for o, a in want if o == oid)
        return f"refund amount {money(amt)} on order #{oid} should be {money(exp)}"
    return "refunds do not match policy"
