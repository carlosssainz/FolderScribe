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


class TestExclusionRulesPersistence:
    def test_save_exclusion_rules(self, repo: SqliteScanSessionRepository) -> None:
        from folderscribe.domain.models import ExclusionRule, RuleSource

        session = ScanSession(
            session_id="excl-test",
            root_path=Path("/tmp/test"),
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)
        rules = (
            ExclusionRule("*.tmp", RuleSource.USER),
            ExclusionRule("privado/**", RuleSource.USER),
        )
        repo.save_exclusion_rules("excl-test", rules)

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        rows = conn.execute(
            "SELECT pattern, source FROM scan_exclusion_rules "
            "WHERE session_id = ? ORDER BY pattern",
            ("excl-test",),
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0][0] == "*.tmp"
        assert rows[0][1] == "user"
        assert rows[1][0] == "privado/**"
        assert rows[1][1] == "user"

    def test_save_no_rules_does_nothing(
        self, repo: SqliteScanSessionRepository
    ) -> None:
        session = ScanSession(
            session_id="excl-none",
            root_path=Path("/tmp/test"),
            started_at=datetime.now(timezone.utc),
        )
        repo.create_session(session)
        repo.save_exclusion_rules("excl-none", ())

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM scan_exclusion_rules WHERE session_id = ?",
            ("excl-none",),
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_scan_with_exclusion_persists_rules(
        self, repo: SqliteScanSessionRepository, tmp_path: Path
    ) -> None:
        from folderscribe.application.scan_folder import ScanFolderUseCase
        from folderscribe.domain.models import ExclusionRule, RuleSource
        from folderscribe.infrastructure.scanner import OsDirectoryScanner

        scan_root = tmp_path / "scan_root"
        scan_root.mkdir()
        (scan_root / "keep.txt").write_text("keep")
        (scan_root / "skip.tmp").write_text("skip")

        scanner = OsDirectoryScanner()
        use_case = ScanFolderUseCase(scanner, repo)
        rules = (ExclusionRule("*.tmp", RuleSource.USER),)
        result = use_case.execute(scan_root, rules)
        assert result.session is not None

        import sqlite3

        conn = sqlite3.connect(str(repo._db_path))
        rule_rows = conn.execute(
            "SELECT pattern, source FROM scan_exclusion_rules WHERE session_id = ?",
            (result.session.session_id,),
        ).fetchall()
        entry_rows = conn.execute(
            "SELECT name, status, skip_reason, skip_detail FROM scan_entries "
            "WHERE session_id = ? ORDER BY name",
            (result.session.session_id,),
        ).fetchall()
        conn.close()

        assert len(rule_rows) == 1
        assert rule_rows[0][0] == "*.tmp"
        assert rule_rows[0][1] == "user"

        names = {r[0]: r for r in entry_rows}
        assert names["keep.txt"][1] == "indexed"
        assert names["skip.tmp"][1] == "skipped"
        assert names["skip.tmp"][2] == "excluded_by_user_pattern"
        assert names["skip.tmp"][3] == "*.tmp"


class TestScanWithExclusions:
    def test_scan_with_exclude_flag_files_only(self, tmp_path: Path) -> None:
        from folderscribe.main import main

        root = tmp_path / "test_root"
        root.mkdir()
        (root / "keep.txt").write_text("keep")
        (root / "a.tmp").write_text("skip")
        (root / "b.tmp").write_text("skip")
        db = tmp_path / "test.db"

        exit_code = main(
            [
                "scan",
                str(root),
                "--database",
                str(db),
                "--exclude",
                "*.tmp",
            ]
        )
        assert exit_code == 0

    def test_scan_with_multiple_exclude(self, tmp_path: Path) -> None:
        from folderscribe.main import main

        root = tmp_path / "test_root"
        root.mkdir()
        (root / "keep.txt").write_text("keep")
        (root / "a.tmp").write_text("skip")
        privado = root / "privado"
        privado.mkdir()
        (privado / "secret.txt").write_text("secret")
        db = tmp_path / "test.db"

        exit_code = main(
            [
                "scan",
                str(root),
                "--database",
                str(db),
                "--exclude",
                "*.tmp",
                "--exclude",
                "privado",
            ]
        )
        assert exit_code == 0
        assert db.exists()

        import sqlite3

        conn = sqlite3.connect(str(db))
        entries = conn.execute(
            "SELECT name, status FROM scan_entries WHERE session_id = "
            "(SELECT session_id FROM scan_sessions ORDER BY started_at DESC LIMIT 1)"
        ).fetchall()
        entry_map = {r[0]: r[1] for r in entries}
        conn.close()
        assert entry_map["keep.txt"] == "indexed"
        assert entry_map["a.tmp"] == "skipped"
        assert entry_map["privado"] == "skipped"

    def test_scan_without_exclude_still_works(self, tmp_path: Path) -> None:
        from folderscribe.main import main

        root = tmp_path / "test_root"
        root.mkdir()
        (root / "a.txt").write_text("a")
        (root / "b.tmp").write_text("b")
        db = tmp_path / "test.db"

        exit_code = main(
            [
                "scan",
                str(root),
                "--database",
                str(db),
            ]
        )
        assert exit_code == 0


class TestSchemaMigration:
    def test_new_database_is_v3(self, tmp_path: Path) -> None:
        import sqlite3

        db_path = tmp_path / "new_v3.db"
        repo = SqliteScanSessionRepository(db_path)

        conn = sqlite3.connect(str(db_path))
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        has_rules_table = (  # noqa: E501
            conn.execute(  # noqa: E501
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_exclusion_rules'"  # noqa: E501
            ).fetchone()
            is not None
        )
        has_skip_detail = any(
            row[1] == "skip_detail"
            for row in conn.execute("PRAGMA table_info(scan_entries)")
        )
        has_hashes_table = (  # noqa: E501
            conn.execute(  # noqa: E501
                "SELECT name FROM sqlite_master WHERE type='table' AND name='content_hashes'"  # noqa: E501
            ).fetchone()
            is not None
        )
        conn.close()
        repo.close()

        assert version == 4
        assert has_rules_table
        assert has_skip_detail
        assert has_hashes_table

    def test_migrate_v1_to_v3_preserves_data(self, tmp_path: Path) -> None:  # noqa: E501
        import sqlite3

        db_path = tmp_path / "v1_to_v3.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""  -- noqa: E501
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version (
                version, applied_at
            ) VALUES (1, '2026-07-27T00:00:00+00:00');
            CREATE TABLE scan_sessions (
                session_id TEXT PRIMARY KEY, root_path TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                is_recursive INTEGER NOT NULL DEFAULT 1,
                total_files INTEGER NOT NULL DEFAULT 0,
                total_compatible INTEGER NOT NULL DEFAULT 0,
                total_not_compatible INTEGER NOT NULL DEFAULT 0,
                total_skipped INTEGER NOT NULL DEFAULT 0,
                total_errors INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO scan_sessions (
                session_id, root_path, started_at, status
            ) VALUES (
                'migrate-test', '/tmp', '2026-07-27T00:00:00+00:00', 'completed'
            );
            CREATE TABLE scan_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, absolute_path TEXT NOT NULL,
                relative_path TEXT NOT NULL, name TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                element_type TEXT NOT NULL DEFAULT 'file',
                size INTEGER, modified_at TEXT,
                is_compatible INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'indexed', skip_reason TEXT,
                is_code_project INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
            );
            INSERT INTO scan_entries (
                session_id, absolute_path, relative_path, name, extension, status
            ) VALUES (
                'migrate-test', '/tmp/doc.pdf', 'doc.pdf', 'doc.pdf', '.pdf', 'indexed'
            );
            CREATE TABLE scan_errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, affected_path TEXT NOT NULL,
                error_code TEXT NOT NULL, message TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
            );
        """)
        conn.commit()
        conn.close()

        repo = SqliteScanSessionRepository(db_path)

        conn = sqlite3.connect(str(db_path))
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0]
        entry_count = conn.execute("SELECT COUNT(*) FROM scan_entries").fetchone()[0]
        has_excl_table = (  # noqa: E501
            conn.execute(  # noqa: E501
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_exclusion_rules'"  # noqa: E501
            ).fetchone()
            is not None
        )
        has_skip_detail = any(
            row[1] == "skip_detail"
            for row in conn.execute("PRAGMA table_info(scan_entries)")
        )
        has_hashes_table = (  # noqa: E501
            conn.execute(  # noqa: E501
                "SELECT name FROM sqlite_master WHERE type='table' AND name='content_hashes'"  # noqa: E501
            ).fetchone()
            is not None
        )
        conn.close()
        repo.close()

        assert version == 4
        assert session_count == 1
        assert entry_count == 1
        assert has_excl_table
        assert has_skip_detail
        assert has_hashes_table

    def test_v3_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v3_idempotent.db"
        repo1 = SqliteScanSessionRepository(db_path)
        repo1.close()
        repo2 = SqliteScanSessionRepository(db_path)
        repo2.close()

        import sqlite3

        conn = sqlite3.connect(str(db_path))
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        conn.close()
        assert version == 4

    def test_unknown_schema_version_rejected(self, tmp_path: Path) -> None:
        import sqlite3

        db_path = tmp_path / "future.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            (
                "CREATE TABLE schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        conn.execute(
            (
                "INSERT INTO schema_version (version, applied_at) "
                "VALUES (99, '2026-07-27T00:00:00+00:00')"
            )
        )
        conn.commit()
        conn.close()

        with pytest.raises(Exception) as excinfo:
            SqliteScanSessionRepository(db_path)
        assert "99" in str(excinfo.value)


class TestExclusionStats:
    def test_skipped_count_with_user_exclusion(self, tmp_path: Path) -> None:
        from folderscribe.application.scan_folder import ScanFolderUseCase
        from folderscribe.domain.models import ExclusionRule, RuleSource
        from folderscribe.infrastructure.database import SqliteScanSessionRepository
        from folderscribe.infrastructure.scanner import OsDirectoryScanner

        root = tmp_path / "stats_root"
        root.mkdir()
        (root / "keep.txt").write_text("keep")
        (root / "skip.tmp").write_text("skip")
        sub = root / "sub"
        sub.mkdir()
        (sub / "deep.tmp").write_text("deep skip")

        db_path = tmp_path / "stats.db"
        repo = SqliteScanSessionRepository(db_path)
        scanner = OsDirectoryScanner()
        use_case = ScanFolderUseCase(scanner, repo)
        rules = (ExclusionRule("*.tmp", RuleSource.USER),)
        result = use_case.execute(root, rules)
        repo.close()

        assert result.session is not None
        assert result.session.total_skipped == 2
        assert result.session.total_files == 1

    def test_excluded_directory_content_not_in_entries(self, tmp_path: Path) -> None:
        from folderscribe.application.scan_folder import ScanFolderUseCase
        from folderscribe.domain.models import ExclusionRule, RuleSource
        from folderscribe.infrastructure.database import SqliteScanSessionRepository
        from folderscribe.infrastructure.scanner import OsDirectoryScanner

        root = tmp_path / "prune_root"
        root.mkdir()
        privado = root / "privado"
        privado.mkdir()
        (privado / "secreto.txt").write_text("secret")
        (privado / "sub").mkdir()
        (privado / "sub" / "mas.txt").write_text("more")
        (root / "visible.txt").write_text("visible")

        db_path = tmp_path / "prune.db"
        repo = SqliteScanSessionRepository(db_path)
        scanner = OsDirectoryScanner()
        use_case = ScanFolderUseCase(scanner, repo)
        rules = (ExclusionRule("privado", RuleSource.USER),)
        result = use_case.execute(root, rules)
        assert result.session is not None
        repo.close()

        import sqlite3

        conn = sqlite3.connect(str(db_path))
        entry_paths = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM scan_entries WHERE session_id = ?",
                (result.session.session_id,),
            ).fetchall()
        ]
        conn.close()

        assert "visible.txt" in entry_paths
        assert "privado" in entry_paths
        assert "secreto.txt" not in entry_paths
        assert "mas.txt" not in entry_paths


class TestSchemaV3Migration:
    def test_migrate_v2_to_v3_preserves_data(self, tmp_path: Path) -> None:
        import sqlite3

        db_path = tmp_path / "v2_to_v3.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version (
                version, applied_at
            ) VALUES (2, '2026-07-27T00:00:00+00:00');
            CREATE TABLE scan_sessions (
                session_id TEXT PRIMARY KEY, root_path TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                is_recursive INTEGER NOT NULL DEFAULT 1,
                total_files INTEGER NOT NULL DEFAULT 0,
                total_compatible INTEGER NOT NULL DEFAULT 0,
                total_not_compatible INTEGER NOT NULL DEFAULT 0,
                total_skipped INTEGER NOT NULL DEFAULT 0,
                total_errors INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO scan_sessions (
                session_id, root_path, started_at, status
            ) VALUES (
                'migrate-v3-test', '/tmp', '2026-07-27T00:00:00+00:00', 'completed'
            );
            CREATE TABLE scan_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, absolute_path TEXT NOT NULL,
                relative_path TEXT NOT NULL, name TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                element_type TEXT NOT NULL DEFAULT 'file',
                size INTEGER, modified_at TEXT,
                is_compatible INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'indexed', skip_reason TEXT,
                is_code_project INTEGER NOT NULL DEFAULT 0,
                skip_detail TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
            );
            INSERT INTO scan_entries (
                session_id, absolute_path, relative_path,
                name, extension, status
            ) VALUES (
                'migrate-v3-test', '/tmp/doc.pdf', 'doc.pdf',
                'doc.pdf', '.pdf', 'indexed'
            );
            CREATE TABLE scan_errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, affected_path TEXT NOT NULL,
                error_code TEXT NOT NULL, message TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
            );
            CREATE TABLE scan_exclusion_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, pattern TEXT NOT NULL,
                source TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id)
            );
        """)
        conn.commit()
        conn.close()

        repo = SqliteScanSessionRepository(db_path)

        conn = sqlite3.connect(str(db_path))
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0]
        entry_count = conn.execute("SELECT COUNT(*) FROM scan_entries").fetchone()[0]
        has_hashes_table = (  # noqa: E501
            conn.execute(  # noqa: E501
                "SELECT name FROM sqlite_master WHERE type='table' AND name='content_hashes'"  # noqa: E501
            ).fetchone()
            is not None
        )
        conn.close()
        repo.close()

        assert version == 4
        assert session_count == 1
        assert entry_count == 1
        assert has_hashes_table

    def test_v3_has_expected_indexes(self, tmp_path: Path) -> None:
        import sqlite3

        db_path = tmp_path / "v3_indexes.db"
        repo = SqliteScanSessionRepository(db_path)
        conn = sqlite3.connect(str(db_path))
        indexes = [  # noqa: E501
            r[1]  # noqa: E501
            for r in conn.execute(  # noqa: E501
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='content_hashes'"  # noqa: E501
            ).fetchall()
        ]
        conn.close()
        repo.close()

        assert "idx_content_hashes_entry" in indexes
        assert "idx_content_hashes_hash" in indexes
        assert "idx_content_hashes_session" in indexes
