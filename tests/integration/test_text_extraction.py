from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from folderscribe.application.extract_text import ExtractTextUseCase
from folderscribe.domain.extraction import ExtractionStatus
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.extractors.docx_extractor import DocxTextExtractor
from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor
from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor
from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry
from folderscribe.infrastructure.scanner import OsDirectoryScanner


def _make_test_files(root: Path) -> None:
    (root / "hello.txt").write_text("Hello World!", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")

    from docx import Document

    doc = Document()
    doc.add_paragraph("DOCX paragraph")
    doc.save(str(root / "test.docx"))

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.drawString(10, 50, "PDF text content")
    c.showPage()
    c.save()
    packet.seek(0)
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(packet)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.write(str(root / "test.pdf"))
    writer.close()


class TestTextExtractionIntegration:
    def test_extract_all_formats(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        repo = SqliteScanSessionRepository(db_path)
        root = tmp_path / "scan_root"
        root.mkdir()
        _make_test_files(root)

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        registry.register(DocxTextExtractor())
        registry.register(PdfTextExtractor())

        use_case = ExtractTextUseCase(
            registry=registry,
            repository=repo,
            config=ExtractionConfig(),
        )

        result = use_case.execute(session_id=session_id)
        assert result.total_processed == 4
        assert result.extracted_count >= 3
        repo.close()

    def test_cancellation(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cancel.db"
        repo = SqliteScanSessionRepository(db_path)
        root = tmp_path / "scan_root"
        root.mkdir()
        _make_test_files(root)

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        registry.register(DocxTextExtractor())
        registry.register(PdfTextExtractor())

        use_case = ExtractTextUseCase(
            registry=registry,
            repository=repo,
            config=ExtractionConfig(),
        )

        def cancel() -> bool:
            return True

        result = use_case.execute(
            session_id=session_id,
            cancel_check=cancel,
        )
        assert result.cancelled_count == 4
        repo.close()

    def test_unsupported_format_skipped(self, tmp_path: Path) -> None:
        db_path = tmp_path / "unsup.db"
        repo = SqliteScanSessionRepository(db_path)
        root = tmp_path / "scan_root"
        root.mkdir()
        _make_test_files(root)

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())

        use_case = ExtractTextUseCase(
            registry=registry,
            repository=repo,
            config=ExtractionConfig(),
        )

        result = use_case.execute(session_id=session_id)
        unsupported = [
            e
            for e in result.extractions
            if e.status == ExtractionStatus.UNSUPPORTED
        ]
        assert len(unsupported) >= 1
        repo.close()


class TestTextExtractionV4Migration:
    def test_migration_v4_tables_exist(self, tmp_path: Path) -> None:
        import sqlite3

        p = tmp_path / "v4.db"
        repo = SqliteScanSessionRepository(p)

        conn = sqlite3.connect(str(p))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        repo.close()

        assert "text_extractions" in tables
        assert "scan_entry_extractions" in tables

    def test_save_and_retrieve_extraction(self, tmp_path: Path) -> None:
        p = tmp_path / "extract.db"
        repo = SqliteScanSessionRepository(p)

        root = tmp_path / "source"
        root.mkdir()
        (root / "test.txt").write_text("content", encoding="utf-8")

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())

        extract_use_case = ExtractTextUseCase(
            registry=registry, repository=repo
        )
        extract_result = extract_use_case.execute(session_id)
        assert extract_result.extracted_count == 1

        repo2 = SqliteScanSessionRepository(p)
        try:
            extractions = repo2.get_text_extractions_for_session(session_id)
            assert len(extractions) == 1
            assert extractions[0].content == "content"
        finally:
            repo2.close()
        repo.close()

    def test_find_by_path(self, tmp_path: Path) -> None:
        from folderscribe.domain.extraction import ExtractionStatus
        from folderscribe.infrastructure.extraction_config import ExtractionConfig

        p = tmp_path / "sha.db"
        repo = SqliteScanSessionRepository(p)

        root = tmp_path / "src"
        root.mkdir()
        f = root / "a.txt"
        f.write_text("same content", encoding="utf-8")

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        config = ExtractionConfig()
        config_version = config.config_version

        entries = repo.get_entries_for_session(session_id)
        entry = entries[0]

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())
        uc = ExtractTextUseCase(
            registry=registry, repository=repo, config=config
        )
        uc.execute(session_id)

        match = repo.find_reusable_extraction(
            absolute_path=entry.absolute_path,
            sha256_hash=None,
            file_size=entry.size,
            file_modified_at=entry.modified_at,
            extractor="plain_text",
            extractor_version="1",
            config_version=config_version,
        )
        assert match is not None
        assert match.status == ExtractionStatus.EXTRACTED
        assert match.content == "same content"

        repo.close()

    def test_stale_after_modification(self, tmp_path: Path) -> None:
        p = tmp_path / "stale.db"
        repo = SqliteScanSessionRepository(p)

        root = tmp_path / "source3"
        root.mkdir()
        f = root / "test.txt"
        f.write_text("original content", encoding="utf-8")

        from folderscribe.application.scan_folder import ScanFolderUseCase

        scan_use_case = ScanFolderUseCase(OsDirectoryScanner(), repo)
        scan_result = scan_use_case.execute(root)
        session_id = scan_result.session.session_id

        registry = TextExtractorRegistry()
        registry.register(PlainTextExtractor())

        extract_use_case = ExtractTextUseCase(
            registry=registry, repository=repo
        )

        extract_use_case.execute(session_id)

        f.write_text("modified content longer", encoding="utf-8")

        extract_result = extract_use_case.execute(session_id)

        stale = [
            e
            for e in extract_result.extractions
            if e.status == ExtractionStatus.STALE
        ]
        assert len(stale) == 1
        repo.close()
