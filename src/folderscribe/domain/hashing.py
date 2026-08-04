from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class HashStatus(Enum):
    PENDING = "pending"
    COMPUTED = "computed"
    REUSED = "reused"
    SKIPPED = "skipped"
    MODIFIED_DURING_READ = "modified_during_read"
    ERROR = "error"


@dataclass(frozen=True)
class ContentHash:
    absolute_path: Path
    algorithm: str
    hash_sha256: str | None
    file_size: int
    file_modified_at: datetime | None
    status: HashStatus
    error_message: str | None = None
    computed_at: datetime | None = None


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: str
    hash_sha256: str
    file_size: int
    file_count: int
    wasted_space: int
    file_paths: tuple[Path, ...]


@dataclass(frozen=True)
class HashResult:
    session_id: str
    hashes: tuple[ContentHash, ...]
    total_processed: int
    computed_count: int
    reused_count: int
    skipped_count: int
    modified_count: int
    error_count: int
    duplicate_groups: tuple[DuplicateGroup, ...]
