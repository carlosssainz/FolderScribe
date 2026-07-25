from enum import Enum, auto
from pathlib import Path
from dataclasses import dataclass


class Compatibility(Enum):
    COMPATIBLE = auto()
    NOT_COMPATIBLE = auto()


@dataclass(frozen=True)
class FileEntry:
    path: Path
    compatibility: Compatibility


@dataclass(frozen=True)
class SkippedEntry:
    path: Path
    reason: str


@dataclass(frozen=True)
class ScanError:
    path: Path
    code: str
    message: str


@dataclass(frozen=True)
class InventoryResult:
    root: Path
    files: tuple[FileEntry, ...] = ()
    skipped: tuple[SkippedEntry, ...] = ()
    errors: tuple[ScanError, ...] = ()

    @property
    def compatible_files(self) -> tuple[FileEntry, ...]:
        return tuple(
            f for f in self.files if f.compatibility == Compatibility.COMPATIBLE
        )

    @property
    def not_compatible_files(self) -> tuple[FileEntry, ...]:
        return tuple(
            f for f in self.files if f.compatibility == Compatibility.NOT_COMPATIBLE
        )

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped)

    @property
    def total_errors(self) -> int:
        return len(self.errors)
