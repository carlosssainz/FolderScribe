import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.models import (
    ScanEntry,
    ScanError,
    ScanSession,
    SessionStatus,
)
from folderscribe.domain.interfaces import ScanSessionRepository

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    session_id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    is_recursive INTEGER NOT NULL DEFAULT 1,
    total_files INTEGER NOT NULL DEFAULT 0,
    total_compatible INTEGER NOT NULL DEFAULT 0,
    total_not_compatible INTEGER NOT NULL DEFAULT 0,
    total_skipped INTEGER NOT NULL DEFAULT 0,
    total_errors INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_entries (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    absolute_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    name TEXT NOT NULL,
    extension TEXT NOT NULL DEFAULT '',
    element_type TEXT NOT NULL DEFAULT 'file',
    size INTEGER,
    modified_at TEXT,
    is_compatible INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'indexed',
    skip_reason TEXT,
    is_code_project INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS scan_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    affected_path TEXT NOT NULL,
    error_code TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
);
"""


def get_default_db_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        base = Path(data_home)
    else:
        base = Path.home() / ".local" / "share"
    return base / "folderscribe" / "folderscribe.db"


class SqliteScanSessionRepository(ScanSessionRepository):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        cursor = self._conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0
        if current_version < _SCHEMA_VERSION:
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",  # noqa: E501
                (_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
        self._conn.commit()

    def create_session(self, session: ScanSession) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO scan_sessions
                   (session_id, root_path, started_at, status, is_recursive)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session.session_id,
                    str(session.root_path),
                    session.started_at.isoformat(),
                    session.status.value,
                    int(session.is_recursive),
                ),
            )

    def complete_session(
        self,
        session: ScanSession,
        entries: list[ScanEntry],
        errors: list[ScanError],
    ) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE scan_sessions SET
                   finished_at = ?, status = ?,
                   total_files = ?, total_compatible = ?,
                   total_not_compatible = ?, total_skipped = ?,
                   total_errors = ?
                   WHERE session_id = ?""",
                (
                    session.finished_at.isoformat() if session.finished_at else None,
                    session.status.value,
                    session.total_files,
                    session.total_compatible,
                    session.total_not_compatible,
                    session.total_skipped,
                    session.total_errors,
                    session.session_id,
                ),
            )
            for entry in entries:
                self._conn.execute(
                    """INSERT INTO scan_entries
                       (session_id, absolute_path, relative_path, name,
                        extension, element_type, size, modified_at,
                        is_compatible, status, skip_reason, is_code_project)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.session_id,
                        str(entry.absolute_path),
                        entry.relative_path,
                        entry.name,
                        entry.extension,
                        entry.element_type,
                        entry.size,
                        entry.modified_at.isoformat() if entry.modified_at else None,
                        int(entry.is_compatible),
                        entry.status,
                        entry.skip_reason,
                        int(entry.is_code_project),
                    ),
                )
            for error in errors:
                self._conn.execute(
                    """INSERT INTO scan_errors
                       (session_id, affected_path, error_code, message, occurred_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        session.session_id,
                        str(error.path),
                        error.code,
                        error.message,
                        (
                            error.occurred_at.isoformat()
                            if error.occurred_at
                            else datetime.now(timezone.utc).isoformat()
                        ),
                    ),
                )

    def mark_session_failed(
        self, session_id: str, finished_at: datetime, message: str
    ) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE scan_sessions SET
                   finished_at = ?, status = ?
                   WHERE session_id = ?""",
                (finished_at.isoformat(), SessionStatus.FAILED.value, session_id),
            )
            self._conn.execute(
                """INSERT INTO scan_errors
                   (session_id, affected_path, error_code, message, occurred_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, "", "persistence_error", message, finished_at.isoformat()),
            )

    def close(self) -> None:
        self._conn.close()
