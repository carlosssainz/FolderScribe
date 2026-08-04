import logging

logger = logging.getLogger(__name__)

_OCR_HEURISTIC_VERSION = "1"


def get_ocr_heuristic_version() -> str:
    return _OCR_HEURISTIC_VERSION


def assess_needs_ocr(
    total_pages: int,
    processed_pages: int,
    char_count: int,
    pages_with_text: int,
    is_encrypted: bool = False,
    is_truncated: bool = False,
    error_code: str | None = None,
) -> tuple[bool, str | None]:
    if is_encrypted:
        return False, None
    if error_code is not None:
        return False, None
    if is_truncated:
        return False, None
    if total_pages == 0:
        return False, None
    if processed_pages == 0:
        return False, None
    if char_count == 0 and pages_with_text == 0 and total_pages > 0:
        return True, "no_extractable_text"
    if char_count == 0 and pages_with_text < processed_pages:
        return True, "no_extractable_text"
    total_chars = char_count
    if total_chars < 20 and pages_with_text <= 1 and processed_pages > 1:
        return True, "insufficient_text"
    if pages_with_text == 0 and processed_pages > 0:
        return True, "no_extractable_text"
    text_ratio = pages_with_text / processed_pages
    if text_ratio < 0.1 and processed_pages > 5:
        return True, "text_in_too_few_pages"
    if total_chars < 50 and processed_pages > 3:
        return True, "insufficient_text"
    return False, None
