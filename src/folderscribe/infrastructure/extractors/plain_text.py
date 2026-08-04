import logging
from collections.abc import Callable
from pathlib import Path

from folderscribe.domain.extraction import ExtractionStatus, TextExtraction
from folderscribe.domain.interfaces import TextExtractor

_EXTENSIONS = frozenset({".txt", ".md", ".markdown"})

logger = logging.getLogger(__name__)


class PlainTextExtractor(TextExtractor):
    def __init__(self) -> None:
        self._name = "plain_text"
        self._version = "1"

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _EXTENSIONS

    def extract(
        self,
        path: Path,
        max_chars: int = 100000,
        max_pages: int = 500,
        max_read_bytes: int = 10485760,
        cancel_check: Callable[[], bool] | None = None,
    ) -> TextExtraction:
        stat = path.stat()
        file_size = stat.st_size

        if cancel_check is not None and cancel_check():
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.CANCELLED,
                file_size=file_size,
            )

        if _is_binary_content(path, max_read_bytes):
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="binary_content",
                error_message="File appears to be binary, not text",
                file_size=file_size,
            )

        encoding, content, warnings = _read_text_file(path, max_chars, cancel_check)

        if content is None:
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.ERROR,
                error_code="decode_error",
                error_message=f"Could not decode as {encoding}",
                file_size=file_size,
            )

        if cancel_check is not None and cancel_check():
            return TextExtraction(
                absolute_path=path,
                extractor=self._name,
                extractor_version=self._version,
                config_version="",
                status=ExtractionStatus.CANCELLED,
                file_size=file_size,
            )

        char_count = len(content)
        is_truncated = char_count >= max_chars

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
                encoding=encoding,
                decoding_warnings=warnings,
            )

        status: ExtractionStatus = ExtractionStatus.EXTRACTED
        is_partial = False
        partial_reason: str | None = None

        if is_truncated:
            status = ExtractionStatus.PARTIAL
            is_partial = True
            partial_reason = f"reached_char_limit_{max_chars}"

        return TextExtraction(
            absolute_path=path,
            extractor=self._name,
            extractor_version=self._version,
            config_version="",
            status=status,
            content=content,
            char_count=char_count,
            file_size=file_size,
            is_truncated=is_truncated,
            is_partial=is_partial,
            partial_reason=partial_reason,
            encoding=encoding,
            decoding_warnings=warnings,
        )


def _is_binary_content(path: Path, max_read_bytes: int) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
    except OSError:
        return False

    if not chunk:
        return False

    text_chars = 0
    control_chars = 0
    null_count = chunk.count(b"\x00")
    for byte in chunk:
        if 32 <= byte <= 126 or byte in (9, 10, 13):
            text_chars += 1
        elif byte < 32:
            control_chars += 1

    if null_count > 0:
        return True

    if len(chunk) == 0:
        return False

    ratio = text_chars / len(chunk)
    if ratio < 0.5 and control_chars > len(chunk) * 0.3:
        return True
    return False


def _detect_bom(raw: bytes) -> tuple[str, int]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", 3
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le", 2
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be", 2
    return "utf-8", 0


def _read_text_file(
    path: Path,
    max_chars: int,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[str, str | None, str | None]:
    try:
        with open(path, "rb") as f:
            raw = f.read(8192)
    except OSError as e:
        return "utf-8", None, str(e)

    bom_encoding, bom_offset = _detect_bom(raw)
    encoding = bom_encoding if bom_encoding != "utf-8" else "utf-8"

    try:
        content = _read_and_decode(
            path, encoding, max_chars, bom_offset, cancel_check
        )
        if content is None and encoding != "utf-8":
            return encoding, None, None
        if content is None:
            return encoding, None, None
        content = _normalize_newlines(content)
        content = content.replace("\x00", "")
        return encoding, content, None
    except UnicodeDecodeError:
        if encoding == "utf-8" or encoding == "utf-8-sig":
            try:
                content = _read_and_decode(
                    path, "latin-1", max_chars, bom_offset, cancel_check
                )
                if content is not None:
                    content = _normalize_newlines(content)
                    content = content.replace("\x00", "")
                return "latin-1", content, "fallback_from_utf8"
            except UnicodeDecodeError:
                try:
                    content = _read_and_decode(
                        path, "cp1252", max_chars, bom_offset, cancel_check
                    )
                    if content is not None:
                        content = _normalize_newlines(content)
                        content = content.replace("\x00", "")
                    return "cp1252", content, "fallback_from_utf8"
                except UnicodeDecodeError:
                    return encoding, None, "all_decodings_failed"
        return encoding, None, str(UnicodeDecodeError)


def _read_and_decode(
    path: Path,
    encoding: str,
    max_chars: int,
    bom_offset: int = 0,
    cancel_check: Callable[[], bool] | None = None,
) -> str | None:
    result_chars: list[str] = []
    total = 0

    try:
        with open(path, "r", encoding=encoding) as f:
            if bom_offset > 0 and encoding != "utf-8-sig":
                f.read(bom_offset)
            while True:
                if cancel_check is not None and cancel_check():
                    return None
                if total >= max_chars:
                    break
                chunk = f.read(4096)
                if not chunk:
                    break
                result_chars.append(chunk)
                total += len(chunk)
    except (UnicodeDecodeError, OSError):
        raise

    return "".join(result_chars)[:max_chars]


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text
