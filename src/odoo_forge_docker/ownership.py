import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from odoo_forge.database.types import CreationReceipt


class BackendOwnershipCustody:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def default(cls) -> "BackendOwnershipCustody":
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        return cls(state / "odoo-forge" / "backend" / "custody.json")

    def record(
        self, project: str, instance: str, receipt: CreationReceipt, token: str | None
    ) -> None:
        def update(state: dict[str, object]) -> None:
            projects = state.setdefault(project, {})
            assert isinstance(projects, dict)
            projects[instance] = {
                "receipt": receipt.model_dump(mode="json"),
                "token": token,
            }

        self._update(update)

    def remove(self, project: str, instance: str) -> None:
        def update(state: dict[str, object]) -> None:
            entries = state.get(project)
            if isinstance(entries, dict):
                entries.pop(instance, None)
                if not entries:
                    state.pop(project, None)

        self._update(update)

    def consume(self, project: str, instance: str) -> tuple[CreationReceipt, str | None] | None:
        proof: tuple[CreationReceipt, str | None] | None = None

        def update(state: dict[str, object]) -> None:
            nonlocal proof
            entries = state.get(project)
            if not isinstance(entries, dict):
                return
            entry = entries.get(instance)
            if not isinstance(entry, dict):
                return
            try:
                proof = CreationReceipt.model_validate(entry["receipt"]), entry.get("token")
            except (KeyError, TypeError, ValueError):
                return
            entry["state"] = "in_progress"

        self._update(update)
        return proof

    def complete(
        self, project: str, instance: str, receipt: CreationReceipt, token: str | None
    ) -> None:
        def update(state: dict[str, object]) -> None:
            entries = state.get(project)
            if not isinstance(entries, dict):
                return
            entry = entries.get(instance)
            expected = {"receipt": receipt.model_dump(mode="json"), "token": token}
            if (
                not isinstance(entry, dict)
                or entry.get("state") != "in_progress"
                or any(entry.get(key) != value for key, value in expected.items())
            ):
                return
            entries.pop(instance)
            if not entries:
                state.pop(project)

        self._update(update)

    def restore(
        self, project: str, instance: str, receipt: CreationReceipt, token: str | None
    ) -> None:
        self.record(project, instance, receipt, token)

    def _update(self, update: Callable[[dict[str, object]], None]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = json.loads(self.path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                state = {}
            update(state)
            fd, raw_temporary = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
            temporary = Path(raw_temporary)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(state, stream, separators=(",", ":"))
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)

    def load(self, project: str, instance: str) -> tuple[CreationReceipt, str | None] | None:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
            with lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH)
                try:
                    state = json.loads(self.path.read_text())
                    entry = state[project][instance]
                    return CreationReceipt.model_validate(entry["receipt"]), entry.get("token")
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
