from collections.abc import Callable
from pathlib import Path

import pytest

from folderscribe.domain.interfaces import OcrEngine
from folderscribe.domain.ocr import OcrError, OcrMode, OcrPage, OcrPdfDocument


class FakeOcrEngine(OcrEngine):
    def __init__(
        self,
        available: bool = True,
        text: str = "FAKE OCR TEXT",
        fail_on_call: bool = False,
    ) -> None:
        self._available = available
        self._text = text
        self._fail_on_call = fail_on_call
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake_ocr"

    @property
    def version(self) -> str:
        return "1"

    def is_available(self) -> bool:
        return self._available

    def ocr_pdf(
        self,
        path: Path,
        mode: OcrMode,
        max_pages: int = 500,
        lang: str = "eng",
        cancel_check: Callable[[], bool] | None = None,
    ) -> OcrPdfDocument:
        self.calls += 1
        if self._fail_on_call:
            raise OcrError("ocr_failed", "fake engine failure")
        pages = tuple(
            OcrPage(page_number=i + 1, text=f"{self._text} page {i + 1}")
            for i in range(3)
        )
        return OcrPdfDocument(
            absolute_path=path,
            total_pages=3,
            processed_pages=3,
            pages=pages,
            engine=self.name,
            engine_version=self.version,
        )


@pytest.fixture
def fake_ocr_engine() -> FakeOcrEngine:
    return FakeOcrEngine()


@pytest.fixture
def scanned_session(tmp_path: Path) -> tuple[Path, str]:
    from pypdf import PdfWriter

    from folderscribe.application.extract_text import ExtractTextUseCase
    from folderscribe.application.scan_folder import ScanFolderUseCase
    from folderscribe.infrastructure.database import SqliteScanSessionRepository
    from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor
    from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor
    from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry
    from folderscribe.infrastructure.scanner import OsDirectoryScanner

    db_path = tmp_path / "ocr.db"
    repo = SqliteScanSessionRepository(db_path)
    root = tmp_path / "scan_root"
    root.mkdir()

    scanned = root / "scanned.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(72, 72)
    writer.write(str(scanned))
    writer.close()

    (root / "notes.txt").write_text("plain notes", encoding="utf-8")

    scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
    scan_result = scan_use_case.execute(root)
    session_id = scan_result.session.session_id

    registry = TextExtractorRegistry()
    registry.register(PlainTextExtractor())
    registry.register(PdfTextExtractor())
    ExtractTextUseCase(registry=registry, repository=repo).execute(session_id)
    repo.close()
    return db_path, session_id
