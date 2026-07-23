"""Pure, provider-neutral pipeline (CI) domain types — zero I/O.

Mirrors `backend/status.py`: pydantic `BaseModel`s and a `Literal` state
enum, no adapter or engine-specific vocabulary. A (future, out of scope)
adapter maps these neutral values to a concrete CI engine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PipelineRunState = Literal["pending", "running", "succeeded", "failed", "canceled", "unknown"]


class PipelineRunSpec(BaseModel):
    definition: str
    parameters: dict[str, str] = {}


class PipelineRunRef(BaseModel):
    run_id: str


class PipelineRunStatus(BaseModel):
    state: PipelineRunState


__all__ = [
    "PipelineRunState",
    "PipelineRunSpec",
    "PipelineRunRef",
    "PipelineRunStatus",
]
