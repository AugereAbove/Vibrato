from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..analysis.pipeline import AnalysisCancelled
from ..audio.errors import UserFacingError
from ..db import get_db
from ..logging_setup import get_logger
from ..util import dumps, new_id, to_jsonable, utcnow

log = get_logger("tasks")
PERSIST_INTERVAL_S = 0.5
FINISHED = {"complete", "failed", "cancelled", "interrupted"}


@dataclass
class TaskState:
    id: str
    kind: str
    status: str
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    project_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: dict[str, Any] | None = None
    created_at: str = field(default_factory=utcnow)
    started_at: str | None = None
    finished_at: str | None = None
    dedupe_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "message": self.message,
            "project_id": self.project_id,
            "params": to_jsonable(self.params),
            "result": to_jsonable(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ProgressReporter(Protocol):
    def progress(self, fraction: float, message: str = "", stage: str | None = None) -> None: ...

    def sub(self, start: float, end: float) -> Callable[[float, str], None]: ...

    def check_cancelled(self) -> None: ...


class TaskContext:
    def __init__(self, manager: TaskManager, state: TaskState, cancel_event: threading.Event) -> None:
        self._manager = manager
        self._state = state
        self._cancel = cancel_event
        self._last_persist = 0.0

    @property
    def task_id(self) -> str:
        return self._state.id

    def progress(self, fraction: float, message: str = "", stage: str | None = None) -> None:
        self.check_cancelled()
        self._state.progress = max(self._state.progress, min(1.0, max(0.0, float(fraction))))
        if message:
            self._state.message = message
        if stage:
            self._state.stage = stage
        now = time.monotonic()
        if now - self._last_persist >= PERSIST_INTERVAL_S:
            self._last_persist = now
            self._manager.persist(self._state)

    def sub(self, start: float, end: float) -> Callable[[float, str], None]:
        def report(fraction: float, message: str) -> None:
            self.progress(start + (end - start) * fraction, message)

        return report

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise AnalysisCancelled("Cancelled by user")


class TaskManager:
    def __init__(self, workers: int = 2) -> None:
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vibrato-task")
        self.tasks: dict[str, TaskState] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    def recover_interrupted(self) -> int:
        with get_db().tx() as conn:
            return conn.execute(
                "UPDATE tasks SET status = 'interrupted', finished_at = ?, message = 'The application stopped while this task was running.' WHERE status IN ('queued', 'running')",
                (utcnow(),),
            ).rowcount

    def persist(self, state: TaskState) -> None:
        try:
            with get_db().tx() as conn:
                conn.execute(
                    "INSERT INTO tasks (id, kind, status, progress, stage, message, project_id, params_json, result_json, error_json, created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET status = excluded.status, progress = excluded.progress, stage = excluded.stage, message = excluded.message, result_json = excluded.result_json, error_json = excluded.error_json, started_at = excluded.started_at, finished_at = excluded.finished_at",
                    (
                        state.id,
                        state.kind,
                        state.status,
                        state.progress,
                        state.stage,
                        state.message,
                        state.project_id,
                        dumps(state.params),
                        None if state.result is None else dumps(state.result),
                        None if state.error is None else dumps(state.error),
                        state.created_at,
                        state.started_at,
                        state.finished_at,
                    ),
                )
        except Exception:
            log.exception("Could not persist task %s", state.id)

    def submit(
        self,
        kind: str,
        function: Callable[[TaskContext], Any],
        params: dict[str, Any] | None = None,
        project_id: str | None = None,
        dedupe_key: str | None = None,
        label: str = "",
    ) -> TaskState:
        with self.lock:
            if dedupe_key:
                for state in self.tasks.values():
                    if state.dedupe_key == dedupe_key and state.status not in FINISHED:
                        return state
            state = TaskState(
                id=new_id("tsk"),
                kind=kind,
                status="queued",
                params=params or {},
                project_id=project_id,
                dedupe_key=dedupe_key,
                message=label or "Waiting to start",
            )
            self.tasks[state.id] = state
            event = threading.Event()
            self.cancel_events[state.id] = event
        self.persist(state)
        self.executor.submit(self._run, state, function, event)
        return state

    def _run(self, state: TaskState, function: Callable[[TaskContext], Any], event: threading.Event) -> None:
        if event.is_set():
            state.status = "cancelled"
            state.finished_at = utcnow()
            self.persist(state)
            return
        state.status = "running"
        state.started_at = utcnow()
        self.persist(state)
        context = TaskContext(self, state, event)
        try:
            state.result = function(context)
            state.status = "complete"
            state.progress = 1.0
            state.message = "Done"
        except AnalysisCancelled:
            state.status = "cancelled"
            state.message = "Cancelled. Nothing was saved for this step; existing results are unchanged."
        except UserFacingError as exc:
            state.status = "failed"
            state.error = exc.to_dict()
            state.message = exc.what
            log.warning("Task %s failed: %s", state.id, exc.what)
        except Exception as exc:
            state.status = "failed"
            state.error = {
                "code": "internal_error",
                "what": f"The {state.kind.replace('_', ' ')} task stopped unexpectedly.",
                "why": f"{type(exc).__name__}: {exc}",
                "action": "Try again. If it keeps happening, export a debug bundle from Settings > Advanced and include it in a bug report.",
                "details": traceback.format_exc(limit=8).splitlines()[-6:],
            }
            state.message = state.error["what"]
            log.exception("Task %s crashed", state.id)
        finally:
            state.finished_at = utcnow()
            self.persist(state)
            with self.lock:
                self.cancel_events.pop(state.id, None)

    def cancel(self, task_id: str) -> TaskState | None:
        with self.lock:
            state = self.tasks.get(task_id)
            event = self.cancel_events.get(task_id)
        if state is None:
            return None
        if event is not None:
            event.set()
        if state.status == "queued":
            state.status = "cancelled"
            state.finished_at = utcnow()
            self.persist(state)
        return state

    def get(self, task_id: str) -> dict[str, Any] | None:
        state = self.tasks.get(task_id)
        if state is not None:
            return state.to_dict()
        with get_db().read() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        from ..store.rows import row_to_dict

        data = row_to_dict(row) or {}
        data["result"] = data.pop("result", None)
        return data

    def list(
        self, active_only: bool = False, project_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        states = sorted(self.tasks.values(), key=lambda s: s.created_at, reverse=True)
        out = [
            s.to_dict()
            for s in states
            if (not active_only or s.status not in FINISHED)
            and (project_id is None or s.project_id == project_id)
        ]
        return out[:limit]

    def wait(self, task_id: str, timeout: float = 120.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.tasks.get(task_id)
            if state is None or state.status in FINISHED:
                return self.get(task_id)
            time.sleep(0.05)
        return self.get(task_id)

    def shutdown(self) -> None:
        for event in list(self.cancel_events.values()):
            event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)


_manager: TaskManager | None = None


def init_tasks(workers: int) -> TaskManager:
    global _manager
    _manager = TaskManager(workers)
    _manager.recover_interrupted()
    return _manager


def get_tasks() -> TaskManager:
    if _manager is None:
        raise RuntimeError("Task manager not initialized")
    return _manager
