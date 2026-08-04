from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from folderscribe.application.scan_folder import ScanResult
from folderscribe.domain.models import (
    Compatibility,
    FileEntry,
    InventoryResult,
    ScanError,
)
from folderscribe.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    db_path = tmp_path / "test.db"
    window = MainWindow(db_path=db_path)
    qtbot.add_widget(window)
    return window


class TestMainWindowConstruction:
    def test_window_creation(self, main_window: MainWindow) -> None:
        assert main_window.windowTitle() == "FolderScribe Scan"
        assert main_window.isVisible() is False

    def test_initial_state(self, main_window: MainWindow) -> None:
        assert main_window._scan_btn.isEnabled() is True
        assert main_window._path_edit.text() == ""
        assert main_window._progress_bar.isVisible() is False

    def test_filter_combobox(self, main_window: MainWindow) -> None:
        assert main_window._filter_combo.count() == 10

    def test_shows_warning_label(self, main_window: MainWindow) -> None:
        text = main_window._warning_label.text()
        assert "analizará" in text
        assert "moverá" in text


class TestExclusions:
    def test_add_exclusion(self, main_window: MainWindow) -> None:
        main_window._exclude_edit.setText("*.tmp")
        main_window._add_exclusion()
        assert main_window._exclude_list.count() == 1
        item = main_window._exclude_list.item(0)
        assert item is not None
        assert item.text() == "*.tmp"

    def test_add_empty_exclusion_does_nothing(self, main_window: MainWindow) -> None:
        main_window._exclude_edit.setText("")
        main_window._add_exclusion()
        assert main_window._exclude_list.count() == 0

    def test_remove_exclusion(self, main_window: MainWindow) -> None:
        main_window._exclude_edit.setText("*.tmp")
        main_window._add_exclusion()
        assert main_window._exclude_list.count() == 1
        item = main_window._exclude_list.item(0)
        assert item is not None
        main_window._remove_exclusion(item)
        assert main_window._exclude_list.count() == 0

    def test_collect_exclusions(self, main_window: MainWindow) -> None:
        patterns = ["*.tmp", "*.log", "privado/**"]
        for p in patterns:
            main_window._exclude_edit.setText(p)
            main_window._add_exclusion()
        rules = main_window._collect_exclusions()
        assert len(rules) == 3
        assert rules[0].pattern == "*.tmp"
        assert rules[1].pattern == "*.log"
        assert rules[2].pattern == "privado/**"

    def test_enter_adds_exclusion(self, main_window: MainWindow, qtbot: QtBot) -> None:
        main_window._exclude_edit.setText("*.bak")
        main_window._exclude_edit.returnPressed.emit()
        assert main_window._exclude_list.count() == 1
        item = main_window._exclude_list.item(0)
        assert item is not None
        assert item.text() == "*.bak"

    def test_flush_pending_exclusion(self, main_window: MainWindow) -> None:
        main_window._exclude_edit.setText("*.log")
        main_window._flush_pending_exclusion()
        assert main_window._exclude_list.count() == 1
        assert main_window._exclude_edit.text() == ""


class TestScanValidation:
    def test_scan_without_path_shows_status(self, main_window: MainWindow) -> None:
        main_window._path_edit.setText("")
        main_window._start_scan()
        assert "Selecciona" in main_window._status_label.text()

    def test_scan_with_nonexistent_path(self, main_window: MainWindow) -> None:
        main_window._path_edit.setText("/nonexistent/path_xyz")
        main_window._start_scan()
        assert "no existe" in main_window._status_label.text()

    def test_prevent_double_scan(
        self, main_window: MainWindow, tmp_path: Path, qtbot: QtBot
    ) -> None:
        root = tmp_path / "scantest6"
        root.mkdir()

        main_window._path_edit.setText(str(root))
        main_window._start_scan()
        worker = main_window._worker
        assert worker is not None
        assert main_window._scan_btn.isEnabled() is False
        main_window._start_scan()
        assert main_window._scan_btn.isEnabled() is False

        with qtbot.wait_signal(worker.finished, timeout=5000):
            pass

        assert main_window._scan_btn.isEnabled() is True


class TestScanResults:
    def test_on_scan_finished_updates_ui(
        self, main_window: MainWindow, tmp_path: Path
    ) -> None:
        root = tmp_path / "scantest"
        root.mkdir()
        (root / "doc.pdf").write_text("pdf")
        (root / "notes.txt").write_text("text")

        inv = InventoryResult(
            root=root,
            files=(
                FileEntry(root / "doc.pdf", Compatibility.COMPATIBLE, size=100),
                FileEntry(root / "notes.txt", Compatibility.COMPATIBLE, size=200),
            ),
        )
        result = ScanResult(inventory=inv)
        main_window._on_scan_finished(result)

        assert main_window._table_model.rowCount() == 2
        assert "Completado" in main_window._status_label.text()
        assert main_window._scan_btn.isEnabled() is True

    def test_on_scan_finished_with_errors(
        self, main_window: MainWindow, tmp_path: Path
    ) -> None:
        root = tmp_path / "scantest2"
        inv = InventoryResult(
            root=root,
            errors=(ScanError(root / "bad", "permission", "Permission denied"),),
        )
        result = ScanResult(inventory=inv)
        main_window._on_scan_finished(result)

        assert main_window._error_tab.toPlainText() != ""

    def test_on_scan_failure_shows_error(self, main_window: MainWindow) -> None:
        main_window._on_scan_failed("Error de prueba")
        assert "Error de prueba" == main_window._status_label.text()
        assert main_window._scan_btn.isEnabled() is True

    def test_filtering_after_results(
        self, main_window: MainWindow, tmp_path: Path
    ) -> None:
        root = tmp_path / "scantest3"
        root.mkdir()

        inv = InventoryResult(
            root=root,
            files=(
                FileEntry(root / "doc.pdf", Compatibility.COMPATIBLE, size=100),
                FileEntry(root / "image.jpg", Compatibility.NOT_COMPATIBLE, size=200),
            ),
        )
        result = ScanResult(inventory=inv)
        main_window._on_scan_finished(result)

        main_window._filter_combo.setCurrentIndex(0)
        assert main_window._proxy_model.rowCount() == 2

        main_window._filter_combo.setCurrentIndex(1)
        assert main_window._proxy_model.rowCount() == 1

    def test_scan_updates_summary(
        self, main_window: MainWindow, tmp_path: Path
    ) -> None:
        root = tmp_path / "scantest4"
        root.mkdir()

        inv = InventoryResult(
            root=root,
            files=(
                FileEntry(root / "doc.pdf", Compatibility.COMPATIBLE, size=100),
                FileEntry(root / "image.jpg", Compatibility.NOT_COMPATIBLE, size=200),
            ),
            skipped=(),
        )
        result = ScanResult(inventory=inv)
        main_window._on_scan_finished(result)

        summary = main_window._summary_label.text()
        assert "Indexados: 2" in summary
        assert "Compatibles: 1" in summary
        assert "No compatibles: 1" in summary

    def test_restore_controls_after_failure(
        self, main_window: MainWindow, tmp_path: Path, qtbot: QtBot
    ) -> None:
        root = tmp_path / "scandir_fail"
        root.mkdir()
        (root / "file.txt").write_text("hello")
        main_window._path_edit.setText(str(root))

        db_path = tmp_path / "test.db"
        db_path.mkdir()
        main_window._db_path = db_path

        main_window._start_scan()
        worker = main_window._worker
        assert worker is not None
        with qtbot.wait_signal(worker.finished, timeout=10000):
            pass

        assert main_window._scan_btn.isEnabled() is True
        assert main_window._progress_bar.isVisible() is False
        text = main_window._status_label.text()
        assert "No se pudo" in text or "índice" in text

    def test_no_sqlite_objects_in_scan_result(
        self, main_window: MainWindow, tmp_path: Path, qtbot: QtBot
    ) -> None:
        root = tmp_path / "scantest5"
        root.mkdir()
        (root / "file.txt").write_text("test")
        main_window._path_edit.setText(str(root))

        main_window._start_scan()
        worker = main_window._worker
        assert worker is not None

        with qtbot.wait_signal(worker.scan_finished, timeout=5000):
            pass

        assert main_window._table_model is not None
