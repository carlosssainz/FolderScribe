import sqlite3
from pathlib import Path

from pytestqt.qtbot import QtBot

from folderscribe.ui.main_window import MainWindow


def _count_scan_sessions(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()
    assert row is not None
    count: int = row[0]
    conn.close()
    return count


def _count_scan_entries(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT COUNT(*) FROM scan_entries").fetchone()
    assert row is not None
    count: int = row[0]
    conn.close()
    return count


class TestRegressionQThread:
    def test_scan_completes_via_qthread(self, qtbot: QtBot, tmp_path: Path) -> None:
        root = tmp_path / "scandir"
        root.mkdir()
        (root / "document.pdf").write_text("pdf content")
        (root / "notes.txt").write_text("text content")
        (root / "skip.tmp").write_text("temporary")
        db_path = tmp_path / "test.db"

        window = MainWindow(db_path=db_path)
        qtbot.add_widget(window)
        window._path_edit.setText(str(root))
        window._exclude_edit.setText("*.tmp")
        window._add_exclusion()

        assert not db_path.exists()

        window._start_scan()
        assert window._scan_btn.isEnabled() is False
        worker = window._worker
        assert worker is not None

        with qtbot.wait_signal(worker.scan_finished, timeout=10000):
            pass

        qtbot.wait_until(lambda: window._scan_btn.isEnabled(), timeout=5000)
        assert window._worker is None
        assert db_path.exists()

        session_count = _count_scan_sessions(db_path)
        entry_count = _count_scan_entries(db_path)
        assert session_count == 1
        assert entry_count == 3

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT name, status, skip_reason FROM scan_entries ORDER BY name"
        ).fetchall()
        conn.close()

        names = {r[0]: r for r in rows}
        assert names["document.pdf"][1] == "indexed"
        assert names["notes.txt"][1] == "indexed"
        assert names["skip.tmp"][1] == "skipped"
        assert names["skip.tmp"][2] == "excluded_by_user_pattern"

    def test_two_consecutive_scans(self, qtbot: QtBot, tmp_path: Path) -> None:
        root = tmp_path / "scandir2"
        root.mkdir()
        (root / "alpha.txt").write_text("alpha")
        (root / "beta.txt").write_text("beta")
        db_path = tmp_path / "test2.db"

        window = MainWindow(db_path=db_path)
        qtbot.add_widget(window)
        window._path_edit.setText(str(root))

        window._start_scan()
        worker1 = window._worker
        assert worker1 is not None
        with qtbot.wait_signal(worker1.scan_finished, timeout=10000):
            pass
        qtbot.wait_until(lambda: window._scan_btn.isEnabled(), timeout=5000)

        assert _count_scan_sessions(db_path) == 1

        (root / "gamma.txt").write_text("gamma")
        window._start_scan()
        worker2 = window._worker
        assert worker2 is not None
        with qtbot.wait_signal(worker2.scan_finished, timeout=10000):
            pass
        qtbot.wait_until(lambda: window._scan_btn.isEnabled(), timeout=5000)

        assert _count_scan_sessions(db_path) == 2
        assert _count_scan_entries(db_path) == 5

    def test_scan_failure_restores_controls(self, qtbot: QtBot, tmp_path: Path) -> None:
        root = tmp_path / "scandir3"
        root.mkdir()
        (root / "file.txt").write_text("content")
        db_path = tmp_path / "test3.db"
        db_path.mkdir()

        window = MainWindow(db_path=db_path)
        qtbot.add_widget(window)
        window._path_edit.setText(str(root))

        window._start_scan()
        worker = window._worker
        assert worker is not None
        with qtbot.wait_signal(worker.scan_failed, timeout=10000):
            pass
        qtbot.wait_until(lambda: window._scan_btn.isEnabled(), timeout=5000)

        assert window._progress_bar.isVisible() is False

    def test_prevent_double_scan(self, qtbot: QtBot, tmp_path: Path) -> None:
        root = tmp_path / "scandir4"
        root.mkdir()
        (root / "file.txt").write_text("content")
        db_path = tmp_path / "test4.db"

        window = MainWindow(db_path=db_path)
        qtbot.add_widget(window)
        window._path_edit.setText(str(root))

        window._start_scan()
        assert window._worker is not None
        assert window._scan_btn.isEnabled() is False

        window._start_scan()
        assert window._scan_btn.isEnabled() is False

        worker = window._worker
        assert worker is not None
        with qtbot.wait_signal(worker.scan_finished, timeout=10000):
            pass
        qtbot.wait_until(lambda: window._scan_btn.isEnabled(), timeout=5000)

    def test_sqlite_error_shows_friendly_message(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        root = tmp_path / "scandir5"
        root.mkdir()
        (root / "file.txt").write_text("content")
        db_path = tmp_path / "test5.db"
        db_path.mkdir()

        window = MainWindow(db_path=db_path)
        qtbot.add_widget(window)
        window._path_edit.setText(str(root))

        window._start_scan()
        worker = window._worker
        assert worker is not None
        with qtbot.wait_signal(worker.scan_failed, timeout=10000):
            pass

        msg = window._status_label.text()
        assert "índice" in msg.lower()
        assert "sqlite" not in msg.lower()
