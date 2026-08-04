from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from folderscribe.domain.extraction import TextExtraction
from folderscribe.domain.hashing import ContentHash, DuplicateGroup
from folderscribe.domain.models import (
    ExclusionRule,
    InventoryResult,
    ScanEntry,
    ScanError,
    ScanSession,
)
from folderscribe.domain.ocr import OcrMode, OcrPdfDocument


class DirectoryScanner(ABC):
    @abstractmethod
    def scan(
        self,
        root: Path,
        exclusion_rules: tuple[ExclusionRule, ...] = (),
    ) -> InventoryResult: ...


class ContentHasher(ABC):
    @abstractmethod
    def compute_hash(self, path: Path) -> ContentHash: ...


class ScanSessionRepository(ABC):
    @abstractmethod
    def create_session(self, session: ScanSession) -> None: ...

    @abstractmethod
    def save_exclusion_rules(
        self,
        session_id: str,
        rules: tuple[ExclusionRule, ...],
    ) -> None: ...

    @abstractmethod
    def complete_session(
        self,
        session: ScanSession,
        entries: list[ScanEntry],
        errors: list[ScanError],
    ) -> None: ...

    @abstractmethod
    def mark_session_failed(
        self, session_id: str, finished_at: datetime, message: str
    ) -> None: ...

    @abstractmethod
    def get_entries_for_session(self, session_id: str) -> list[ScanEntry]: ...

    @abstractmethod
    def save_content_hashes(
        self, session_id: str, hashes: list[ContentHash]
    ) -> None: ...

    @abstractmethod
    def find_reusable_hash(
        self, absolute_path: Path, file_size: int, modified_at: datetime
    ) -> ContentHash | None: ...

    @abstractmethod
    def find_duplicates(self, session_id: str) -> tuple[DuplicateGroup, ...]: ...

    @abstractmethod
    def save_text_extractions(
        self,
        session_id: str,
        extractions: list[TextExtraction],
    ) -> None: ...

    @abstractmethod
    def find_reusable_extraction(
        self,
        absolute_path: Path,
        sha256_hash: str | None,
        file_size: int | None,
        file_modified_at: datetime | None,
        extractor: str,
        extractor_version: str,
        config_version: str,
    ) -> TextExtraction | None: ...

    @abstractmethod
    def get_text_extractions_for_session(
        self, session_id: str
    ) -> list[TextExtraction]: ...

    @abstractmethod
    def get_text_extraction_by_entry(
        self, session_id: str, entry_id: int
    ) -> TextExtraction | None: ...

    @abstractmethod
    def get_text_extraction_by_path(
        self, session_id: str, absolute_path: Path
    ) -> TextExtraction | None: ...

    @abstractmethod
    def close(self) -> None: ...


class TextExtractor(ABC):
    @abstractmethod
    def supports(self, path: Path) -> bool: ...

    @abstractmethod
    def extract(
        self,
        path: Path,
        max_chars: int = 100000,
        max_pages: int = 500,
        max_read_bytes: int = 10485760,
        cancel_check: Callable[[], bool] | None = None,
    ) -> TextExtraction: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...


class OcrEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def ocr_pdf(
        self,
        path: Path,
        mode: OcrMode,
        max_pages: int = 500,
        lang: str = "eng",
        cancel_check: Callable[[], bool] | None = None,
    ) -> OcrPdfDocument: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...
