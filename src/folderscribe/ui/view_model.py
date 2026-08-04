from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from folderscribe.domain.extraction import ExtractionResult
from folderscribe.domain.hashing import HashResult
from folderscribe.domain.models import (
    Compatibility,
    InventoryResult,
)
from folderscribe.domain.ocr import OcrResult


@dataclass
class DisplayRow:
    name: str
    relative_path: str
    status: str
    skip_reason: str | None
    skip_detail: str
    element_type: str
    size: int | None
    is_compatible: bool
    absolute_path: str = ""
    hash_status: str = ""
    hash_value: str = ""
    extraction_status: str = ""
    extraction_chars: int = 0
    extraction_truncated: bool = False
    extraction_needs_ocr: bool = False
    extraction_pages: int = 0
    extraction_error: str = ""
    entry_id: int = 0


@dataclass
class ErrorRow:
    path: str
    code: str
    message: str


@dataclass
class DuplicateGroupRow:
    group_id: str
    hash_value: str
    file_size: int
    file_count: int
    wasted_space: int
    file_paths: str


@dataclass
class ViewModel:
    rows: list[DisplayRow] = field(default_factory=list)
    errors: list[ErrorRow] = field(default_factory=list)
    total_files: int = 0
    total_indexed: int = 0
    total_compatible: int = 0
    total_not_compatible: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    hash_computed: int = 0
    hash_reused: int = 0
    hash_errors: int = 0
    hash_modified: int = 0
    duplicate_groups: list[DuplicateGroupRow] = field(default_factory=list)
    duplicate_count: int = 0

    STATUS_INDEXED: ClassVar[str] = "indexed"
    STATUS_SKIPPED: ClassVar[str] = "skipped"

    @classmethod
    def from_inventory(cls, inventory: InventoryResult) -> "ViewModel":
        root = inventory.root
        rows: list[DisplayRow] = []
        indexed_count = 0
        compatible_count = 0
        not_compatible_count = 0

        for fe in inventory.files:
            indexed_count += 1
            if fe.compatibility == Compatibility.COMPATIBLE:
                compatible_count += 1
            else:
                not_compatible_count += 1
            try:
                rel = fe.path.relative_to(root)
            except ValueError:
                rel = Path(fe.path.name)
            rows.append(
                DisplayRow(
                    name=fe.path.name,
                    relative_path=str(rel),
                    status=cls.STATUS_INDEXED,
                    skip_reason=None,
                    skip_detail="",
                    element_type="file",
                    size=fe.size,
                    is_compatible=fe.compatibility == Compatibility.COMPATIBLE,
                    absolute_path=str(fe.path),
                )
            )

        for se in inventory.skipped:
            try:
                rel = se.path.relative_to(root)
            except ValueError:
                rel = Path(se.path.name)
            is_dir = se.path.is_dir()
            rows.append(
                DisplayRow(
                    name=se.path.name,
                    relative_path=str(rel),
                    status=cls.STATUS_SKIPPED,
                    skip_reason=se.reason,
                    skip_detail=se.details,
                    element_type="directory" if is_dir else "other",
                    size=None,
                    is_compatible=False,
                )
            )

        error_rows = [
            ErrorRow(
                path=str(e.path),
                code=e.code,
                message=e.message,
            )
            for e in inventory.errors
        ]

        rows.sort(key=lambda r: r.relative_path)

        return cls(
            rows=rows,
            errors=error_rows,
            total_files=inventory.total_files,
            total_indexed=indexed_count,
            total_compatible=compatible_count,
            total_not_compatible=not_compatible_count,
            total_skipped=inventory.total_skipped,
            total_errors=inventory.total_errors,
        )

    def apply_hash_result(self, result: HashResult) -> None:
        self.hash_computed = result.computed_count
        self.hash_reused = result.reused_count
        self.hash_errors = result.error_count
        self.hash_modified = result.modified_count

        hash_map: dict[Path, tuple[str, str]] = {}
        for h in result.hashes:
            hash_map[h.absolute_path] = (
                h.status.value,
                h.hash_sha256[:16] if h.hash_sha256 else "",
            )

        for row in self.rows:
            if row.status == self.STATUS_INDEXED:
                for abs_path, (h_status, h_val) in hash_map.items():
                    if abs_path.name == row.name or str(abs_path).endswith(
                        row.relative_path
                    ):
                        row.hash_status = h_status
                        row.hash_value = h_val
                        break

        groups = []
        for g in result.duplicate_groups:
            paths_str = "\n".join(str(p) for p in g.file_paths)
            groups.append(
                DuplicateGroupRow(
                    group_id=g.group_id,
                    hash_value=g.hash_sha256,
                    file_size=g.file_size,
                    file_count=g.file_count,
                    wasted_space=g.wasted_space,
                    file_paths=paths_str,
                )
            )
        self.duplicate_groups = groups
        self.duplicate_count = len(groups)

    def apply_ocr_result(self, result: OcrResult) -> None:
        ocr_map: dict[str, tuple[str, int, bool, int, str]] = {}
        for e in result.ocr_extractions:
            ocr_map[str(e.absolute_path)] = (
                e.status.value,
                e.char_count,
                e.is_truncated,
                e.processed_pages,
                e.error_message or "",
            )

        for row in self.rows:
            if row.status == self.STATUS_INDEXED:
                entry = ocr_map.get(row.absolute_path)
                if entry is None:
                    continue
                e_status, e_chars, e_trunc, e_pages, e_err = entry
                row.extraction_status = e_status
                row.extraction_chars = e_chars
                row.extraction_truncated = e_trunc
                row.extraction_needs_ocr = False
                row.extraction_pages = e_pages
                row.extraction_error = e_err

    def apply_extraction_result(self, result: ExtractionResult) -> None:
        ext_map: dict[Path, tuple[str, int, bool, bool, int, str]] = {}
        for e in result.extractions:
            ext_map[e.absolute_path] = (
                e.status.value,
                e.char_count,
                e.is_truncated,
                e.needs_ocr,
                e.processed_pages,
                e.error_message or "",
            )

        for row in self.rows:
            if row.status == self.STATUS_INDEXED:
                for abs_path, (
                    e_status,
                    e_chars,
                    e_trunc,
                    e_ocr,
                    e_pages,
                    e_err,
                ) in ext_map.items():
                    if abs_path.name == row.name or str(abs_path).endswith(
                        row.relative_path
                    ):
                        row.extraction_status = e_status
                        row.extraction_chars = e_chars
                        row.extraction_truncated = e_trunc
                        row.extraction_needs_ocr = e_ocr
                        row.extraction_pages = e_pages
                        row.extraction_error = e_err
                        break
