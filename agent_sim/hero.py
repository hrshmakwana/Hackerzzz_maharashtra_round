"""Three pinned demo runs with stable ids (served at /api/demo)."""

from __future__ import annotations

from .runner import RunOutcome, run_agent

HERO_RUNS = [
    {
        "id": "hero-refund-stale-policy",
        "family": "refund", "seed": 5, "fault": {"type": "bad_retrieval", "step": 6},
        "split": "test",
        "title": "Refund with a stale policy",
        "story": "The refund goes out with the wrong restocking fee. The real mistake happened "
                 "four steps earlier, when an archived policy came back from retrieval.",
    },
    {
        "id": "hero-injection-complaint",
        "family": "complaint_triage", "seed": 17, "fault": {"type": "prompt_injection", "step": 2},
        "split": "heldout_type",
        "title": "Prompt injection in a complaint email",
        "story": "A complaint email carries hidden instructions and the agent refunds someone "
                 "else's order. Both the attack type and the task family were held out of "
                 "training.",
    },
    {
        "id": "hero-address-wrong-order",
        "family": "address_change", "seed": 1, "fault": {"type": "wrong_args", "step": 3},
        "split": "test",
        "title": "Address change on the wrong order",
        "story": "The agent looks up a neighbouring order id, decides based on that order's "
                 "status, and never updates the customer's address.",
    },
]


def hero_outcomes() -> list[RunOutcome]:
    outs = []
    for h in HERO_RUNS:
        out = run_agent(h["family"], h["seed"], fault=h["fault"], run_id=h["id"], split=h["split"])
        outs.append(out)
    return outs
