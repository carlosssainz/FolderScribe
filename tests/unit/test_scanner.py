import os
from pathlib import Path
from unittest.mock import patch

import pytest

from folderscribe.application.scan_folder import ScanFolderUseCase
from folderscribe.domain.models import (
    Compatibility,
    FileEntry,
    InventoryResult,
    ScanError,
    SkippedEntry,
)
from folderscribe.infrastructure.scanner import OsDirectoryScanner


@pytest.fixture
def scanner() -> OsDirectoryScanner:
    return OsDirectoryScanner()


@pytest.fixture
def use_case(scanner: OsDirectoryScanner) -> ScanFolderUseCase:
    return ScanFolderUseCase(scanner)


class TestOsDirectoryScanner:
    def test_empty_directory(self, tmp_path: Path, scanner: OsDirectoryScanner) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        result = scanner.scan(root)
        assert result.total_files == 0
        assert result.total_skipped == 0
        assert result.total_errors == 0

    def test_pdf_compatible(self, tmp_path: Path, scanner: OsDirectoryScanner) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "doc.pdf").write_text("dummy")
        result = scanner.scan(root)
        assert result.total_files == 1
        assert result.files[0].compatibility == Compatibility.COMPATIBLE

    def test_uppercase_extension(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "DOC.PDF").write_text("dummy")
        result = scanner.scan(root)
        assert result.total_files == 1
        assert result.files[0].compatibility == Compatibility.COMPATIBLE

    def test_not_compatible(self, tmp_path: Path, scanner: OsDirectoryScanner) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "image.jpg").write_text("dummy")
        result = scanner.scan(root)
        assert result.total_files == 1
        assert result.files[0].compatibility == Compatibility.NOT_COMPATIBLE

    def test_nested_directories(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        sub = root / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("hello")
        result = scanner.scan(root)
        assert result.total_files == 1
        assert result.files[0].path == sub / "nested.txt"

    def test_symlink_file_skipped(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        target = root / "real.txt"
        target.write_text("content")
        link = root / "link.txt"
        link.symlink_to(target)
        result = scanner.scan(root)
        assert link in [s.path for s in result.skipped]
        assert target in [f.path for f in result.files]

    def test_symlink_directory_skipped(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        real_dir = root / "real_dir"
        real_dir.mkdir()
        (real_dir / "inside.txt").write_text("content")
        link = root / "link_to_dir"
        link.symlink_to(real_dir, target_is_directory=True)
        result = scanner.scan(root)
        assert link in [s.path for s in result.skipped]
        assert real_dir / "inside.txt" in [f.path for f in result.files]

    def test_permission_error_continues(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "ok.txt").write_text("ok")
        restricted = root / "restricted"
        restricted.mkdir()
        (restricted / "inner.txt").write_text("should not be scanned")

        original_scandir = os.scandir

        def _mock_scandir(path):
            if Path(path) == restricted:
                raise PermissionError(13, "Permission denied")
            return original_scandir(path)

        with patch(
            "folderscribe.infrastructure.scanner.os.scandir", side_effect=_mock_scandir
        ):
            result = scanner.scan(root)

        assert result.total_files == 1
        assert result.files[0].path.name == "ok.txt"
        assert result.total_errors == 1
        assert result.errors[0].code == "permission"

    def test_files_not_modified(
        self, tmp_path: Path, scanner: OsDirectoryScanner
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        f = root / "test.txt"
        f.write_text("hello")
        before = f.stat()
        scanner.scan(root)
        after = f.stat()
        assert before.st_mtime == after.st_mtime
        assert before.st_size == after.st_size


class TestScanFolderUseCase:
    def test_nonexistent_path(
        self, tmp_path: Path, use_case: ScanFolderUseCase
    ) -> None:
        path = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            use_case.execute(path)

    def test_path_is_file(self, tmp_path: Path, use_case: ScanFolderUseCase) -> None:
        path = tmp_path / "a_file.txt"
        path.write_text("not a directory")
        with pytest.raises(NotADirectoryError):
            use_case.execute(path)

    def test_inventory_result_properties(self) -> None:
        compatible = FileEntry(Path("/a.pdf"), Compatibility.COMPATIBLE)
        not_compatible = FileEntry(Path("/b.jpg"), Compatibility.NOT_COMPATIBLE)
        skipped = SkippedEntry(Path("/link"), "symlink")
        error = ScanError(Path("/bad"), "permission", "denied")
        result = InventoryResult(
            root=Path("/"),
            files=(compatible, not_compatible),
            skipped=(skipped,),
            errors=(error,),
        )
        assert result.compatible_files == (compatible,)
        assert result.not_compatible_files == (not_compatible,)
        assert result.total_files == 2
        assert result.total_skipped == 1
        assert result.total_errors == 1
