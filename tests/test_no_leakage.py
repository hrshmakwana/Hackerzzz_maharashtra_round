"""Ground truth must stay on the run row. Steps (and checkpoints) carry no trace of it."""

import re
from pathlib import Path

from agent_sim.faults import FAULT_TYPES
from agent_sim.generate import build_specs, simulate
from agent_sim.runner import run_agent
from blackbox_sdk import canonical_json

ROOT = Path(__file__).resolve().parent.parent
MARKERS = re.compile(r"\bfault|inject|halluc|corrupt|ground.?truth", re.I)
LLM_OUTPUT_KEYS = {"thought", "memory_update", "skip", "plan_update", "extra_actions"}


def _faulty_sample(n_per_type=6):
    specs = [s for s in build_specs(1200) if s["fault"]]
    seen = {t: 0 for t in FAULT_TYPES}
    for spec in specs:
        if seen[spec["fault"]] >= n_per_type:
            continue
        out, final = simulate(spec, keep_checkpoints=True)
        if out is None:
            continue
        seen[spec["fault"]] += 1
        yield out
    assert all(v == n_per_type for v in seen.values()), seen


def test_steps_and_checkpoints_carry_no_fault_markers():
    for out in _faulty_sample():
        for s in out.record.steps:
            text = canonical_json([s.kind, s.name, s.input, s.output, s.error])
            assert not MARKERS.search(text), (out.record.fault_type, s.idx, text[:200])
        for cp in out.checkpoints.values():
            assert not MARKERS.search(canonical_json(cp.agent_state))


def test_faulty_steps_use_the_same_shapes_as_clean_steps():
    clean_keys: dict[str, set] = {}
    for fam in ("refund", "address_change", "discount_quote", "cancel", "complaint_triage"):
        for seed in range(30):
            for s in run_agent(fam, seed, keep_checkpoints=False).record.steps:
                clean_keys.setdefault(s.name, set()).update(s.input.keys())
    for out in _faulty_sample(3):
        for s in out.record.steps:
            assert set(s.input) <= clean_keys[s.name], (s.name, s.input)
            if s.kind == "llm":
                assert set(s.output) <= LLM_OUTPUT_KEYS


def test_feature_code_never_reads_ground_truth():
    for path in (ROOT / "ml" / "features.py", ROOT / "ml" / "explain.py"):
        src = path.read_text()
        assert not re.search(r"\bfault", src, re.I), f"{path.name} mentions fault columns"
