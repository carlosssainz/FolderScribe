import logging
from collections.abc import Callable
from pathlib import Path

from folderscribe.domain.extraction import ExtractionStatus, TextExtraction
from folderscribe.domain.interfaces import TextExtractor
from folderscribe.infrastructure.needs_ocr import (
    assess_needs_ocr,
    get_ocr_heuristic_version,
)

logger = logging.getLogger(__name__)


class PdfTextExtractor(TextExtractor):
    def __init__(self) -> None:
        self._name = "pdf"
        self._version = "1"

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def extract(
        self,
        path: Path,
        max_chars: int = 100000,
        max_pages: int = 500,
        max_read_bytes: int = 10485760,
        cancel_check: Callable[[], bool] | None = None,
    ) -> TextExtraction:
        if cancel_check is not None and cancel_check():
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.CANCELLED,
            )

        try:
            stat = path.stat()
            file_size = stat.st_size
        except OSError as e:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="stat_error",
                error_message=str(e),
            )

        try:
            import pypdf
        except ImportError:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="missing_dependency",
                error_message="pypdf is not installed",
            )

        try:
            reader = pypdf.PdfReader(str(path))
        except pypdf.errors.PdfReadError as e:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="pdf_read_error",
                error_message=str(e),
            )
        except FileNotFoundError:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="file_not_found",
                error_message="File does not exist",
            )
        except Exception as e:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="pdf_open_error",
                error_message=str(e),
            )

        if reader.is_encrypted:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ENCRYPTED,
                file_size=file_size,
            )

        total_pages = len(reader.pages)
        if total_pages == 0:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.EXTRACTED_EMPTY,
                content="",
                char_count=0,
                file_size=file_size,
                total_pages=0,
                processed_pages=0,
            )

        pages_to_process = min(total_pages, max_pages)
        parts: list[str] = []
        char_count = 0
        pages_with_text = 0
        pages_attempted = 0
        is_truncated = False
        is_partial = False
        partial_reason: str | None = None

        for i in range(pages_to_process):
            if cancel_check is not None and cancel_check():
                return TextExtraction(
                    absolute_path=path,
                    extractor=self._name,
                    extractor_version=self._version,
                    config_version="",
                    status=ExtractionStatus.CANCELLED,
                    file_size=file_size,
                    total_pages=total_pages,
                    processed_pages=pages_attempted,
                )

            try:
                page = reader.pages[i]
                page_text = page.extract_text()
            except Exception:
                pages_attempted += 1
                continue

            pages_attempted += 1
            if page_text and page_text.strip():
                pages_with_text += 1
                parts.append(page_text.strip())
                char_count += len(page_text.strip())
                if char_count >= max_chars:
                    is_truncated = True
                    partial_reason = f"reached_char_limit_{max_chars}"
                    break

        if len(parts) < pages_to_process and not is_truncated:
            is_partial = True
            partial_reason = partial_reason or "partial_page_extraction"

        processed_pages = pages_attempted

        if cancel_check is not None and cancel_check():
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.CANCELLED,
                file_size=file_size,
                total_pages=total_pages,
                processed_pages=processed_pages,
            )

        content = "\n".join(parts)
        char_count = len(content)

        needs_ocr, ocr_reason = assess_needs_ocr(
            total_pages=total_pages,
            processed_pages=processed_pages,
            char_count=char_count,
            pages_with_text=pages_with_text,
            is_truncated=is_truncated,
        )

        if needs_ocr:
            ocr_heuristic_version = get_ocr_heuristic_version()
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.NEEDS_OCR,
                content=content if content else None,
                char_count=char_count,
                file_size=file_size,
                total_pages=total_pages,
                processed_pages=processed_pages,
                needs_ocr=True,
                ocr_heuristic_version=ocr_heuristic_version,
                partial_reason=ocr_reason,
                is_partial=True,
            )

        if char_count == 0:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.EXTRACTED_EMPTY,
                content="",
                char_count=0,
                file_size=file_size,
                total_pages=total_pages,
                processed_pages=processed_pages,
            )

        status: ExtractionStatus = ExtractionStatus.EXTRACTED
        if is_truncated:
            status = ExtractionStatus.PARTIAL
            is_partial = True
        elif is_partial:
            status = ExtractionStatus.PARTIAL

        return TextExtraction(
            absolute_path=path,
            extractor=self._name,
            extractor_version=self._version,
            config_version="",
            status=status,
            content=content,
            char_count=char_count,
            file_size=file_size,
            total_pages=total_pages,
            processed_pages=processed_pages,
            is_truncated=is_truncated,
            is_partial=is_partial,
            partial_reason=partial_reason,
        )
