"""Black Box recorder SDK.

Instrument any agent in a few lines and get a hash-chained, checkpointed trace.
"""

from .recorder import HttpSink, MemorySink, Recorder, Sink, SQLiteSink, verify_chain
from .schema import (
    CheckpointRecord,
    Edit,
    RunRecord,
    StepRecord,
    canonical_json,
    genesis_hash,
    sha256,
    step_hash,
)

__version__ = "0.1.0"

__all__ = [
    "Recorder",
    "Sink",
    "MemorySink",
    "SQLiteSink",
    "HttpSink",
    "verify_chain",
    "RunRecord",
    "StepRecord",
    "CheckpointRecord",
    "Edit",
    "canonical_json",
    "genesis_hash",
    "sha256",
    "step_hash",
]
