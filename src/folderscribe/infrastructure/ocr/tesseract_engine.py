import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from folderscribe.domain.interfaces import OcrEngine
from folderscribe.domain.ocr import OcrError, OcrMode, OcrPage, OcrPdfDocument

logger = logging.getLogger(__name__)

try:
    import fitz  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    fitz = None

try:
    import pytesseract  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pytesseract = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

_ENGINE_NAME = "tesseract"
_ENGINE_VERSION = "1"

_MODE_SETTINGS: dict[OcrMode, tuple[int, int]] = {
    OcrMode.FAST: (150, 3),
    OcrMode.FULL: (300, 6),
}


class TesseractOcrEngine(OcrEngine):
    def __init__(self, binary: str = "tesseract") -> None:
        self._binary = binary

    @property
    def name(self) -> str:
        return _ENGINE_NAME

    @property
    def version(self) -> str:
        return _ENGINE_VERSION

    def is_available(self) -> bool:
        if pytesseract is None:
            return False
        if shutil.which(self._binary) is None:
            return False
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return False
        return True

    def ocr_pdf(
        self,
        path: Path,
        mode: OcrMode,
        max_pages: int = 500,
        lang: str = "eng",
        cancel_check: Callable[[], bool] | None = None,
    ) -> OcrPdfDocument:
        if fitz is None:
            raise OcrError("missing_dependency", "pymupdf is not installed")
        if pytesseract is None:
            raise OcrError("missing_dependency", "pytesseract is not installed")
        if Image is None:
            raise OcrError("missing_dependency", "pillow is not installed")

        try:
            document = fitz.open(str(path))
        except Exception as e:
            raise OcrError("pdf_open_error", str(e)) from e

        dpi, psm = _settings_for_mode(mode)
        total_pages = document.page_count
        pages_to_process = min(total_pages, max_pages)
        pages: list[OcrPage] = []
        processed = 0

        for page_index in range(pages_to_process):
            if cancel_check is not None and cancel_check():
                break
            try:
                page = document.load_page(page_index)
                pix = page.get_pixmap(dpi=dpi)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(
                    image, lang=lang, config=f"--psm {psm}"
                )
                pages.append(
                    OcrPage(
                        page_number=page_index + 1,
                        text=text if text is not None else "",
                    )
                )
            except Exception as e:
                pages.append(
                    OcrPage(
                        page_number=page_index + 1,
                        text="",
                        error_message=str(e),
                    )
                )
            processed += 1

        document.close()

        return OcrPdfDocument(
            absolute_path=path,
            total_pages=total_pages,
            processed_pages=processed,
            pages=tuple(pages),
            engine=self.name,
            engine_version=self.version,
        )


def _settings_for_mode(mode: OcrMode) -> tuple[int, int]:
    return _MODE_SETTINGS.get(mode, _MODE_SETTINGS[OcrMode.FAST])
