from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from folderscribe.domain.extraction import TextExtraction


class OcrMode(Enum):
    FAST = "fast"
    FULL = "full"


class OcrError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    error_message: str | None = None


@dataclass(frozen=True)
class OcrPdfDocument:
    absolute_path: Path
    total_pages: int
    processed_pages: int
    pages: tuple[OcrPage, ...]
    engine: str
    engine_version: str


@dataclass(frozen=True)
class OcrResult:
    session_id: str
    ocr_extractions: tuple[TextExtraction, ...]
    total_processed: int
    engine_available: bool
    ocr_count: int
    reused_count: int
    partial_count: int
    skipped_count: int
    error_count: int
    cancelled_count: int
    stale_count: int
