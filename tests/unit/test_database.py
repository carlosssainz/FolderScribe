from datetime import datetime, timezone
from pathlib import Path

import pytest

from folderscribe.domain.models import (
    PersistenceError,
    ScanEntry,
    ScanSession,
    SessionStatus,
)


class TestSessionStatus:
    def test_values(self) -> None:
        assert SessionStatus.RUNNING.value == "running"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.COMPLETED_WITH_ERRORS.value == "completed_with_errors"
        assert SessionStatus.FAILED.value == "failed"
        assert SessionStatus.CANCELLED.value == "cancelled"


class TestScanSession:
    def test_create_session(self) -> None:
        now = datetime.now(timezone.utc)
        session = ScanSession(
            session_id="test-id",
            root_path=Path("/tmp/test"),
            started_at=now,
        )
        assert session.session_id == "test-id"
        assert session.root_path == Path("/tmp/test")
        assert session.started_at == now
        assert session.finished_at is None
        assert session.status == SessionStatus.RUNNING
        assert session.is_recursive is True
        assert session.total_files == 0

    def test_completed_session_stats(self) -> None:
        now = datetime.now(timezone.utc)
        session = ScanSession(
            session_id="test-id",
            root_path=Path("/tmp/test"),
            started_at=now,
            finished_at=now,
            status=SessionStatus.COMPLETED,
            total_files=10,
            total_compatible=7,
            total_not_compatible=3,
            total_skipped=2,
            total_errors=0,
        )
        assert session.status == SessionStatus.COMPLETED
        assert session.total_files == 10
        assert session.total_compatible == 7


class TestScanEntry:
    def test_create_file_entry(self) -> None:
        entry = ScanEntry(
            session_id="s1",
            absolute_path=Path("/tmp/test/doc.pdf"),
            relative_path="doc.pdf",
            name="doc.pdf",
            extension=".pdf",
        )
        assert entry.session_id == "s1"
        assert entry.element_type == "file"
        assert entry.is_compatible is False
        assert entry.status == "indexed"

    def test_skipped_directory_entry(self) -> None:
        entry = ScanEntry(
            session_id="s1",
            absolute_path=Path("/tmp/test/.git"),
            relative_path=".git",
            name=".git",
            extension="",
            element_type="directory",
            is_compatible=False,
            status="skipped",
            skip_reason="excluded_directory",
        )
        assert entry.status == "skipped"
        assert entry.skip_reason == "excluded_directory"


class TestPersistenceError:
    def test_is_exception(self) -> None:
        err = PersistenceError("something failed")
        assert isinstance(err, Exception)
        assert str(err) == "something failed"

    def test_is_raiseable(self) -> None:
        try:
            raise PersistenceError("wrapped") from ValueError("original")
        except PersistenceError as err:
            assert isinstance(err.__cause__, ValueError)
            assert str(err) == "wrapped"


class TestGetDefaultDbPath:
    def test_uses_xdg_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        from folderscribe.infrastructure.database import get_default_db_path

        monkeypatch.setitem(os.environ, "XDG_DATA_HOME", "/custom/data")
        path = get_default_db_path()
        assert str(path).startswith("/custom/data/folderscribe/")
        assert path.name == "folderscribe.db"

    def test_fallback_when_no_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from folderscribe.infrastructure.database import get_default_db_path

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        path = get_default_db_path()
        home = Path.home()
        assert str(path).startswith(str(home / ".local" / "share" / "folderscribe"))
        assert path.name == "folderscribe.db"
