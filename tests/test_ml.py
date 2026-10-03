import math

import pytest

from agent_sim.generate import build_specs, simulate
from agent_sim.repair import propose_fix
from agent_sim.replay import fork_run
from agent_sim.runner import run_agent
from ml.common import models_available
from ml.features import feature_names, step_features

needs_model = pytest.mark.skipif(not models_available(), reason="run `make train` first")


def _record(spec_fault, n=1):
    out = []
    for spec in build_specs(1500):
        if spec["fault"] != spec_fault:
            continue
        o, final = simulate(spec, keep_checkpoints=True)
        if o is not None:
            out.append(o)
        if len(out) == n:
            return out
    return out


def test_features_are_finite_and_complete():
    names = feature_names()
    run = run_agent("refund", 4, keep_checkpoints=False).record.model_dump(mode="json")
    rows = step_features(run)
    assert len(rows) == len(run["steps"])
    for r in rows:
        assert set(names) == set(r["f"])
        assert all(math.isfinite(v) for v in r["f"].values())


def test_autofix_at_the_faulty_step_flips_bad_retrieval():
    (o,) = _record("bad_retrieval")
    run = o.record.model_dump(mode="json")
    load = lambda cid: o.checkpoints[cid].model_dump()  # noqa: E731
    k = run["fault_step"]
    fix = propose_fix(run, k, load_checkpoint=load)
    assert fix and fix["edit"]["type"] == "swap_document"
    fork = fork_run(run, k, [fix["edit"]], load_checkpoint=load)
    assert run["status"] == "fail" and fork.record.status == "success"
    assert fork.record.steps_reused == k
    assert all(s.reused for s in fork.record.steps[:k])


def test_steps_without_visible_problems_get_no_fix():
    run_out = run_agent("cancel", 9)
    run = run_out.record.model_dump(mode="json")
    load = lambda cid: run_out.checkpoints[cid].model_dump()  # noqa: E731
    fixes = [propose_fix(run, s["idx"], load_checkpoint=load) for s in run["steps"]
             if not s.get("error")]
    assert all(f is None for f in fixes)


@needs_model
def test_diagnosis_ranks_every_step():
    from ml.explain import diagnose

    (o,) = _record("wrong_args")
    run = o.record.model_dump(mode="json")
    d = diagnose(run)
    assert len(d["ranking"]) == len(run["steps"])
    assert abs(sum(r["prob"] for r in d["ranking"]) - 1) < 1e-3
    assert d["ranking"][0]["idx"] == run["fault_step"]
    assert d["ranking"][0]["evidence"] and d["ranking"][0]["shap"]
