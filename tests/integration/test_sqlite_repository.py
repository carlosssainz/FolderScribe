from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from folderscribe.domain.models import (
    ScanEntry,
    ScanError,
    ScanSession,
    SessionStatus,
)
from folderscribe.infrastructure.database import SqliteScanSessionRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def repo(db_path: Path) -> Iterator[SqliteScanSessionRepository]:
    r = SqliteScanSessionRepository(db_path)
    yield r
    r.close()


@pytest.fixture
def sample_session() -> ScanSession:
    return ScanSession(
        session_id="test-session-1",
        root_path=Path("/tmp/test"),
        started_at=datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc),
        status=SessionStatus.RUNNING,
    )


@pytest.fixture
def completed_session() -> ScanSession:
    return ScanSession(
        session_id="test-session-2",
        root_path=Path("/tmp/test"),
        started_at=datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 27, 10, 1, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_files=3,
        total_compatible=2,
        total_not_compatible=1,
        total_skipped=1,
        total_errors=0,
    )


class TestSchemaCreation:
    def test_creates_new_database(self, db_path: Path) -> None:
        assert not db_path.exists()
        SqliteScanSessionRepository(db_path).close()
        assert db_path.exists()

    def test_idempotent_schema(self, db_path: Path) -> None:
        SqliteScanSessionRepository(db_path).close()
        SqliteScanSessionRepository(db_path).close()
        assert db_path.exists()

    def test_schema_version_stored(self, db_path: Path) -> None:
        repo = SqliteScanSessionRepository(db_path)
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        conn.close()
        repo.close()
        assert row is not None
        assert row[0] >= 1

    def test_foreign_keys_enabled(self, db_path: Path) -> None:
        repo = SqliteScanSessionRepository(db_path)
        row = repo._conn.execute("PRAGMA foreign_keys").fetchone()
        repo.close()
        assert row is not None
        assert row[0] == 1


class TestSessionPersistence:
    def test_create_running_session(self, repo: SqliteScanSessionRepository) -> None:
        session = ScanSession(
            session_id="create-test",
            root_path=Path("/some/path"),
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.RUNNING,
        )
        repo.create_session(session)

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT session_id, root_path, status "
            "FROM scan_sessions WHERE session_id = ?"
        )
        row = conn.execute(sql, ("create-test",)).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "create-test"
        assert row[1] == "/some/path"
        assert row[2] == "running"

    def test_complete_session_with_entries_and_errors(
        self, repo: SqliteScanSessionRepository
    ) -> None:
        session = ScanSession(
            session_id="complete-test",
            root_path=Path("/tmp/test"),
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.RUNNING,
        )
        repo.create_session(session)

        entries = [
            ScanEntry(
                session_id="complete-test",
                absolute_path=Path("/tmp/test/doc.pdf"),
                relative_path="doc.pdf",
                name="doc.pdf",
                extension=".pdf",
                element_type="file",
                size=1024,
                modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                is_compatible=True,
            ),
            ScanEntry(
                session_id="complete-test",
                absolute_path=Path("/tmp/test/img.jpg"),
                relative_path="img.jpg",
                name="img.jpg",
                extension=".jpg",
                element_type="file",
                size=2048,
                is_compatible=False,
            ),
            ScanEntry(
                session_id="complete-test",
                absolute_path=Path("/tmp/test/.git"),
                relative_path=".git",
                name=".git",
                extension="",
                element_type="directory",
                is_compatible=False,
                status="skipped",
                skip_reason="excluded_directory",
            ),
        ]
        errors = [
            ScanError(
                path=Path("/tmp/test/bad"),
                code="permission",
                message="Permission denied",
                session_id="complete-test",
                occurred_at=datetime.now(timezone.utc),
            ),
        ]

        completed = ScanSession(
            session_id="complete-test",
            root_path=session.root_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED_WITH_ERRORS,
            total_files=2,
            total_compatible=1,
            total_not_compatible=1,
            total_skipped=1,
            total_errors=1,
        )
        repo.complete_session(completed, entries, errors)

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT status, total_files, total_errors "
            "FROM scan_sessions WHERE session_id = ?"
        )
        session_row = conn.execute(sql, ("complete-test",)).fetchone()
        entry_rows = conn.execute(
            "SELECT COUNT(*) FROM scan_entries WHERE session_id = ?",
            ("complete-test",),
        ).fetchone()
        error_rows = conn.execute(
            "SELECT COUNT(*) FROM scan_errors WHERE session_id = ?",
            ("complete-test",),
        ).fetchone()
        sql = (
            "SELECT name, is_compatible FROM scan_entries "
            "WHERE session_id = ? AND is_compatible = 1"
        )
        compatible_entry = conn.execute(sql, ("complete-test",)).fetchone()
        sql = (
            "SELECT name, status, skip_reason FROM scan_entries "
            "WHERE session_id = ? AND status = 'skipped'"
        )
        skipped_entry = conn.execute(sql, ("complete-test",)).fetchone()
        conn.close()

        assert session_row[0] == "completed_with_errors"
        assert session_row[1] == 2
        assert session_row[2] == 1
        assert entry_rows[0] == 3
        assert error_rows[0] == 1
        assert compatible_entry[0] == "doc.pdf"
        assert compatible_entry[1] == 1
        assert skipped_entry[0] == ".git"
        assert skipped_entry[1] == "skipped"
        assert skipped_entry[2] == "excluded_directory"

    def test_foreign_key_enforced(self, repo: SqliteScanSessionRepository) -> None:
        with pytest.raises(Exception):
            repo.complete_session(
                ScanSession(
                    session_id="orphan",
                    root_path=Path("/tmp"),
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    status=SessionStatus.COMPLETED,
                ),
                [
                    ScanEntry(
                        session_id="nonexistent",
                        absolute_path=Path("/tmp/f.txt"),
                        relative_path="f.txt",
                        name="f.txt",
                        extension=".txt",
                    )
                ],
                [],
            )

    def test_mark_session_failed(self, repo: SqliteScanSessionRepository) -> None:
        session = ScanSession(
            session_id="fail-test",
            root_path=Path("/tmp/test"),
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.RUNNING,
        )
        repo.create_session(session)
        repo.mark_session_failed(
            "fail-test", datetime.now(timezone.utc), "Unexpected error"
        )

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        row = conn.execute(
            "SELECT status FROM scan_sessions WHERE session_id = ?",
            ("fail-test",),
        ).fetchone()
        error_row = conn.execute(
            "SELECT error_code, message FROM scan_errors WHERE session_id = ?",
            ("fail-test",),
        ).fetchone()
        conn.close()

        assert row[0] == "failed"
        assert error_row[0] == "persistence_error"
        assert error_row[1] == "Unexpected error"


class TestInventoryPersistence:
    def test_compatible_entries(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        session = ScanSession(
            session_id="inv-compat",
            root_path=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)

        entries = [
            ScanEntry(
                session_id="inv-compat",
                absolute_path=tmp_path / "doc.pdf",
                relative_path="doc.pdf",
                name="doc.pdf",
                extension=".pdf",
                size=100,
                is_compatible=True,
            ),
            ScanEntry(
                session_id="inv-compat",
                absolute_path=tmp_path / "readme.txt",
                relative_path="readme.txt",
                name="readme.txt",
                extension=".txt",
                size=200,
                is_compatible=True,
            ),
        ]
        completed = ScanSession(
            session_id="inv-compat",
            root_path=tmp_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_files=2,
            total_compatible=2,
        )
        repo.complete_session(completed, entries, [])

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT name, is_compatible FROM scan_entries "
            "WHERE session_id = ? ORDER BY name"
        )
        rows = conn.execute(sql, ("inv-compat",)).fetchall()
        conn.close()
        assert len(rows) == 2
        assert all(r[1] == 1 for r in rows)

    def test_not_compatible_entries(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        session = ScanSession(
            session_id="inv-notcompat",
            root_path=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)

        entries = [
            ScanEntry(
                session_id="inv-notcompat",
                absolute_path=tmp_path / "image.jpg",
                relative_path="image.jpg",
                name="image.jpg",
                extension=".jpg",
                is_compatible=False,
            ),
        ]
        completed = ScanSession(
            session_id="inv-notcompat",
            root_path=tmp_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_files=1,
            total_not_compatible=1,
        )
        repo.complete_session(completed, entries, [])

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        row = conn.execute(
            "SELECT is_compatible FROM scan_entries WHERE session_id = ?",
            ("inv-notcompat",),
        ).fetchone()
        conn.close()
        assert row[0] == 0

    def test_skipped_entries(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        session = ScanSession(
            session_id="inv-skipped",
            root_path=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)

        entries = [
            ScanEntry(
                session_id="inv-skipped",
                absolute_path=tmp_path / "node_modules",
                relative_path="node_modules",
                name="node_modules",
                extension="",
                element_type="directory",
                status="skipped",
                skip_reason="excluded_directory",
            ),
            ScanEntry(
                session_id="inv-skipped",
                absolute_path=tmp_path / "link.txt",
                relative_path="link.txt",
                name="link.txt",
                extension=".txt",
                element_type="file",
                status="skipped",
                skip_reason="symlink",
            ),
        ]
        completed = ScanSession(
            session_id="inv-skipped",
            root_path=tmp_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_skipped=2,
        )
        repo.complete_session(completed, entries, [])

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT status, skip_reason FROM scan_entries "
            "WHERE session_id = ? ORDER BY skip_reason"
        )
        rows = conn.execute(sql, ("inv-skipped",)).fetchall()
        conn.close()
        assert len(rows) == 2
        assert all(r[0] == "skipped" for r in rows)

    def test_error_entry_persisted(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        session = ScanSession(
            session_id="inv-err",
            root_path=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)
        errors = [
            ScanError(
                path=tmp_path / "restricted",
                code="permission",
                message="Permission denied: /restricted",
                session_id="inv-err",
                occurred_at=datetime.now(timezone.utc),
            ),
        ]
        completed = ScanSession(
            session_id="inv-err",
            root_path=tmp_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED_WITH_ERRORS,
            total_errors=1,
        )
        repo.complete_session(completed, [], errors)

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        row = conn.execute(
            "SELECT error_code, message FROM scan_errors WHERE session_id = ?",
            ("inv-err",),
        ).fetchone()
        conn.close()
        assert row[0] == "permission"
        assert "Permission denied" in row[1]


class TestUnicodeSupport:
    def test_unicode_paths(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        session = ScanSession(
            session_id="unicode-test",
            root_path=tmp_path,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)
        entries = [
            ScanEntry(
                session_id="unicode-test",
                absolute_path=tmp_path / "café.pdf",
                relative_path="café.pdf",
                name="café.pdf",
                extension=".pdf",
                size=100,
                is_compatible=True,
            ),
            ScanEntry(
                session_id="unicode-test",
                absolute_path=tmp_path / "中文.txt",
                relative_path="中文.txt",
                name="中文.txt",
                extension=".txt",
                size=200,
                is_compatible=True,
            ),
            ScanEntry(
                session_id="unicode-test",
                absolute_path=tmp_path / "file with spaces.md",
                relative_path="file with spaces.md",
                name="file with spaces.md",
                extension=".md",
                size=300,
                is_compatible=True,
            ),
        ]
        completed = ScanSession(
            session_id="unicode-test",
            root_path=tmp_path,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_files=3,
            total_compatible=3,
        )
        repo.complete_session(completed, entries, [])

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT name, relative_path FROM scan_entries "
            "WHERE session_id = ? ORDER BY name"
        )
        rows = conn.execute(sql, ("unicode-test",)).fetchall()
        conn.close()

        names = [r[0] for r in rows]
        assert "café.pdf" in names
        assert "中文.txt" in names
        assert "file with spaces.md" in names


class TestDatabaseCreation:
    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "nested" / "dir" / "test.db"
        assert not nested_path.parent.exists()
        repo = SqliteScanSessionRepository(nested_path)
        repo.close()
        assert nested_path.parent.exists()
        assert nested_path.exists()


class TestEndToEndMapping:
    def test_scan_result_saved_correctly(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        from folderscribe.application.scan_folder import _map_to_entries
        from folderscribe.infrastructure.scanner import OsDirectoryScanner

        scan_root = tmp_path / "scan_root"
        scan_root.mkdir()
        (scan_root / "doc.pdf").write_text("pdf content")
        (scan_root / "image.jpg").write_text("image content")
        sub = scan_root / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")

        scanner = OsDirectoryScanner()
        inventory = scanner.scan(scan_root)

        session = ScanSession(
            session_id="e2e-test",
            root_path=scan_root,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)

        entries = _map_to_entries("e2e-test", scan_root, inventory)
        errors = [
            ScanError(
                path=e.path,
                code=e.code,
                message=e.message,
                session_id="e2e-test",
                occurred_at=datetime.now(timezone.utc),
            )
            for e in inventory.errors
        ]

        completed = ScanSession(
            session_id="e2e-test",
            root_path=scan_root,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_files=inventory.total_files,
            total_compatible=len(inventory.compatible_files),
            total_not_compatible=len(inventory.not_compatible_files),
        )
        repo.complete_session(completed, entries, errors)

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        session_row = conn.execute(
            "SELECT status, total_files FROM scan_sessions WHERE session_id = ?",
            ("e2e-test",),
        ).fetchone()
        entry_count = conn.execute(
            "SELECT COUNT(*) FROM scan_entries WHERE session_id = ?",
            ("e2e-test",),
        ).fetchone()
        conn.close()

        assert session_row[0] == "completed"
        assert session_row[1] == 3
        assert entry_count[0] == 3


class TestSymlinkExclusion:
    def test_no_symlinks_followed(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        from folderscribe.application.scan_folder import _map_to_entries
        from folderscribe.infrastructure.scanner import OsDirectoryScanner

        scan_root = tmp_path / "scan_root"
        scan_root.mkdir()
        real_file = scan_root / "real.txt"
        real_file.write_text("real")
        link = scan_root / "link.txt"
        link.symlink_to(real_file)

        real_dir = scan_root / "real_dir"
        real_dir.mkdir()
        (real_dir / "inner.txt").write_text("inner")
        dir_link = scan_root / "dir_link"
        dir_link.symlink_to(real_dir, target_is_directory=True)

        scanner = OsDirectoryScanner()
        inventory = scanner.scan(scan_root)

        skipped_paths = [s.path for s in inventory.skipped]
        assert link in skipped_paths
        assert dir_link in skipped_paths

        session = ScanSession(
            session_id="symlink-test",
            root_path=scan_root,
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)
        entries = _map_to_entries("symlink-test", scan_root, inventory)
        completed = ScanSession(
            session_id="symlink-test",
            root_path=scan_root,
            started_at=session.started_at,
            finished_at=datetime.now(timezone.utc),
            status=SessionStatus.COMPLETED,
            total_skipped=inventory.total_skipped,
        )
        repo.complete_session(completed, entries, [])

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        sql = (
            "SELECT name, skip_reason FROM scan_entries "
            "WHERE session_id = ? AND status = 'skipped'"
        )
        skipped_entries = conn.execute(sql, ("symlink-test",)).fetchall()
        conn.close()

        skip_reasons = {r[0]: r[1] for r in skipped_entries}
        assert skip_reasons.get("link.txt") == "symlink"
        assert skip_reasons.get("dir_link") == "symlink"
