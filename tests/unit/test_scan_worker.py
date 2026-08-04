from pathlib import Path
from unittest.mock import MagicMock

from folderscribe.domain.models import ExclusionRule, RuleSource
from folderscribe.ui.scan_worker import ScanWorker


def test_worker_emits_finished_on_success(tmp_path: Path) -> None:
    root = tmp_path / "testdir"
    root.mkdir()
    (root / "file.txt").write_text("hello")

    db_path = tmp_path / "test.db"
    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=(),
    )

    finished_fn = MagicMock()
    failed_fn = MagicMock()
    worker.scan_finished.connect(finished_fn)
    worker.scan_failed.connect(failed_fn)

    worker.run()

    finished_fn.assert_called_once()
    failed_fn.assert_not_called()


def test_worker_emits_failed_on_file_not_found(tmp_path: Path) -> None:
    root = Path("/nonexistent/path")
    db_path = tmp_path / "test.db"

    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=(),
    )

    failed_fn = MagicMock()
    finished_fn = MagicMock()
    worker.scan_failed.connect(failed_fn)
    worker.scan_finished.connect(finished_fn)

    worker.run()

    failed_fn.assert_called_once()
    finished_fn.assert_not_called()
    msg = failed_fn.call_args[0][0]
    assert "no existe" in msg.lower()


def test_worker_emits_failed_on_not_a_directory(tmp_path: Path) -> None:
    root = tmp_path / "afile.txt"
    root.write_text("not a dir")
    db_path = tmp_path / "test.db"

    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=(),
    )

    failed_fn = MagicMock()
    finished_fn = MagicMock()
    worker.scan_failed.connect(failed_fn)
    worker.scan_finished.connect(finished_fn)

    worker.run()

    failed_fn.assert_called_once()
    finished_fn.assert_not_called()
    msg = failed_fn.call_args[0][0]
    assert "directorio" in msg.lower()


def test_worker_passes_exclusion_rules_and_creates_db(tmp_path: Path) -> None:
    root = tmp_path / "testdir"
    root.mkdir()
    (root / "keep.txt").write_text("keep")
    (root / "skip.tmp").write_text("skip")

    db_path = tmp_path / "test.db"
    rules = (ExclusionRule("*.tmp", RuleSource.USER),)

    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=rules,
    )

    finished_fn = MagicMock()
    failed_fn = MagicMock()
    worker.scan_finished.connect(finished_fn)
    worker.scan_failed.connect(failed_fn)

    worker.run()

    finished_fn.assert_called_once()
    failed_fn.assert_not_called()
    assert db_path.exists()

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name, status, skip_reason FROM scan_entries ORDER BY name"
    ).fetchall()
    conn.close()

    entry_map = {r[0]: r for r in rows}
    assert entry_map["keep.txt"][1] == "indexed"
    assert entry_map["skip.tmp"][1] == "skipped"
    assert entry_map["skip.tmp"][2] == "excluded_by_user_pattern"


def test_worker_handles_sqlite_connect_error(tmp_path: Path) -> None:
    root = tmp_path / "testdir"
    root.mkdir()
    (root / "file.txt").write_text("hello")
    db_path = tmp_path / "test.db"
    db_path.mkdir()

    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=(),
    )

    failed_fn = MagicMock()
    finished_fn = MagicMock()
    worker.scan_failed.connect(failed_fn)
    worker.scan_finished.connect(finished_fn)

    worker.run()

    failed_fn.assert_called_once()
    finished_fn.assert_not_called()
    msg = failed_fn.call_args[0][0]
    assert "completar" in msg.lower() or "índice" in msg.lower()


def test_worker_result_has_no_sqlite_objects(tmp_path: Path) -> None:
    root = tmp_path / "testdir"
    root.mkdir()
    (root / "file.txt").write_text("hello")
    db_path = tmp_path / "test.db"

    worker = ScanWorker(
        root=root,
        database_path=db_path,
        exclusion_rules=(),
    )

    result_container: list[object] = []
    worker.scan_finished.connect(result_container.append)

    worker.run()

    assert len(result_container) == 1
    result = result_container[0]
    assert "sqlite3" not in type(result).__module__
    assert "Connection" not in type(result).__module__
    assert "Cursor" not in type(result).__module__
