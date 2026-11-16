"""Atomic worker heartbeat and dependency state for liveness diagnostics."""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUS_PATH = Path(os.getenv("WORKER_STATUS_FILE", "/tmp/coldchain-worker-status.json"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


class WorkerStatus:
    def __init__(self, path: Path = STATUS_PATH) -> None:
        self.path = path
        self.state: dict[str, Any] = {
            "pid": os.getpid(),
            "started_at": _now(),
            "last_cycle_at": None,
            "cycle": 0,
            "phase": "starting",
            "last_result": None,
            "database": "unknown",
            "chain": "unknown",
            "last_error": None,
            "last_error_dependency": None,
            "dependency_errors": {},
            "last_business_ref": None,
        }
        self._write()

    def begin_cycle(self) -> None:
        self.state["phase"] = "processing"
        self.state["cycle_started_at"] = _now()
        self._write()

    def complete_cycle(self, result: str, *, error: str | None = None) -> None:
        self.state["cycle"] += 1
        self.state["phase"] = "idle"
        self.state["last_cycle_at"] = _now()
        self.state["last_result"] = result
        if error is not None:
            self.state["last_error"] = error
        self._write()

    def dependency(self, name: str, status: str, *, error: str | None = None) -> None:
        self.state[name] = status
        errors = self.state["dependency_errors"]
        if error:
            errors[name] = error
            self.state["last_error"] = error
            self.state["last_error_dependency"] = name
        elif status == "available":
            errors.pop(name, None)
            if self.state["last_error_dependency"] == name:
                if errors:
                    next_name = next(reversed(errors))
                    self.state["last_error_dependency"] = next_name
                    self.state["last_error"] = errors[next_name]
                else:
                    self.state["last_error"] = None
                    self.state["last_error_dependency"] = None
        self._write()

    def business_ref(self, value: str) -> None:
        self.state["last_business_ref"] = value
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="worker-health-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.state, stream, sort_keys=True)
                stream.write("\n")
            os.replace(tmp_name, self.path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


worker_status = WorkerStatus()
