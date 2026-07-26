"""Provider-neutral results for irreversible backend destruction."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

DestroyOutcome = Literal["removed", "absent", "protected", "failed"]


class DestroyResourceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    kind: Literal["container", "network", "volume"]
    identifier: str
    outcome: DestroyOutcome
    detail: str | None = None


class DestroyResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    resources: tuple[DestroyResourceResult, ...]


__all__ = ["DestroyOutcome", "DestroyResourceResult", "DestroyResult"]
