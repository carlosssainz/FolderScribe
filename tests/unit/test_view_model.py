from pathlib import Path

from folderscribe.domain.models import (
    Compatibility,
    FileEntry,
    InventoryResult,
    ScanError,
    SkippedEntry,
)
from folderscribe.ui.view_model import ViewModel


def test_empty_inventory() -> None:
    root = Path("/test")
    inv = InventoryResult(root=root)
    vm = ViewModel.from_inventory(inv)
    assert vm.rows == []
    assert vm.errors == []
    assert vm.total_files == 0
    assert vm.total_indexed == 0
    assert vm.total_compatible == 0
    assert vm.total_not_compatible == 0
    assert vm.total_skipped == 0
    assert vm.total_errors == 0


def test_compatible_file() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(
            FileEntry(
                path=root / "doc.pdf",
                compatibility=Compatibility.COMPATIBLE,
                size=1024,
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    assert len(vm.rows) == 1
    row = vm.rows[0]
    assert row.name == "doc.pdf"
    assert row.relative_path == "doc.pdf"
    assert row.status == "indexed"
    assert row.skip_reason is None
    assert row.element_type == "file"
    assert row.size == 1024
    assert row.is_compatible is True
    assert vm.total_indexed == 1
    assert vm.total_compatible == 1
    assert vm.total_not_compatible == 0


def test_not_compatible_file() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(
            FileEntry(
                path=root / "image.jpg",
                compatibility=Compatibility.NOT_COMPATIBLE,
                size=2048,
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    row = vm.rows[0]
    assert row.status == "indexed"
    assert row.is_compatible is False
    assert vm.total_not_compatible == 1


def test_skipped_symlink() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        skipped=(
            SkippedEntry(
                path=root / "link.txt",
                reason="symlink",
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    assert len(vm.rows) == 1
    row = vm.rows[0]
    assert row.name == "link.txt"
    assert row.relative_path == "link.txt"
    assert row.status == "skipped"
    assert row.skip_reason == "symlink"
    assert row.is_compatible is False
    assert vm.total_skipped == 1


def test_skipped_user_exclusion() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        skipped=(
            SkippedEntry(
                path=root / "secret.txt",
                reason="excluded_by_user_pattern",
                details="*.txt",
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    row = vm.rows[0]
    assert row.skip_reason == "excluded_by_user_pattern"
    assert row.skip_detail == "*.txt"


def test_skipped_code_project() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        skipped=(
            SkippedEntry(
                path=root / "my_project",
                reason="code_project",
                details="pyproject.toml",
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    row = vm.rows[0]
    assert row.skip_reason == "code_project"
    assert row.skip_detail == "pyproject.toml"


def test_errors() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        errors=(
            ScanError(
                path=root / "bad_dir",
                code="permission",
                message="Permission denied: /test/bad_dir",
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    assert len(vm.errors) == 1
    err = vm.errors[0]
    assert err.path == str(root / "bad_dir")
    assert err.code == "permission"
    assert "Permission denied" in err.message
    assert vm.total_errors == 1


def test_unicode_and_spaces() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(
            FileEntry(
                path=root / "café 2024.pdf",
                compatibility=Compatibility.COMPATIBLE,
                size=512,
            ),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    row = vm.rows[0]
    assert row.name == "café 2024.pdf"
    assert vm.total_files == 1


def test_mixed_content() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(
            FileEntry(root / "a.pdf", Compatibility.COMPATIBLE, size=100),
            FileEntry(root / "b.jpg", Compatibility.NOT_COMPATIBLE, size=200),
        ),
        skipped=(
            SkippedEntry(root / "secret.tmp", "excluded_by_user_pattern", "*.tmp"),
            SkippedEntry(root / "link", "symlink"),
        ),
        errors=(ScanError(root / "bad", "permission", "Denied"),),
    )
    vm = ViewModel.from_inventory(inv)
    assert len(vm.rows) == 4
    assert vm.total_files == 2
    assert vm.total_indexed == 2
    assert vm.total_compatible == 1
    assert vm.total_not_compatible == 1
    assert vm.total_skipped == 2
    assert vm.total_errors == 1
    assert len(vm.errors) == 1

    assert vm.rows[0].name == "a.pdf"
    assert vm.rows[1].name == "b.jpg"
    assert vm.rows[2].name == "link"
    assert vm.rows[3].name == "secret.tmp"


def test_sorted_by_relative_path() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(
            FileEntry(root / "z.txt", Compatibility.COMPATIBLE, size=1),
            FileEntry(root / "a.txt", Compatibility.COMPATIBLE, size=2),
        ),
    )
    vm = ViewModel.from_inventory(inv)
    assert vm.rows[0].name == "a.txt"
    assert vm.rows[1].name == "z.txt"


def test_absolute_path_populated() -> None:
    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(FileEntry(root / "doc.pdf", Compatibility.COMPATIBLE, size=100),),
    )
    vm = ViewModel.from_inventory(inv)
    assert vm.rows[0].absolute_path == str(root / "doc.pdf")


def test_apply_ocr_result_updates_row() -> None:
    from folderscribe.domain.extraction import ExtractionStatus, TextExtraction
    from folderscribe.domain.ocr import OcrResult

    root = Path("/test")
    inv = InventoryResult(
        root=root,
        files=(FileEntry(root / "scanned.pdf", Compatibility.COMPATIBLE, size=100),),
    )
    vm = ViewModel.from_inventory(inv)
    row = vm.rows[0]
    row.extraction_status = "needs_ocr"
    row.extraction_needs_ocr = True

    extraction = TextExtraction(
        absolute_path=root / "scanned.pdf",
        extractor="pdf_ocr",
        extractor_version="1",
        config_version="ocr_mode=fast",
        status=ExtractionStatus.EXTRACTED,
        content="OCR result",
        char_count=10,
        processed_pages=3,
        needs_ocr=False,
    )
    result = OcrResult(
        session_id="s1",
        ocr_extractions=(extraction,),
        total_processed=1,
        engine_available=True,
        ocr_count=1,
        reused_count=0,
        partial_count=0,
        skipped_count=0,
        error_count=0,
        cancelled_count=0,
        stale_count=0,
    )

    vm.apply_ocr_result(result)

    assert row.extraction_status == "extracted"
    assert row.extraction_needs_ocr is False
    assert row.extraction_chars == 10
    assert row.extraction_pages == 3
