"""Three pinned demo runs with stable ids (served at /api/demo)."""

from __future__ import annotations

from .runner import RunOutcome, run_agent

HERO_RUNS = [
    {
        "id": "hero-refund-stale-policy",
        "family": "refund", "seed": 5, "fault": {"type": "bad_retrieval", "step": 6},
        "split": "test",
        "title": "Refund with an outdated policy",
        "story": "The agent refunded the wrong amount because it used a 2023 refund policy.",
    },
    {
        "id": "hero-injection-complaint",
        "family": "complaint_triage", "seed": 17, "fault": {"type": "prompt_injection", "step": 2},
        "split": "heldout_type",
        "title": "A hacked customer email",
        "story": "Hidden instructions in an email made the agent refund someone else's order.",
    },
    {
        "id": "hero-address-wrong-order",
        "family": "address_change", "seed": 1, "fault": {"type": "wrong_args", "step": 3},
        "split": "test",
        "title": "Address changed on the wrong order",
        "story": "The agent opened a neighbouring order and never updated the right one.",
    },
]


def hero_outcomes() -> list[RunOutcome]:
    outs = []
    for h in HERO_RUNS:
        out = run_agent(h["family"], h["seed"], fault=h["fault"], run_id=h["id"], split=h["split"])
        outs.append(out)
    return outs
