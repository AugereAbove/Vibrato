from __future__ import annotations

import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..logging_setup import get_logger
from ..util import utcnow

log = get_logger("db")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BACKUP_KEEP = 7


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        prefix, _, rest = path.stem.partition("_")
        migrations.append(Migration(int(prefix), rest or path.stem, path.read_text(encoding="utf-8")))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Duplicate migration versions found")
    return migrations


def latest_schema_version() -> int:
    migrations = load_migrations()
    return migrations[-1].version if migrations else 0


class Database:
    def __init__(self, path: Path, backups_dir: Path) -> None:
        self.path = path
        self.backups_dir = backups_dir
        self._init_lock = threading.Lock()
        self.recovery_status: dict[str, Any] = {"recovered": False, "message": ""}

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self.read() as conn:
            row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
            return int(row["v"] or 0)

    def initialize(self) -> dict[str, Any]:
        with self._init_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and not self._integrity_ok():
                self.recovery_status = self._recover_from_backup()
            with self.connect() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
            self.migrate()
            self.backup("startup")
            return self.recovery_status

    def migrate(self) -> list[int]:
        conn = self.connect()
        applied_now: list[int] = []
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            conn.commit()
            applied = {int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations")}
            pending = [m for m in load_migrations() if m.version not in applied]
            if pending and applied:
                self.backup("pre-migration")
            for migration in pending:
                script = (
                    "BEGIN;\n"
                    f"{migration.sql}\n"
                    "INSERT INTO schema_migrations(version, name, applied_at) "
                    f"VALUES ({migration.version}, '{migration.name}', '{utcnow()}');\n"
                    "COMMIT;"
                )
                try:
                    conn.executescript(script)
                except sqlite3.Error:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    log.exception("Migration %s failed", migration.version)
                    raise
                applied_now.append(migration.version)
                log.info("Applied migration %s (%s)", migration.version, migration.name)
        finally:
            conn.close()
        return applied_now

    def backup(self, reason: str) -> Path | None:
        if not self.path.exists():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        target = self.backups_dir / f"vibrato-{stamp}-{reason}.db"
        source = self.connect()
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        self._prune_backups()
        return target

    def list_backups(self) -> list[Path]:
        return sorted(self.backups_dir.glob("vibrato-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)

    def _prune_backups(self) -> None:
        for stale in self.list_backups()[BACKUP_KEEP:]:
            stale.unlink(missing_ok=True)

    def _integrity_ok(self) -> bool:
        try:
            conn = sqlite3.connect(self.path, timeout=10.0)
            try:
                row = conn.execute("PRAGMA quick_check").fetchone()
                return bool(row) and str(row[0]).lower() == "ok"
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return False

    def _recover_from_backup(self) -> dict[str, Any]:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        quarantine = self.path.with_name(f"vibrato-corrupt-{stamp}.db")
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists():
                shutil.move(str(candidate), str(quarantine) + suffix)
        for backup in self.list_backups():
            try:
                conn = sqlite3.connect(backup)
                ok = str(conn.execute("PRAGMA quick_check").fetchone()[0]).lower() == "ok"
                conn.close()
            except sqlite3.DatabaseError:
                ok = False
            if ok:
                shutil.copy2(backup, self.path)
                message = (
                    f"The project database failed an integrity check and was restored from backup "
                    f"{backup.name}. The damaged file was kept as {quarantine.name}."
                )
                log.warning(message)
                return {"recovered": True, "message": message, "backup": backup.name}
        message = (
            "The project database failed an integrity check and no healthy backup was found. "
            f"A new empty database was created; the damaged file was kept as {quarantine.name}."
        )
        log.error(message)
        return {"recovered": True, "message": message, "backup": None}


_db: Database | None = None


def init_db(path: Path, backups_dir: Path) -> Database:
    global _db
    database = Database(path, backups_dir)
    database.initialize()
    _db = database
    return database


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db
