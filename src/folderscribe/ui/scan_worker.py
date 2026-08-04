import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from folderscribe.application.scan_folder import ScanFolderUseCase
from folderscribe.domain.models import ExclusionRule, PersistenceError
from folderscribe.infrastructure.database import SqliteScanSessionRepository
from folderscribe.infrastructure.scanner import OsDirectoryScanner

logger = logging.getLogger(__name__)


class ScanWorker(QThread):
    scan_started = Signal()
    scan_finished = Signal(object)
    scan_failed = Signal(str)

    def __init__(
        self,
        root: Path,
        database_path: Path,
        exclusion_rules: tuple[ExclusionRule, ...],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._root = root
        self._database_path = database_path
        self._exclusion_rules = exclusion_rules

    def run(self) -> None:
        self.scan_started.emit()
        repo: SqliteScanSessionRepository | None = None
        try:
            scanner = OsDirectoryScanner()
            repo = SqliteScanSessionRepository(self._database_path)
            use_case = ScanFolderUseCase(scanner, repo)
            result = use_case.execute(self._root, self._exclusion_rules)
        except FileNotFoundError:
            self.scan_failed.emit(f"La ruta no existe: {self._root}")
        except NotADirectoryError:
            self.scan_failed.emit(f"La ruta no es un directorio: {self._root}")
        except PersistenceError:
            logger.exception("Error de persistencia durante el escaneo")
            self.scan_failed.emit("No se pudo completar el escaneo.")
        except sqlite3.Error:
            logger.exception("Error de SQLite durante el escaneo")
            self.scan_failed.emit("FolderScribe no pudo acceder al índice local.")
        except Exception:
            logger.exception("Error inesperado durante el escaneo")
            self.scan_failed.emit("No se pudo completar el escaneo.")
        else:
            self.scan_finished.emit(result)
        finally:
            if repo is not None:
                try:
                    repo.close()
                except Exception:
                    logger.exception("Error al cerrar el repositorio SQLite")
