from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from folderscribe.domain.models import (
    InventoryResult,
    ScanEntry,
    ScanError,
    ScanSession,
)


class DirectoryScanner(ABC):
    @abstractmethod
    def scan(self, root: Path) -> InventoryResult: ...


class ScanSessionRepository(ABC):
    @abstractmethod
    def create_session(self, session: ScanSession) -> None: ...

    @abstractmethod
    def complete_session(
        self,
        session: ScanSession,
        entries: list[ScanEntry],
        errors: list[ScanError],
    ) -> None: ...

    @abstractmethod
    def mark_session_failed(
        self, session_id: str, finished_at: datetime, message: str
    ) -> None: ...

    @abstractmethod
    def close(self) -> None: ...
