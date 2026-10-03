import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("api")
    mp.setenv("DATABASE_URL", f"sqlite:///{tmp}/api.db")
    mp.setenv("SEED_RUNS_ON_START", "0")
    from agent_sim.generate import seed_database
    from backend import db
    from backend.main import app

    mp.delenv("GEMINI_API_KEY", raising=False)  # after imports: they load .env

    engine = db.init_db()
    seed_database(80, engine)
    with TestClient(app) as c:
        yield c
    mp.undo()


def test_health_and_meta(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["runs"] >= 80 and h["gemini"] is False
    meta = client.get("/api/meta").json()
    assert "refund" in meta["families"] and "prompt_injection" in meta["fault_types"]


def test_list_and_filters(client):
    page = client.get("/api/runs", params={"limit": 10}).json()
    assert page["total"] >= 80 and len(page["items"]) == 10
    fails = client.get("/api/runs", params={"status": "fail", "limit": 500}).json()
    assert fails["items"] and all(r["status"] == "fail" for r in fails["items"])
    fam = client.get("/api/runs", params={"family": "cancel", "limit": 500}).json()
    assert all(r["task_family"] == "cancel" for r in fam["items"])


def test_run_detail_verify_and_state(client):
    run = client.get("/api/runs/hero-refund-stale-policy").json()
    assert run["status"] == "fail" and len(run["steps"]) == 14
    assert any(e["kind"] == "data" for e in run["edges"])
    assert client.get("/api/runs/hero-refund-stale-policy/verify").json()["valid"] is True
    state = client.get("/api/runs/hero-refund-stale-policy/steps/6/state").json()
    assert state["after"]["agent_state"]["memory"]["policy"]["doc_id"] == "refund-v1"
    assert any(d["path"].startswith("agent.memory.policy") for d in state["diff"])
    assert client.get("/api/runs/nope").status_code == 404


def test_diagnose_points_at_the_canon_event(client):
    d = client.post("/api/runs/hero-refund-stale-policy/diagnose", params={"report": True}).json()
    assert d["canon_event"]["idx"] == 6
    assert d["ground_truth"] == {"step": 6, "type": "bad_retrieval"}
    assert d["suggested_fix"]["edit"]["type"] == "swap_document"
    assert d["report_source"] == "template" and "Canon Event" in d["report_md"]
    again = client.get("/api/runs/hero-refund-stale-policy/diagnosis").json()
    assert again["canon_event"]["idx"] == 6


def test_fork_reuses_exactly_k_steps(client):
    res = client.post("/api/runs/hero-refund-stale-policy/fork", json={"step": 6, "edits": []}).json()
    assert res["savings"]["steps_reused"] == 6
    fork = client.get(f"/api/runs/{res['id']}").json()
    assert [s["reused"] for s in fork["steps"][:6]] == [True] * 6
    assert not any(s["reused"] for s in fork["steps"][6:])
    assert fork["parent_run_id"] == "hero-refund-stale-policy" and fork["fork_step_idx"] == 6
    assert res["status"] == "fail"  # replaying without a change reproduces the failure


def test_autofix_flips_bad_retrieval_and_compare(client):
    res = client.post("/api/runs/hero-refund-stale-policy/autofix", params={"step": 6}).json()
    assert res["flipped"] is True and res["fix"]["edit"]["type"] == "swap_document"
    cmp = client.get("/api/compare", params={"a": "hero-refund-stale-policy", "b": res["id"]}).json()
    assert cmp["is_fork"] and cmp["outcome"]["flipped"]
    assert cmp["fork_step"] == 6 and cmp["divergence"]["a"] == 6
    assert cmp["savings"]["steps_reused"] == 6 and cmp["savings"]["tokens_saved"] > 0


def test_autofix_without_a_visible_problem_is_refused(client):
    r = client.post("/api/runs/hero-refund-stale-policy/autofix", params={"step": 1})
    assert r.status_code == 422


def test_sweep_finds_flips(client):
    flips = 0
    runs = client.get("/api/runs", params={"status": "fail", "forks": False, "limit": 500}).json()["items"]
    sample = [r for r in runs if r["fault_type"] and not r["id"].startswith("hero")][:20]
    for r in sample:
        res = client.post(f"/api/runs/{r['id']}/sweep", params={"top_k": 3}).json()
        assert len(res["universes"]) == 3
        flips += res["confirmed_step"] is not None
    rate = flips / len(sample)
    print(f"sweep flip rate on {len(sample)} failed runs: {rate:.0%}")
    assert rate >= 0.6


def test_sweep_confirms_hero_injection(client):
    res = client.post("/api/runs/hero-injection-complaint/sweep", params={"top_k": 3}).json()
    assert res["confirmed_step"] == 2


def test_live_run_streams_steps(client):
    started = client.post("/api/runs", json={"family": "cancel", "seed": 42, "delay_ms": 0,
                                             "fault": {"type": "ignored_error"}}).json()
    rid = started["id"]
    events = []
    with client.stream("GET", f"/api/runs/{rid}/stream") as s:
        for line in s.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if events and events[-1] == "done":
                break
    assert events.count("step") >= 8 and events[-1] == "done"
    for _ in range(40):
        run = client.get(f"/api/runs/{rid}").json()
        if run["diagnosis"]:
            break
        time.sleep(0.1)
    assert run["status"] == "fail" and run["diagnosis"]["canon_event"]["idx"] == started["fault"]["step"]


def test_stats_eval_demo(client):
    st = client.get("/api/stats").json()
    assert st["runs"] >= 80 and st["forks"] >= 1 and 0 < st["fail_rate"] < 1
    ev = client.get("/api/eval").json()
    assert ev["splits"]["test"]["methods"]["model"]["top1"] > ev["splits"]["test"]["methods"]["last_step"]["top1"]
    demo = client.get("/api/demo").json()["runs"]
    assert len(demo) == 3 and all(d["available"] for d in demo)


def test_ingest_from_sdk(client):
    from blackbox_sdk import Recorder

    rec = Recorder(task_family="external", policy="custom")
    with rec.step("tool", "lookup", {"q": "x"}) as s:
        s.output = {"hit": 1}
    run = rec.finish("success", "ok")
    r = client.post("/api/ingest", json={"run": run.model_dump(mode="json"), "checkpoints": []})
    assert r.status_code == 200
    assert client.get(f"/api/runs/{run.id}/verify").json()["valid"] is True
