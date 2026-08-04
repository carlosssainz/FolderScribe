import hashlib
from pathlib import Path

import pytest

from folderscribe.domain.extraction import ExtractionStatus
from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor


@pytest.fixture
def extractor() -> PlainTextExtractor:
    return PlainTextExtractor()


class TestPlainTextExtractor:
    def test_supports_txt(self, extractor: PlainTextExtractor) -> None:
        assert extractor.supports(Path("file.txt"))
        assert extractor.supports(Path("file.TXT"))
        assert not extractor.supports(Path("file.pdf"))

    def test_supports_md(self, extractor: PlainTextExtractor) -> None:
        assert extractor.supports(Path("file.md"))
        assert extractor.supports(Path("file.markdown"))

    def test_name_and_version(self, extractor: PlainTextExtractor) -> None:
        assert extractor.name == "plain_text"
        assert extractor.version == "1"

    def test_extract_utf8(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "test.txt"
        content = "Hello, FolderScribe!\nSecond line."
        f.write_text(content, encoding="utf-8")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert result.content == content
        assert result.char_count == len(content)
        assert result.encoding == "utf-8"

    def test_extract_utf8_with_bom(
        self, tmp_path: Path, extractor: PlainTextExtractor
    ) -> None:
        f = tmp_path / "bom.txt"
        content = "Hello with BOM"
        f.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert result.content == content
        assert result.encoding == "utf-8-sig"

    def test_extract_empty(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED_EMPTY
        assert result.content == ""
        assert result.char_count == 0

    def test_extract_unicode(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "unicode.txt"
        content = "Hello 世界 café ñoño Σ"
        f.write_text(content, encoding="utf-8")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert result.content == content

    def test_extract_markdown_preserved(
        self, tmp_path: Path, extractor: PlainTextExtractor
    ) -> None:
        f = tmp_path / "test.md"
        content = "# Title\n\n**bold** and *italic*\n\n- list item"
        f.write_text(content, encoding="utf-8")
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert result.content == content

    def test_extract_mixed_newlines(
        self, tmp_path: Path, extractor: PlainTextExtractor
    ) -> None:
        f = tmp_path / "newlines.txt"
        content = "line1\r\nline2\rline3\nline4"
        f.write_bytes(content.encode("utf-8"))
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert result.content == "line1\nline2\nline3\nline4"

    def test_char_limit(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "long.txt"
        content = "A" * 1000
        f.write_text(content, encoding="utf-8")
        result = extractor.extract(f, max_chars=100)
        assert result.status == ExtractionStatus.PARTIAL
        assert result.is_truncated
        assert result.char_count == 100
        assert len(result.content) == 100

    def test_cancel(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "cancel.txt"
        f.write_text("test content", encoding="utf-8")
        cancelled = False

        def cancel() -> bool:
            return cancelled

        cancelled = True
        result = extractor.extract(f, cancel_check=cancel)
        assert result.status == ExtractionStatus.CANCELLED

    def test_latin1_fallback(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "latin1.txt"
        content = "Héllo Wörld résumé"
        f.write_bytes(content.encode("latin-1"))
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.EXTRACTED
        assert "Héllo" in (result.content or "")

    def test_binary_as_txt(self, tmp_path: Path, extractor: PlainTextExtractor) -> None:
        f = tmp_path / "binary.txt"
        f.write_bytes(bytes(range(256)))
        result = extractor.extract(f)
        assert result.status == ExtractionStatus.ERROR
        assert result.error_code == "binary_content"
