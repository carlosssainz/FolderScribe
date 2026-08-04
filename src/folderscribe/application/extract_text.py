import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from folderscribe.domain.extraction import (
    ExtractionResult,
    ExtractionStatus,
    TextExtraction,
)
from folderscribe.domain.interfaces import ScanSessionRepository, TextExtractor
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry

logger = logging.getLogger(__name__)


class ExtractTextUseCase:
    def __init__(
        self,
        registry: TextExtractorRegistry,
        repository: ScanSessionRepository,
        config: ExtractionConfig | None = None,
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._config = config or ExtractionConfig()

    def execute(
        self,
        session_id: str,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        privacy_filter: Callable[[Path], bool] | None = None,
    ) -> ExtractionResult:
        entries = self._repository.get_entries_for_session(session_id)

        file_entries = [
            e for e in entries
            if e.element_type == "file" and e.status == "indexed" and e.is_compatible
        ]

        total = len(file_entries)
        batch_size = 50
        results: list[TextExtraction] = []

        extracted_count = 0
        reused_count = 0
        partial_count = 0
        needs_ocr_count = 0
        skipped_count = 0
        error_count = 0
        cancelled_count = 0
        stale_count = 0

        for idx, entry in enumerate(file_entries):
            if cancel_check is not None and cancel_check():
                cancelled_count = total - len(results)
                break

            path = entry.absolute_path

            if privacy_filter is not None and not privacy_filter(path):
                results.append(
                    TextExtraction(
                        absolute_path=path,
                        extractor="",
                        extractor_version="",
                        config_version="",
                        status=ExtractionStatus.SKIPPED_PRIVACY,
                        file_size=entry.size,
                    )
                )
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped (privacy)")
                continue

            extractor = self._registry.get_extractor(path)
            if extractor is None:
                results.append(
                    TextExtraction(
                        absolute_path=path,
                        extractor="",
                        extractor_version="",
                        config_version="",
                        status=ExtractionStatus.UNSUPPORTED,
                        file_size=entry.size,
                    )
                )
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Unsupported format")
                continue

            reuse = self._try_reuse(
                path=path,
                entry_size=entry.size,
                entry_modified=entry.modified_at,
                extractor=extractor,
            )
            if reuse is not None:
                if reuse.status == ExtractionStatus.STALE:
                    stale_count += 1
                    results.append(reuse)
                    if progress_callback is not None:
                        progress_callback(idx + 1, total, "Stale")
                else:
                    results.append(reuse)
                    reused_count += 1
                    if progress_callback is not None:
                        progress_callback(idx + 1, total, "Reused")
                continue

            extraction = extractor.extract(
                path=path,
                max_chars=self._config.max_stored_chars,
                max_pages=self._config.max_pdf_pages,
                max_read_bytes=self._config.max_read_bytes,
                cancel_check=cancel_check,
            )

            extraction = self._check_stale(path, extraction, entry)

            status = extraction.status
            if status == ExtractionStatus.EXTRACTED:
                extracted_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Extracted")
            elif status == ExtractionStatus.EXTRACTED_EMPTY:
                extracted_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Empty")
            elif status == ExtractionStatus.PARTIAL:
                partial_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Partial")
            elif status == ExtractionStatus.NEEDS_OCR:
                needs_ocr_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Needs OCR")
            elif status == ExtractionStatus.ENCRYPTED:
                needs_ocr_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Encrypted")
            elif status == ExtractionStatus.SKIPPED_PRIVACY:
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped (privacy)")
            elif status == ExtractionStatus.UNSUPPORTED:
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Unsupported")
            elif status == ExtractionStatus.SKIPPED_LIMIT:
                skipped_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped (limit)")
            elif status == ExtractionStatus.CANCELLED:
                cancelled_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Cancelled")
            elif status == ExtractionStatus.STALE:
                stale_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Stale")
            elif status == ExtractionStatus.ERROR:
                error_count += 1
                if progress_callback is not None:
                    msg = extraction.error_message or "unknown"
                    progress_callback(idx + 1, total, f"Error: {msg}")

            results.append(extraction)

            if len(results) >= batch_size:
                patched = [
                    TextExtraction(
                        **{**e.__dict__, "config_version": self._config.config_version}
                    )
                    for e in results
                ]
                self._repository.save_text_extractions(session_id, patched)
                results.clear()

        if results:
            patched = [
                TextExtraction(
                    **{**e.__dict__, "config_version": self._config.config_version}
                )
                for e in results
            ]
            self._repository.save_text_extractions(session_id, patched)

        return ExtractionResult(
            session_id=session_id,
            extractions=tuple(results),
            total_processed=len(results),
            extracted_count=extracted_count,
            reused_count=reused_count,
            partial_count=partial_count,
            needs_ocr_count=needs_ocr_count,
            skipped_count=skipped_count,
            error_count=error_count,
            cancelled_count=cancelled_count,
            stale_count=stale_count,
        )

    def _try_reuse(
        self,
        path: Path,
        entry_size: int | None,
        entry_modified: datetime | None,
        extractor: TextExtractor,
    ) -> TextExtraction | None:
        match = self._repository.find_reusable_extraction(
            absolute_path=path,
            sha256_hash=None,
            file_size=entry_size,
            file_modified_at=entry_modified,
            extractor=extractor.name,
            extractor_version=extractor.version,
            config_version=self._config.config_version,
        )
        if match is None:
            return None

        try:
            current_stat = path.stat()
        except OSError:
            return None

        if match.file_size is not None and current_stat.st_size != match.file_size:
            return TextExtraction(
                absolute_path=path,
                extractor=extractor.name,
                extractor_version=extractor.version,
                config_version=self._config.config_version,
                status=ExtractionStatus.STALE,
                file_size=current_stat.st_size,
            )

        return match

    def _check_stale(
        self,
        path: Path,
        extraction: TextExtraction,
        entry: object,  # noqa: ARG002
    ) -> TextExtraction:
        if extraction.status in (
            ExtractionStatus.CANCELLED,
            ExtractionStatus.ERROR,
            ExtractionStatus.SKIPPED_PRIVACY,
        ):
            return extraction

        try:
            stat = path.stat()
        except OSError:
            return extraction

        expected_size = extraction.file_size
        if expected_size is not None and stat.st_size != expected_size:
            return TextExtraction(
                absolute_path=extraction.absolute_path,
                extractor=extraction.extractor,
                extractor_version=extraction.extractor_version,
                config_version=extraction.config_version,
                status=ExtractionStatus.STALE,
                error_message="File size changed during extraction",
                file_size=stat.st_size,
            )

        return extraction
