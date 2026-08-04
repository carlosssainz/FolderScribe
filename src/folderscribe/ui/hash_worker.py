import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from folderscribe.application.compute_hashes import ComputeHashesUseCase
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.hasher import StreamingHasher

logger = logging.getLogger(__name__)


class HashWorker(QThread):
    progress_changed = Signal(int, int)
    stage_changed = Signal(str)
    hash_finished = Signal(object)
    hash_failed = Signal(str)

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
        self._repo: SqliteScanSessionRepository | None = None

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        repo: SqliteScanSessionRepository | None = None
        try:
            repo = SqliteScanSessionRepository(self._database_path)
            hasher = StreamingHasher()
            use_case = ComputeHashesUseCase(hasher, repo)

            def cancel_check() -> bool:
                return self._cancel_requested

            def progress_callback(current: int, total: int, stage: str) -> None:
                self.progress_changed.emit(current, total)
                self.stage_changed.emit(stage)

            self.stage_changed.emit("Calculating fingerprints…")
            result = use_case.execute(
                session_id=self._session_id,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            self.hash_finished.emit(result)
        except sqlite3.Error:
            logger.exception("SQLite error during hash computation")
            self.hash_failed.emit("Database error during fingerprint calculation.")
        except Exception:
            logger.exception("Unexpected error during hash computation")
            self.hash_failed.emit("Fingerprint calculation failed.")
        finally:
            if repo is not None:
                try:
                    repo.close()
                except Exception:
                    logger.exception("Error closing repository")
