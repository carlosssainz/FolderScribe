from pathlib import Path
from unittest.mock import patch

from folderscribe.domain.models import (
    Compatibility,
    FileEntry,
    InventoryResult,
    ScanError,
)
from folderscribe.main import main


def test_main_returns_zero() -> None:
    assert main([]) == 0


def test_main_prints_message(capsys) -> None:
    main([])
    captured = capsys.readouterr()
    assert captured.out.strip() == "FolderScribe is ready."


def test_scan_empty_directory(tmp_path: Path, capsys) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    exit_code = main(["scan", str(root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total files: 0" in captured.out
    assert "Errors: 0" in captured.out


def test_scan_with_files(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "doc.pdf").write_text("pdf")
    (root / "image.jpg").write_text("jpg")
    (root / "readme.txt").write_text("txt")
    exit_code = main(["scan", str(root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total files: 3" in captured.out
    assert "Compatible files: 2" in captured.out
    assert "Unsupported files: 1" in captured.out
    assert "  doc.pdf" in captured.out
    assert "  readme.txt" in captured.out
    assert "  image.jpg" not in captured.out


def test_scan_nonexistent_path(capsys) -> None:
    exit_code = main(["scan", "/this/path/does/not/exist_42"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
    assert captured.out == ""


def test_scan_path_is_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "a_file.txt"
    path.write_text("not a directory")
    exit_code = main(["scan", str(path)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "is not a directory" in captured.err
    assert captured.out == ""


def test_scan_sorted_output(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "b.txt").write_text("b")
    (root / "a.txt").write_text("a")
    (root / "c.txt").write_text("c")
    exit_code = main(["scan", str(root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    idx_a = lines.index("  a.txt")
    idx_b = lines.index("  b.txt")
    idx_c = lines.index("  c.txt")
    assert idx_a < idx_b < idx_c


def test_scan_errors_partial_return_1(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.pdf").write_text("ok")

    with patch(
        "folderscribe.infrastructure.scanner.OsDirectoryScanner.scan",
        return_value=InventoryResult(
            root=root,
            files=(FileEntry(root / "ok.pdf", Compatibility.COMPATIBLE),),
            errors=(ScanError(root / "bad", "permission", "Permission denied"),),
        ),
    ):
        exit_code = main(["scan", str(root)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Total files: 1" in captured.out
    assert "Errors: 1" in captured.out
    assert "Permission denied" in captured.err
