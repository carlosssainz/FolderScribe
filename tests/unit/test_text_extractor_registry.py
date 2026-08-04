from pathlib import Path

from folderscribe.infrastructure.extractors.docx_extractor import DocxTextExtractor
from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor
from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor
from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry


class TestTextExtractorRegistry:
    def test_empty_registry(self) -> None:
        registry = TextExtractorRegistry()
        assert registry.get_extractor(Path("test.txt")) is None

    def test_register_and_get(self) -> None:
        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        assert registry.get_extractor(Path("test.txt")) is not None
        assert registry.get_extractor(Path("test.md")) is not None
        assert registry.get_extractor(Path("test.pdf")) is None

    def test_multiple_extractors(self) -> None:
        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        registry.register(DocxTextExtractor())
        registry.register(PdfTextExtractor())
        assert registry.get_extractor(Path("test.txt")) is not None
        assert registry.get_extractor(Path("test.docx")) is not None
        assert registry.get_extractor(Path("test.pdf")) is not None
        assert registry.get_extractor(Path("test.jpg")) is None

    def test_extractors_property(self) -> None:
        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        registry.register(PdfTextExtractor())
        assert len(registry.extractors) == 2

    def test_priority_order(self) -> None:
        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        registry.register(DocxTextExtractor())
        found = registry.get_extractor(Path("test.txt"))
        assert isinstance(found, PlainTextExtractor)
        found2 = registry.get_extractor(Path("test.docx"))
        assert isinstance(found2, DocxTextExtractor)
