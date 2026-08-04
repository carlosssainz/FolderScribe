import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from folderscribe.domain.extraction import ExtractionStatus, TextExtraction
from folderscribe.domain.interfaces import OcrEngine, ScanSessionRepository
from folderscribe.domain.ocr import OcrError, OcrMode, OcrPdfDocument, OcrResult
from folderscribe.infrastructure.extraction_config import ExtractionConfig

logger = logging.getLogger(__name__)

_OCR_EXTRACTOR = "pdf_ocr"


class OcrTextUseCase:
    def __init__(
        self,
        engine: OcrEngine,
        repository: ScanSessionRepository,
        config: ExtractionConfig | None = None,
    ) -> None:
        self._engine = engine
        self._repository = repository
        self._config = config or ExtractionConfig()

    def execute(
        self,
        session_id: str,
        mode: OcrMode = OcrMode.FAST,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        privacy_filter: Callable[[Path], bool] | None = None,
    ) -> OcrResult:
        if not self._engine.is_available():
            return OcrResult(
                session_id=session_id,
                ocr_extractions=(),
                total_processed=0,
                engine_available=False,
                ocr_count=0,
                reused_count=0,
                partial_count=0,
                skipped_count=0,
                error_count=0,
                cancelled_count=0,
                stale_count=0,
            )

        extractions = self._repository.get_text_extractions_for_session(session_id)
        candidates = [e for e in extractions if e.needs_ocr]

        total = len(candidates)
        batch_size = 50
        results: list[TextExtraction] = []

        ocr_count = 0
        reused_count = 0
        partial_count = 0
        skipped_count = 0
        error_count = 0
        cancelled_count = 0
        stale_count = 0
        processed_count = 0

        config_version = (
            f"{self._config.ocr_config_version(mode)}|engine={self._engine.version}"
        )

        for idx, extraction in enumerate(candidates):
            if cancel_check is not None and cancel_check():
                cancelled_count = total - processed_count
                break

            path = extraction.absolute_path

            if privacy_filter is not None and not privacy_filter(path):
                skipped_count += 1
                processed_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "Skipped (privacy)")
                continue

            reuse = self._try_reuse(path, extraction, config_version)
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
                processed_count += 1
                self._flush_batch(session_id, results, batch_size)
                continue

            if cancel_check is not None and cancel_check():
                cancelled_count = total - processed_count
                break

            try:
                document = self._engine.ocr_pdf(
                    path=path,
                    mode=mode,
                    max_pages=self._config.max_pdf_pages,
                    lang=self._config.ocr_lang,
                    cancel_check=cancel_check,
                )
            except OcrError as e:
                results.append(
                    self._build_extraction(path, None, config_version, extraction, e)
                )
                error_count += 1
                processed_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, f"Error: {e.message}")
                self._flush_batch(session_id, results, batch_size)
                continue

            if cancel_check is not None and cancel_check():
                cancelled_count = total - processed_count
                break

            result_extraction = self._build_extraction(
                path, document, config_version, extraction, None
            )
            result_extraction = self._check_stale(path, result_extraction)

            status = result_extraction.status
            if status in (ExtractionStatus.EXTRACTED, ExtractionStatus.EXTRACTED_EMPTY):
                ocr_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "OCR complete")
            elif status == ExtractionStatus.PARTIAL:
                partial_count += 1
                if progress_callback is not None:
                    progress_callback(idx + 1, total, "OCR partial")
            elif status == ExtractionStatus.ERROR:
                error_count += 1
                msg = result_extraction.error_message or "unknown"
                if progress_callback is not None:
                    progress_callback(idx + 1, total, f"Error: {msg}")
            else:
                if progress_callback is not None:
                    progress_callback(idx + 1, total, status.value)

            results.append(result_extraction)
            processed_count += 1
            self._flush_batch(session_id, results, batch_size)

        self._flush_batch(session_id, results, batch_size)

        if results:
            self._repository.save_text_extractions(session_id, results)

        return OcrResult(
            session_id=session_id,
            ocr_extractions=tuple(results),
            total_processed=len(results),
            engine_available=True,
            ocr_count=ocr_count,
            reused_count=reused_count,
            partial_count=partial_count,
            skipped_count=skipped_count,
            error_count=error_count,
            cancelled_count=cancelled_count,
            stale_count=stale_count,
        )

    def _flush_batch(
        self,
        session_id: str,
        results: list[TextExtraction],
        batch_size: int,
    ) -> None:
        if len(results) < batch_size:
            return
        self._repository.save_text_extractions(session_id, results)
        results.clear()

    def _try_reuse(
        self,
        path: Path,
        extraction: TextExtraction,
        config_version: str,
    ) -> TextExtraction | None:
        match = self._repository.find_reusable_extraction(
            absolute_path=path,
            sha256_hash=None,
            file_size=extraction.file_size,
            file_modified_at=extraction.file_modified_at,
            extractor=_OCR_EXTRACTOR,
            extractor_version=self._engine.version,
            config_version=config_version,
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
                extractor=_OCR_EXTRACTOR,
                extractor_version=self._engine.version,
                config_version=config_version,
                status=ExtractionStatus.STALE,
                file_size=current_stat.st_size,
            )

        return match

    def _build_extraction(
        self,
        path: Path,
        document: OcrPdfDocument | None,
        config_version: str,
        original: TextExtraction,
        error: OcrError | None,
    ) -> TextExtraction:
        if error is not None or document is None:
            return TextExtraction(
                absolute_path=path,
                extractor=_OCR_EXTRACTOR,
                extractor_version=self._engine.version,
                config_version=config_version,
                status=ExtractionStatus.ERROR,
                error_code=error.code if error is not None else "ocr_failed",
                error_message=(
                    error.message if error is not None else "OCR returned no document"
                ),
                file_size=original.file_size,
                file_modified_at=original.file_modified_at,
                needs_ocr=False,
                total_pages=original.total_pages,
            )

        parts: list[str] = []
        char_count = 0
        for page in document.pages:
            text = page.text.strip()
            if text:
                parts.append(text)
                char_count += len(text)

        content = "\n".join(parts)
        is_truncated = char_count >= self._config.max_stored_chars
        if is_truncated:
            content = content[: self._config.max_stored_chars]
        char_count = len(content)

        page_errors = [
            p.error_message for p in document.pages if p.error_message is not None
        ]
        is_partial = (
            bool(page_errors)
            or document.processed_pages < document.total_pages
            or is_truncated
        )

        file_size: int | None
        file_mtime: datetime | None
        try:
            stat = path.stat()
            file_size = stat.st_size
            file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except OSError:
            file_size = original.file_size
            file_mtime = original.file_modified_at

        if document.processed_pages == 0:
            return TextExtraction(
                absolute_path=path,
                extractor=_OCR_EXTRACTOR,
                extractor_version=self._engine.version,
                config_version=config_version,
                status=ExtractionStatus.ERROR,
                error_code="ocr_no_pages",
                error_message="OCR processed no pages",
                char_count=0,
                file_size=file_size,
                file_modified_at=file_mtime,
                total_pages=document.total_pages,
                processed_pages=0,
                needs_ocr=False,
            )

        if char_count == 0 and page_errors:
            return TextExtraction(
                absolute_path=path,
                extractor=_OCR_EXTRACTOR,
                extractor_version=self._engine.version,
                config_version=config_version,
                status=ExtractionStatus.ERROR,
                error_code="ocr_failed",
                error_message="; ".join(page_errors[:3]),
                char_count=0,
                file_size=file_size,
                file_modified_at=file_mtime,
                total_pages=document.total_pages,
                processed_pages=document.processed_pages,
                is_partial=True,
                needs_ocr=False,
            )

        if char_count == 0:
            return TextExtraction(
                absolute_path=path,
                extractor=_OCR_EXTRACTOR,
                extractor_version=self._engine.version,
                config_version=config_version,
                status=ExtractionStatus.EXTRACTED_EMPTY,
                content="",
                char_count=0,
                file_size=file_size,
                file_modified_at=file_mtime,
                total_pages=document.total_pages,
                processed_pages=document.processed_pages,
                is_partial=is_partial,
                needs_ocr=False,
            )

        status: ExtractionStatus = ExtractionStatus.EXTRACTED
        if is_partial:
            status = ExtractionStatus.PARTIAL
            partial_reason = self._partial_reason(page_errors, is_truncated)
        else:
            partial_reason = None

        return TextExtraction(
            absolute_path=path,
            extractor=_OCR_EXTRACTOR,
            extractor_version=self._engine.version,
            config_version=config_version,
            status=status,
            content=content,
            char_count=char_count,
            file_size=file_size,
            file_modified_at=file_mtime,
            total_pages=document.total_pages,
            processed_pages=document.processed_pages,
            is_truncated=is_truncated,
            is_partial=is_partial,
            partial_reason=partial_reason,
            needs_ocr=False,
        )

    def _partial_reason(self, page_errors: list[str], is_truncated: bool) -> str:
        if is_truncated:
            return f"reached_char_limit_{self._config.max_stored_chars}"
        if page_errors:
            return "page_ocr_errors"
        return "partial_pages"

    def _check_stale(
        self,
        path: Path,
        extraction: TextExtraction,
    ) -> TextExtraction:
        if extraction.status in (
            ExtractionStatus.CANCELLED,
            ExtractionStatus.ERROR,
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
                error_message="File size changed during OCR",
                file_size=stat.st_size,
            )

        return extraction
