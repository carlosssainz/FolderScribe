import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.extraction import ExtractionStatus, TextExtraction
from folderscribe.domain.hashing import ContentHash, DuplicateGroup, HashStatus
from folderscribe.domain.interfaces import ScanSessionRepository
from folderscribe.domain.models import (
    ExclusionRule,
    ScanEntry,
    ScanError,
    ScanSession,
    SessionStatus,
)

_SCHEMA_VERSION = 4
_UNKNOWN_SCHEMA_MSG = "Unsupported database schema version: {}"

_V1_SCHEMA_SQL = """
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

_V2_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_exclusion_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    pattern TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
);
"""

_V3_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS content_hashes (
    hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    algorithm TEXT NOT NULL DEFAULT 'sha-256',
    hash_sha256 TEXT,
    file_size INTEGER NOT NULL,
    file_modified_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    computed_at TEXT,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id),
    FOREIGN KEY (entry_id) REFERENCES scan_entries(entry_id)
);
CREATE INDEX IF NOT EXISTS idx_content_hashes_entry
    ON content_hashes(entry_id);
CREATE INDEX IF NOT EXISTS idx_content_hashes_hash
    ON content_hashes(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_content_hashes_session
    ON content_hashes(session_id);
"""

_V4_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS text_extractions (
    extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256_hash TEXT,
    extractor TEXT NOT NULL,
    extractor_version TEXT NOT NULL DEFAULT '1',
    config_version TEXT NOT NULL DEFAULT '1',
    status TEXT NOT NULL,
    content TEXT,
    char_count INTEGER NOT NULL DEFAULT 0,
    total_pages INTEGER NOT NULL DEFAULT 0,
    processed_pages INTEGER NOT NULL DEFAULT 0,
    is_truncated INTEGER NOT NULL DEFAULT 0,
    is_partial INTEGER NOT NULL DEFAULT 0,
    needs_ocr INTEGER NOT NULL DEFAULT 0,
    ocr_heuristic_version TEXT,
    partial_reason TEXT,
    skip_reason TEXT,
    error_code TEXT,
    error_message TEXT,
    encoding TEXT,
    decoding_warnings TEXT,
    observed_size INTEGER,
    observed_mtime TEXT,
    computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_extractions_sha256
    ON text_extractions(sha256_hash);

CREATE TABLE IF NOT EXISTS scan_entry_extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    extraction_id INTEGER,
    status TEXT NOT NULL,
    is_reused INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id),
    FOREIGN KEY (entry_id) REFERENCES scan_entries(entry_id),
    FOREIGN KEY (extraction_id) REFERENCES text_extractions(extraction_id)
);
CREATE INDEX IF NOT EXISTS idx_scan_entry_extractions_session
    ON scan_entry_extractions(session_id);
CREATE INDEX IF NOT EXISTS idx_scan_entry_extractions_entry
    ON scan_entry_extractions(entry_id);
"""


def get_default_db_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        base = Path(data_home)
    else:
        base = Path.home() / ".local" / "share"
    return base / "folderscribe" / "folderscribe.db"


class SchemaError(Exception):
    """Raised when the database schema version is unknown."""


class SqliteScanSessionRepository(ScanSessionRepository):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def _current_version(self) -> int:
        cursor = self._conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def _apply_v1(self) -> None:
        self._conn.executescript(_V1_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )

    def _apply_v2(self) -> None:
        self._conn.executescript(_V2_SCHEMA_SQL)
        cursor = self._conn.execute("PRAGMA table_info(scan_entries)")
        columns = {row[1] for row in cursor}
        if "skip_detail" not in columns:
            self._conn.execute(
                (
                    "ALTER TABLE scan_entries "
                    "ADD COLUMN skip_detail TEXT NOT NULL DEFAULT ''"
                )
            )
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (2, datetime.now(timezone.utc).isoformat()),
        )

    def _apply_v3(self) -> None:
        self._conn.executescript(_V3_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (3, datetime.now(timezone.utc).isoformat()),
        )

    def _apply_v4(self) -> None:
        self._conn.executescript(_V4_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (4, datetime.now(timezone.utc).isoformat()),
        )

    def _ensure_schema(self) -> None:
        self._conn.execute(
            (
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        current = self._current_version()
        if current == 0:
            self._apply_v1()
            self._apply_v2()
            self._apply_v3()
            self._apply_v4()
        elif current == 1:
            self._apply_v2()
            self._apply_v3()
            self._apply_v4()
        elif current == 2:
            self._apply_v3()
            self._apply_v4()
        elif current == 3:
            self._apply_v4()
        elif current == 4:
            pass
        else:
            self.close()
            raise SchemaError(_UNKNOWN_SCHEMA_MSG.format(current))
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

    def save_exclusion_rules(
        self,
        session_id: str,
        rules: tuple[ExclusionRule, ...],
    ) -> None:
        if not rules:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            for rule in rules:
                self._conn.execute(
                    """INSERT INTO scan_exclusion_rules
                       (session_id, pattern, source, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (session_id, rule.pattern, rule.source.value, now),
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
                        is_compatible, status, skip_reason, is_code_project,
                        skip_detail)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        entry.skip_detail,
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

    def get_entries_for_session(self, session_id: str) -> list[ScanEntry]:
        cursor = self._conn.execute(
            "SELECT * FROM scan_entries WHERE session_id = ?",
            (session_id,),
        )
        results: list[ScanEntry] = []
        for row in cursor:
            modified = None
            if row["modified_at"]:
                modified = datetime.fromisoformat(row["modified_at"])
            results.append(
                ScanEntry(
                    session_id=row["session_id"],
                    absolute_path=Path(row["absolute_path"]),
                    relative_path=row["relative_path"],
                    name=row["name"],
                    extension=row["extension"] or "",
                    element_type=row["element_type"],
                    size=row["size"],
                    modified_at=modified,
                    is_compatible=bool(row["is_compatible"]),
                    status=row["status"],
                    skip_reason=row["skip_reason"],
                    is_code_project=bool(row["is_code_project"]),
                    skip_detail=row["skip_detail"] or "",
                )
            )
        return results

    def save_content_hashes(self, session_id: str, hashes: list[ContentHash]) -> None:
        if not hashes:
            return
        with self._conn:
            for h in hashes:
                if h.file_modified_at is None:
                    continue
                cursor = self._conn.execute(
                    "SELECT entry_id FROM scan_entries "
                    "WHERE session_id = ? AND absolute_path = ? "
                    "ORDER BY entry_id DESC LIMIT 1",
                    (session_id, str(h.absolute_path)),
                )
                row = cursor.fetchone()
                if row is None:
                    continue
                self._conn.execute(
                    """INSERT INTO content_hashes
                       (session_id, entry_id, algorithm, hash_sha256,
                        file_size, file_modified_at, status, error_message,
                        computed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        int(row[0]),
                        h.algorithm,
                        h.hash_sha256,
                        h.file_size,
                        h.file_modified_at.isoformat(),
                        h.status.value,
                        h.error_message,
                        h.computed_at.isoformat() if h.computed_at else None,
                    ),
                )

    def find_reusable_hash(
        self, absolute_path: Path, file_size: int, modified_at: datetime
    ) -> ContentHash | None:
        cursor = self._conn.execute(
            """SELECT ch.hash_sha256, ch.algorithm, ch.file_size,
                      ch.file_modified_at, ch.status, ch.error_message,
                      ch.computed_at
               FROM content_hashes ch
               JOIN scan_entries se ON ch.entry_id = se.entry_id
               WHERE se.absolute_path = ?
                 AND ch.file_size = ?
                 AND ch.file_modified_at = ?
                 AND ch.status IN ('computed', 'reused')
               ORDER BY ch.computed_at DESC
               LIMIT 1""",
            (str(absolute_path), file_size, modified_at.isoformat()),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        modified = datetime.fromisoformat(row["file_modified_at"])
        computed = (
            datetime.fromisoformat(row["computed_at"]) if row["computed_at"] else None
        )
        return ContentHash(
            absolute_path=absolute_path,
            algorithm=row["algorithm"],
            hash_sha256=row["hash_sha256"],
            file_size=row["file_size"],
            file_modified_at=modified,
            status=HashStatus.REUSED,
            error_message=row["error_message"],
            computed_at=computed,
        )

    def find_duplicates(self, session_id: str) -> tuple[DuplicateGroup, ...]:
        cursor = self._conn.execute(
            """SELECT ch.hash_sha256, ch.file_size,
                      COUNT(*) as file_count,
                      (COUNT(*) - 1) * ch.file_size as wasted_space
               FROM content_hashes ch
               JOIN scan_entries se ON ch.entry_id = se.entry_id
               WHERE ch.session_id = ?
                 AND ch.hash_sha256 IS NOT NULL
                 AND ch.status IN ('computed', 'reused')
               GROUP BY ch.hash_sha256, ch.file_size
               HAVING COUNT(*) > 1
               ORDER BY wasted_space DESC""",
            (session_id,),
        )
        groups: list[DuplicateGroup] = []
        for row in cursor:
            hash_hex = str(row["hash_sha256"])
            file_size = int(row["file_size"])
            group_id = hash_hex[:16]

            path_cursor = self._conn.execute(
                """SELECT se.absolute_path
                   FROM content_hashes ch
                   JOIN scan_entries se ON ch.entry_id = se.entry_id
                   WHERE ch.session_id = ?
                     AND ch.hash_sha256 = ?
                     AND ch.file_size = ?
                   ORDER BY se.absolute_path""",
                (session_id, hash_hex, file_size),
            )
            file_paths = tuple(Path(r[0]) for r in path_cursor.fetchall())

            groups.append(
                DuplicateGroup(
                    group_id=group_id,
                    hash_sha256=hash_hex,
                    file_size=file_size,
                    file_count=int(row["file_count"]),
                    wasted_space=int(row["wasted_space"]),
                    file_paths=file_paths,
                )
            )
        return tuple(groups)

    def save_text_extractions(
        self,
        session_id: str,
        extractions: list[TextExtraction],
    ) -> None:
        if not extractions:
            return
        with self._conn:
            for ext in extractions:
                cursor = self._conn.execute(
                    "SELECT entry_id FROM scan_entries "
                    "WHERE session_id = ? AND absolute_path = ? "
                    "ORDER BY entry_id DESC LIMIT 1",
                    (session_id, str(ext.absolute_path)),
                )
                entry_row = cursor.fetchone()
                if entry_row is None:
                    continue

                if ext.status == ExtractionStatus.CANCELLED:
                    continue

                computed_at = ext.computed_at or datetime.now(timezone.utc)

                cur = self._conn.execute(
                    """INSERT INTO text_extractions
                       (sha256_hash, extractor, extractor_version, config_version,
                        status, content, char_count, total_pages, processed_pages,
                        is_truncated, is_partial, needs_ocr, ocr_heuristic_version,
                        partial_reason, skip_reason, error_code, error_message,
                        encoding, decoding_warnings, observed_size, observed_mtime,
                        computed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ext.sha256_hash,
                        ext.extractor,
                        ext.extractor_version,
                        ext.config_version,
                        ext.status.value,
                        ext.content,
                        ext.char_count,
                        ext.total_pages,
                        ext.processed_pages,
                        int(ext.is_truncated),
                        int(ext.is_partial),
                        int(ext.needs_ocr),
                        ext.ocr_heuristic_version,
                        ext.partial_reason,
                        ext.skip_reason,
                        ext.error_code,
                        ext.error_message,
                        ext.encoding,
                        ext.decoding_warnings,
                        ext.file_size,
                        (
                            ext.file_modified_at.isoformat()
                            if ext.file_modified_at
                            else None
                        ),
                        computed_at.isoformat(),
                    ),
                )
                extraction_id = cur.lastrowid

                self._conn.execute(
                    """INSERT INTO scan_entry_extractions
                       (session_id, entry_id, extraction_id, status, is_reused)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        int(entry_row[0]),
                        extraction_id,
                        ext.status.value,
                        0,
                    ),
                )

    def find_reusable_extraction(
        self,
        absolute_path: Path,
        sha256_hash: str | None,
        file_size: int | None,
        file_modified_at: datetime | None,
        extractor: str,
        extractor_version: str,
        config_version: str,
    ) -> TextExtraction | None:
        if sha256_hash is not None:
            row = self._conn.execute(
                """SELECT te.*
                   FROM text_extractions te
                   JOIN scan_entry_extractions see
                       ON te.extraction_id = see.extraction_id
                   WHERE te.sha256_hash = ?
                     AND te.extractor = ?
                     AND te.extractor_version = ?
                     AND te.config_version = ?
                     AND te.status NOT IN ('cancelled', 'stale', 'error')
                   ORDER BY te.computed_at DESC
                   LIMIT 1""",
                (sha256_hash, extractor, extractor_version, config_version),
            ).fetchone()
            if row is not None:
                return _row_to_text_extraction(row, absolute_path)

        if file_size is not None:
            row = self._conn.execute(
                """SELECT te.* FROM text_extractions te
                    JOIN scan_entry_extractions see
                        ON te.extraction_id = see.extraction_id
                    JOIN scan_entries se ON see.entry_id = se.entry_id
                    WHERE se.absolute_path = ?
                      AND te.observed_size = ?
                      AND te.extractor = ?
                      AND te.extractor_version = ?
                      AND te.config_version = ?
                      AND te.status NOT IN ('cancelled', 'stale', 'error')
                    ORDER BY te.computed_at DESC
                    LIMIT 1""",
                (
                    str(absolute_path),
                    file_size,
                    extractor,
                    extractor_version,
                    config_version,
                ),
            ).fetchone()
            if row is not None:
                return _row_to_text_extraction(row, absolute_path)

        return None

    def get_text_extractions_for_session(self, session_id: str) -> list[TextExtraction]:
        cursor = self._conn.execute(
            """SELECT te.*, se.absolute_path as abs_path,
                      see.status as link_status, see.is_reused
               FROM text_extractions te
               JOIN scan_entry_extractions see ON te.extraction_id = see.extraction_id
               JOIN scan_entries se ON see.entry_id = se.entry_id
               WHERE see.session_id = ?
               ORDER BY se.absolute_path""",
            (session_id,),
        )
        results: list[TextExtraction] = []
        for row in cursor:
            abs_path = Path(row["abs_path"])
            results.append(_row_to_text_extraction(row, abs_path))
        return results

    def get_text_extraction_by_entry(
        self, session_id: str, entry_id: int
    ) -> TextExtraction | None:
        row = self._conn.execute(
            """SELECT te.*, see.status as link_status, see.is_reused
               FROM text_extractions te
               JOIN scan_entry_extractions see ON te.extraction_id = see.extraction_id
               WHERE see.session_id = ? AND see.entry_id = ?
               ORDER BY te.needs_ocr ASC, te.extraction_id DESC
               LIMIT 1""",
            (session_id, entry_id),
        ).fetchone()
        if row is None:
            return None
        abs_path = Path(
            self._conn.execute(
                "SELECT absolute_path FROM scan_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()[0]
        )
        return _row_to_text_extraction(row, abs_path)

    def get_text_extraction_by_path(
        self, session_id: str, absolute_path: Path
    ) -> TextExtraction | None:
        row = self._conn.execute(
            """SELECT te.*, see.status as link_status, see.is_reused
               FROM text_extractions te
               JOIN scan_entry_extractions see ON te.extraction_id = see.extraction_id
               JOIN scan_entries se ON see.entry_id = se.entry_id
               WHERE see.session_id = ? AND se.absolute_path = ?
               ORDER BY te.needs_ocr ASC, te.extraction_id DESC
               LIMIT 1""",
            (session_id, str(absolute_path)),
        ).fetchone()
        if row is None:
            return None
        return _row_to_text_extraction(row, absolute_path)

    def __enter__(self) -> "SqliteScanSessionRepository":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()


def _row_to_text_extraction(row: sqlite3.Row, absolute_path: Path) -> TextExtraction:
    modified = None
    if row["observed_mtime"]:
        modified = datetime.fromisoformat(row["observed_mtime"])
    computed = None
    if row["computed_at"]:
        computed = datetime.fromisoformat(row["computed_at"])
    return TextExtraction(
        absolute_path=absolute_path,
        extractor=row["extractor"],
        extractor_version=row["extractor_version"],
        config_version=row["config_version"],
        status=ExtractionStatus(row["status"]),
        content=row["content"],
        sha256_hash=row["sha256_hash"],
        file_size=row["observed_size"],
        file_modified_at=modified,
        char_count=row["char_count"],
        total_pages=row["total_pages"],
        processed_pages=row["processed_pages"],
        is_truncated=bool(row["is_truncated"]),
        is_partial=bool(row["is_partial"]),
        needs_ocr=bool(row["needs_ocr"]),
        ocr_heuristic_version=row["ocr_heuristic_version"],
        partial_reason=row["partial_reason"],
        skip_reason=row["skip_reason"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        encoding=row["encoding"],
        decoding_warnings=row["decoding_warnings"],
        computed_at=computed,
    )
