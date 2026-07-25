import os
from pathlib import Path

from folderscribe.domain.interfaces import DirectoryScanner
from folderscribe.domain.models import (
    Compatibility,
    FileEntry,
    InventoryResult,
    ScanError,
    SkippedEntry,
)

_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md", ".markdown"})


def _classify(path: Path) -> Compatibility:
    suffix = path.suffix.lower()
    if suffix in _SUPPORTED_EXTENSIONS:
        return Compatibility.COMPATIBLE
    return Compatibility.NOT_COMPATIBLE


class OsDirectoryScanner(DirectoryScanner):
    def scan(self, root: Path) -> InventoryResult:
        files: list[FileEntry] = []
        skipped: list[SkippedEntry] = []
        errors: list[ScanError] = []

        dirs_to_scan: list[Path] = [root]

        while dirs_to_scan:
            current = dirs_to_scan.pop()

            try:
                entries = list(os.scandir(current))
            except PermissionError:
                errors.append(
                    ScanError(
                        path=current,
                        code="permission",
                        message=f"Permission denied: {current}",
                    )
                )
                continue
            except OSError as e:
                errors.append(
                    ScanError(
                        path=current,
                        code="access",
                        message=str(e),
                    )
                )
                continue

            entries.sort(key=lambda e: e.name)

            for entry in entries:
                entry_path = Path(entry.path)

                if entry.is_symlink():
                    skipped.append(
                        SkippedEntry(
                            path=entry_path,
                            reason="symlink",
                        )
                    )
                    continue

                try:
                    if entry.is_dir():
                        dirs_to_scan.append(entry_path)
                    elif entry.is_file():
                        files.append(
                            FileEntry(
                                path=entry_path,
                                compatibility=_classify(entry_path),
                            )
                        )
                except OSError as e:
                    errors.append(
                        ScanError(
                            path=entry_path,
                            code="access",
                            message=str(e),
                        )
                    )

        files.sort(key=lambda f: f.path)
        skipped.sort(key=lambda s: s.path)
        errors.sort(key=lambda e: e.path)

        return InventoryResult(
            root=root,
            files=tuple(files),
            skipped=tuple(skipped),
            errors=tuple(errors),
        )
