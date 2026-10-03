"""/live endpoints: start a run in the background and stream its steps (SSE)."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from agent_sim import faults
from agent_sim.llm import gemini_available
from agent_sim.runner import run_agent
from agent_sim.tasks import FAMILIES
from blackbox_sdk.recorder import SQLiteSink

from ..db import get_engine
from ..models import Run, Step
from ..store import run_dict, step_dict

router = APIRouter(tags=["live"])


class FaultBody(BaseModel):
    type: str
    step: Optional[int] = Field(None, ge=0)


class StartBody(BaseModel):
    family: str = "refund"
    seed: Optional[int] = None
    policy: str = "sim"
    fault: Optional[FaultBody] = None
    delay_ms: int = Field(350, ge=0, le=3000)
    auto_diagnose: bool = True


def _pick_fault_step(family: str, seed: int, ftype: str, policy: str) -> int:
    clean = run_agent(family, seed, keep_checkpoints=False)
    cands = faults.candidate_steps(ftype, [s.model_dump() for s in clean.record.steps], clean.tags)
    if not cands:
        raise HTTPException(422, f"{ftype} cannot be injected into this {family} run; try "
                                 f"another seed or fault type")
    return cands[0]


def _execute(run_id: str, body: StartBody, seed: int, fault: Optional[dict]) -> None:
    try:
        run_agent(body.family, seed, body.policy, fault, sink=SQLiteSink(stream=True),
                  run_id=run_id, split="live", step_delay=body.delay_ms / 1000)
    except Exception as exc:  # noqa: BLE001 - record the crash on the run
        with Session(get_engine()) as s:
            run = s.get(Run, run_id)
            if run is not None:
                run.status = "fail"
                run.outcome_detail = f"agent crashed: {exc}"[:500]
                s.add(run)
                s.commit()
        return
    if body.auto_diagnose:
        from ..services.diagnosis_service import diagnose

        with Session(get_engine()) as s:
            run = s.get(Run, run_id)
            if run is not None and run.status == "fail":
                try:
                    diagnose(s, run_id)
                except Exception:  # noqa: BLE001 - diagnosis is best-effort here
                    pass


@router.post("/runs")
def start_run(body: StartBody) -> dict:
    if body.family not in FAMILIES:
        raise HTTPException(422, f"unknown family {body.family}")
    if body.policy not in ("sim", "gemini"):
        raise HTTPException(422, "policy must be sim or gemini")
    if body.policy == "gemini" and not gemini_available():
        raise HTTPException(503, "Gemini is not configured: set GEMINI_API_KEY and GEMINI_MODEL")
    seed = body.seed if body.seed is not None else uuid.uuid4().int % 1_000_000
    fault = None
    if body.fault:
        if body.fault.type not in faults.FAULT_TYPES:
            raise HTTPException(422, f"unknown fault type {body.fault.type}")
        step = body.fault.step
        if step is None:
            step = _pick_fault_step(body.family, seed, body.fault.type, body.policy)
        fault = {"type": body.fault.type, "step": step}
    run_id = uuid.uuid4().hex
    threading.Thread(target=_execute, args=(run_id, body, seed, fault), daemon=True).start()
    return {"id": run_id, "seed": seed, "fault": fault, "policy": body.policy}


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request) -> StreamingResponse:
    async def events():
        last = -1
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            with Session(get_engine()) as s:
                run = s.get(Run, run_id)
                steps = s.exec(select(Step).where(Step.run_id == run_id, Step.idx > last)
                               .order_by(Step.idx)).all()
                for st in steps:
                    last = st.idx
                    yield f"event: step\ndata: {json.dumps(step_dict(st), default=str)}\n\n"
                if run is not None and run.status != "running":
                    yield f"event: done\ndata: {json.dumps(run_dict(run), default=str)}\n\n"
                    return
            idle = 0 if steps else idle + 1
            if run is None and idle > 40:
                yield "event: error\ndata: {\"detail\": \"run not found\"}\n\n"
                return
            if idle and idle % 40 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
