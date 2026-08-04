from pathlib import Path

from folderscribe.application.ocr_text import OcrTextUseCase
from folderscribe.domain.extraction import ExtractionStatus
from folderscribe.domain.ocr import OcrMode, OcrResult
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.ocr import TesseractOcrEngine

from tests.conftest import FakeOcrEngine


def _ocr_row_paths(db_path: Path, session_id: str) -> list[Path]:
    repo = SqliteScanSessionRepository(db_path)
    try:
        return [
            e.absolute_path
            for e in repo.get_text_extractions_for_session(session_id)
            if e.extractor == "pdf_ocr"
        ]
    finally:
        repo.close()


class TestOcrUseCase:
    def test_engine_unavailable_short_circuits(
        self, scanned_session: tuple[Path, str]
    ) -> None:
        db_path, session_id = scanned_session
        engine = FakeOcrEngine(available=False)
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(
                engine=engine, repository=repo, config=ExtractionConfig()
            ).execute(session_id)
        finally:
            repo.close()

        assert isinstance(result, OcrResult)
        assert result.engine_available is False
        assert result.total_processed == 0
        assert engine.calls == 0
        assert _ocr_row_paths(db_path, session_id) == []

    def test_ocrs_needs_ocr_entries(
        self, scanned_session: tuple[Path, str], fake_ocr_engine: FakeOcrEngine
    ) -> None:
        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(engine=fake_ocr_engine, repository=repo).execute(
                session_id, mode=OcrMode.FAST
            )
        finally:
            repo.close()

        assert result.engine_available
        assert result.ocr_count == 1
        assert result.error_count == 0
        assert result.skipped_count == 0
        assert fake_ocr_engine.calls == 1

        repo = SqliteScanSessionRepository(db_path)
        try:
            rows = [
                e
                for e in repo.get_text_extractions_for_session(session_id)
                if e.extractor == "pdf_ocr"
            ]
            assert len(rows) == 1
            row = rows[0]
            assert row.status == ExtractionStatus.EXTRACTED
            assert row.needs_ocr is False
            assert "FAKE OCR TEXT page 1" in (row.content or "")
            by_path = repo.get_text_extraction_by_path(session_id, row.absolute_path)
            assert by_path is not None
            assert by_path.extractor == "pdf_ocr"
        finally:
            repo.close()

    def test_privacy_filter_skips(
        self, scanned_session: tuple[Path, str], fake_ocr_engine: FakeOcrEngine
    ) -> None:
        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(engine=fake_ocr_engine, repository=repo).execute(
                session_id, privacy_filter=lambda p: False
            )
        finally:
            repo.close()

        assert result.skipped_count == 1
        assert result.ocr_count == 0
        assert fake_ocr_engine.calls == 0
        assert _ocr_row_paths(db_path, session_id) == []

    def test_cancellation(
        self, scanned_session: tuple[Path, str], fake_ocr_engine: FakeOcrEngine
    ) -> None:
        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(engine=fake_ocr_engine, repository=repo).execute(
                session_id, cancel_check=lambda: True
            )
        finally:
            repo.close()

        assert result.cancelled_count == 1
        assert result.ocr_count == 0
        assert fake_ocr_engine.calls == 0
        assert _ocr_row_paths(db_path, session_id) == []

    def test_reuse_on_second_run(
        self, scanned_session: tuple[Path, str], fake_ocr_engine: FakeOcrEngine
    ) -> None:
        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            use_case = OcrTextUseCase(engine=fake_ocr_engine, repository=repo)
            first = use_case.execute(session_id)
            second = use_case.execute(session_id)
        finally:
            repo.close()

        assert first.ocr_count == 1
        assert second.ocr_count == 0
        assert second.reused_count == 1
        assert fake_ocr_engine.calls == 1

    def test_engine_error_reported(self, scanned_session: tuple[Path, str]) -> None:
        db_path, session_id = scanned_session
        engine = FakeOcrEngine(fail_on_call=True)
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(engine=engine, repository=repo).execute(session_id)
        finally:
            repo.close()

        assert result.error_count == 1

        repo = SqliteScanSessionRepository(db_path)
        try:
            rows = [
                e
                for e in repo.get_text_extractions_for_session(session_id)
                if e.extractor == "pdf_ocr"
            ]
            assert len(rows) == 1
            assert rows[0].status == ExtractionStatus.ERROR
            assert rows[0].error_code == "ocr_failed"
        finally:
            repo.close()

    def test_stale_after_modification(
        self, scanned_session: tuple[Path, str], fake_ocr_engine: FakeOcrEngine
    ) -> None:
        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            use_case = OcrTextUseCase(engine=fake_ocr_engine, repository=repo)
            first = use_case.execute(session_id)
            assert first.ocr_count == 1

            scanned = db_path.parent / "scan_root" / "scanned.pdf"
            with open(scanned, "ab") as f:
                f.write(b"extra bytes to change the size")

            second = use_case.execute(session_id)
        finally:
            repo.close()

        assert second.ocr_count == 0
        assert second.stale_count == 1

    def test_real_engine_degradation_when_tesseract_missing(
        self, scanned_session: tuple[Path, str], tmp_path: Path, monkeypatch
    ) -> None:
        import folderscribe.infrastructure.ocr.tesseract_engine as engine_module

        monkeypatch.setattr(engine_module, "pytesseract", None)

        db_path, session_id = scanned_session
        repo = SqliteScanSessionRepository(db_path)
        try:
            result = OcrTextUseCase(
                engine=TesseractOcrEngine(), repository=repo
            ).execute(session_id)
        finally:
            repo.close()

        assert result.engine_available is False
        assert result.total_processed == 0
