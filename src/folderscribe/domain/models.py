from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class Compatibility(Enum):
    COMPATIBLE = "compatible"
    NOT_COMPATIBLE = "not_compatible"


class RuleSource(Enum):
    USER = "user"
    TECHNICAL = "technical"  # Reserved for future use


@dataclass(frozen=True)
class ExclusionRule:
    pattern: str
    source: RuleSource


@dataclass(frozen=True)
class FileEntry:
    path: Path
    compatibility: Compatibility
    size: int | None = None
    modified_at: datetime | None = None


@dataclass(frozen=True)
class SkippedEntry:
    path: Path
    reason: str
    details: str = ""


@dataclass(frozen=True)
class ScanError:
    path: Path
    code: str
    message: str
    session_id: str | None = None
    occurred_at: datetime | None = None


class SessionStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ScanSession:
    session_id: str
    root_path: Path
    started_at: datetime
    finished_at: datetime | None = None
    status: SessionStatus = SessionStatus.RUNNING
    is_recursive: bool = True
    total_files: int = 0
    total_compatible: int = 0
    total_not_compatible: int = 0
    total_skipped: int = 0
    total_errors: int = 0


@dataclass(frozen=True)
class ScanEntry:
    session_id: str
    absolute_path: Path
    relative_path: str
    name: str
    extension: str
    element_type: str = "file"
    size: int | None = None
    modified_at: datetime | None = None
    is_compatible: bool = False
    status: str = "indexed"
    skip_reason: str | None = None
    is_code_project: bool = False
    skip_detail: str = ""


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


class PersistenceError(Exception):
    """Raised when persisting a scan session fails."""
