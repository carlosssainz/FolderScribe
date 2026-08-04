import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from folderscribe.application.ocr_text import OcrTextUseCase
from folderscribe.domain.interfaces import OcrEngine
from folderscribe.domain.ocr import OcrMode
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.ocr import TesseractOcrEngine

logger = logging.getLogger(__name__)


class OcrWorker(QThread):
    progress_changed = Signal(int, int)
    stage_changed = Signal(str)
    ocr_finished = Signal(object)
    ocr_failed = Signal(str)

    def __init__(
        self,
        session_id: str,
        database_path: Path,
        mode: OcrMode = OcrMode.FAST,
        engine: OcrEngine | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_id = session_id
        self._database_path = database_path
        self._mode = mode
        self._engine = engine if engine is not None else TesseractOcrEngine()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        repo: SqliteScanSessionRepository | None = None
        try:
            repo = SqliteScanSessionRepository(self._database_path)

            use_case = OcrTextUseCase(
                engine=self._engine,
                repository=repo,
                config=ExtractionConfig(),
            )

            def cancel_check() -> bool:
                return self._cancel_requested

            def progress_callback(current: int, total: int, stage: str) -> None:
                self.progress_changed.emit(current, total)
                self.stage_changed.emit(stage)

            self.stage_changed.emit("Running OCR…")
            result = use_case.execute(
                session_id=self._session_id,
                mode=self._mode,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            if not result.engine_available:
                self.ocr_failed.emit(
                    "OCR no disponible: instala tesseract-ocr "
                    "(sudo apt install tesseract-ocr tesseract-ocr-spa)."
                )
                return
            self.ocr_finished.emit(result)
        except sqlite3.Error:
            logger.exception("SQLite error during OCR")
            self.ocr_failed.emit("Database error during OCR.")
        except Exception:
            logger.exception("Unexpected error during OCR")
            self.ocr_failed.emit("OCR failed.")
        finally:
            if repo is not None:
                try:
                    repo.close()
                except Exception:
                    logger.exception("Error closing repository")
