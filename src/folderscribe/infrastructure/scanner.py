import os
from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.exclusion import ExclusionMatcher
from folderscribe.domain.interfaces import DirectoryScanner
from folderscribe.domain.models import (
    Compatibility,
    ExclusionRule,
    FileEntry,
    InventoryResult,
    ScanError,
    SkippedEntry,
)

_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md", ".markdown"})

_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

_CODE_PROJECT_MARKERS = frozenset(
    {
        ".git",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "CMakeLists.txt",
    }
)


def _classify(path: Path) -> Compatibility:
    suffix = path.suffix.lower()
    if suffix in _SUPPORTED_EXTENSIONS:
        return Compatibility.COMPATIBLE
    return Compatibility.NOT_COMPATIBLE


def _detect_project_marker(dir_path: Path) -> str | None:
    try:
        for entry in os.scandir(dir_path):
            if entry.name in _CODE_PROJECT_MARKERS:
                return entry.name
    except OSError:
        return None
    return None


class OsDirectoryScanner(DirectoryScanner):
    def scan(
        self,
        root: Path,
        exclusion_rules: tuple[ExclusionRule, ...] = (),
    ) -> InventoryResult:
        files: list[FileEntry] = []
        skipped: list[SkippedEntry] = []
        errors: list[ScanError] = []

        matcher = ExclusionMatcher(exclusion_rules) if exclusion_rules else None

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
                        if entry.name in _EXCLUDED_DIR_NAMES:
                            skipped.append(
                                SkippedEntry(
                                    path=entry_path,
                                    reason="excluded_directory",
                                    details=entry.name,
                                )
                            )
                            continue

                        marker = _detect_project_marker(entry_path)
                        if marker is not None:
                            skipped.append(
                                SkippedEntry(
                                    path=entry_path,
                                    reason="code_project",
                                    details=marker,
                                )
                            )
                            continue

                        if matcher is not None:
                            relative = entry_path.relative_to(root).as_posix()
                            excluded, rule = matcher.is_excluded(relative)
                            if excluded:
                                assert rule is not None
                                skipped.append(
                                    SkippedEntry(
                                        path=entry_path,
                                        reason="excluded_by_user_pattern",
                                        details=rule.pattern,
                                    )
                                )
                                continue

                        dirs_to_scan.append(entry_path)
                    elif entry.is_file():
                        if matcher is not None:
                            relative = entry_path.relative_to(root).as_posix()
                            excluded, rule = matcher.is_excluded(relative)
                            if excluded:
                                assert rule is not None
                                skipped.append(
                                    SkippedEntry(
                                        path=entry_path,
                                        reason="excluded_by_user_pattern",
                                        details=rule.pattern,
                                    )
                                )
                                continue

                        stat = entry_path.stat()
                        modified_at = datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        )
                        files.append(
                            FileEntry(
                                path=entry_path,
                                compatibility=_classify(entry_path),
                                size=stat.st_size,
                                modified_at=modified_at,
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
