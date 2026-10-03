"""Recorder: step context managers, @tool decorator, hash chain and checkpoint writes.

Typical use::

    rec = Recorder(sink="sqlite:///data/blackbox.db", task_family="refund")
    with rec.step(kind="tool", name="get_order", input={"order_id": "1043"}) as s:
        s.output = get_order("1043")
    rec.checkpoint(agent_state, world_state)
    rec.finish(status="fail", outcome_detail="refund issued to wrong order")
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from .schema import (
    CheckpointRecord,
    RunRecord,
    StepRecord,
    canonical_json,
    checkpoint_id,
    genesis_hash,
    step_hash,
    utcnow,
    world_id,
)


class StepHandle:
    """Mutable handle yielded by ``Recorder.step``; set ``output`` (and optionally tokens)."""

    def __init__(self, kind: str, name: str, input: dict, parent_idx: Optional[int]):
        self.kind = kind
        self.name = name
        self.input = input
        self.parent_idx = parent_idx
        self.output: Any = None
        self.error: Optional[str] = None
        self.latency_ms: Optional[int] = None
        self.tokens_in = 0
        self.tokens_out = 0
        self.record: Optional[StepRecord] = None


# --------------------------------------------------------------------------- sinks


class Sink:
    """Where recorded runs go. Subclasses override what they need."""

    def start(self, run: RunRecord) -> None: ...

    def step(self, run: RunRecord, step: StepRecord) -> None: ...

    def checkpoint(self, run: RunRecord, step: StepRecord, cp: CheckpointRecord) -> None: ...

    def finish(self, run: RunRecord, checkpoints: dict[str, CheckpointRecord]) -> None: ...


class MemorySink(Sink):
    """Keeps everything on the Recorder object only."""


class SQLiteSink(Sink):
    """Writes into the Black Box database.

    With ``stream=True`` every step is committed as soon as it is recorded, which is what
    the live view polls. Otherwise the whole run is written in one transaction at the end.
    """

    def __init__(self, url: Optional[str] = None, stream: bool = False):
        from backend import db  # local import keeps the SDK importable on its own

        self.engine = db.get_engine(url)
        self.stream = stream
        db.init_db(self.engine)

    def start(self, run: RunRecord) -> None:
        if self.stream:
            from backend.store import save_run_header

            save_run_header(self.engine, run)

    def step(self, run: RunRecord, step: StepRecord) -> None:
        if self.stream:
            from backend.store import save_step

            save_step(self.engine, run.id, step)

    def checkpoint(self, run: RunRecord, step: StepRecord, cp: CheckpointRecord) -> None:
        if self.stream:
            from backend.store import save_checkpoint

            save_checkpoint(self.engine, run.id, step, cp)

    def finish(self, run: RunRecord, checkpoints: dict[str, CheckpointRecord]) -> None:
        from backend.store import save_run, update_run_header

        if self.stream:
            update_run_header(self.engine, run)
        else:
            save_run(self.engine, run, checkpoints)


class HttpSink(Sink):
    """Ships the finished run to a running Black Box API (``POST /api/ingest``)."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def finish(self, run: RunRecord, checkpoints: dict[str, CheckpointRecord]) -> None:
        import httpx

        url = self.base_url if self.base_url.endswith("/api") else self.base_url + "/api"
        payload = {
            "run": run.model_dump(mode="json"),
            "checkpoints": [c.model_dump(mode="json") for c in checkpoints.values()],
        }
        httpx.post(url + "/ingest", json=payload, timeout=self.timeout).raise_for_status()


def make_sink(sink: Any) -> Sink:
    if sink is None:
        return MemorySink()
    if isinstance(sink, Sink):
        return sink
    if isinstance(sink, str):
        if sink.startswith("sqlite"):
            return SQLiteSink(sink)
        if sink.startswith("http://") or sink.startswith("https://"):
            return HttpSink(sink)
    raise ValueError(f"unsupported sink: {sink!r}")


# ------------------------------------------------------------------------ recorder


class Recorder:
    def __init__(self, run_id: Optional[str] = None, sink: Any = None,
                 keep_checkpoints: bool = True, **meta: Any):
        self.run = RunRecord(id=run_id or uuid.uuid4().hex, **meta)
        self.sink = make_sink(sink)
        self.keep_checkpoints = keep_checkpoints
        self.steps: list[StepRecord] = []
        self.checkpoints: dict[str, CheckpointRecord] = {}
        self._prev_hash = genesis_hash(self.run.id)
        self.sink.start(self.run)

    @property
    def run_id(self) -> str:
        return self.run.id

    # -- recording -----------------------------------------------------------------

    def record(self, kind: str, name: str, input: Optional[dict] = None, output: Any = None,
               error: Optional[str] = None, *, latency_ms: int = 0, tokens_in: int = 0,
               tokens_out: int = 0, parent_idx: Optional[int] = None, reused: bool = False,
               checkpoint_id: Optional[str] = None) -> StepRecord:
        idx = len(self.steps)
        input = _jsonable(input or {})
        output = _jsonable(output)
        h = step_hash(self._prev_hash, kind=kind, name=name, input=input, output=output,
                      error=error, idx=idx)
        step = StepRecord(
            idx=idx,
            parent_idx=parent_idx if parent_idx is not None else (idx - 1 if idx else None),
            kind=kind,
            name=name,
            input=input,
            output=output,
            error=error,
            latency_ms=int(latency_ms),
            tokens_in=int(tokens_in),
            tokens_out=int(tokens_out),
            checkpoint_id=checkpoint_id,
            prev_hash=self._prev_hash,
            hash=h,
            reused=reused,
        )
        self._prev_hash = h
        self.steps.append(step)
        self.sink.step(self.run, step)
        return step

    @contextmanager
    def step(self, kind: str, name: str, input: Optional[dict] = None,
             parent_idx: Optional[int] = None, swallow: bool = False) -> Iterator[StepHandle]:
        """Record one step. Exceptions are stored as the step error and re-raised
        unless ``swallow`` is set."""
        handle = StepHandle(kind, name, dict(input or {}), parent_idx)
        t0 = time.perf_counter()
        try:
            yield handle
        except Exception as exc:  # noqa: BLE001 - we want every failure on the record
            handle.error = f"{type(exc).__name__}: {exc}"
            self._commit(handle, t0)
            if not swallow:
                raise
            return
        self._commit(handle, t0)

    def _commit(self, h: StepHandle, t0: float) -> None:
        latency = h.latency_ms if h.latency_ms is not None else (time.perf_counter() - t0) * 1000
        h.record = self.record(h.kind, h.name, h.input, h.output, h.error,
                               latency_ms=latency, tokens_in=h.tokens_in,
                               tokens_out=h.tokens_out, parent_idx=h.parent_idx)

    def checkpoint(self, agent_state: dict, world_state: dict) -> Optional[str]:
        """Snapshot agent + world state after the latest step (content-addressed)."""
        if not self.steps or not self.keep_checkpoints:
            return None
        # snapshot now: callers keep mutating their state objects after this point
        agent_state, world_state = _jsonable(agent_state), _jsonable(world_state)
        wid = world_id(world_state)
        cid = checkpoint_id(agent_state, wid)
        step = self.steps[-1]
        step.checkpoint_id = cid
        if cid not in self.checkpoints:
            cp = CheckpointRecord(id=cid, agent_state=agent_state, world_id=wid,
                                  world_state=world_state)
            self.checkpoints[cid] = cp
            self.sink.checkpoint(self.run, step, cp)
        return cid

    def tool(self, fn: Optional[Callable] = None, *, name: Optional[str] = None,
             kind: str = "tool") -> Callable:
        """Decorator: every call of the wrapped function becomes a recorded step."""

        def wrap(f: Callable) -> Callable:
            sig = inspect.signature(f)
            step_name = name or f.__name__

            @functools.wraps(f)
            def inner(*args: Any, **kwargs: Any) -> Any:
                bound = sig.bind_partial(*args, **kwargs)
                with self.step(kind=kind, name=step_name, input=dict(bound.arguments)) as s:
                    out = f(*args, **kwargs)
                    s.output = out
                return out

            return inner

        return wrap(fn) if fn is not None else wrap

    def finish(self, status: str, outcome_detail: str = "", final_answer: str = "",
               **extra: Any) -> RunRecord:
        run = self.run
        run.status = status
        run.outcome_detail = outcome_detail
        run.final_answer = final_answer
        for k, v in extra.items():
            setattr(run, k, v)
        run.chain_head = self._prev_hash
        run.tokens_total = sum(s.tokens_in + s.tokens_out for s in self.steps if not s.reused)
        run.latency_total_ms = sum(s.latency_ms for s in self.steps)
        run.steps = self.steps
        if run.created_at is None:
            run.created_at = utcnow()
        self.sink.finish(run, self.checkpoints)
        return run


def _jsonable(value: Any) -> Any:
    """Round-trip through canonical JSON so outputs are plain data (and hash the same
    way after a trip through the database)."""
    import json

    return json.loads(canonical_json(value)) if value is not None else None


def verify_chain(run_id: str, steps: list[dict | StepRecord]) -> dict:
    """Recompute the hash chain. Returns ``{"valid": bool, "broken_at": idx | None}``."""
    prev = genesis_hash(run_id)
    for s in sorted(steps, key=lambda s: _get(s, "idx")):
        expected = step_hash(prev, kind=_get(s, "kind"), name=_get(s, "name"),
                             input=_get(s, "input"), output=_get(s, "output"),
                             error=_get(s, "error"), idx=_get(s, "idx"))
        if _get(s, "prev_hash") != prev or _get(s, "hash") != expected:
            return {"valid": False, "broken_at": _get(s, "idx")}
        prev = expected
    return {"valid": True, "broken_at": None}


def _get(obj: Any, key: str) -> Any:
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)
