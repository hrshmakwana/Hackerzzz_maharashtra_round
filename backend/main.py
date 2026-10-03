"""FastAPI entrypoint."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import compare, diagnose, eval, live, replay, runs

load_dotenv()

app = FastAPI(title="Black Box", version="0.1.0")

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (runs, diagnose, replay, compare, eval, live):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
