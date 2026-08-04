from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class ExtractionStatus(Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    EXTRACTED_EMPTY = "extracted_empty"
    PARTIAL = "partial"
    NEEDS_OCR = "needs_ocr"
    UNSUPPORTED = "unsupported"
    SKIPPED_PRIVACY = "skipped_privacy"
    SKIPPED_LIMIT = "skipped_limit"
    ENCRYPTED = "encrypted"
    CANCELLED = "cancelled"
    STALE = "stale"
    ERROR = "error"


@dataclass(frozen=True)
class TextExtraction:
    absolute_path: Path
    extractor: str
    extractor_version: str
    config_version: str
    status: ExtractionStatus
    content: str | None = None
    sha256_hash: str | None = None
    file_size: int | None = None
    file_modified_at: datetime | None = None
    char_count: int = 0
    total_pages: int = 0
    processed_pages: int = 0
    is_truncated: bool = False
    is_partial: bool = False
    needs_ocr: bool = False
    ocr_heuristic_version: str | None = None
    partial_reason: str | None = None
    skip_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    encoding: str | None = None
    decoding_warnings: str | None = None
    computed_at: datetime | None = None


@dataclass(frozen=True)
class ExtractionResult:
    session_id: str
    extractions: tuple[TextExtraction, ...]
    total_processed: int
    extracted_count: int
    reused_count: int
    partial_count: int
    needs_ocr_count: int
    skipped_count: int
    error_count: int
    cancelled_count: int
    stale_count: int
