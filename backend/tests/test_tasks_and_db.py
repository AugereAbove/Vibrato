from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from vibrato.analysis.pipeline import AnalysisCancelled
from vibrato.db.connection import Database, latest_schema_version
from vibrato.tasks.manager import TaskContext, TaskManager


def test_migrations_create_schema(tmp_path: Path) -> None:
    db = Database(tmp_path / "v.db", tmp_path / "backups")
    db.initialize()
    assert db.schema_version() == latest_schema_version()
    with db.read() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in (
        "projects",
        "recordings",
        "segments",
        "acoustic_events",
        "alignments",
        "comparisons",
        "metric_values",
        "coaching_suggestions",
        "calibration_profiles",
        "counterfactual_renders",
        "user_preferences",
    ):
        assert table in tables
    assert db.list_backups()


def test_corrupt_database_is_recovered_from_backup(tmp_path: Path) -> None:
    db = Database(tmp_path / "v.db", tmp_path / "backups")
    db.initialize()
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES ('p1', 'Keep me', 'now', 'now')"
        )
    db.backup("test")
    (tmp_path / "v.db-wal").unlink(missing_ok=True)
    (tmp_path / "v.db-shm").unlink(missing_ok=True)
    (tmp_path / "v.db").write_bytes(b"not a database" * 1000)
    fresh = Database(tmp_path / "v.db", tmp_path / "backups")
    status = fresh.initialize()
    assert status["recovered"]
    with fresh.read() as conn:
        assert conn.execute("SELECT name FROM projects WHERE id = 'p1'").fetchone()[0] == "Keep me"
    assert list(tmp_path.glob("vibrato-corrupt-*.db"))


def test_task_cancellation_and_failure(isolated_settings) -> None:
    from vibrato.db import init_db

    init_db(isolated_settings.db_path, isolated_settings.backups_dir)
    manager = TaskManager(workers=2)

    def slow(ctx: TaskContext) -> str:
        for step in range(200):
            ctx.progress(step / 200, "working")
            time.sleep(0.02)
        return "done"

    def broken(ctx: TaskContext) -> None:
        raise ValueError("boom")

    running = manager.submit("slow", slow)
    time.sleep(0.2)
    manager.cancel(running.id)
    assert manager.wait(running.id, 10)["status"] == "cancelled"
    failed = manager.wait(manager.submit("broken", broken).id, 10)
    assert failed["status"] == "failed"
    assert failed["error"]["what"] and failed["error"]["action"]
    ok = manager.wait(manager.submit("quick", lambda ctx: 42).id, 10)
    assert ok["status"] == "complete" and ok["result"] == 42
    first = manager.submit("slow", slow, dedupe_key="same")
    second = manager.submit("slow", slow, dedupe_key="same")
    assert first.id == second.id
    manager.cancel(first.id)
    manager.shutdown()


def test_cancel_exception_type() -> None:
    with pytest.raises(AnalysisCancelled):
        raise AnalysisCancelled("x")


def test_sqlite_foreign_keys_enforced(tmp_path: Path) -> None:
    db = Database(tmp_path / "v.db", tmp_path / "b")
    db.initialize()
    with pytest.raises(sqlite3.IntegrityError), db.tx() as conn:
        conn.execute(
            "INSERT INTO sessions (id, project_id, started_at, last_activity_at) VALUES ('s', 'missing', 'x', 'x')"
        )
