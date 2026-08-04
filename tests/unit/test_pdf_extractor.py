from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from folderscribe.domain.extraction import ExtractionStatus
from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor


@pytest.fixture
def extractor() -> PdfTextExtractor:
    return PdfTextExtractor()


def _make_pdf(tmp_path: Path, name: str, texts: list[str]) -> Path:
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    for text in texts:
        c.drawString(10, 50, text)
        c.showPage()
    c.save()
    packet.seek(0)

    from pypdf import PdfReader, PdfWriter

    new_pdf = PdfReader(packet)
    writer = PdfWriter()
    for i in range(len(texts)):
        writer.add_page(new_pdf.pages[i])
    f = tmp_path / name
    writer.write(str(f))
    writer.close()
    return f


def _make_blank_pdf(tmp_path: Path, name: str, pages: int = 1) -> Path:
    from pypdf import PdfWriter

    f = tmp_path / name
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(72, 72)
    writer.write(str(f))
    writer.close()
    return f


def _make_encrypted_pdf(tmp_path: Path, name: str) -> Path:
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.drawString(10, 50, "Secret")
    c.showPage()
    c.save()
    packet.seek(0)

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(packet)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("password")
    f = tmp_path / name
    writer.write(str(f))
    writer.close()
    return f


class TestPdfExtractor:
    def test_supports_pdf(self, extractor: PdfTextExtractor) -> None:
        assert extractor.supports(Path("file.pdf"))
        assert not extractor.supports(Path("file.txt"))

    def test_name_and_version(self, extractor: PdfTextExtractor) -> None:
        assert extractor.name == "pdf"
        assert extractor.version == "1"

    def test_one_page_with_text(
        self, tmp_path: Path, extractor: PdfTextExtractor
    ) -> None:
        f = _make_pdf(tmp_path, "one.pdf", ["Hello PDF"])
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert "Hello PDF" in (result.content or "")

    def test_multiple_pages(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        pages = [
            f"This is page number {i} "
            "with enough text to exceed the OCR heuristic threshold"
            for i in range(5)
        ]
        f = _make_pdf(tmp_path, "multi.pdf", pages)
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        for p in pages:
            assert p in (result.content or "")

    def test_encrypted_pdf(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        f = _make_encrypted_pdf(tmp_path, "enc.pdf")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.ENCRYPTED

    def test_blank_pdf_needs_ocr(
        self, tmp_path: Path, extractor: PdfTextExtractor
    ) -> None:
        f = _make_blank_pdf(tmp_path, "blank.pdf", pages=3)
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.NEEDS_OCR
        assert result.needs_ocr

    def test_corrupt_pdf(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        f = tmp_path / "corrupt.pdf"
        f.write_bytes(b"%PDF-1.4\n%garbage%%EOF")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.ERROR

    def test_cancelled(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        f = _make_pdf(tmp_path, "cancel.pdf", ["test"])

        def cancel() -> bool:
            return True

        result = extractor.extract(f, cancel_check=cancel)
        assert result.status == ExtractionStatus.CANCELLED

    def test_char_limit(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        f = _make_pdf(tmp_path, "long.pdf", ["X" * 500])
        result = extractor.extract(f, max_chars=50)
        assert result.status == ExtractionStatus.PARTIAL
        assert result.is_truncated

    def test_empty_pdf(self, tmp_path: Path, extractor: PdfTextExtractor) -> None:
        from pypdf import PdfWriter

        f = tmp_path / "empty.pdf"
        writer = PdfWriter()
        writer.write(str(f))
        writer.close()
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED_EMPTY
