import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from folderscribe.application.extract_text import ExtractTextUseCase
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.extractors.docx_extractor import DocxTextExtractor
from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor
from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor
from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry

logger = logging.getLogger(__name__)


class ExtractWorker(QThread):
    progress_changed = Signal(int, int)
    stage_changed = Signal(str)
    extract_finished = Signal(object)
    extract_failed = Signal(str)

    def __init__(
        self,
        session_id: str,
        database_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_id = session_id
        self._database_path = database_path
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        repo: SqliteScanSessionRepository | None = None
        try:
            repo = SqliteScanSessionRepository(self._database_path)

            registry = TextExtractorRegistry()
            registry.register(PlainTextExtractor())
            registry.register(DocxTextExtractor())
            registry.register(PdfTextExtractor())

            use_case = ExtractTextUseCase(
                registry=registry,
                repository=repo,
                config=ExtractionConfig(),
            )

            def cancel_check() -> bool:
                return self._cancel_requested

            def progress_callback(current: int, total: int, stage: str) -> None:
                self.progress_changed.emit(current, total)
                self.stage_changed.emit(stage)

            self.stage_changed.emit("Extracting text…")
            result = use_case.execute(
                session_id=self._session_id,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            self.extract_finished.emit(result)
        except sqlite3.Error:
            logger.exception("SQLite error during text extraction")
            self.extract_failed.emit("Database error during text extraction.")
        except Exception:
            logger.exception("Unexpected error during text extraction")
            self.extract_failed.emit("Text extraction failed.")
        finally:
            if repo is not None:
                try:
                    repo.close()
                except Exception:
                    logger.exception("Error closing repository")
