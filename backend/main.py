"""FastAPI entrypoint."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_sim.llm import gemini_available
from ml.common import load_models, models_available

from . import db
from .routers import compare, diagnose, eval, live, replay, runs

STATE = {"seeding": False, "seeded": 0, "seed_error": None}


def _seed_in_background() -> None:
    STATE["seeding"] = True
    try:
        STATE["seeded"] = db.seed_if_empty()
    except Exception as exc:  # noqa: BLE001
        STATE["seed_error"] = str(exc)
    finally:
        STATE["seeding"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if os.getenv("SEED_RUNS_ON_START", "1500") != "0" and db.run_count() == 0:
        threading.Thread(target=_seed_in_background, daemon=True).start()
    if models_available():
        threading.Thread(target=load_models, daemon=True).start()
    yield


app = FastAPI(
    title="Black Box",
    version="0.1.0",
    description="Flight recorder for AI agents: record, blame, fork, prove.",
    lifespan=lifespan,
)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
           if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=os.getenv("ALLOWED_ORIGIN_REGEX") or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (runs, diagnose, replay, compare, eval, live):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    model_version = None
    if models_available():
        try:
            model_version = load_models().version
        except Exception:
            model_version = None
    return {
        "status": "ok",
        "runs": db.run_count(),
        "seeding": STATE["seeding"],
        "seed_error": STATE["seed_error"],
        "model": model_version,
        "gemini": gemini_available(),
    }
