from sqlmodel import Session, select

from agent_sim.runner import run_agent
from agent_sim.tasks import FAMILIES
from backend import db
from backend.models import Step
from backend.store import load_run, save_run
from blackbox_sdk import Recorder, verify_chain


def _sig(steps):
    return [(s.kind, s.name, s.input, s.output, s.error) for s in steps]


def test_same_seed_same_hashes():
    for fam in FAMILIES:
        a = run_agent(fam, 11, run_id="r-fixed", keep_checkpoints=False).record
        b = run_agent(fam, 11, run_id="r-fixed", keep_checkpoints=False).record
        assert [s.hash for s in a.steps] == [s.hash for s in b.steps]
        assert a.chain_head == b.chain_head


def test_clean_runs_mostly_succeed():
    total = ok = 0
    for fam in FAMILIES:
        for seed in range(40):
            out = run_agent(fam, seed, keep_checkpoints=False)
            total += 1
            ok += out.success
            assert 8 <= len(out.record.steps) <= 25
    assert ok / total >= 0.95


def test_clean_runs_contain_benign_noise():
    errors = requeries = 0
    for fam in FAMILIES:
        for seed in range(40):
            steps = run_agent(fam, seed, keep_checkpoints=False).record.steps
            errors += sum(1 for s in steps if s.error)
            requeries += sum(1 for s in steps if s.name == "retrieve_policy") > 1
    assert errors > 5 and requeries > 5


def test_tampering_breaks_the_chain(tmp_path):
    engine = db.init_db(db.get_engine(f"sqlite:///{tmp_path}/t.db"))
    out = run_agent("refund", 3)
    save_run(engine, out.record, {})
    with Session(engine) as s:
        run = load_run(s, out.record.id)
        assert verify_chain(run["id"], run["steps"]) == {"valid": True, "broken_at": None}
        row = s.exec(select(Step).where(Step.run_id == out.record.id, Step.idx == 4)).one()
        row.output = {**(row.output or {}), "amount": 1.0}
        s.add(row)
        s.commit()
        run = load_run(s, out.record.id)
    assert verify_chain(run["id"], run["steps"]) == {"valid": False, "broken_at": 4}


def test_resume_from_checkpoint_reproduces_suffix():
    for fam in FAMILIES:
        rec = Recorder(task_family=fam)
        out = run_agent(fam, 5, recorder=rec)
        steps = out.record.steps
        for k in (1, 3, len(steps) // 2, len(steps) - 1):
            cp = rec.checkpoints[steps[k - 1].checkpoint_id]
            start = {"prefix": [s.model_dump() for s in steps[:k]],
                     "agent_state": cp.agent_state, "world_state": cp.world_state,
                     "tags": out.tags[:k]}
            fork = run_agent(fam, 5, start=start)
            assert fork.record.steps_reused == k
            assert all(s.reused for s in fork.record.steps[:k])
            assert _sig(fork.record.steps[k:]) == _sig(steps[k:])
            assert fork.record.status == out.record.status


def test_recorder_decorator_and_errors():
    rec = Recorder()

    @rec.tool
    def add(a, b):
        return {"sum": a + b}

    add(2, 3)
    try:
        with rec.step("tool", "boom", {"x": 1}):
            raise RuntimeError("nope")
    except RuntimeError:
        pass
    run = rec.finish("fail", "boom failed")
    assert [s.name for s in run.steps] == ["add", "boom"]
    assert run.steps[0].input == {"a": 2, "b": 3} and run.steps[0].output == {"sum": 5}
    assert run.steps[1].error == "RuntimeError: nope"
    assert verify_chain(run.id, run.steps)["valid"]
